"""구·시 평균 녹지율(지역 기준선, plan.md 8-2)."""
import json
import logging

import numpy as np
import rasterio
import rasterio.mask
from django.db import transaction

from buildings.models import Region

from .composite import ALGO_VERSION
from .index_scaling import MASK_NODATA
from .models import RasterProduct, RegionStat

logger = logging.getLogger(__name__)

REGION_LEVELS = ["sido", "sigungu"]  # "시"·"구" 두 레벨만(결정 사항 10)


def zonal_green_ratio(green_mask_path: str, region_geom_4326) -> float:
    """region_geom_4326(GEOSGeometry, 4326)을 32652로 변환한 뒤 rasterio.mask로 녹지 비율을
    구한다(결정 사항 8-3 — 4326 지오메트리를 32652 래스터에 그대로 마스킹하면 좌표가 안 맞는다)."""
    geom_32652 = region_geom_4326.transform(32652, clone=True)
    geom_mapping = json.loads(geom_32652.geojson)

    with rasterio.open(green_mask_path) as ds:
        data, _ = rasterio.mask.mask(ds, [geom_mapping], crop=True)

    band = data[0]
    valid = band != MASK_NODATA
    valid_count = int(np.count_nonzero(valid))
    if valid_count == 0:
        return 0.0
    green_count = int(np.count_nonzero((band == 1) & valid))
    return green_count / valid_count


def run_region_stat(year: int, season: str) -> dict:
    """green_mask COG가 이미 있어야 한다(season_composite 먼저 실행). region이 비어 있으면
    0건으로 끝난다(4단계 load_regions가 먼저 돌아 있어야 의미가 있음 — 알려진 한계)."""
    product = RasterProduct.objects.filter(
        product_type="green_mask", year=year, season=season, algo_version=ALGO_VERSION
    ).first()
    if product is None:
        raise ValueError(f"{year} {season} green_mask가 아직 없습니다(season_composite 먼저 필요).")

    regions = list(Region.objects.filter(level__in=REGION_LEVELS))
    created = 0
    with transaction.atomic():
        RegionStat.objects.filter(product=product).delete()
        for region in regions:
            ratio = zonal_green_ratio(product.cog_path, region.geom)
            RegionStat.objects.create(region=region, product=product, green_ratio=ratio)
            created += 1

    logger.info("region_stat year=%s season=%s regions=%s", year, season, created)
    return {"regions": created}
