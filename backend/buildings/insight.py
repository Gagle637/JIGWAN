"""insight 응답 조립. building·spec은 2단계, trades는 4단계, green·change는 8단계,
crime은 9단계에서 채웠다."""
import json
from datetime import date, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connection

from core.models import IndexRun
from demo.snapshots import apply_demo_overlay, get_demo_snapshot
from crime.models import CrimeSegment
from crime.radius_stats import compute_crime_stats
from publicdata.matching import determine_house_types_for_building
from satellite.radius_stats import catalog_product_ids, compute_change_stats, compute_green_stats
from satellite.seasons import parse_season

ALLOWED_RADIUS_M = (500, 1000)
TRADES_RADIUS_M = 500  # spec 8-1: trades는 radius_m 쿼리와 무관하게 항상 500m 고정
TRADES_MONTHS = 24
CACHE_TTL_SECONDS = 3600


def _address(building) -> str | None:
    text = f"{building.bjd_name or ''} {building.jibun or ''}".strip()
    return text or None


def _age_years(approval_date) -> int | None:
    if approval_date is None:
        return None
    return (date.today() - approval_date).days // 365


def _months_ago(n: int) -> str:
    cursor = date.today().replace(day=1)
    for _ in range(n):
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return cursor.strftime("%Y-%m")


_TRADES_SQL = """
SELECT deal_ym,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY (price::float / area_m2)) AS median,
       COUNT(*)
FROM trade
WHERE house_type = ANY(%s) AND deal_type = 'sale' AND is_canceled = false
  AND match_failure_reason IS NULL AND pnu IS NOT NULL
  AND area_m2 > 0 AND price IS NOT NULL AND geom IS NOT NULL
  AND ST_DWithin(geom::geography, %s::geography, %s)
  AND deal_ym >= %s
GROUP BY deal_ym
ORDER BY deal_ym
"""


def _build_trades_section(building) -> tuple[dict | None, dict | None]:
    """(trades, missing_entry). spec 8-1: 반경 500m·24개월·같은 주택 유형·매매 ㎡당 중앙값."""
    representative_type, house_types = determine_house_types_for_building(building)

    if not house_types:
        return None, {"field": "trades", "reason": "house_type_unmapped"}
    if representative_type == "detached":
        return None, {"field": "trades", "reason": "detached_house_district_not_implemented"}

    cutoff_ym = _months_ago(TRADES_MONTHS)
    with connection.cursor() as cur:
        cur.execute(
            _TRADES_SQL,
            [house_types, building.geom.centroid.ewkt, TRADES_RADIUS_M, cutoff_ym],
        )
        rows = cur.fetchall()

    monthly = [
        {
            "ym": ym,
            "deal_type": "sale",
            "median_price_per_m2": round(median, 1) if median is not None else None,
            "count": count,
        }
        for ym, median, count in rows
    ]
    total_count = sum(count for _, _, count in rows)
    return {"months": TRADES_MONTHS, "count": total_count, "monthly": monthly}, None


def _build_green_section(building, radius_m: int) -> tuple[dict | None, dict | None]:
    """(green, missing_entry). None이면 카탈로그에 게시된 green_mask가 전혀 없다(spec 3-2·5-3)."""
    stats = compute_green_stats(building, radius_m)
    if stats is None:
        return None, {"field": "green", "reason": "no_satellite_data"}
    stats = dict(stats)
    stats.pop("product_ids", None)
    return stats, None


def _build_change_section(building, radius_m: int) -> tuple[dict | None, dict | None]:
    """(change, missing_entry). None이면 truecolor·change_mask가 전혀 없다(spec 3-2·5-4)."""
    stats = compute_change_stats(building, radius_m)
    if stats is None:
        return None, {"field": "change", "reason": "no_satellite_data"}
    stats = dict(stats)
    stats.pop("product_ids", None)
    return stats, None


def _build_crime_section(building, radius_m: int) -> tuple[dict | None, dict | None]:
    """(crime, missing_entry). None이면 반경과 겹치는 주의구간이 없다 — '안전'이 아니라
    '주의구간 미지정'으로 표현한다(spec 8-5)."""
    stats = compute_crime_stats(building, radius_m)
    if stats is None:
        return None, {"field": "crime", "reason": "no_crime_segment"}
    return stats, None


def _crime_data_period() -> str | None:
    return CrimeSegment.objects.values_list("data_period", flat=True).first()


def _satellite_period_str(green: dict | None) -> str | None:
    if not green or not green.get("series"):
        return None
    latest = green["series"][-1]
    start, end = parse_season(f"{latest['year']}-{latest['season']}")
    return f"{start.isoformat()}/{end.isoformat()}"


def _latest_trade_sync_finished_at():
    run = (
        IndexRun.objects.filter(job="trade_sync", status=IndexRun.Status.SUCCEEDED)
        .exclude(finished_at__isnull=True)
        .order_by("-finished_at")
        .first()
    )
    return run.finished_at if run else None


def _latest_safety_sync_finished_at():
    run = (
        IndexRun.objects.filter(job="safety_sync", status=IndexRun.Status.SUCCEEDED)
        .exclude(finished_at__isnull=True)
        .order_by("-finished_at")
        .first()
    )
    return run.finished_at if run else None


