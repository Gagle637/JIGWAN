"""장면별 COG 보관 기한 정리(spec 5-4: "장면별 COG | 해당 계절 합성 후 90일")."""
import logging
from datetime import timedelta
from pathlib import Path

from django.db.models import Q
from django.utils import timezone

from .models import RasterProduct, SatelliteScene

logger = logging.getLogger(__name__)

SCENE_COG_RETENTION_DAYS = 90


def _used_scene_ids_before(cutoff_date) -> set[tuple[str, str]]:
    """cutoff_date 이전에 끝난 계절의, 게시된 합성에 쓰인 (scene_id, region_code) 쌍 전체.

    "합성 후 90일"의 기준 시각으로 쓸 합성 완료 시각이 raster_product에 없어(created_at
    같은 컬럼이 없음), period_end(계절 끝)를 대신 쓴다 — 합성은 항상 period_end 이후에
    일어나므로 실제보다 보수적으로(조금 더 늦게) 지우는 쪽으로만 어긋난다.

    region_code를 같이 묶는 이유(다지역 지원 6단계): 같은 scene_id를 두 지역이 각자 다시
    투영해 따로 저장할 수 있어, scene_id만으로는 한 지역의 오래된 합성 때문에 다른 지역의
    최근 장면 COG까지 지워버릴 수 있다.
    """
    rows = RasterProduct.objects.filter(
        is_published=True, period_end__lt=cutoff_date
    ).values_list("scene_ids", "region_code")
    used: set[tuple[str, str]] = set()
    for ids, region_code in rows:
        used.update((scene_id, region_code) for scene_id in (ids or []))
    return used


def cleanup_old_scene_cogs(today=None) -> dict:
    """status=ready(=합성에 실제로 쓰인) 장면 중, 쓰인 계절이 90일보다 오래된 것의 COG
    파일을 지우고 cog_path/scl_cog_path를 비운다. satellite_scene 행 자체(메타데이터)는
    남긴다 — 영구 보관 대상은 raster_product·change_area 같은 결과물이고, 장면 COG는
    원본에 가까운 중간 산물이라 파일만 지운다(spec 5-4)."""
    today = today or timezone.now().date()
    cutoff_date = today - timedelta(days=SCENE_COG_RETENTION_DAYS)
    used_pairs = _used_scene_ids_before(cutoff_date)

    if not used_pairs:
        scenes = SatelliteScene.objects.none()
    else:
        pair_query = Q()
        for scene_id, region_code in used_pairs:
            pair_query |= Q(scene_id=scene_id, region_code=region_code)
        scenes = SatelliteScene.objects.filter(
            pair_query, status=SatelliteScene.Status.READY
        ).exclude(cog_path__isnull=True)

    deleted_files = 0
    cleared_scenes = 0
    for scene in scenes:
        for path_str in (scene.cog_path, scene.scl_cog_path):
            if not path_str:
                continue
            try:
                Path(path_str).unlink(missing_ok=True)
                deleted_files += 1
            except OSError as exc:
                logger.warning("scene COG 삭제 실패 path=%s err=%s", path_str, exc)
        scene.cog_path = None
        scene.scl_cog_path = None
        scene.save(update_fields=["cog_path", "scl_cog_path"])
        cleared_scenes += 1

    logger.info(
        "cleanup_old_scene_cogs: scenes=%s files=%s cutoff=%s",
        cleared_scenes,
        deleted_files,
        cutoff_date,
    )
    return {"scenes_cleared": cleared_scenes, "files_deleted": deleted_files}
