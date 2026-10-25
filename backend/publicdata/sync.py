"""실거래 수집 오케스트레이션: 월별 수집 -> 매칭 -> 교체 저장 -> 유형별 매칭률 로깅."""
import asyncio
import logging
from collections import defaultdict
from datetime import date, timedelta

import httpx
from django.conf import settings
from django.db import connection, transaction

from core.areas import get_sgg_codes

from . import molit_client
from .matching import build_apt_seq_cache, match_trade
from .models import Trade
from .trade_fields import SERVICES

logger = logging.getLogger(__name__)

CONCURRENCY_LIMIT = 5  # API 초당 최대 30건 한도 보호(spec 8-7)
APT_TRADE_SERVICE = "RTMSDataSvcAptTradeDev"


async def collect_month(sgg_codes: list[str], deal_ymd: str, service_key: str) -> list[dict]:
    """아파트 매매를 먼저 전부 끝내고, 나머지 7종은 세마포어로 동시 호출을 제한해 수집한다."""
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    normalized_rows: list[dict] = []

    async with httpx.AsyncClient() as client:
        apt_trade_normalizer = SERVICES[APT_TRADE_SERVICE]
        apt_trade_raw_lists = await asyncio.gather(
            *[
                molit_client.fetch_all(
                    client, semaphore, APT_TRADE_SERVICE, service_key, sgg, deal_ymd
                )
                for sgg in sgg_codes
            ]
        )
        for raws in apt_trade_raw_lists:
            normalized_rows.extend(apt_trade_normalizer(raw) for raw in raws)

        remaining = [(s, n) for s, n in SERVICES.items() if s != APT_TRADE_SERVICE]
        tasks = []
        normalizers = []
        for service, normalizer in remaining:
            for sgg in sgg_codes:
                tasks.append(
                    molit_client.fetch_all(client, semaphore, service, service_key, sgg, deal_ymd)
                )
                normalizers.append(normalizer)
        results = await asyncio.gather(*tasks)
        for raws, normalizer in zip(results, normalizers):
            normalized_rows.extend(normalizer(raw) for raw in raws)

    return normalized_rows


