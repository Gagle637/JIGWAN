import numpy as np
import pytest
import rasterio
from django.contrib.gis.geos import Polygon
from rasterio.transform import Affine
from rasterio.warp import transform_bounds

from buildings.models import Building, Region
from satellite.composite import ALGO_VERSION
from satellite.index_scaling import MASK_NODATA
from satellite.models import ChangeArea, RasterProduct, RegionStat
from satellite.radius_stats import compute_change_stats, compute_green_stats

_BBOX = (127.24, 36.18, 127.56, 36.50)

pytestmark = pytest.mark.django_db

_BUILDING_LON = 127.385
_BUILDING_LAT = 36.351
_MARGIN_DEG = 0.02
_RESOLUTION_M = 10


def _square_wkt(lon, lat, size=0.001):
    """(lon, lat)를 중심으로 한 정사각형. 모서리를 (lon,lat)에 두면 건물 중심(重心)이
    (lon,lat)에서 size/2만큼 동북쪽으로 밀려, 반경 버퍼 중심도 그만큼 어긋난다(이 테스트
    파일에서 쓰는 margin bbox·코그 경계는 모두 (lon,lat)를 중심으로 깔아서, 실제 PostgreSQL로
    돌려보니 50% 테스트가 ~45m 어긋나 있었다 — 감사에서 발견)."""
    half = size / 2
    return (
        f"POLYGON(({lon - half} {lat - half}, {lon + half} {lat - half}, "
        f"{lon + half} {lat + half}, {lon - half} {lat + half}, {lon - half} {lat - half}))"
    )


def _make_building(**overrides):
    defaults = dict(
        building_key="RB1",
        gis_bldg_id="RB1",
        pnu="3011010300101530099",
        bjd_code="3011010300",
        use_code="01000",
        use_name="공동주택",
        source_date="2026-10-06",
        geom=_square_wkt(_BUILDING_LON, _BUILDING_LAT),
    )
    defaults.update(overrides)
    return Building.objects.create(**defaults)


def _margin_bounds_32652():
    """건물 주변 500m 반경을 넉넉히 덮는 32652 bbox(여유 margin=0.02도 ≈ 2km)."""
    return transform_bounds(
        "EPSG:4326",
        "EPSG:32652",
        _BUILDING_LON - _MARGIN_DEG,
        _BUILDING_LAT - _MARGIN_DEG,
        _BUILDING_LON + _MARGIN_DEG,
        _BUILDING_LAT + _MARGIN_DEG,
    )


def _write_tile(path, left, bottom, right, top, array):
    width = array.shape[1]
    height = array.shape[0]
    transform = Affine(_RESOLUTION_M, 0, left, 0, -_RESOLUTION_M, top)
    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "count": 1,
        "width": width,
        "height": height,
        "crs": "EPSG:32652",
        "transform": transform,
        "nodata": MASK_NODATA,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array, 1)


def _tile_shape(left, bottom, right, top):
    width = max(int((right - left) / _RESOLUTION_M), 1)
    height = max(int((top - bottom) / _RESOLUTION_M), 1)
    return height, width


