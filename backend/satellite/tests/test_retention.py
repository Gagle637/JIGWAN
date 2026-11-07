from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.gis.geos import Polygon
from django.utils import timezone

from satellite.composite import ALGO_VERSION
from satellite.models import RasterProduct, SatelliteScene
from satellite.retention import (
    cleanup_old_excluded_scene_cogs,
    cleanup_old_scene_cogs,
    cleanup_superseded_scene_cogs,
)

_BBOX = (127.24, 36.18, 127.56, 36.50)

pytestmark = pytest.mark.django_db


def _make_scene(
    scene_id, tmp_path, status=SatelliteScene.Status.READY, region_code="30", collected_at=None
):
    cog_path = tmp_path / f"{region_code}_{scene_id}_REFL.tif"
    scl_path = tmp_path / f"{region_code}_{scene_id}_SCL.tif"
    cog_path.write_bytes(b"fake")
    scl_path.write_bytes(b"fake")
    return SatelliteScene.objects.create(
        scene_id=scene_id,
        region_code=region_code,
        sensed_at=timezone.now(),
        mgrs_tile="T52SCF",
        cloud_pct=5.0,
        processing_baseline="N0512",
        band_offsets={},
        boa_quantification_value=10000,
        status=status,
        cog_path=str(cog_path),
        scl_cog_path=str(scl_path),
        collected_at=collected_at or timezone.now(),
    )


def _make_product(
    scene_ids, composited_at, is_published=True, region_code="30", period_end="2026-08-31"
):
    """period_end는 모델 필수 필드라 채우지만, 정리 기준으로는 안 쓴다(버그5 — 반드시
    composited_at을 써야 한다, 아래 몰아서 백필 테스트 참고)."""
    return RasterProduct.objects.create(
        region_code=region_code,
        product_type="ndvi",
        year=2026,
        season="summer",
        period_start="2026-06-01",
        period_end=period_end,
        bbox=Polygon.from_bbox(_BBOX),
        cog_path="/tmp/x.tif",
        algo_version=ALGO_VERSION,
        scene_ids=scene_ids,
        is_published=is_published,
        composited_at=composited_at,
    )


def test_cleanup_deletes_files_and_clears_paths_for_scenes_in_old_composite(tmp_path):
    now = timezone.now()
    scene = _make_scene("OLD1", tmp_path)
    cog_path, scl_path = scene.cog_path, scene.scl_cog_path
    _make_product(["OLD1"], composited_at=now - timedelta(days=100))

    result = cleanup_old_scene_cogs(now=now, dry_run=False)

    scene.refresh_from_db()
    assert scene.cog_path is None
    assert scene.scl_cog_path is None
    assert not Path(cog_path).exists()
    assert not Path(scl_path).exists()
    assert result == {
        "dry_run": False, "scenes": 1, "files": 2, "bytes": 8,
        "paths": [cog_path, scl_path],
    }


def test_cleanup_keeps_scenes_used_in_recent_composite(tmp_path):
    now = timezone.now()
    scene = _make_scene("NEW1", tmp_path)
    _make_product(["NEW1"], composited_at=now - timedelta(days=10))

    result = cleanup_old_scene_cogs(now=now, dry_run=False)

    scene.refresh_from_db()
    assert scene.cog_path is not None
    assert result == {"dry_run": False, "scenes": 0, "files": 0, "bytes": 0, "paths": []}


def test_cleanup_ignores_scenes_not_referenced_by_any_product(tmp_path):
    scene = _make_scene("UNUSED1", tmp_path)

    cleanup_old_scene_cogs(dry_run=False)

    scene.refresh_from_db()
    assert scene.cog_path is not None


def test_cleanup_skips_excluded_scenes_even_if_listed_in_an_old_product(tmp_path):
    now = timezone.now()
    scene = _make_scene("EXC1", tmp_path, status=SatelliteScene.Status.EXCLUDED)
    _make_product(["EXC1"], composited_at=now - timedelta(days=100))

    cleanup_old_scene_cogs(now=now, dry_run=False)

    scene.refresh_from_db()
    assert scene.cog_path is not None


def test_cleanup_ignores_unpublished_products(tmp_path):
    now = timezone.now()
    scene = _make_scene("UNPUB1", tmp_path)
    _make_product(["UNPUB1"], composited_at=now - timedelta(days=100), is_published=False)

    cleanup_old_scene_cogs(now=now, dry_run=False)

    scene.refresh_from_db()
    assert scene.cog_path is not None


