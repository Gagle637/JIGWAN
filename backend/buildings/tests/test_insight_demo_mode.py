import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from .test_insight_green_change import _make_building

pytestmark = pytest.mark.django_db

DEMO_PNU = "DEMO000000000000001"  # demo/fixtures/demo_snapshots.json에 있는 예시 PNU


def test_demo_mode_returns_fixed_snapshot_for_demo_building(settings):
    settings.DEMO_MODE = True
    cache.clear()
    building = _make_building(building_key="DMB1", gis_bldg_id="DMB1", pnu=DEMO_PNU)
    client = APIClient()

    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["status"] == "ready"
    assert body["green"]["ratio_pct"] == 23.4
    # 분석 섹션은 고정값이지만, 건물 식별자·geometry는 실제 DB 행을 따른다.
    assert body["building"]["id"] == building.id
    assert body["building"]["pnu"] == DEMO_PNU


def test_demo_mode_does_not_affect_buildings_outside_the_fixture(settings):
    settings.DEMO_MODE = True
    cache.clear()
    building = _make_building(
        building_key="DMB2", gis_bldg_id="DMB2", pnu="3011010300101530020"
    )
    client = APIClient()

    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    # 데모 목록에 없는 건물은 평소처럼 계산되고(위성 데이터가 없어 pending), 데모 값이 섞이지 않는다.
    assert body["status"] == "pending"
    assert body["green"] is None


def test_demo_mode_off_ignores_matching_pnu(settings):
    settings.DEMO_MODE = False
    cache.clear()
    building = _make_building(building_key="DMB3", gis_bldg_id="DMB3", pnu=DEMO_PNU)
    client = APIClient()

    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    # DEMO_MODE가 꺼져 있으면 PNU가 같아도 데모 값을 쓰지 않고 평소처럼 계산한다.
    assert body["status"] == "pending"
