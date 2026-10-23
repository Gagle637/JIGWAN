import math

import pytest

from buildings.models import Building
from buildings.tiles import render_building_tile


def _lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


@pytest.mark.django_db
def test_tile_below_min_zoom_is_empty(django_assert_num_queries):
    with django_assert_num_queries(0):
        tile = render_building_tile(13, 0, 0)
    assert tile == b""


@pytest.mark.django_db
def test_tile_at_min_zoom_contains_building():
    lon, lat = 127.385, 36.351
    square = (
        f"POLYGON(({lon} {lat}, {lon + 0.001} {lat}, "
        f"{lon + 0.001} {lat + 0.001}, {lon} {lat + 0.001}, {lon} {lat}))"
    )
    Building.objects.create(
        building_key="TILE1",
        gis_bldg_id="TILE1",
        pnu="0000000000000000000",
        bjd_code="0000000000",
        use_name="단독주택",
        floors_above=2,
        source_date="2026-01-01",
        geom=square,
    )

    x, y = _lonlat_to_tile(lon + 0.0005, lat + 0.0005, 14)
    tile = render_building_tile(14, x, y)
    assert tile != b""


@pytest.mark.django_db
def test_tile_with_no_buildings_in_range_is_empty():
    x, y = _lonlat_to_tile(0.0, 0.0, 14)  # 대전과 무관한 좌표(대서양)
    tile = render_building_tile(14, x, y)
    assert tile == b""