def test_cleanup_does_not_delete_another_regions_recent_scene_sharing_the_same_scene_id(tmp_path):
    """같은 scene_id를 두 지역이 각자 투영해 따로 저장할 수 있다(다지역 지원 6단계) —
    대전(30)의 오래된 합성이 이 scene_id를 "지워도 되는 것"으로 봐도, 세종(36)이 최근
    합성에서 같은 scene_id를 쓰고 있으면 세종 쪽 장면 COG는 지우면 안 된다."""
    now = timezone.now()
    daejeon_scene = _make_scene("SHARED1", tmp_path, region_code="30")
    sejong_scene = _make_scene("SHARED1", tmp_path, region_code="36")
    _make_product(["SHARED1"], composited_at=now - timedelta(days=100), region_code="30")
    _make_product(["SHARED1"], composited_at=now - timedelta(days=10), region_code="36")

    result = cleanup_old_scene_cogs(now=now, dry_run=False)

    daejeon_scene.refresh_from_db()
    sejong_scene.refresh_from_db()
    assert daejeon_scene.cog_path is None  # 대전 쪽은 오래됐으니 지워져야 한다
    assert sejong_scene.cog_path is not None  # 세종 쪽은 최근이니 그대로 남아야 한다
    assert result["scenes"] == 1


# ---- 버그5: period_end가 아니라 composited_at을 써야 한다(몰아서 백필하는 상황) ----


def test_cleanup_keeps_scene_when_composited_recently_even_if_season_is_years_old(tmp_path):
    """실제로 벌어진 사고를 재현한다: 2023년 여름 "계절"을 지금(2026년) 막 백필해서
    period_end는 3년 전이지만 composited_at은 방금이다 — period_end를 기준으로 쓰면
    바로 지워버리는데, composited_at 기준이면 지키면 안 된다."""
    now = timezone.now()
    scene = _make_scene("BACKFILL_OLD_SEASON", tmp_path)
    _make_product(
        ["BACKFILL_OLD_SEASON"],
        composited_at=now - timedelta(days=1),  # 합성은 어제 끝남(방금 백필)
        period_end="2023-08-31",  # 계절 자체는 3년 전
    )

    result = cleanup_old_scene_cogs(now=now, dry_run=False)

    scene.refresh_from_db()
    assert scene.cog_path is not None
    assert result["scenes"] == 0


def test_cleanup_uses_most_recent_composited_at_when_scene_used_in_multiple_products(tmp_path):
    """한 장면이 여러 계절/합성에 걸쳐 쓰였으면, 그중 가장 최근 composited_at으로
    90일을 잰다 — 오래된 합성 하나만 보고 지우면 최근 합성이 아직 쓰고 있는 장면을
    지워버린다."""
    now = timezone.now()
    scene = _make_scene("MULTI1", tmp_path)
    _make_product(["MULTI1"], composited_at=now - timedelta(days=200), region_code="30")
    _make_product(["MULTI1"], composited_at=now - timedelta(days=5), region_code="30")

    result = cleanup_old_scene_cogs(now=now, dry_run=False)

    scene.refresh_from_db()
    assert scene.cog_path is not None
    assert result["scenes"] == 0


# ---- dry_run 동작 ----


def test_cleanup_old_scene_cogs_dry_run_reports_without_deleting(tmp_path):
    now = timezone.now()
    scene = _make_scene("DRYRUN1", tmp_path)
    cog_path = scene.cog_path
    _make_product(["DRYRUN1"], composited_at=now - timedelta(days=100))

    result = cleanup_old_scene_cogs(now=now)  # dry_run 기본값(True)

    assert result["dry_run"] is True
    assert result["scenes"] == 1
    assert result["files"] == 2
    assert result["bytes"] == 8
    assert cog_path in result["paths"]
    scene.refresh_from_db()
    assert scene.cog_path == cog_path  # 아무것도 안 지워짐
    assert Path(cog_path).exists()


# ---- 버그4: excluded 30일(collected_at 기준) + superseded 즉시 정리 ----


