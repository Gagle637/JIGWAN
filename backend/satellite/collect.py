"""검색 -> baseline 중복 제거 -> 날짜별 그룹 -> 이미 적재된 scene_id 제외 -> ingest."""
import logging
from datetime import date

from .ingest import ingest_date_group
from .models import SatelliteScene
from .stac_search import dedupe_latest_baseline, group_by_date, search_scenes

logger = logging.getLogger(__name__)


def collect_scenes(start: date, end: date) -> dict:
    """spec 5-1: '직전 실행 이후 등록된 장면만 다운로드·변환' — scene_id가 이미 DB에 있으면 건너뛴다."""
    items = search_scenes(start, end)
    items = dedupe_latest_baseline(items)
    date_groups = group_by_date(items)

    # listed(백필 dry run이 미리 적어둔 행, 4장)는 아직 다운로드 전이라 "이미 처리됨"으로
    # 치지 않는다 — 실제로 받아서 ready/excluded로 올려야 한다.
    existing_scene_ids = set(
        SatelliteScene.objects.exclude(status=SatelliteScene.Status.LISTED).values_list(
            "scene_id", flat=True
        )
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

        scenes = ingest_date_group(new_items)
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
