import pytest
from django.contrib.gis.geos import Polygon

from layers.models import MapLayer
from layers.registry import sync_cog_layer
from satellite.composite import ALGO_VERSION
from satellite.models import RasterProduct

_BBOX = (127.24, 36.18, 127.56, 36.50)

pytestmark = pytest.mark.django_db


def _make_product(product_type, period_start, period_end, cog_path, year=2026, season="summer"):
    return RasterProduct.objects.create(
        product_type=product_type,
        year=year,
        season=season,
        period_start=period_start,
        period_end=period_end,
        bbox=Polygon.from_bbox(_BBOX),
        cog_path=cog_path,
        algo_version=ALGO_VERSION,
        scene_ids=[],
        is_published=True,
    )


def test_sync_cog_layer_updates_when_period_start_is_newer():
    layer = MapLayer.objects.create(
        name="녹지 마스크",
        group="satellite",
        order=1,
        source_type=MapLayer.SourceType.TITILER,
        source_params={"cog_path": "/old/path.tif", "period_start": "2026-03-01"},
    )
    product = _make_product(
        RasterProduct.ProductType.GREEN_MASK,
        "2026-06-01",
        "2026-08-31",
        "/new/path.tif",
        season="summer",
    )

    updated = sync_cog_layer(product)

    layer.refresh_from_db()
    assert updated is True
    assert layer.source_params["cog_path"] == "/new/path.tif"
    assert layer.source_params["period_start"] == "2026-06-01"
    assert "tile_url" in layer.source_params
    assert layer.synced_at is not None


def test_sync_cog_layer_skips_when_period_start_is_older():
    layer = MapLayer.objects.create(
        name="녹지 마스크",
        group="satellite",
        order=1,
        source_type=MapLayer.SourceType.TITILER,
        source_params={"cog_path": "/current/path.tif", "period_start": "2026-06-01"},
    )
    product = _make_product(
        RasterProduct.ProductType.GREEN_MASK,
        "2026-03-01",  # 백필(backfill) — 과거 계절이 나중에 게시됨
        "2026-05-31",
        "/backfill/path.tif",
        season="spring",
    )

    updated = sync_cog_layer(product)

    layer.refresh_from_db()
    assert updated is False
    assert layer.source_params["cog_path"] == "/current/path.tif"
    assert layer.source_params["period_start"] == "2026-06-01"


def test_sync_cog_layer_skips_when_no_matching_layer_registered():
    product = _make_product(
        RasterProduct.ProductType.NDVI, "2026-06-01", "2026-08-31", "/ndvi/path.tif"
    )

    assert sync_cog_layer(product) is False


def test_sync_cog_layer_handles_truecolor_product_type():
    layer = MapLayer.objects.create(
        name="Before/After 위성 영상",
        group="satellite",
        order=2,
        source_type=MapLayer.SourceType.TITILER,
        source_params={},
    )
    product = _make_product(
        RasterProduct.ProductType.TRUECOLOR, "2026-06-01", "2026-08-31", "/truecolor/path.tif"
    )

    updated = sync_cog_layer(product)

    layer.refresh_from_db()
    assert updated is True
    assert layer.source_params["cog_path"] == "/truecolor/path.tif"
