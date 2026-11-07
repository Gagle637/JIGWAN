import pytest
from django.contrib.gis.geos import Polygon

from core.models import ServiceArea
from layers.models import MapLayer
from layers.registry import serialize_layer, sync_cog_layer
from satellite.composite import ALGO_VERSION
from satellite.models import RasterProduct

_BBOX_30 = (127.24, 36.18, 127.56, 36.50)
_BBOX_36 = (127.0, 36.0, 127.3, 36.3)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _service_areas():
    ServiceArea.objects.update_or_create(
        sido_code="30",
        defaults={"name": "대전", "bbox_minx": _BBOX_30[0], "bbox_miny": _BBOX_30[1],
                  "bbox_maxx": _BBOX_30[2], "bbox_maxy": _BBOX_30[3]},
    )
    ServiceArea.objects.update_or_create(
        sido_code="36",
        defaults={"name": "세종", "bbox_minx": _BBOX_36[0], "bbox_miny": _BBOX_36[1],
                  "bbox_maxx": _BBOX_36[2], "bbox_maxy": _BBOX_36[3]},
    )


def _make_product(
    product_type, period_start, period_end, cog_path, year=2026, season="summer", region_code="30"
):
    return RasterProduct.objects.create(
        region_code=region_code,
        product_type=product_type,
        year=year,
        season=season,
        period_start=period_start,
        period_end=period_end,
        bbox=Polygon.from_bbox(_BBOX_30),
        cog_path=cog_path,
        algo_version=ALGO_VERSION,
        scene_ids=[],
        is_published=True,
    )


def _make_layer(slug, **overrides):
    defaults = dict(
        slug=slug, name=slug, group="satellite", source_type=MapLayer.SourceType.TITILER,
        source_params={},
    )
    defaults.update(overrides)
    return MapLayer.objects.create(**defaults)


def test_sync_cog_layer_adds_region_entry_with_year_in_attribution():
    layer = _make_layer("green_mask")
    product = _make_product(
        RasterProduct.ProductType.GREEN_MASK, "2026-06-01", "2026-08-31", "/new/path.tif"
    )

    updated = sync_cog_layer(product)

    layer.refresh_from_db()
    assert updated is True
    region = layer.source_params["regions"]["30"]
    assert region["region_code"] == "30"
    assert region["bbox"] == list(_BBOX_30)
    assert region["season"] == "2026-summer"
    assert region["attribution"] == "Contains modified Copernicus Sentinel data 2026"
    assert "tile_url" in region
    assert layer.synced_at is not None


def test_sync_cog_layer_skips_when_period_start_is_older_for_that_region():
    layer = _make_layer(
        "green_mask",
        source_params={"regions": {"30": {
            "region_code": "30", "bbox": list(_BBOX_30), "tile_url": "/current.png",
            "season": "2026-summer", "period_start": "2026-06-01",
            "attribution": "Contains modified Copernicus Sentinel data 2026",
        }}},
    )
    product = _make_product(
        RasterProduct.ProductType.GREEN_MASK, "2026-03-01", "2026-05-31", "/backfill/path.tif",
        season="spring",
    )

    updated = sync_cog_layer(product)

    layer.refresh_from_db()
    assert updated is False
    assert layer.source_params["regions"]["30"]["tile_url"] == "/current.png"


def test_sync_cog_layer_skips_when_no_matching_layer_registered():
    product = _make_product(
        RasterProduct.ProductType.NDVI, "2026-06-01", "2026-08-31", "/ndvi/path.tif"
    )

    assert sync_cog_layer(product) is False


def test_sync_cog_layer_handles_truecolor_product_type_via_before_after_slug():
    layer = _make_layer("before_after")
    product = _make_product(
        RasterProduct.ProductType.TRUECOLOR, "2026-06-01", "2026-08-31", "/truecolor/path.tif"
    )

    updated = sync_cog_layer(product)

    layer.refresh_from_db()
    assert updated is True
    assert layer.source_params["regions"]["30"]["tile_url"]


