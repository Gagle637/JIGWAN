from datetime import date

import pytest

from buildings.models import Building
from crime.management.commands.probe_crime_feature_cap import _building_density_centroid

pytestmark = pytest.mark.django_db


def _square_wkt(lon, lat, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


def _building(key, bjd_code, lon, lat):
    return Building.objects.create(
        building_key=key,
        gis_bldg_id=key,
        pnu=f"{bjd_code}000000000",
        bjd_code=bjd_code,
        source_date=date(2026, 1, 1),
        geom=_square_wkt(lon, lat),
    )


def test_building_density_centroid_picks_the_most_populous_sigungu():
    """시군구(bjd_code 앞 5자리) "91110"에 건물 2개, "91200"에 1개 — 더 밀집된 91110의
    건물 중심점을 써야 한다."""
    _building("A", "9111010100", 127.0, 36.0)
    _building("B", "9111010100", 127.01, 36.01)
    _building("C", "9120010100", 128.0, 37.0)

    centroid = _building_density_centroid("91")

    assert centroid is not None
    lon, lat = centroid
    assert lon == pytest.approx(127.005, abs=1e-3)
    assert lat == pytest.approx(36.005, abs=1e-3)


def test_building_density_centroid_ignores_inactive_buildings():
    building = _building("A", "9111010100", 127.0, 36.0)
    building.is_active = False
    building.save(update_fields=["is_active"])

    assert _building_density_centroid("91") is None


def test_building_density_centroid_returns_none_when_no_buildings():
    assert _building_density_centroid("99") is None
