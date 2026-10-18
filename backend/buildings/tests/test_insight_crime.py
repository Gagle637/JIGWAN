import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import IndexRun
from crime.models import CrimeSegment
from publicdata.models import Trade

from .test_insight_green_change import (
    _make_building,
    _make_green_product,
    _make_truecolor_product,
    _write_all_green_covering_building,
)

pytestmark = pytest.mark.django_db


def test_crime_section_null_with_no_crime_segment_reason():
    cache.clear()
    building = _make_building(
        building_key="CR1", gis_bldg_id="CR1", pnu="3011010300101530093"
    )

    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["crime"] is None
    reasons = {m["field"]: m["reason"] for m in body["missing"]}
    assert reasons["crime"] == "no_crime_segment"


def test_crime_section_present_when_segment_intersects_radius():
    cache.clear()
    building = _make_building(
        building_key="CR2", gis_bldg_id="CR2", pnu="3011010300101530092"
    )
    CrimeSegment.objects.create(
        objt_id="SEG1",
        grad=7,
        data_period="2023-07/2024-06",
        geom="LINESTRING(127.385 36.351, 127.3852 36.351)",
    )

    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["crime"] is not None
    assert body["crime"]["max_grad"] == 7
    assert "crime" not in {m["field"] for m in body["missing"]}


def test_as_of_crime_data_period_reflects_latest_collection_even_without_nearby_segment():
    cache.clear()
    building = _make_building(
        building_key="CR3", gis_bldg_id="CR3", pnu="3011010300101530091"
    )
    CrimeSegment.objects.create(
        objt_id="FARAWAY",
        grad=5,
        data_period="2023-07/2024-06",
        geom="LINESTRING(128.0 37.0, 128.001 37.001)",  # 건물과 무관한 위치
    )

    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["crime"] is None  # 반경과 겹치는 구간은 없음
    assert body["as_of"]["crime_data_period"] == "2023-07/2024-06"


def test_insight_cache_invalidates_after_new_safety_sync_indexrun():
    cache.clear()
    building = _make_building(
        building_key="CR4", gis_bldg_id="CR4", pnu="3011010300101530090"
    )
    CrimeSegment.objects.create(
        objt_id="SEG2",
        grad=5,
        data_period="2023-07/2024-06",
        geom="LINESTRING(127.385 36.351, 127.3852 36.351)",
    )

    client = APIClient()
    first = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500}).json()
    assert first["crime"]["max_grad"] == 5

    # 운영자가 등급을 바꾸고 safety_sync가 새로 성공했다고 가정한다.
    CrimeSegment.objects.filter(objt_id="SEG2").update(grad=9)
    IndexRun.objects.create(
        job="safety_sync",
        region_code="daejeon",
        status=IndexRun.Status.SUCCEEDED,
        finished_at=timezone.now(),
    )

    second = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500}).json()
    assert second["crime"]["max_grad"] == 9  # 캐시가 무효화돼 새 값을 반영


def test_status_ready_when_every_section_is_present(tmp_path):
    cache.clear()
    building = _make_building(
        building_key="CR5",
        gis_bldg_id="CR5",
        pnu="3011010300101530089",
        use_code="01000",
        use_name="공동주택",
    )
    Trade.objects.create(
        sgg_code="30110",
        pnu="OTHER_PNU",
        house_type=Trade.HouseType.APARTMENT,
        deal_type=Trade.DealType.SALE,
        deal_ym="2026-09",
        area_m2=100.0,
        price=50000,
        is_canceled=False,
        geom="SRID=4326;POINT(127.3851 36.3511)",
    )
    _write_all_green_covering_building(tmp_path / "green.tif")
    _make_green_product(tmp_path, "green")
    _make_truecolor_product(tmp_path, "cur", 2026, "summer")
    CrimeSegment.objects.create(
        objt_id="SEG3",
        grad=5,
        data_period="2023-07/2024-06",
        geom="LINESTRING(127.385 36.351, 127.3852 36.351)",
    )

    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["missing"] == []
    assert body["status"] == "ready"
