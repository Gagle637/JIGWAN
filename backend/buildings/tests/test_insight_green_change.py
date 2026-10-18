import numpy as np
import pytest
import rasterio
from django.contrib.gis.geos import Polygon
from django.core.cache import cache
from rasterio.transform import Affine
from rasterio.warp import transform_bounds
from rest_framework.test import APIClient

import buildings.insight as insight_module
from buildings.models import Building
from satellite.composite import ALGO_VERSION
from satellite.models import RasterProduct
from satellite.stac_search import DAEJEON_BBOX

pytestmark = pytest.mark.django_db

_BUILDING_LON = 127.385
_BUILDING_LAT = 36.351
_MARGIN_DEG = 0.02
_RESOLUTION_M = 10


def _square_wkt(lon, lat, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


def _make_building(**overrides):
    defaults = dict(
        building_key="IGB1",
        gis_bldg_id="IGB1",
        pnu="3011010300101530098",
        bjd_code="3011010300",
        use_code="01000",
        use_name="공동주택",
        source_date="2026-10-06",
        geom=_square_wkt(_BUILDING_LON, _BUILDING_LAT),
    )
    defaults.update(overrides)
    return Building.objects.create(**defaults)


def _write_all_green_covering_building(path):
    left, bottom, right, top = transform_bounds(
        "EPSG:4326",
        "EPSG:32652",
        _BUILDING_LON - _MARGIN_DEG,
        _BUILDING_LAT - _MARGIN_DEG,
        _BUILDING_LON + _MARGIN_DEG,
        _BUILDING_LAT + _MARGIN_DEG,
    )
    width = max(int((right - left) / _RESOLUTION_M), 1)
    height = max(int((top - bottom) / _RESOLUTION_M), 1)
    transform = Affine(_RESOLUTION_M, 0, left, 0, -_RESOLUTION_M, top)
    array = np.ones((height, width), dtype=np.uint8)
    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "count": 1,
        "width": width,
        "height": height,
        "crs": "EPSG:32652",
        "transform": transform,
        "nodata": 255,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array, 1)


def _make_green_product(tmp_path, name="green", year=2026, season="summer", **overrides):
    defaults = dict(
        product_type=RasterProduct.ProductType.GREEN_MASK,
        year=year,
        season=season,
        period_start=f"{year}-06-01",
        period_end=f"{year}-08-31",
        bbox=Polygon.from_bbox(DAEJEON_BBOX),
        cog_path=str(tmp_path / f"{name}.tif"),
        algo_version=ALGO_VERSION,
        scene_ids=[],
        is_published=True,
    )
    defaults.update(overrides)
    return RasterProduct.objects.create(**defaults)


def _make_truecolor_product(tmp_path, name, year, season, **overrides):
    defaults = dict(
        product_type=RasterProduct.ProductType.TRUECOLOR,
        year=year,
        season=season,
        period_start=f"{year}-06-01",
        period_end=f"{year}-08-31",
        bbox=Polygon.from_bbox(DAEJEON_BBOX),
        cog_path=str(tmp_path / f"{name}.tif"),
        algo_version=ALGO_VERSION,
        scene_ids=[],
        is_published=True,
    )
    defaults.update(overrides)
    return RasterProduct.objects.create(**defaults)


def test_status_pending_when_no_satellite_data_at_all():
    building = _make_building()
    client = APIClient()

    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["status"] == "pending"
    assert body["green"] is None
    assert body["change"] is None
    reasons = {m["field"]: m["reason"] for m in body["missing"]}
    assert reasons["green"] == "no_satellite_data"
    assert reasons["change"] == "no_satellite_data"
    # crime은 9단계에서 구현됨 — 범죄주의구간 데이터가 전혀 없을 때의 사유는 no_crime_segment.
    assert reasons["crime"] == "no_crime_segment"


def test_status_partial_when_green_data_exists(tmp_path):
    cache.clear()
    building = _make_building()
    _write_all_green_covering_building(tmp_path / "green.tif")
    _make_green_product(tmp_path, "green")

    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["status"] == "partial"
    assert body["green"] is not None
    assert body["green"]["ratio_pct"] == pytest.approx(100.0, abs=1.0)
    assert "product_ids" not in body["green"]  # 내부 식별자는 응답에 노출하지 않는다
    assert body["as_of"]["satellite_period"] is not None


def test_change_tiles_before_only_has_published_periods(tmp_path):
    cache.clear()
    building = _make_building()
    _make_truecolor_product(tmp_path, "cur", 2026, "summer")
    _make_truecolor_product(tmp_path, "y1", 2025, "summer")

    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["status"] == "partial"
    assert body["change"]["tiles"]["after"] is not None
    assert set(body["change"]["tiles"]["before"].keys()) == {"1y"}
    assert body["change"]["tiles"]["default_compare"] == "1y"
    assert "product_ids" not in body["change"]


def test_insight_cache_hit_avoids_recompute(tmp_path, monkeypatch):
    cache.clear()
    building = _make_building()
    _write_all_green_covering_building(tmp_path / "green.tif")
    _make_green_product(tmp_path, "green")

    calls = {"green": 0, "change": 0}
    original_green = insight_module.compute_green_stats
    original_change = insight_module.compute_change_stats

    def counting_green(*args, **kwargs):
        calls["green"] += 1
        return original_green(*args, **kwargs)

    def counting_change(*args, **kwargs):
        calls["change"] += 1
        return original_change(*args, **kwargs)

    monkeypatch.setattr(insight_module, "compute_green_stats", counting_green)
    monkeypatch.setattr(insight_module, "compute_change_stats", counting_change)

    client = APIClient()
    first = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    second = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["green"] == 1  # 두 번째 요청은 캐시 히트라 다시 계산하지 않는다
    assert calls["change"] == 1
    assert first.json()["green"] == second.json()["green"]


def test_my_section_is_always_fresh_never_cached(monkeypatch):
    cache.clear()
    building = _make_building()

    def fake_my(building, user):
        return {"user_id": getattr(user, "id", None)}

    monkeypatch.setattr(insight_module, "_build_my_section", fake_my)

    class FakeUser:
        def __init__(self, user_id):
            self.id = user_id
            self.is_authenticated = True

    response_a = insight_module.build_insight_for_request(building, 500, FakeUser(1))
    response_b = insight_module.build_insight_for_request(building, 500, FakeUser(2))

    assert response_a["my"] == {"user_id": 1}
    assert response_b["my"] == {"user_id": 2}

    a_without_my = {k: v for k, v in response_a.items() if k != "my"}
    b_without_my = {k: v for k, v in response_b.items() if k != "my"}
    assert a_without_my == b_without_my  # my를 뺀 나머지는 캐시에서 와서 완전히 동일해야 한다