def test_cleanup_old_excluded_scene_cogs_deletes_files_past_30_days(tmp_path):
    scene = _make_scene(
        "OLDEXC1",
        tmp_path,
        status=SatelliteScene.Status.EXCLUDED,
        collected_at=timezone.now() - timedelta(days=31),
    )
    cog_path, scl_path = scene.cog_path, scene.scl_cog_path

    result = cleanup_old_excluded_scene_cogs(dry_run=False)

    scene.refresh_from_db()
    assert scene.cog_path is None
    assert scene.scl_cog_path is None
    assert scene.status == SatelliteScene.Status.EXCLUDED  # 행은 유지
    assert not Path(cog_path).exists()
    assert not Path(scl_path).exists()
    assert result["dry_run"] is False
    assert result["scenes"] == 1
    assert result["files"] == 2


def test_cleanup_old_excluded_scene_cogs_keeps_files_within_30_days(tmp_path):
    scene = _make_scene(
        "NEWEXC1",
        tmp_path,
        status=SatelliteScene.Status.EXCLUDED,
        collected_at=timezone.now() - timedelta(days=10),
    )

    result = cleanup_old_excluded_scene_cogs(dry_run=False)

    scene.refresh_from_db()
    assert scene.cog_path is not None
    assert result["scenes"] == 0


def test_cleanup_old_excluded_scene_cogs_uses_collected_at_not_sensed_at(tmp_path):
    """sensed_at(촬영일)은 몇 년 전이어도, collected_at(실제 수집 완료 시각)이 최근이면
    지우면 안 된다 — 백필로 오래된 장면을 지금 받은 경우가 그렇다."""
    scene = _make_scene(
        "BACKFILLED1",
        tmp_path,
        status=SatelliteScene.Status.EXCLUDED,
        collected_at=timezone.now() - timedelta(days=1),
    )
    scene.sensed_at = timezone.now() - timedelta(days=1000)
    scene.save(update_fields=["sensed_at"])

    cleanup_old_excluded_scene_cogs(dry_run=False)

    scene.refresh_from_db()
    assert scene.cog_path is not None


def test_cleanup_ignores_ready_scenes_even_if_old(tmp_path):
    """excluded 정리는 status=excluded만 본다 — ready는 cleanup_old_scene_cogs(90일,
    합성에 쓰였는지 기준)가 따로 담당한다."""
    scene = _make_scene(
        "READYOLD1",
        tmp_path,
        status=SatelliteScene.Status.READY,
        collected_at=timezone.now() - timedelta(days=100),
    )

    cleanup_old_excluded_scene_cogs(dry_run=False)

    scene.refresh_from_db()
    assert scene.cog_path is not None


def test_cleanup_old_excluded_scene_cogs_dry_run_reports_without_deleting(tmp_path):
    scene = _make_scene(
        "DRYEXC1",
        tmp_path,
        status=SatelliteScene.Status.EXCLUDED,
        collected_at=timezone.now() - timedelta(days=31),
    )

    result = cleanup_old_excluded_scene_cogs()  # dry_run 기본값(True)

    assert result["dry_run"] is True
    assert result["scenes"] == 1
    scene.refresh_from_db()
    assert scene.cog_path is not None
    assert Path(scene.cog_path).exists()


def test_cleanup_superseded_scene_cogs_deletes_files_regardless_of_age(tmp_path):
    scene = _make_scene(
        "SUP1",
        tmp_path,
        status=SatelliteScene.Status.SUPERSEDED,
        collected_at=timezone.now(),  # 방금 대체됐어도 바로 정리 대상
    )
    cog_path, scl_path = scene.cog_path, scene.scl_cog_path

    result = cleanup_superseded_scene_cogs(dry_run=False)

    scene.refresh_from_db()
    assert scene.cog_path is None
    assert scene.scl_cog_path is None
    assert scene.status == SatelliteScene.Status.SUPERSEDED  # 행은 유지
    assert not Path(cog_path).exists()
    assert not Path(scl_path).exists()
    assert result["dry_run"] is False
    assert result["scenes"] == 1
    assert result["files"] == 2


def test_cleanup_superseded_scene_cogs_dry_run_reports_without_deleting(tmp_path):
    scene = _make_scene(
        "DRYSUP1", tmp_path, status=SatelliteScene.Status.SUPERSEDED,
    )

    result = cleanup_superseded_scene_cogs()  # dry_run 기본값(True)

    assert result["dry_run"] is True
    assert result["scenes"] == 1
    scene.refresh_from_db()
    assert scene.cog_path is not None