def test_sync_cog_layer_updates_only_that_regions_entry_leaving_others_untouched():
    """대전(30)이 새로 게시돼도 세종(36)의 기존 항목은 그대로 남아야 한다(지역별 적용)."""
    layer = _make_layer(
        "green_mask",
        source_params={"regions": {"36": {
            "region_code": "36", "bbox": list(_BBOX_36), "tile_url": "/sejong.png",
            "season": "2026-summer", "period_start": "2026-06-01",
            "attribution": "Contains modified Copernicus Sentinel data 2026",
        }}},
    )
    product = _make_product(
        RasterProduct.ProductType.GREEN_MASK, "2026-06-01", "2026-08-31", "/daejeon.tif",
        region_code="30",
    )

    updated = sync_cog_layer(product)

    layer.refresh_from_db()
    assert updated is True
    regions = layer.source_params["regions"]
    assert set(regions.keys()) == {"30", "36"}
    assert regions["36"]["tile_url"] == "/sejong.png"  # 안 건드려짐
    assert regions["30"]["region_code"] == "30"


# ---- serialize_layer: regions 리스트 변환 + 레이어 전체 attribution 연도 범위 ----


def test_serialize_layer_converts_regions_dict_to_sorted_list():
    layer = _make_layer(
        "before_after",
        source_params={"regions": {
            "36": {"region_code": "36", "bbox": list(_BBOX_36), "tile_url": "/b.png",
                   "season": "2026-summer", "period_start": "2026-06-01",
                   "attribution": "Contains modified Copernicus Sentinel data 2026"},
            "30": {"region_code": "30", "bbox": list(_BBOX_30), "tile_url": "/a.png",
                   "season": "2025-summer", "period_start": "2025-06-01",
                   "attribution": "Contains modified Copernicus Sentinel data 2025"},
        }},
    )

    data = serialize_layer(layer)

    regions = data["source_params"]["regions"]
    assert [r["region_code"] for r in regions] == ["30", "36"]  # 정렬됨
    assert "period_start" not in regions[0]  # 내부 전용 필드는 응답에서 빠진다


def test_serialize_layer_computes_attribution_year_range_from_current_regions():
    layer = _make_layer(
        "before_after",
        attribution="Contains modified Copernicus Sentinel data",  # regions 없을 때의 대체값
        source_params={"regions": {
            "30": {"region_code": "30", "bbox": list(_BBOX_30), "tile_url": "/a.png",
                   "season": "2025-summer", "period_start": "2025-06-01",
                   "attribution": "Contains modified Copernicus Sentinel data 2025"},
            "36": {"region_code": "36", "bbox": list(_BBOX_36), "tile_url": "/b.png",
                   "season": "2026-summer", "period_start": "2026-06-01",
                   "attribution": "Contains modified Copernicus Sentinel data 2026"},
        }},
    )

    data = serialize_layer(layer)

    assert data["attribution"] == "Contains modified Copernicus Sentinel data 2025–2026"


def test_serialize_layer_attribution_single_year_has_no_range_dash():
    layer = _make_layer(
        "before_after",
        source_params={"regions": {
            "30": {"region_code": "30", "bbox": list(_BBOX_30), "tile_url": "/a.png",
                   "season": "2026-summer", "period_start": "2026-06-01",
                   "attribution": "Contains modified Copernicus Sentinel data 2026"},
        }},
    )

    data = serialize_layer(layer)

    assert data["attribution"] == "Contains modified Copernicus Sentinel data 2026"


def test_serialize_layer_returns_empty_regions_list_for_non_cog_layers():
    layer = _make_layer(
        "trade_location", source_type=MapLayer.SourceType.GEOJSON, source_params={"url": "/api/me"},
        attribution="국토교통부 실거래가 공개시스템(공공데이터포털)",
    )

    data = serialize_layer(layer)

    assert data["source_params"]["regions"] == []
    assert data["source_params"]["url"] == "/api/me"  # 기존 필드는 안 건드려짐
    assert data["attribution"] == "국토교통부 실거래가 공개시스템(공공데이터포털)"  # 저장값 유지