def _centroid_for_pnu(pnu: str) -> tuple[float, float] | None:
    """매칭된 필지 건물들의 대표점(spec 8-1: '거래 위치는 매칭된 필지 건물들의 대표점')."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT ST_X(c), ST_Y(c) FROM ("
            "  SELECT ST_Centroid(ST_Collect(geom)) AS c FROM building "
            "  WHERE pnu = %s AND is_active"
            ") t WHERE c IS NOT NULL",
            [pnu],
        )
        row = cur.fetchone()
    return (row[0], row[1]) if row and row[0] is not None else None


def persist_batch(normalized_rows: list[dict]) -> dict:
    """(house_type, deal_type, sgg_code, deal_ym) 단위로 지우고 다시 넣는다(멱등, CLAUDE.md 배치 규칙).

    반환: {house_type: {"total", "matched", "match_rate_pct", "failed"}}(단독다가구는 매칭 대상이
    아니므로 "matched"/"match_rate_pct"가 None).
    """
    apt_seq_cache = build_apt_seq_cache()
    centroid_cache: dict[str, tuple[float, float] | None] = {}
    stats = defaultdict(lambda: {"total": 0, "matched": 0, "failed": defaultdict(int)})

    groups = defaultdict(list)
    for row in normalized_rows:
        if row.get("deal_ym") is None:
            continue  # 계약연월을 못 읽은 행은 데이터 이상이라 저장하지 않음
        key = (row["house_type"], row["deal_type"], row["sgg_code"], row["deal_ym"])
        groups[key].append(row)

    with transaction.atomic():
        for (house_type, deal_type, sgg_code, deal_ym), rows in groups.items():
            Trade.objects.filter(
                house_type=house_type, deal_type=deal_type, sgg_code=sgg_code, deal_ym=deal_ym
            ).delete()

            to_create = []
            for row in rows:
                pnu, failure_reason = match_trade(row, apt_seq_cache)
                stats[house_type]["total"] += 1
                if pnu:
                    stats[house_type]["matched"] += 1
                    if (
                        house_type == Trade.HouseType.APARTMENT
                        and deal_type == Trade.DealType.SALE
                        and row.get("apt_seq")
                    ):
                        apt_seq_cache[row["apt_seq"]] = pnu
                elif failure_reason:
                    stats[house_type]["failed"][failure_reason] += 1

                geom_point = None
                if pnu:
                    if pnu not in centroid_cache:
                        centroid_cache[pnu] = _centroid_for_pnu(pnu)
                    coords = centroid_cache[pnu]
                    if coords:
                        geom_point = f"SRID=4326;POINT({coords[0]} {coords[1]})"

                to_create.append(
                    Trade(
                        sgg_code=row["sgg_code"],
                        pnu=pnu,
                        house_type=house_type,
                        deal_type=deal_type,
                        deal_ym=deal_ym,
                        deal_day=row.get("deal_day"),
                        area_m2=row.get("area_m2"),
                        price=row.get("price"),
                        deposit=row.get("deposit"),
                        monthly_rent=row.get("monthly_rent"),
                        apt_seq=row.get("apt_seq"),
                        building_name=row.get("building_name"),
                        floor=row.get("floor"),
                        build_year=row.get("build_year"),
                        is_canceled=row.get("is_canceled", False),
                        canceled_at=row.get("canceled_at"),
                        match_failure_reason=failure_reason,
                        raw_bjd_name=row.get("bjd_name"),
                        raw_jibun=row.get("jibun_raw"),
                        geom=geom_point,
                    )
                )
            Trade.objects.bulk_create(to_create)

    summary = {}
    for house_type, s in stats.items():
        if house_type == Trade.HouseType.DETACHED:
            summary[house_type] = {
                "total": s["total"],
                "matched": None,
                "match_rate_pct": None,
                "failed": {},
                "note": "법정동 단위 집계 대상, PNU 매칭 안 함(spec 8-1)",
            }
        else:
            summary[house_type] = {
                "total": s["total"],
                "matched": s["matched"],
                "match_rate_pct": round(s["matched"] / s["total"] * 100, 1) if s["total"] else None,
                "failed": dict(s["failed"]),
            }
    return summary


def sync_trades_for_months(months: list[str], sido_code: str) -> dict:
    """months: ['202610','202609'] 같은 YYYYMM 리스트. 월별로 수집·저장하고 매칭률을 로그로 남긴다.
    sido_code(다지역 지원 3단계)로 수집 대상 시군구 코드를 정한다."""
    service_key = settings.DATA_GO_KR_API_KEY
    if not service_key:
        raise ValueError("DATA_GO_KR_API_KEY가 설정되지 않았습니다.")

    sgg_codes = get_sgg_codes(sido_code)
    overall = {}
    for deal_ymd in months:
        normalized_rows = asyncio.run(collect_month(sgg_codes, deal_ymd, service_key))
        month_stats = persist_batch(normalized_rows)
        for house_type, stat in month_stats.items():
            logger.info(
                "trade_sync deal_ymd=%s house_type=%s total=%s matched=%s rate=%s%% failed=%s",
                deal_ymd,
                house_type,
                stat["total"],
                stat.get("matched"),
                stat.get("match_rate_pct"),
                stat.get("failed"),
            )
        overall[deal_ymd] = month_stats
    return overall


def current_and_previous_month() -> list[str]:
    today = date.today()
    this_month = today.strftime("%Y%m")
    previous_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y%m")
    return [this_month, previous_month]


def months_back(n: int) -> list[str]:
    """이번 달부터 n개월 전까지 YYYYMM 리스트(오래된 달이 마지막)."""
    cursor = date.today().replace(day=1)
    result = []
    for _ in range(n):
        result.append(cursor.strftime("%Y%m"))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return result
