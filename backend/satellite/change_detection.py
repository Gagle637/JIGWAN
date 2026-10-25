"""변화 감지: ΔNDBI·ΔNDVI 후보 → 8방향 연결 10화소 미만 제거 → 폴리곤화(spec 3-4·5-4)."""
import logging

import numpy as np
import rasterio
from django.contrib.gis.geos import GEOSGeometry
from django.db import transaction
from rasterio.features import shapes
from rasterio.warp import transform_geom
from scipy import ndimage

from core.areas import get_grid

from .cog import open_cog_writer
from .composite import ALGO_VERSION
from .index_scaling import MASK_NODATA, int16_to_index
from .models import ChangeArea, RasterProduct

logger = logging.getLogger(__name__)

DELTA_NDBI_THRESHOLD = 0.1
DELTA_NDVI_THRESHOLD = -0.15
MIN_CHANGE_PIXELS = 10  # 8방향 연결 10화소(0.1ha) 미만 제거(spec 3-4)
CONNECTIVITY_8 = np.ones((3, 3), dtype=int)
COMPARE_PERIODS = ["1y", "2y", "3y"]


def detect_change(
    current_ndvi: np.ndarray,
    current_ndbi: np.ndarray,
    past_ndvi: np.ndarray,
    past_ndbi: np.ndarray,
) -> np.ndarray:
    """ΔNDBI>0.1 and ΔNDVI<-0.15 후보 → 8방향 연결 10화소 미만 제거 → bool mask(spec 3-4)."""
    delta_ndbi = current_ndbi - past_ndbi
    delta_ndvi = current_ndvi - past_ndvi
    valid = ~(
        np.isnan(current_ndvi) | np.isnan(current_ndbi) | np.isnan(past_ndvi) | np.isnan(past_ndbi)
    )
    candidate = valid & (delta_ndbi > DELTA_NDBI_THRESHOLD) & (delta_ndvi < DELTA_NDVI_THRESHOLD)

    labeled, num_features = ndimage.label(candidate, structure=CONNECTIVITY_8)
    if num_features == 0:
        return candidate

    sizes = ndimage.sum(candidate, labeled, index=range(1, num_features + 1))
    small_labels = [i + 1 for i, size in enumerate(sizes) if size < MIN_CHANGE_PIXELS]
    mask = candidate.copy()
    if small_labels:
        mask[np.isin(labeled, small_labels)] = False
    return mask


def vectorize_change(
    mask: np.ndarray, transform, delta_ndbi: np.ndarray, delta_ndvi: np.ndarray, src_crs="EPSG:32652"
) -> list[dict]:
    """연결 요소별로 폴리곤화(4326) + 면적·평균 ΔNDBI·ΔNDVI를 담은 dict 목록을 만든다."""
    results = []
    labeled, num_features = ndimage.label(mask, structure=CONNECTIVITY_8)
    pixel_area_m2 = abs(transform.a * transform.e)

    for feature_id in range(1, num_features + 1):
        region_mask = labeled == feature_id
        if not region_mask.any():
            continue

        polygons = [
            geom
            for geom, value in shapes(
                region_mask.astype(np.uint8), mask=region_mask, transform=transform
            )
            if value == 1
        ]
        if not polygons:
            continue

        geom_4326 = transform_geom(src_crs, "EPSG:4326", polygons[0])
        area_m2 = float(region_mask.sum()) * pixel_area_m2

        results.append(
            {
                "geom": geom_4326,
                "area_m2": area_m2,
                "delta_ndbi": float(np.nanmean(delta_ndbi[region_mask])),
                "delta_ndvi": float(np.nanmean(delta_ndvi[region_mask])),
            }
        )
    return results


def _load_index(product: RasterProduct) -> tuple[np.ndarray, object]:
    with rasterio.open(product.cog_path) as ds:
        return int16_to_index(ds.read(1)), ds.transform


