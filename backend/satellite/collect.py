"""검색 -> baseline 중복 제거 -> 날짜별 그룹 -> 이미 적재된 scene_id 제외 -> ingest."""
import logging
from datetime import date

from core.areas import get_bbox, get_grid

from .ingest import ingest_date_group
from .models import SatelliteScene
from .stac_search import dedupe_latest_baseline, group_by_date, search_scenes

logger = logging.getLogger(__name__)


def collect_scenes(start: date, end: date, sido_code: str = "30") -> dict:
    """spec 5-1: '직전 실행 이후 등록된 장면만 다운로드·변환' — scene_id가 이미 DB에 있으면
    건너뛴다. sido_code(다지역 지원 2단계)로 검색 bbox·격자를 정한다."""
    bbox = get_bbox(sido_code)
    grid = get_grid(sido_code)
    items = search_scenes(start, end, bbox=bbox)
    items = dedupe_latest_baseline(items)
    date_groups = group_by_date(items)

    # listed(백필 dry run이 미리 적어둔 행, 4장)는 아직 다운로드 전이라 "이미 처리됨"으로
    # 치지 않는다 — 실제로 받아서 ready/excluded로 올려야 한다. region_code로 좁히는 이유
    # (다지역 지원 6단계): 다른 지역이 이미 처리한 scene_id를 "이미 처리됨"으로 보고 이
    # 지역에서 건너뛰면 안 된다 — 지역마다 자기 격자로 따로 투영해야 한다.
    existing_scene_ids = set(
        SatelliteScene.objects.filter(region_code=sido_code)
        .exclude(status=SatelliteScene.Status.LISTED)
        .values_list("scene_id", flat=True)
    )

    tiles_covered: set[str] = set()
    ready_count = 0
    excluded_count = 0
    skipped_existing = 0

    for sensing_date in sorted(date_groups):
        group_items = date_groups[sensing_date]
        new_items = [item for item in group_items if item.id not in existing_scene_ids]
        skipped_existing += len(group_items) - len(new_items)
        if not new_items:
            continue

        scenes = ingest_date_group(new_items, grid=grid, sido_code=sido_code)
        for scene in scenes:
            tiles_covered.add(scene.mgrs_tile)
            if scene.status == SatelliteScene.Status.READY:
                ready_count += 1
            elif scene.status == SatelliteScene.Status.EXCLUDED:
                excluded_count += 1

        logger.info(
            "satellite_collect date=%s items=%s 처리 완료",
            sensing_date,
            [item.id for item in new_items],
        )

    return {
        "ready": ready_count,
        "excluded": excluded_count,
        "skipped_existing": skipped_existing,
        "tiles": sorted(tiles_covered),
    }
