import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine
from rasterio.warp import transform_bounds

from buildings.models import Region
from satellite.index_scaling import MASK_NODATA
from satellite.region_stats import zonal_green_ratio

pytestmark = pytest.mark.django_db


def _write_mask(path, array):
    transform = Affine(10, 0, 300000, 0, -10, 4000000)
    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "count": 1,
        "width": array.shape[1],
        "height": array.shape[0],
        "crs": "EPSG:32652",
        "transform": transform,
        "nodata": MASK_NODATA,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array, 1)
    return transform


def _region_covering_raster(transform, width, height, region_code="99"):
    minx, miny = transform * (0, height)
    maxx, maxy = transform * (width, 0)
    lon_min, lat_min, lon_max, lat_max = transform_bounds(
        "EPSG:32652", "EPSG:4326", minx, miny, maxx, maxy
    )
    geom_wkt = (
        f"MULTIPOLYGON((({lon_min} {lat_min}, {lon_max} {lat_min}, "
        f"{lon_max} {lat_max}, {lon_min} {lat_max}, {lon_min} {lat_min})))"
    )
    return Region.objects.create(
        region_code=region_code, level="sido", name="테스트", geom=geom_wkt
    )


def test_zonal_green_ratio_computes_fraction_within_region(tmp_path):
    array = np.zeros((10, 10), dtype=np.uint8)
    array[:, :5] = 1  # 왼쪽 절반 녹지
    path = tmp_path / "green_mask.tif"
    transform = _write_mask(path, array)
    region = _region_covering_raster(transform, 10, 10)

    ratio = zonal_green_ratio(str(path), region.geom)

    assert ratio == pytest.approx(0.5, abs=0.05)


def test_zonal_green_ratio_all_nodata_returns_zero(tmp_path):
    array = np.full((10, 10), MASK_NODATA, dtype=np.uint8)
    path = tmp_path / "green_mask.tif"
    transform = _write_mask(path, array)
    region = _region_covering_raster(transform, 10, 10, region_code="98")

    ratio = zonal_green_ratio(str(path), region.geom)

    assert ratio == 0.0


def test_zonal_green_ratio_all_green_returns_one(tmp_path):
    array = np.ones((10, 10), dtype=np.uint8)
    path = tmp_path / "green_mask.tif"
    transform = _write_mask(path, array)
    region = _region_covering_raster(transform, 10, 10, region_code="97")

    ratio = zonal_green_ratio(str(path), region.geom)

    assert ratio == pytest.approx(1.0, abs=0.01)