def run_change_analysis(year: int, season: str, sido_code: str = "30") -> dict:
    """같은 계절 1·2·3년 전 대비 변화 마스크·폴리곤을 만든다. 과거 비교 대상은 "있는 것만"
    (이미 게시된 것만) 쓴다(spec 5-4). 현재 계절은 이번 체인에서 막 만든 것(아직 미게시)을 쓴다.
    sido_code(다지역 지원 5단계)로 조회·저장을 그 지역 raster_product로 좁힌다 — 안 그러면
    다른 지역의 같은 연/계절 산물을 잘못 집어 쓰거나 지워버릴 수 있다."""
    algo_version = ALGO_VERSION
    grid = get_grid(sido_code)

    current_ndvi_product = RasterProduct.objects.filter(
        region_code=sido_code, product_type="ndvi", year=year, season=season,
        algo_version=algo_version,
    ).first()
    current_ndbi_product = RasterProduct.objects.filter(
        region_code=sido_code, product_type="ndbi", year=year, season=season,
        algo_version=algo_version,
    ).first()
    if current_ndvi_product is None or current_ndbi_product is None:
        raise ValueError(f"{year} {season} ndvi/ndbi가 아직 없습니다(season_composite 먼저 필요).")

    current_ndvi, transform = _load_index(current_ndvi_product)
    current_ndbi, _ = _load_index(current_ndbi_product)

    processed_periods = []
    for offset, period in zip((1, 2, 3), COMPARE_PERIODS):
        past_year = year - offset
        past_ndvi_product = RasterProduct.objects.filter(
            region_code=sido_code,
            product_type="ndvi",
            year=past_year,
            season=season,
            algo_version=algo_version,
            is_published=True,
        ).first()
        past_ndbi_product = RasterProduct.objects.filter(
            region_code=sido_code,
            product_type="ndbi",
            year=past_year,
            season=season,
            algo_version=algo_version,
            is_published=True,
        ).first()
        if past_ndvi_product is None or past_ndbi_product is None:
            continue  # spec 5-4: "있는 것만"

        past_ndvi, _ = _load_index(past_ndvi_product)
        past_ndbi, _ = _load_index(past_ndbi_product)

        mask = detect_change(current_ndvi, current_ndbi, past_ndvi, past_ndbi)
        delta_ndbi = current_ndbi - past_ndbi
        delta_ndvi = current_ndvi - past_ndvi
        areas = vectorize_change(mask, transform, delta_ndbi, delta_ndvi)

        out_path = (
            current_ndvi_product.cog_path.rsplit("_ndvi.tif", 1)[0] + f"_change_mask_{period}.tif"
        )
        with open_cog_writer(out_path, 1, "uint8", MASK_NODATA, grid=grid) as dst:
            encoded = np.where(
                np.isnan(current_ndvi) | np.isnan(past_ndvi), MASK_NODATA, mask.astype(np.uint8)
            )
            dst.write(encoded.astype(np.uint8), 1)

        valid_mask = ~(np.isnan(current_ndvi) | np.isnan(past_ndvi))
        valid_ratio = float(valid_mask.sum() / valid_mask.size) if valid_mask.size else 0.0

        with transaction.atomic():
            RasterProduct.objects.filter(
                region_code=sido_code,
                product_type="change_mask",
                year=year,
                season=season,
                algo_version=algo_version,
                compare_period=period,
            ).delete()

            product = RasterProduct.objects.create(
                region_code=sido_code,
                product_type="change_mask",
                year=year,
                season=season,
                period_start=current_ndvi_product.period_start,
                period_end=current_ndvi_product.period_end,
                compare_period=period,
                bbox=current_ndvi_product.bbox,
                cog_path=out_path,
                algo_version=algo_version,
                scene_ids=current_ndvi_product.scene_ids,
                valid_ratio=valid_ratio,
                is_published=False,
            )
            for area in areas:
                ChangeArea.objects.create(
                    product=product,
                    period=period,
                    area_m2=area["area_m2"],
                    delta_ndbi=area["delta_ndbi"],
                    delta_ndvi=area["delta_ndvi"],
                    geom=GEOSGeometry(_to_wkt(area["geom"]), srid=4326),
                )

        processed_periods.append({"period": period, "areas": len(areas)})
        logger.info(
            "change_analysis year=%s season=%s period=%s areas=%s", year, season, period, len(areas)
        )

    return {"processed_periods": processed_periods}


def _to_wkt(geojson_geom: dict) -> str:
    from shapely.geometry import shape

    return shape(geojson_geom).wkt
