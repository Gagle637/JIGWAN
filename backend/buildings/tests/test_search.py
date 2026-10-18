import pytest

from buildings.models import Building
from buildings.search import search_buildings

pytestmark = pytest.mark.django_db


def _square_wkt(lon, lat, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


def test_search_buildings_orders_by_similarity_score():
    Building.objects.create(
        building_key="EXACT", gis_bldg_id="EXACT", pnu="1" * 19,
        bjd_code="3011010300", bjd_name="대전광역시 동구 효동", jibun="153-3",
        source_date="2026-01-01", geom=_square_wkt(127.38, 36.35),
    )
    Building.objects.create(
        building_key="PARTIAL", gis_bldg_id="PARTIAL", pnu="2" * 19,
        bjd_code="3011010300", bjd_name="대전광역시 동구 효동", jibun="999-1",
        source_date="2026-01-01", geom=_square_wkt(127.39, 36.36),
    )

    results = search_buildings("효동 153-3")

    assert results[0]["address"] == "대전광역시 동구 효동 153-3"


def test_search_buildings_respects_limit():
    for i in range(5):
        Building.objects.create(
            building_key=f"L{i}", gis_bldg_id=f"L{i}", pnu=f"{i:019d}",
            bjd_code="3014011600", bjd_name="대전광역시 중구 은행동", jibun=f"{i}-1",
            source_date="2026-01-01", geom=_square_wkt(127.4 + i * 0.001, 36.3),
        )

    results = search_buildings("은행동", limit=3)

    assert len(results) == 3


def test_search_buildings_no_match_returns_empty_list():
    assert search_buildings("존재하지않는동네이름") == []
