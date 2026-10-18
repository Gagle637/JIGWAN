from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.gis.geos import Polygon
from django.utils import timezone

from satellite.composite import ALGO_VERSION
from satellite.models import RasterProduct, SatelliteScene
from satellite.retention import cleanup_old_scene_cogs
from satellite.stac_search import DAEJEON_BBOX

pytestmark = pytest.mark.django_db


def _make_scene(scene_id, tmp_path, status=SatelliteScene.Status.READY):
    cog_path = tmp_path / f"{scene_id}_REFL.tif"
    scl_path = tmp_path / f"{scene_id}_SCL.tif"
    cog_path.write_bytes(b"fake")
    scl_path.write_bytes(b"fake")
    return SatelliteScene.objects.create(
        scene_id=scene_id,
        sensed_at=timezone.now(),
        mgrs_tile="T52SCF",
        cloud_pct=5.0,
        processing_baseline="N0512",
        band_offsets={},
        boa_quantification_value=10000,
        status=status,
        cog_path=str(cog_path),
        scl_cog_path=str(scl_path),
    )


def _make_product(scene_ids, period_end, is_published=True):
    return RasterProduct.objects.create(
        product_type="ndvi",
        year=2026,
        season="summer",
        period_start="2026-06-01",
        period_end=period_end,
        bbox=Polygon.from_bbox(DAEJEON_BBOX),
        cog_path="/tmp/x.tif",
        algo_version=ALGO_VERSION,
        scene_ids=scene_ids,
        is_published=is_published,
    )


def test_cleanup_deletes_files_and_clears_paths_for_scenes_in_old_published_composite(tmp_path):
    today = timezone.now().date()
    scene = _make_scene("OLD1", tmp_path)
    cog_path, scl_path = scene.cog_path, scene.scl_cog_path
    _make_product(["OLD1"], period_end=today - timedelta(days=100))

    result = cleanup_old_scene_cogs(today=today)

    scene.refresh_from_db()
    assert scene.cog_path is None
    assert scene.scl_cog_path is None
    assert not Path(cog_path).exists()
    assert not Path(scl_path).exists()
    assert result == {"scenes_cleared": 1, "files_deleted": 2}


def test_cleanup_keeps_scenes_used_in_recent_composite(tmp_path):
    today = timezone.now().date()
    scene = _make_scene("NEW1", tmp_path)
    _make_product(["NEW1"], period_end=today - timedelta(days=10))

    result = cleanup_old_scene_cogs(today=today)

    scene.refresh_from_db()
    assert scene.cog_path is not None
    assert result == {"scenes_cleared": 0, "files_deleted": 0}


def test_cleanup_ignores_scenes_not_referenced_by_any_product(tmp_path):
    today = timezone.now().date()
    scene = _make_scene("UNUSED1", tmp_path)

    cleanup_old_scene_cogs(today=today)

    scene.refresh_from_db()
    assert scene.cog_path is not None


def test_cleanup_skips_excluded_scenes_even_if_listed_in_an_old_product(tmp_path):
    today = timezone.now().date()
    scene = _make_scene("EXC1", tmp_path, status=SatelliteScene.Status.EXCLUDED)
    _make_product(["EXC1"], period_end=today - timedelta(days=100))

    cleanup_old_scene_cogs(today=today)

    scene.refresh_from_db()
    assert scene.cog_path is not None


def test_cleanup_ignores_unpublished_products(tmp_path):
    today = timezone.now().date()
    scene = _make_scene("UNPUB1", tmp_path)
    _make_product(["UNPUB1"], period_end=today - timedelta(days=100), is_published=False)

    cleanup_old_scene_cogs(today=today)

    scene.refresh_from_db()
    assert scene.cog_path is not None
