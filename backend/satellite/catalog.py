"""게시 검사(값 범위·격자 일치·유효비율) + is_published 반영(spec 5-3, 결정 사항 11)."""
import json
import logging

import numpy as np
import rasterio
import rasterio.mask
from rasterio.crs import CRS

from buildings.models import Region
from core.areas import get_grid
from layers.registry import sync_cog_layer

from .cog import grid_transform
from .composite import ALGO_VERSION
from .index_scaling import INDEX_NODATA, MASK_NODATA, int16_to_index
from .models import RasterProduct

logger = logging.getLogger(__name__)

VALID_RATIO_MIN = 0.10  # 장마철 여름 합성이 통째로 빠지지 않게 하려는 낮은 기준(사용자 확정)
INDEX_VALUE_EPS = 1e-6
INDEX_PRODUCT_TYPES = {"ndvi", "ndbi"}

NODATA_BY_PRODUCT_TYPE = {
    "ndvi": INDEX_NODATA,
    "ndbi": INDEX_NODATA,
    "green_mask": MASK_NODATA,
    "change_mask": MASK_NODATA,
    "truecolor": 0,
}


def _grid_matches(ds, grid: dict) -> bool:
    expected_crs = CRS.from_user_input(grid["crs"])
    return (
        ds.crs == expected_crs
        and ds.transform == grid_transform(grid)
        and ds.width == grid["width"]
        and ds.height == grid["height"]
    )


def _value_range_ok(ds, nodata) -> bool:
    data = ds.read(1)
    valid = data != nodata
    if not valid.any():
        return True  # 유효 화소가 없으면 범위를 벗어날 수 없다 — 유효비율 검사가 따로 걸러낸다
    values = int16_to_index(data[valid])
    return bool(np.all((values >= -1 - INDEX_VALUE_EPS) & (values <= 1 + INDEX_VALUE_EPS)))


def _region_aoi_32652(sido_code: str):
    """지역 경계(Region sido=sido_code)가 있으면 그 지오메트리를 32652로 변환해 돌려준다.
    없으면 None — 호출부가 전체 격자를 그대로 쓴다(결정 사항 11)."""
    region = Region.objects.filter(level="sido", region_code=sido_code).first()
    if region is None:
        return None
    return region.geom.transform(32652, clone=True)


def _measure_valid_ratio(ds, nodata, sido_code: str) -> float:
    aoi = _region_aoi_32652(sido_code)
    if aoi is not None:
        geom_mapping = json.loads(aoi.geojson)
        data, _ = rasterio.mask.mask(ds, [geom_mapping], crop=True)
        band = data[0]
    else:
        band = ds.read(1)

    if band.size == 0:
        return 0.0
    valid = band != nodata
    return float(np.count_nonzero(valid) / band.size)


def validate_and_publish(product: RasterProduct, sido_code: str = "30") -> bool:
    """결정 사항 11의 세 검사(격자 일치·값 범위·유효 비율)를 수행하고, 전부 통과하면
    is_published=True로 저장한다. valid_ratio는 통과 여부와 무관하게 측정값을 그대로 기록한다.
    sido_code(다지역 지원 2단계)로 비교할 격자·AOI를 정한다."""
    nodata = NODATA_BY_PRODUCT_TYPE[product.product_type]
    grid = get_grid(sido_code)

    with rasterio.open(product.cog_path) as ds:
        if not _grid_matches(ds, grid):
            logger.warning(
                "catalog_publish grid mismatch id=%s path=%s", product.id, product.cog_path
            )
            product.is_published = False
            product.save(update_fields=["is_published"])
            return False

        if product.product_type in INDEX_PRODUCT_TYPES and not _value_range_ok(ds, nodata):
            logger.warning("catalog_publish value range violation id=%s", product.id)
            product.is_published = False
            product.save(update_fields=["is_published"])
            return False

        valid_ratio = _measure_valid_ratio(ds, nodata, sido_code)

    product.valid_ratio = valid_ratio
    passed = valid_ratio >= VALID_RATIO_MIN
    product.is_published = passed
    product.save(update_fields=["valid_ratio", "is_published"])

    if passed:
        sync_cog_layer(product)

    return passed


def run_catalog_publish(year: int, season: str, sido_code: str = "30") -> dict:
    """이번 체인 실행에서 만들어진(아직 미게시) product들을 전부 독립적으로 검사·게시한다.
    sido_code(다지역 지원 5단계)로 후보를 그 지역 raster_product로 좁힌다 — 안 그러면 다른
    지역의 미게시 product까지 같이 검사·게시해버린다."""
    candidates = RasterProduct.objects.filter(
        region_code=sido_code, year=year, season=season, algo_version=ALGO_VERSION,
        is_published=False,
    )
    published = 0
    rejected = 0
    for product in candidates:
        if validate_and_publish(product, sido_code):
            published += 1
        else:
            rejected += 1

    logger.info(
        "catalog_publish year=%s season=%s published=%s rejected=%s",
        year, season, published, rejected,
    )
    return {"published": published, "rejected": rejected}
