"""초기 적재(백필) 오케스트레이션(spec 4장). manage.py backfill이 이 모듈을 쓴다."""
import logging
from datetime import date

from core.areas import get_bbox

from .collect import collect_scenes
from .composite import ALGO_VERSION
from .models import RasterProduct, SatelliteScene
from .season_chain import run_season_chain_sync
from .seasons import parse_season
from .stac_search import (
    dedupe_latest_baseline,
    processing_baseline,
    search_scenes,
    sensed_at,
    tile_code,
)

logger = logging.getLogger(__name__)

SEASON_ORDER = ["spring", "summer", "fall", "winter"]
TOTAL_SEASONS = 13  # spec 4장: 최신 계절 + 그 이전 3년치(계절 슬롯 기준, 같은 계절 반복 아님)

# CDSE에 직접 접근해 실제 자산 크기를 확인할 수 없어 둔 보수적 추정치(장면당 B02·B03·B04·
# B08·B11 10m 밴드 + SCL 20m 압축 JP2 용량 어림). dry run 용량 "추정"에만 쓰이고 실제
# 다운로드 여부 판단에는 영향을 주지 않는다 — 완료 보고에서 가정으로 다시 밝힌다.
ESTIMATED_MB_PER_SCENE = 150


def _previous_season(year: int, season: str) -> tuple[int, str]:
    idx = SEASON_ORDER.index(season)
    if idx == 0:
        return year - 1, "winter"
    return year, SEASON_ORDER[idx - 1]


def _season_containing(today: date) -> tuple[int, str]:
    month = today.month
    if month in (3, 4, 5):
        return today.year, "spring"
    if month in (6, 7, 8):
        return today.year, "summer"
    if month in (9, 10, 11):
        return today.year, "fall"
    if month == 12:
        return today.year, "winter"
    return today.year - 1, "winter"  # 1·2월은 작년 12월에 시작한 겨울에 속함(spec 3-3)


def target_seasons(today: date | None = None, count: int = TOTAL_SEASONS) -> list[tuple[int, str]]:
    """오늘 기준으로 '완전히 끝난' 최신 계절부터 거슬러 count개(기본 13개)를, 오래된 것부터
    돌려준다(spec 4장: "2026년 10월 기준이면 2023년 여름부터 2026년 여름까지")."""
    today = today or date.today()
    year, season = _previous_season(*_season_containing(today))
    seasons = []
    for _ in range(count):
        seasons.append((year, season))
        year, season = _previous_season(year, season)
    return list(reversed(seasons))


def dry_run_list_scenes(seasons: list[tuple[int, str]], sido_code: str = "30") -> dict:
    """spec 4장 2단계: 대상 계절 전체를 STAC로 검색해 status=listed로 기록하고, 신규 장면
    수·예상 다운로드 용량을 집계한다(CDSE 한도 안에서 일정을 잡는 용도)."""
    bbox = get_bbox(sido_code)
    existing_ids = set(SatelliteScene.objects.values_list("scene_id", flat=True))
    new_count = 0
    per_season = []

    for year, season in seasons:
        start, end = parse_season(f"{year}-{season}")
        items = dedupe_latest_baseline(search_scenes(start, end, bbox=bbox))
        season_new = 0
        for item in items:
            if item.id in existing_ids:
                continue
            SatelliteScene.objects.update_or_create(
                scene_id=item.id,
                defaults={
                    "sensed_at": sensed_at(item),
                    "mgrs_tile": tile_code(item),
                    "cloud_pct": item.properties.get("eo:cloud_cover", 0.0),
                    "processing_baseline": processing_baseline(item),
                    "status": SatelliteScene.Status.LISTED,
                },
            )
            existing_ids.add(item.id)
            season_new += 1
        new_count += season_new
        per_season.append(
            {"season": f"{year}-{season}", "scenes": len(items), "new": season_new}
        )
        logger.info(
            "backfill dry-run %s-%s: %s개 장면(신규 %s)", year, season, len(items), season_new
        )

    return {
        "seasons": per_season,
        "total_new_scenes": new_count,
        "estimated_download_mb": new_count * ESTIMATED_MB_PER_SCENE,
    }


_REQUIRED_PRODUCT_TYPES = {"ndvi", "ndbi", "green_mask", "truecolor"}


def _season_already_published(year: int, season: str) -> bool:
    published_types = set(
        RasterProduct.objects.filter(
            year=year, season=season, algo_version=ALGO_VERSION, is_published=True
        ).values_list("product_type", flat=True)
    )
    return _REQUIRED_PRODUCT_TYPES <= published_types


def run_backfill(seasons: list[tuple[int, str]], sido_code: str = "30") -> list[dict]:
    """spec 4장 3·4·5단계: 오래된 계절부터 수집 → 합성 → 변화·기준선 → 게시 순으로 한
    계절을 끝내고 다음 계절로 넘어간다 — 한 계절을 끝내기 전에 다음 계절을 내려받지 않으므로
    디스크 최대 사용량이 한 계절분으로 제한된다.

    계절 단위 중단·재개: 이미 4종(ndvi·ndbi·green_mask·truecolor)이 다 게시된 계절은
    다시 받지 않고 건너뛴다 — 중간에 끊긴 뒤 다시 실행하면 안 끝난 계절부터 이어진다."""
    results = []
    for year, season in seasons:
        if _season_already_published(year, season):
            logger.info("backfill %s-%s 이미 게시됨, 건너뜀", year, season)
            results.append({"season": f"{year}-{season}", "skipped": True})
            continue

        start, end = parse_season(f"{year}-{season}")
        logger.info("backfill %s-%s 수집 시작", year, season)
        collect_summary = collect_scenes(start, end, sido_code=sido_code)
        logger.info("backfill %s-%s 수집 완료, 합성 체인 시작: %s", year, season, collect_summary)
        chain_result = run_season_chain_sync(year, season, sido_code)
        results.append(
            {"season": f"{year}-{season}", "collect": collect_summary, "chain": chain_result}
        )
    return results
