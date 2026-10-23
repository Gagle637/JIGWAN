import pytest

from buildings.models import Building
from crime.models import CrimeSegment
from crime.radius_stats import compute_crime_stats

pytestmark = pytest.mark.django_db

_BUILDING_LON = 127.385
_BUILDING_LAT = 36.351


def _square_wkt(lon, lat, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


def _polygon_wkt(min_lon, min_lat, width, height):
    """범죄주의구간(전체)은 실측 확인 결과 도로 선이 아니라 MultiPolygon 밀도분석 구역이다
    (spec 8-3)."""
    max_lon, max_lat = min_lon + width, min_lat + height
    return (
        f"MULTIPOLYGON((({min_lon} {min_lat}, {max_lon} {min_lat}, "
        f"{max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat})))"
    )


def _make_building(**overrides):
    defaults = dict(
        building_key="CRB1",
        gis_bldg_id="CRB1",
        pnu="3011010300101530095",
        bjd_code="3011010300",
        use_code="01000",
        use_name="공동주택",
        source_date="2026-10-06",
        geom=_square_wkt(_BUILDING_LON, _BUILDING_LAT),
    )
    defaults.update(overrides)
    return Building.objects.create(**defaults)


def test_compute_crime_stats_returns_none_when_no_segment_in_radius():
    building = _make_building()

    assert compute_crime_stats(building, 500) is None


def test_compute_crime_stats_excludes_segment_outside_radius():
    building = _make_building()
    CrimeSegment.objects.create(
        objt_id="OUTSIDE",
        grad=10,
        data_period="2023-07/2024-06",
        # 약 1.1km 북쪽(500m 반경 밖)
        geom=_polygon_wkt(_BUILDING_LON, _BUILDING_LAT + 0.01, 0.001, 0.0005),
    )

    assert compute_crime_stats(building, 500) is None


def test_compute_crime_stats_near_grad_null_when_nothing_within_50m():
    building = _make_building()
    # 약 300m 떨어진 구역(반경 500m 안이지만 50m 밖)
    CrimeSegment.objects.create(
        objt_id="FAR300",
        grad=6,
        data_period="2023-07/2024-06",
        geom=_polygon_wkt(_BUILDING_LON, _BUILDING_LAT + 0.0027, 0.0005, 0.0003),
    )

    stats = compute_crime_stats(building, 500)

    assert stats is not None
    assert stats["max_grad"] == 6
    assert stats["near_grad"] is None
    assert stats["flagged_area_m2"] > 0


def test_compute_crime_stats_near_grad_from_segment_within_50m():
    building = _make_building()
    CrimeSegment.objects.create(
        objt_id="NEAR1",
        grad=9,
        data_period="2023-07/2024-06",
        geom=_polygon_wkt(_BUILDING_LON, _BUILDING_LAT, 0.0002, 0.0002),
    )

    stats = compute_crime_stats(building, 500)

    assert stats["near_grad"] == 9
    assert stats["max_grad"] == 9


def test_compute_crime_stats_high_share_from_grad_8_and_above():
    building = _make_building()
    CrimeSegment.objects.create(
        objt_id="HIGH1",
        grad=8,
        data_period="2023-07/2024-06",
        geom=_polygon_wkt(_BUILDING_LON, _BUILDING_LAT, 0.001, 0.0001),
    )
    CrimeSegment.objects.create(
        objt_id="LOW1",
        grad=3,
        data_period="2023-07/2024-06",
        geom=_polygon_wkt(_BUILDING_LON, _BUILDING_LAT + 0.0003, 0.001, 0.0003),
    )

    stats = compute_crime_stats(building, 500)

    assert stats["max_grad"] == 8
    assert 0 < stats["high_share_pct"] < 100
    assert stats["flagged_area_m2"] > 0
