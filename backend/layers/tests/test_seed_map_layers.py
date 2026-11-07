import pytest
from django.contrib.gis.geos import Polygon
from django.core.management import call_command
from rest_framework.test import APIClient

from core.models import ServiceArea
from layers.models import MapLayer
from layers.registry import sync_cog_layer
from satellite.composite import ALGO_VERSION
from satellite.models import RasterProduct

pytestmark = pytest.mark.django_db


def test_seed_map_layers_fills_crime_layer_legend_and_source_params():
    call_command("seed_map_layers")

    layer = MapLayer.objects.get(slug="crime_hotspot")

    assert layer.source_type == MapLayer.SourceType.WMS
    assert layer.source_params["service_url"] == "https://safemap.go.kr/openapi2/IF_0087_WMS"
    assert layer.source_params["layers"] == "A2SM_CRMNLHSPOT_TOT"
    assert layer.notice.startswith("경찰청의 요청으로")

    assert len(layer.legend) == 10
    # LGD_NO 기준으로 정렬돼 있어야 한다(사용자 확인: 실제 응답은 순서가 섞여 있음).
    assert [item["no"] for item in layer.legend] == list(range(1, 11))
    assert layer.legend[0] == {"no": 1, "label": "1등급", "color": "#ffffb2"}
    assert layer.legend[-1] == {"no": 10, "label": "10등급", "color": "#bd0026"}


def test_seed_map_layers_is_idempotent_on_rerun():
    call_command("seed_map_layers")
    first_count = MapLayer.objects.count()

    call_command("seed_map_layers")

    assert MapLayer.objects.count() == first_count == 9


def test_seed_map_layers_updates_existing_row_by_slug_even_if_name_differs():
    """버그0: name이 upsert 키면 이름을 바꾸는 순간 중복 행이 생긴다. slug는 바뀌지 않으니
    기존에 옛 이름으로 들어있던 행도 slug로 찾아 그 자리에서 갱신해야 한다."""
    old = MapLayer.objects.create(
        slug="green_mask", name="녹지 마스크", group="환경",
        source_type=MapLayer.SourceType.TITILER, order=5,
    )

    call_command("seed_map_layers")

    old.refresh_from_db()
    assert old.name == "녹지 마스크 (10m 해상도)"
    assert MapLayer.objects.filter(slug="green_mask").count() == 1


def test_seed_map_layers_sets_max_zoom_15_for_sentinel_layers():
    call_command("seed_map_layers")

    green = MapLayer.objects.get(slug="green_mask")
    before_after = MapLayer.objects.get(slug="before_after")

    assert green.max_zoom == 15
    assert "(10m 해상도)" in green.name
    assert before_after.max_zoom == 15
    assert "(10m 해상도)" in before_after.name


def test_seed_map_layers_fills_attribution_for_externally_sourced_layers_only():
    call_command("seed_map_layers")

    external_slugs = [
        "osm_basemap", "building_footprint", "green_mask", "before_after",
        "change_area", "trade_location", "crime_hotspot",
    ]
    for slug in external_slugs:
        attribution = MapLayer.objects.get(slug=slug).attribution
        assert attribution, f"{slug}의 attribution이 비어있으면 안 된다"

    # 사용자 결정: 자체 데이터(외부 출처 없음)는 비워 둔다.
    assert MapLayer.objects.get(slug="my_buildings").attribution is None
    assert MapLayer.objects.get(slug="analysis_radius").attribution is None


def test_two_regions_each_get_their_own_cog_in_layers_response():
    ServiceArea.objects.update_or_create(
        sido_code="30",
        defaults={"name": "대전", "bbox_minx": 127.24, "bbox_miny": 36.18,
                  "bbox_maxx": 127.56, "bbox_maxy": 36.50},
    )
    ServiceArea.objects.update_or_create(
        sido_code="36",
        defaults={"name": "세종", "bbox_minx": 127.0, "bbox_miny": 36.0,
                  "bbox_maxx": 127.3, "bbox_maxy": 36.3},
    )
    call_command("seed_map_layers")

    bbox = Polygon.from_bbox((127.24, 36.18, 127.56, 36.50))
    for region_code, cog_path in (("30", "/daejeon_green.tif"), ("36", "/sejong_green.tif")):
        product = RasterProduct.objects.create(
            region_code=region_code, product_type="green_mask", year=2026, season="summer",
            period_start="2026-06-01", period_end="2026-08-31", bbox=bbox,
            cog_path=cog_path, algo_version=ALGO_VERSION, scene_ids=[], is_published=True,
        )
        assert sync_cog_layer(product) is True

    response = APIClient().get("/api/layers")
    layer = next(row for row in response.json() if row["slug"] == "green_mask")
    regions = {r["region_code"]: r for r in layer["source_params"]["regions"]}

    assert set(regions.keys()) == {"30", "36"}
    assert "daejeon_green" in regions["30"]["tile_url"]
    assert "sejong_green" in regions["36"]["tile_url"]
    assert regions["30"]["season"] == "2026-summer"
