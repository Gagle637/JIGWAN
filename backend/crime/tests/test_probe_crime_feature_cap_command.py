from datetime import date

import pytest

from buildings.models import Building
from crime.management.commands.probe_crime_feature_cap import (
    DEFAULT_LAT,
    DEFAULT_LON,
    _building_density_centroid,
)

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


def test_building_density_centroid_for_daejeon_is_near_the_historical_default_point():
    """대전(30)도 더는 따로 분기하지 않고 다른 지역과 같은 규칙(건물 밀집 시군구의 건물
    중심점)을 쓴다 — 원도심 예시 좌표(DEFAULT_LON/LAT) 근처에 건물을 몰아두면 그 근처
    결과가 나와야 한다."""
    _building("D1", "3014010100", DEFAULT_LON - 0.001, DEFAULT_LAT - 0.001)
    _building("D2", "3014010100", DEFAULT_LON + 0.001, DEFAULT_LAT + 0.001)
    # 다른 구(덜 밀집) — 더 밀집된 중구(30140)가 선택돼야 한다.
    _building("D3", "3020010100", 127.3, 36.2)

    centroid = _building_density_centroid("30")

    assert centroid is not None
    lon, lat = centroid
    assert lon == pytest.approx(DEFAULT_LON, abs=0.01)
    assert lat == pytest.approx(DEFAULT_LAT, abs=0.01)
