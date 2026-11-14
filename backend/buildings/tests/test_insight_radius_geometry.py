import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from buildings.radius_sql import building_radius_buffers, round_geojson_coordinates

from .test_insight_green_change import _make_building

pytestmark = pytest.mark.django_db

DEMO_PNU = "DEMO000000000000001"  # demo/fixtures/demo_snapshots.json에 있는 예시 PNU


def test_radius_geometry_present_as_polygon():
    cache.clear()
    building = _make_building(
        building_key="RGB1", gis_bldg_id="RGB1", pnu="3011010300101530070"
    )
    client = APIClient()

    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["radius_geometry"]["type"] == "Polygon"
    assert body["radius_geometry"]["coordinates"]


def test_radius_geometry_differs_between_500_and_1000():
    cache.clear()
    building = _make_building(
        building_key="RGB2", gis_bldg_id="RGB2", pnu="3011010300101530071"
    )
    client = APIClient()

    body_500 = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500}).json()
    body_1000 = client.get(f"/api/buildings/{building.id}/insight", {"radius": 1000}).json()

    assert body_500["radius_geometry"] != body_1000["radius_geometry"]


def test_radius_geometry_present_when_status_is_pending():
    cache.clear()
    building = _make_building(
        building_key="RGB3", gis_bldg_id="RGB3", pnu="3011010300101530072"
    )
    client = APIClient()

    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["status"] == "pending"
    assert body["radius_geometry"]["type"] == "Polygon"


def test_radius_geometry_present_in_demo_mode_and_matches_radius_m(settings):
    settings.DEMO_MODE = True
    cache.clear()
    building = _make_building(building_key="RGB4", gis_bldg_id="RGB4", pnu=DEMO_PNU)
    client = APIClient()

    # 데모 fixture는 radius_m=500으로 고정돼 있다. 요청 파라미터로 1000을 보내도
    # 데모 응답의 radius_m(500)이 그대로 나와야 하고, radius_geometry도 요청 파라미터가
    # 아니라 그 500m 기준이어야 한다(응답의 radius_m과 항상 같은 반경을 가리켜야 함).
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 1000})
    body = response.json()

    assert body["status"] == "ready"
    assert body["radius_m"] == 500
    assert body["radius_geometry"]["type"] == "Polygon"
    expected = round_geojson_coordinates(building_radius_buffers(building.id, 500)["buffer_4326"])
    assert body["radius_geometry"] == expected