def _write_half_green(path, left, bottom, right, top):
    """왼쪽 절반=녹지(1), 오른쪽 절반=유효하지만 녹지 아님(0) — ratio 50% 테스트용."""
    height, width = _tile_shape(left, bottom, right, top)
    array = np.zeros((height, width), dtype=np.uint8)
    array[:, : width // 2] = 1
    _write_tile(path, left, bottom, right, top, array)


def _write_all_green(path, left, bottom, right, top):
    height, width = _tile_shape(left, bottom, right, top)
    array = np.ones((height, width), dtype=np.uint8)
    _write_tile(path, left, bottom, right, top, array)


def _write_partial_valid_band(path, left, bottom, right, top, valid_half_width_m):
    """중심(=건물·반경 중심)에서 좌우로 valid_half_width_m씩, 폭 2*valid_half_width_m인
    세로띠만 유효(녹지)하고 나머지는 MASK_NODATA — insufficient_data 테스트용.

    예전엔 "전체 여유 bbox(margin=0.02도≈2.2km) 폭의 30%"를 왼쪽 끝부터 잘랐는데, 여유
    bbox가 반경(500m)보다 훨씬 커서 그 30%가 반경 원과 전혀 안 겹쳤다(실제 PostgreSQL로
    돌려보니 반경 시작 전 ~230m에서 끝나 coverage_pct=0으로 나옴, 감사에서 발견). 이제는
    반경 중심 기준 미터 단위로 띠를 둬서 실제로 겹치게 한다.
    """
    height, width = _tile_shape(left, bottom, right, top)
    array = np.full((height, width), MASK_NODATA, dtype=np.uint8)
    center_col = width // 2
    half_cols = max(int(valid_half_width_m / _RESOLUTION_M), 1)
    start = max(center_col - half_cols, 0)
    end = min(center_col + half_cols, width)
    array[:, start:end] = 1
    _write_tile(path, left, bottom, right, top, array)


def _make_green_product(tmp_path, name, year=2026, season="summer", **overrides):
    defaults = dict(
        product_type=RasterProduct.ProductType.GREEN_MASK,
        year=year,
        season=season,
        period_start=f"{year}-06-01",
        period_end=f"{year}-08-31",
        bbox=Polygon.from_bbox(_BBOX),
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
        bbox=Polygon.from_bbox(_BBOX),
        cog_path=str(tmp_path / f"{name}.tif"),
        algo_version=ALGO_VERSION,
        scene_ids=[],
        is_published=True,
    )
    defaults.update(overrides)
    return RasterProduct.objects.create(**defaults)


def _make_change_mask_product(tmp_path, name, year=2026, season="summer", compare_period="1y", **overrides):
    defaults = dict(
        product_type=RasterProduct.ProductType.CHANGE_MASK,
        year=year,
        season=season,
        period_start=f"{year}-06-01",
        period_end=f"{year}-08-31",
        compare_period=compare_period,
        bbox=Polygon.from_bbox(_BBOX),
        cog_path=str(tmp_path / f"{name}.tif"),
        algo_version=ALGO_VERSION,
        scene_ids=[],
        is_published=True,
    )
    defaults.update(overrides)
    return RasterProduct.objects.create(**defaults)


def _change_square_wkt(lon, lat, size):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


# ---- compute_green_stats -------------------------------------------------


def test_compute_green_stats_empty_catalog_returns_none():
    building = _make_building()

    assert compute_green_stats(building, 500) is None


def test_compute_green_stats_single_cog_ratio(tmp_path):
    building = _make_building()
    left, bottom, right, top = _margin_bounds_32652()
    path = tmp_path / "green_half.tif"
    _write_half_green(path, left, bottom, right, top)
    _make_green_product(tmp_path, "green_half")

    stats = compute_green_stats(building, 500)

    assert stats is not None
    assert stats["ratio_pct"] == pytest.approx(50.0, abs=5.0)
    assert stats["coverage_pct"] == pytest.approx(100.0, abs=1.0)
    assert stats["series"] == [
        {
            "year": 2026,
            "season": "summer",
            "ratio_pct": stats["ratio_pct"],
            "coverage_pct": stats["coverage_pct"],
        }
    ]
    assert stats["product_ids"]


def test_compute_green_stats_multi_season_series(tmp_path):
    building = _make_building()
    left, bottom, right, top = _margin_bounds_32652()

    path_summer = tmp_path / "green_summer.tif"
    _write_all_green(path_summer, left, bottom, right, top)
    _make_green_product(tmp_path, "green_summer", year=2026, season="summer")

    path_spring = tmp_path / "green_spring.tif"
    _write_all_green(path_spring, left, bottom, right, top)
    _make_green_product(
        tmp_path,
        "green_spring",
        year=2026,
        season="spring",
        period_start="2026-03-01",
        period_end="2026-05-31",
    )

    stats = compute_green_stats(building, 500)

    assert [item["season"] for item in stats["series"]] == ["spring", "summer"]
    # 최신 계절(summer)이 series의 마지막 항목이고, ratio_pct도 그 값을 쓴다.
    assert stats["ratio_pct"] == pytest.approx(100.0, abs=1.0)


def test_compute_green_stats_sums_pixels_across_multiple_cogs_same_period(tmp_path):
    building = _make_building()
    left, bottom, right, top = _margin_bounds_32652()
    mid = (left + right) / 2

    path_a = tmp_path / "tile_a.tif"
    height_a, width_a = _tile_shape(left, bottom, mid, top)
    _write_tile(path_a, left, bottom, mid, top, np.ones((height_a, width_a), dtype=np.uint8))
    _make_green_product(tmp_path, "tile_a")

    path_b = tmp_path / "tile_b.tif"
    height_b, width_b = _tile_shape(mid, bottom, right, top)
    _write_tile(path_b, mid, bottom, right, top, np.ones((height_b, width_b), dtype=np.uint8))
    _make_green_product(tmp_path, "tile_b")

    stats = compute_green_stats(building, 500)

    assert len(stats["series"]) == 1  # 같은 (year, season)이라 한 항목으로 합산
    assert len(stats["product_ids"]) == 2
    assert stats["ratio_pct"] == pytest.approx(100.0, abs=1.0)


def test_compute_green_stats_insufficient_valid_ratio_is_null(tmp_path):
    building = _make_building()
    left, bottom, right, top = _margin_bounds_32652()
    path = tmp_path / "mostly_nodata.tif"
    # 반경(500m) 중심 기준 ±110m 띠만 유효 -> 원 면적의 대략 28%와 겹친다(원-현 면적 공식:
    # 1 - 2*(acos(d/R) - (d/R)*sqrt(1-(d/R)^2))/pi, d=110, R=500 -> ~0.278). 좌표계·픽셀
    # 격자 보정 때문에 실제 값은 이 근처에서 조금 움직일 수 있어 허용폭을 넓게 둔다.
    _write_partial_valid_band(path, left, bottom, right, top, valid_half_width_m=110)
    _make_green_product(tmp_path, "mostly_nodata")

    stats = compute_green_stats(building, 500)

    assert stats["ratio_pct"] is None  # spec 5-3: 유효 비율<50% -> insufficient_data
    assert stats["coverage_pct"] == pytest.approx(28.0, abs=8.0)


def test_compute_green_stats_includes_region_avg_and_diff(tmp_path):
    building = _make_building()
    region = Region.objects.create(
        region_code="30110",
        level="sigungu",
        name="테스트구",
        geom=(
            "MULTIPOLYGON(((127.0 36.0, 127.8 36.0, 127.8 36.7, "
            "127.0 36.7, 127.0 36.0)))"
        ),
    )
    left, bottom, right, top = _margin_bounds_32652()
    path = tmp_path / "green_half2.tif"
    _write_half_green(path, left, bottom, right, top)
    product = _make_green_product(tmp_path, "green_half2")
    RegionStat.objects.create(region=region, product=product, green_ratio=0.6)

    stats = compute_green_stats(building, 500)

    assert stats["region_avg_pct"] == 60.0
    assert stats["diff_pp"] == pytest.approx(stats["ratio_pct"] - 60.0, abs=0.01)


# ---- compute_change_stats --------------------------------------------------


def test_compute_change_stats_empty_catalog_returns_none():
    building = _make_building()

    assert compute_change_stats(building, 500) is None


def test_compute_change_stats_tiles_before_only_has_published_periods(tmp_path):
    building = _make_building()
    _make_truecolor_product(tmp_path, "cur", 2026, "summer")
    _make_truecolor_product(tmp_path, "y1", 2025, "summer")
    _make_truecolor_product(tmp_path, "y3", 2023, "summer")  # 2y(2024)는 없음

    stats = compute_change_stats(building, 500)

    assert stats is not None
    assert stats["tiles"]["after"] is not None
    assert set(stats["tiles"]["before"].keys()) == {"1y", "3y"}
    assert stats["tiles"]["default_compare"] == "1y"
    assert stats["total_area_m2"] == 0.0
    assert stats["areas"] == []


def test_compute_change_stats_default_compare_falls_back_when_1y_missing(tmp_path):
    building = _make_building()
    _make_truecolor_product(tmp_path, "cur", 2026, "summer")
    _make_truecolor_product(tmp_path, "y2", 2024, "summer")  # 1y(2025) 없음

    stats = compute_change_stats(building, 500)

    assert set(stats["tiles"]["before"].keys()) == {"2y"}
    assert stats["tiles"]["default_compare"] == "2y"


def test_compute_change_stats_aggregates_change_areas_in_radius(tmp_path):
    building = _make_building()
    product = _make_change_mask_product(tmp_path, "chg1")

    # 반경(500m) 안 — 거리·면적이 서로 다른 4개
    for lon_offset, lat_offset, size in (
        (0.0, 0.0, 0.0012),
        (0.001, 0.0, 0.0009),
        (-0.001, 0.0, 0.0006),
        (0.0, 0.001, 0.0003),
    ):
        ChangeArea.objects.create(
            product=product,
            period="1y",
            area_m2=1.0,
            delta_ndbi=0.2,
            delta_ndvi=-0.2,
            geom=_change_square_wkt(
                _BUILDING_LON + lon_offset, _BUILDING_LAT + lat_offset, size
            ),
        )
    # 반경 밖(수 km) — 제외돼야 함
    ChangeArea.objects.create(
        product=product,
        period="1y",
        area_m2=1.0,
        delta_ndbi=0.2,
        delta_ndvi=-0.2,
        geom=_change_square_wkt(_BUILDING_LON + 0.1, _BUILDING_LAT, 0.001),
    )

    stats = compute_change_stats(building, 500)

    assert stats is not None
    assert len(stats["areas"]) == 3  # 최대 3개(spec 3-2-5)
    sizes = [area["area_m2"] for area in stats["areas"]]
    assert sizes == sorted(sizes, reverse=True)
    for area in stats["areas"]:
        assert {"id", "area_m2", "distance_m", "period", "geometry"} <= area.keys()
    assert stats["total_area_m2"] > 0.0