def build_insight_response(building, radius_m: int) -> dict:
    """캐시 가능한 섹션 전부(my 제외, 결정 사항 7-1). 직접 호출하지 말고
    get_insight_cached/build_insight_for_request를 통해 쓴다."""
    missing = []

    if building.use_code is None:
        spec = None
        missing.append({"field": "spec", "reason": "no_registry_data"})
    else:
        spec = {
            "use": building.use_name,
            "land_area_m2": building.land_area_m2,
            "total_floor_area_m2": building.total_floor_area_m2,
            "bcr_pct": building.bcr_pct,
            "far_pct": building.far_pct,
            "approval_date": building.approval_date.isoformat() if building.approval_date else None,
            "age_years": _age_years(building.approval_date),
        }

    trades, trades_missing = _build_trades_section(building)
    if trades_missing:
        missing.append(trades_missing)

    green, green_missing = _build_green_section(building, radius_m)
    if green_missing:
        missing.append(green_missing)

    change, change_missing = _build_change_section(building, radius_m)
    if change_missing:
        missing.append(change_missing)

    crime, crime_missing = _build_crime_section(building, radius_m)
    if crime_missing:
        missing.append(crime_missing)

    # spec 6-2: "pending"은 해당 범위의 위성 결과가 카탈로그에 전혀 없을 때만 쓴다.
    # 위성 결과가 있으면, 빠진 섹션이 하나도 없어야 "ready"고 그 외엔 "partial".
    if green is None and change is None:
        status = "pending"
    elif missing:
        status = "partial"
    else:
        status = "ready"

    trade_synced_at = _latest_trade_sync_finished_at()

    return {
        "status": status,
        "building": {
            "id": building.id,
            "pnu": building.pnu,
            "name": building.name,
            "address": _address(building),
            "use_type": building.use_name,
            "geometry": json.loads(building.geom.geojson),
        },
        "radius_m": radius_m,
        "as_of": {
            "satellite_period": _satellite_period_str(green),
            "trade_synced_at": trade_synced_at.isoformat() if trade_synced_at else None,
            "register_synced_at": None,
            "crime_data_period": _crime_data_period(),
        },
        "green": green,
        "change": change,
        "spec": spec,
        "trades": trades,
        "crime": crime,
        "my": None,
        "missing": missing,
    }


def _cache_key_for(
    building_id: int,
    radius_m: int,
    product_ids: list[int],
    trade_synced_at,
    safety_synced_at,
) -> str:
    ids_part = ",".join(str(pid) for pid in sorted(product_ids))
    trade_part = trade_synced_at.isoformat() if trade_synced_at else "none"
    safety_part = safety_synced_at.isoformat() if safety_synced_at else "none"
    return f"insight:{building_id}:{radius_m}:{ids_part}:{trade_part}:{safety_part}"


def get_insight_cached(building, radius_m: int) -> dict:
    """캐시 가능한 섹션만(my 제외). 가벼운 카탈로그 조회(rasterio 없음)로 키를 먼저 만들고,
    캐시 미스일 때만 무거운 계산(build_insight_response)을 한다(결정 사항 7, 닭-달걀 회피).
    crime_segment는 연 1회(safety_sync)만 통째로 바뀌므로, 그 완료 시각도 키에 넣어
    매년 수집이 끝나면 캐시가 자동으로 무효화되게 한다."""
    product_ids = catalog_product_ids(building, radius_m)
    trade_synced_at = _latest_trade_sync_finished_at()
    safety_synced_at = _latest_safety_sync_finished_at()
    cache_key = _cache_key_for(
        building.id, radius_m, product_ids, trade_synced_at, safety_synced_at
    )

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    response = build_insight_response(building, radius_m)
    cache.set(cache_key, response, timeout=CACHE_TTL_SECONDS)
    return response


def _build_my_section(building, user):
    """로그인 안 했으면 None. 로그인했으면 항상 객체(마크가 없어도 기본값, spec 6-2)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None

    from favorites.models import UserBuilding
    from reports.models import Report

    mark = UserBuilding.objects.filter(user=user, building=building).first()
    report_count = (
        Report.objects.filter(user=user, building=building)
        .exclude(status=Report.Status.FAILED)
        .count()
    )
    return {
        "is_favorite": mark.is_favorite if mark else False,
        "color": mark.color if mark else None,
        "label": mark.label if mark else None,
        "folder_id": mark.folder_id if mark else None,
        "report_count": report_count,
    }


def build_insight_for_request(building, radius_m: int, user) -> dict:
    """get_insight_cached 결과를 복사해 my만 요청 사용자 기준으로 새로 채운다(결정 사항 7-1 —
    my는 절대 캐시되지 않으므로 서로 다른 사용자끼리 섞이지 않는다).

    DEMO_MODE고 이 건물이 데모 스냅샷에 있으면, 실제 배치 결과(Redis·satellite/crime/trade
    데이터) 없이 고정값을 돌려준다(13단계: "서버가 꺼져 있어도 시연할 수 있게")."""
    if settings.DEMO_MODE:
        demo = get_demo_snapshot(building.pnu)
        if demo is not None:
            response = apply_demo_overlay(demo["insight"], building)
            response["my"] = _build_my_section(building, user)
            return response

    cached = get_insight_cached(building, radius_m)
    response = dict(cached)
    response["my"] = _build_my_section(building, user)
    return response
