"""검색 -> baseline 중복 제거 -> 날짜별 그룹 -> 이미 적재된/대체된 scene_id 판정 -> ingest."""
import logging
from datetime import date

from django.conf import settings
from django.db.models import Q

from core.areas import get_bbox, get_grid

from .ingest import ingest_date_group
from .models import RasterProduct, SatelliteScene
from .stac_search import baseline_number, dedupe_latest_baseline, group_by_date, search_scenes, tile_code

logger = logging.getLogger(__name__)


def _baseline_num(processing_baseline: str) -> int:
    return int(processing_baseline.lstrip("N"))


def _published_seasons_using(scene_ids: list[str], sido_code: str) -> set[str]:
    """scene_ids 중 하나라도 이미 게시된(is_published=True) raster_product.scene_ids에
    들어있으면 "{year}-{season}" 집합을 돌려준다(버그2 — baseline 교체로 superseded된
    장면이 기존 게시물에 쓰였는지 알려주기 위함, 자동 재합성은 안 함)."""
    if not scene_ids:
        return set()
    query = Q()
    for scene_id in scene_ids:
        query |= Q(scene_ids__contains=[scene_id])
    products = RasterProduct.objects.filter(query, region_code=sido_code, is_published=True)
    return {f"{p.year}-{p.season}" for p in products}


def _resolve_date_group(
    group_items: list, sensing_date, sido_code: str
) -> tuple[list, int, set[str]]:
    """한 날짜 그룹(1~2타일)을 검사해 실제로 ingest할 item 목록을 정한다.

    타일별로 DB의 "현재" 행(listed·superseded 제외)과 이번 item을 비교한다:
    - 기존 행이 없음 -> 새 장면, ingest
    - scene_id가 똑같음 -> 이미 처리된 장면(보통 경로, 대부분 여기)
    - baseline이 더 높음 -> ESA가 재처리해 재공개한 경우(②) — 기존 행을 대체
    - baseline이 같거나 낮음 -> 회귀/중복, 건너뜀(로그만)

    하나라도 "대체"가 일어나면, 그 대체된 행과 cog_path를 공유하는 행 전부(2타일 병합,
    결정 사항 11)를 superseded로 바꾸고 날짜 그룹 전체를 다시 ingest 대상에 넣는다 —
    안 그러면 한쪽 타일만 새 COG로 바뀌어 겹치는 영역이 두 번 세어진다(버그1과 같은
    근본 원인). 이미 처리된 걸로 보고 건너뛴 타일도 이 경우엔 다시 받아야 하므로
    exact-match 판정보다 늦게, supersede 여부가 정해진 뒤에 최종 ingest 목록을 만든다."""
    existing_by_tile = {}
    for item in group_items:
        tile = tile_code(item)
        existing_by_tile[tile] = (
            SatelliteScene.objects.filter(
                region_code=sido_code, mgrs_tile=tile, sensed_at__date=sensing_date
            )
            .exclude(status__in=[SatelliteScene.Status.LISTED, SatelliteScene.Status.SUPERSEDED])
            .first()
        )

    new_items, exact_match_items, upgrade_items = [], [], []
    for item in group_items:
        existing = existing_by_tile[tile_code(item)]
        if existing is None:
            new_items.append(item)
        elif existing.scene_id == item.id:
            exact_match_items.append(item)
        elif baseline_number(item) > _baseline_num(existing.processing_baseline):
            upgrade_items.append(item)
        else:
            logger.warning(
                "satellite_collect baseline 회귀/중복 건너뜀 item=%s existing=%s(%s)",
                item.id, existing.scene_id, existing.processing_baseline,
            )

    if not upgrade_items:
        return new_items, len(exact_match_items), set()

    cog_paths = {
        existing.cog_path
        for existing in existing_by_tile.values()
        if existing is not None and existing.cog_path
    }
    group_qs = SatelliteScene.objects.filter(region_code=sido_code, cog_path__in=cog_paths)
    superseded_scene_ids = list(group_qs.values_list("scene_id", flat=True))
    affected_seasons = _published_seasons_using(superseded_scene_ids, sido_code)
    group_qs.update(status=SatelliteScene.Status.SUPERSEDED)
    logger.info(
        "satellite_collect baseline 교체: date=%s superseded=%s (날짜 그룹 전체 재수집)",
        sensing_date, superseded_scene_ids,
    )

    # 방금 superseded로 바뀐 기존 행과 scene_id가 같던 타일(exact_match_items)도 이제
    # 다시 ingest해야 한다 — 날짜 그룹 전체가 새 cog_path로 다시 합쳐져야 하기 때문.
    items_to_ingest = new_items + upgrade_items + exact_match_items
    return items_to_ingest, 0, affected_seasons


def collect_scenes(start: date, end: date, sido_code: str) -> dict:
    """spec 5-1: '직전 실행 이후 등록된 장면만 다운로드·변환' — scene_id가 이미 DB에 있으면
    건너뛴다(단, 더 높은 baseline으로 재공개된 경우는 ②대로 대체·재수집한다). sido_code
    (다지역 지원 2단계)로 검색 bbox·격자를 정한다."""
    bbox = get_bbox(sido_code)
    grid = get_grid(sido_code)
    items = search_scenes(start, end, bbox=bbox, max_cloud=settings.SATELLITE_MAX_CLOUD_PCT)
    items = dedupe_latest_baseline(items)
    date_groups = group_by_date(items)

    tiles_covered: set[str] = set()
    ready_count = 0
    excluded_count = 0
    skipped_existing = 0
    affected_seasons: set[str] = set()

    for sensing_date in sorted(date_groups):
        group_items = date_groups[sensing_date]
        items_to_ingest, skipped, seasons = _resolve_date_group(
            group_items, sensing_date, sido_code
        )
        skipped_existing += skipped
        affected_seasons |= seasons
        if not items_to_ingest:
            continue

        scenes = ingest_date_group(items_to_ingest, grid=grid, sido_code=sido_code)
        for scene in scenes:
            tiles_covered.add(scene.mgrs_tile)
            if scene.status == SatelliteScene.Status.READY:
                ready_count += 1
            elif scene.status == SatelliteScene.Status.EXCLUDED:
                excluded_count += 1

        logger.info(
            "satellite_collect date=%s items=%s 처리 완료",
            sensing_date,
            [item.id for item in items_to_ingest],
        )

    if affected_seasons:
        logger.warning(
            "satellite_collect baseline 교체가 이미 게시된 합성에 영향을 줌(자동 재합성 "
            "안 함, 수동으로 run_season_chain 재실행 필요): seasons=%s",
            sorted(affected_seasons),
        )

    return {
        "ready": ready_count,
        "excluded": excluded_count,
        "skipped_existing": skipped_existing,
        "tiles": sorted(tiles_covered),
        "superseded_affecting_published_seasons": sorted(affected_seasons),
    }
