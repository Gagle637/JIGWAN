import numpy as np
import pytest
import rasterio
from django.contrib.gis.geos import Polygon
from rasterio.transform import Affine

from core.models import ServiceArea
from satellite.catalog import VALID_RATIO_MIN, validate_and_publish
from satellite.cog import grid_transform
from satellite.composite import ALGO_VERSION
from satellite.index_scaling import INDEX_NODATA
from satellite.models import RasterProduct

pytestmark = pytest.mark.django_db

_GRID = {
    "crs": "EPSG:32652",
    "resolution_m": 10,
    "minx": 341700,
    "miny": 4004820,
    "maxx": 371040,
    "maxy": 4040880,
    "width": 2934,
    "height": 3606,
}
_BBOX = (127.24, 36.18, 127.56, 36.50)


@pytest.fixture(autouse=True)
def _service_area_grid(db):
    """migration 0004가 service_area "30" 행을 만들어 두지만 grid는 비어 있다 — 테스트
    래스터와 같은 _GRID를 넣어 get_grid("30")이 쓰게 한다(다지역 지원 2단계)."""
    ServiceArea.objects.filter(sido_code="30").update(grid=_GRID)


def _write_raster(path, array, dtype, nodata, crs=None, transform=None):
    grid = _GRID
    profile = {
        "driver": "GTiff",
        "dtype": dtype,
        "count": 1,
        "width": array.shape[1],
        "height": array.shape[0],
        "crs": crs or grid["crs"],
        "transform": transform or grid_transform(grid),
        "nodata": nodata,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array, 1)


def _make_product(tmp_path, product_type, array, dtype, nodata, name, **raster_kwargs):
    path = tmp_path / f"{name}.tif"
    _write_raster(path, array, dtype, nodata, **raster_kwargs)
    bbox = Polygon.from_bbox(_BBOX)
    return RasterProduct.objects.create(
        product_type=product_type,
        year=2026,
        season="summer",
        period_start="2026-06-01",
        period_end="2026-08-31",
        bbox=bbox,
        cog_path=str(path),
        algo_version=ALGO_VERSION,
        scene_ids=[],
        is_published=False,
    )


def _grid_full(value, dtype=np.int16):
    grid = _GRID
    return np.full((grid["height"], grid["width"]), value, dtype=dtype)


def test_publishes_when_valid_ratio_above_threshold(tmp_path):
    grid = _GRID
    array = _grid_full(INDEX_NODATA)
    valid_count = int(grid["width"] * grid["height"] * 0.2)  # 20% >= 10% 기준
    flat = array.reshape(-1)
    flat[:valid_count] = 3000  # ndvi=0.3, 정상 범위
    array = flat.reshape(array.shape)

    product = _make_product(tmp_path, "ndvi", array, "int16", INDEX_NODATA, "ndvi_ok")

    result = validate_and_publish(product, "30")

    product.refresh_from_db()
    assert result is True
    assert product.is_published is True
    assert product.valid_ratio == pytest.approx(0.2, abs=0.01)


def test_rejects_when_valid_ratio_below_threshold(tmp_path):
    grid = _GRID
    array = _grid_full(INDEX_NODATA)
    valid_count = int(grid["width"] * grid["height"] * 0.05)  # 5% < 10% 기준
    flat = array.reshape(-1)
    flat[:valid_count] = 3000
    array = flat.reshape(array.shape)

    product = _make_product(tmp_path, "ndvi", array, "int16", INDEX_NODATA, "ndvi_low")

    result = validate_and_publish(product, "30")

    product.refresh_from_db()
    assert result is False
    assert product.is_published is False
    assert product.valid_ratio == pytest.approx(0.05, abs=0.01)  # 실패해도 측정값은 기록


def test_rejects_value_out_of_range_for_ndvi(tmp_path):
    grid = _GRID
    array = _grid_full(INDEX_NODATA)
    valid_count = int(grid["width"] * grid["height"] * 0.5)
    flat = array.reshape(-1)
    flat[:valid_count] = 15000  # ndvi=1.5, 정상 범위 [-1,1] 밖(계산 버그 신호)
    array = flat.reshape(array.shape)

    product = _make_product(tmp_path, "ndvi", array, "int16", INDEX_NODATA, "ndvi_bad_range")

    result = validate_and_publish(product, "30")

    product.refresh_from_db()
    assert result is False
    assert product.is_published is False


def test_truecolor_skips_value_range_check(tmp_path):
    grid = _GRID
    array = np.full((grid["height"], grid["width"]), 5000, dtype=np.uint16)  # 전부 유효(100%)

    product = _make_product(tmp_path, "truecolor", array, "uint16", 0, "truecolor_ok")

    result = validate_and_publish(product, "30")

    assert result is True  # 값범위 검사는 ndvi/ndbi만(결정 사항 11)


def test_grid_mismatch_rejected(tmp_path):
    # _GRID와 다른 transform(해상도 20m)의 작은 래스터
    small_transform = Affine(20, 0, 300000, 0, -20, 4000000)
    array = np.full((50, 50), 3000, dtype=np.int16)
    path = tmp_path / "mismatch.tif"
    _write_raster(path, array, "int16", INDEX_NODATA, transform=small_transform)

    bbox = Polygon.from_bbox(_BBOX)
    product = RasterProduct.objects.create(
        product_type="ndvi",
        year=2026,
        season="summer",
        period_start="2026-06-01",
        period_end="2026-08-31",
        bbox=bbox,
        cog_path=str(path),
        algo_version=ALGO_VERSION,
        scene_ids=[],
        is_published=False,
    )

    result = validate_and_publish(product, "30")

    product.refresh_from_db()
    assert result is False
    assert product.is_published is False


def test_valid_ratio_min_constant():
    assert VALID_RATIO_MIN == 0.10
