"""장면별 COG 보관 기한 정리(spec 5-4: "장면별 COG | 해당 계절 합성 후 90일").

세 함수(ready 90일·excluded 30일·superseded 즉시) 전부 기본이 dry_run=True다 — 실제로
파일을 지우려면 dry_run=False를 명시해야 한다(실측 사고로 확인된 교훈: 스모크 테스트로
무심코 호출해도 안전해야 한다. CLAUDE.md 참고)."""
import logging
from datetime import timedelta
from pathlib import Path

from django.db.models import Q
from django.utils import timezone

from .models import RasterProduct, SatelliteScene

logger = logging.getLogger(__name__)

SCENE_COG_RETENTION_DAYS = 90
EXCLUDED_COG_RETENTION_DAYS = 30


def _most_recent_composited_at_by_scene() -> dict[tuple[str, str], object]:
    """(scene_id, region_code) -> 그 장면을 쓴 게시된 raster_product 중 가장 최근
    composited_at(합성이 실제로 끝난 시각). "합성 후 90일"은 반드시 이 값 기준이어야
    한다 — period_end(계절 달력상 끝)를 쓰면 몰아서 백필할 때(계절은 2023년인데 합성은
    오늘 막 끝남) 방금 받은 장면을 바로 지워버린다(실측 사고로 확인됨, composited_at
    도입 계기)."""
    rows = RasterProduct.objects.filter(
        is_published=True, composited_at__isnull=False
    ).values_list("scene_ids", "region_code", "composited_at")
    most_recent: dict[tuple[str, str], object] = {}
    for scene_ids, region_code, composited_at in rows:
        for scene_id in scene_ids or []:
            key = (scene_id, region_code)
            current = most_recent.get(key)
            if current is None or composited_at > current:
                most_recent[key] = composited_at
    return most_recent


def _collect_or_delete_scene_cog_files(scenes, dry_run: bool) -> dict:
    """공통 삭제/dry-run 로직. dry_run=True면 아무것도 건드리지 않고 지워질 파일 목록·
    개수·용량만 센다. dry_run=False면 실제로 지우고 cog_path/scl_cog_path를 비운다
    (satellite_scene 행 자체는 항상 유지 — 영구 보관 대상은 raster_product 쪽이다)."""
    paths: list[str] = []
    total_bytes = 0
    cleared_scenes = 0
    for scene in scenes:
        scene_paths = [p for p in (scene.cog_path, scene.scl_cog_path) if p]
        if not scene_paths:
            continue
        for path_str in scene_paths:
            try:
                total_bytes += Path(path_str).stat().st_size
            except OSError:
                pass
            paths.append(path_str)
        cleared_scenes += 1
        if dry_run:
            continue
        for path_str in scene_paths:
            try:
                Path(path_str).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("scene COG 삭제 실패 path=%s err=%s", path_str, exc)
        scene.cog_path = None
        scene.scl_cog_path = None
        scene.save(update_fields=["cog_path", "scl_cog_path"])

    return {
        "dry_run": dry_run,
        "scenes": cleared_scenes,
        "files": len(paths),
        "bytes": total_bytes,
        "paths": paths,
    }


def cleanup_old_scene_cogs(now=None, dry_run: bool = True) -> dict:
    """status=ready(=합성에 실제로 쓰인) 장면 중, 쓰인 합성 전부가 90일보다 오래된 것의
    COG 파일을 지우고 cog_path/scl_cog_path를 비운다(행은 유지, spec 5-4). 한 장면이
    여러 합성(여러 계절)에 걸쳐 쓰였으면 그중 가장 최근 composited_at으로 90일을 잰다."""
    now = now or timezone.now()
    cutoff = now - timedelta(days=SCENE_COG_RETENTION_DAYS)
    most_recent = _most_recent_composited_at_by_scene()
    eligible_pairs = {pair for pair, ts in most_recent.items() if ts < cutoff}

    if not eligible_pairs:
        scenes = SatelliteScene.objects.none()
    else:
        pair_query = Q()
        for scene_id, region_code in eligible_pairs:
            pair_query |= Q(scene_id=scene_id, region_code=region_code)
        scenes = SatelliteScene.objects.filter(
            pair_query, status=SatelliteScene.Status.READY
        ).exclude(cog_path__isnull=True)

    result = _collect_or_delete_scene_cog_files(scenes, dry_run)
    logger.info("cleanup_old_scene_cogs: dry_run=%s scenes=%s files=%s bytes=%s cutoff=%s",
                dry_run, result["scenes"], result["files"], result["bytes"], cutoff)
    return result


def cleanup_old_excluded_scene_cogs(now=None, dry_run: bool = True) -> dict:
    """status=excluded 장면은 collected_at(수집 완료 시각 — sensed_at이 아니다, 백필로
    몇 년 전 장면을 지금 받을 수 있어서) 기준 30일 지나면 COG 파일만 지운다(행은 유지).
    ready와 달리 "합성에 쓰였는지"는 상관없다 — 애초에 품질 미달로 안 쓰인 장면이다."""
    now = now or timezone.now()
    cutoff = now - timedelta(days=EXCLUDED_COG_RETENTION_DAYS)
    scenes = SatelliteScene.objects.filter(
        status=SatelliteScene.Status.EXCLUDED, collected_at__lt=cutoff
    ).exclude(cog_path__isnull=True)

    result = _collect_or_delete_scene_cog_files(scenes, dry_run)
    logger.info("cleanup_old_excluded_scene_cogs: dry_run=%s scenes=%s files=%s bytes=%s cutoff=%s",
                dry_run, result["scenes"], result["files"], result["bytes"], cutoff)
    return result


def cleanup_superseded_scene_cogs(dry_run: bool = True) -> dict:
    """status=superseded 장면(baseline 교체로 대체된 행)은 기간 조건 없이 다음 정리 때
    바로 COG 파일만 지운다(행은 유지) — 대체된 즉시 더는 어떤 합성에도 쓰이지 않으므로
    90일·30일처럼 기다릴 이유가 없다."""
    scenes = SatelliteScene.objects.filter(
        status=SatelliteScene.Status.SUPERSEDED
    ).exclude(cog_path__isnull=True)

    result = _collect_or_delete_scene_cog_files(scenes, dry_run)
    logger.info("cleanup_superseded_scene_cogs: dry_run=%s scenes=%s files=%s bytes=%s",
                dry_run, result["scenes"], result["files"], result["bytes"])
    return result
