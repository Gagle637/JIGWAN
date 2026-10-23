"""조회 시 반경 통계(spec 3-2) — insight.green·insight.change의 백엔드."""
import json
import logging

import numpy as np
import rasterio
import rasterio.mask
from django.contrib.gis.geos import GEOSGeometry
from django.db import connection
from rasterio.features import geometry_mask

from buildings.radius_sql import building_radius_buffers
from layers.tile_params import TRUECOLOR_TILE_PARAMS, build_titiler_url

from .composite import ALGO_VERSION
from .index_scaling import MASK_NODATA
from .models import RasterProduct, RegionStat

logger = logging.getLogger(__name__)

MIN_VALID_RATIO_FOR_RATIO = 0.5  # spec 5-3: 유효 픽셀<50%면 insufficient_data
MAX_SERIES_LENGTH = 13  # spec 5-2: 최신 계절 + 최근 3년 13개 계절
COMPARE_PERIODS = ["1y", "2y", "3y"]
_SEASON_ORDER = {"spring": 0, "summer": 1, "fall": 2, "winter": 3}

# GEOS 3.9.0(PostGIS 3.4.3이 쓰는 버전)의 OverlayNG가 한 지오메트리가 다른 지오메트리에
# 완전히 포함되는(경계를 안 건너는) 경우 ST_Intersection을 빈 지오메트리로 돌리는 버그가 있다
# (crime/radius_stats.py에서 실측 확인됨). 3번째 인자로 gridSize를 주면 안정적인
# FixedPrecision 오버레이 경로를 타 정확한 결과가 나온다.
_OVERLAY_GRID_SIZE_DEG = 0.0000001  # 약 1cm — 면적(㎡) 계산에 영향 없는 정밀도

_CHANGE_AREA_SQL = """
SELECT
    ca.id,
    ca.period,
    ST_Area(
        ST_Intersection(
            ca.geom, ST_SetSRID(ST_GeomFromGeoJSON(%(buffer)s), 4326), %(grid_size)s
        )::geography
    ) AS area_within_radius_m2,
    ST_Distance(b.geom::geography, ca.geom::geography) AS distance_m,
    ST_AsGeoJSON(ca.geom) AS geometry
FROM change_area ca
JOIN building b ON b.id = %(building_id)s
WHERE ca.product_id = ANY(%(product_ids)s)
  AND ST_Intersects(ca.geom, ST_SetSRID(ST_GeomFromGeoJSON(%(buffer)s), 4326))
"""


def catalog_product_ids(building, radius_m: int) -> list[int]:
    """캐시 키 계산용 가벼운 조회 — rasterio를 건드리지 않고 카탈로그 id만 모은다
    (buildings.insight.get_insight_cached가 쓴다, 결정 사항 7)."""
    buffers = building_radius_buffers(building.id, radius_m)
    ids = set()
    for product_type in ("green_mask", "truecolor", "change_mask"):
        ids.update(p.id for p in _search_catalog(product_type, buffers["buffer_4326"]))
    return sorted(ids)


def _search_catalog(product_type: str, buffer_4326_geojson: dict, limit: int = MAX_SERIES_LENGTH):
    buffer_geom = GEOSGeometry(json.dumps(buffer_4326_geojson), srid=4326)
    return list(
        RasterProduct.objects.filter(
            product_type=product_type,
            is_published=True,
            algo_version=ALGO_VERSION,
            bbox__intersects=buffer_geom,
        ).order_by("-period_start")[:limit]
    )


def _mask_counts(cog_path: str, buffer_32652_geojson: dict) -> tuple[int, int, int] | None:
    """(usable_count, valid_count, within_buffer_count), COG를 못 읽으면 None.

    spec 3-2: "반경 밖·nodata 픽셀을 빼고 통계를 낸다" — geometry_mask로 반경 안쪽 여부를,
    COG 자체 nodata로 유효 여부를 따로 구분해야 "반경 안 전체 화소"(coverage_pct 분모)를
    정확히 셀 수 있다(rasterio.mask.mask만 쓰면 반경 밖도 nodata로 채워져 구분이 안 됨).
    """
    try:
        with rasterio.open(cog_path) as ds:
            out_image, out_transform = rasterio.mask.mask(
                ds, [buffer_32652_geojson], crop=True, all_touched=False
            )
    except Exception as exc:  # noqa: BLE001 — 실데이터 없는 환경에서도 전체가 죽지 않게
        logger.warning("radius_stats: COG 읽기 실패 path=%s err=%s", cog_path, exc)
        return None

    band = out_image[0]
    inside = geometry_mask(
        [buffer_32652_geojson],
        out_shape=band.shape,
        transform=out_transform,
        invert=True,
        all_touched=False,
    )
    valid = inside & (band != MASK_NODATA)
    usable = inside & (band == 1)
    return (
        int(np.count_nonzero(usable)),
        int(np.count_nonzero(valid)),
        int(np.count_nonzero(inside)),
    )


def _lookup_region_avg(building, year: int, season: str) -> float | None:
    sigungu_code = (building.bjd_code or "")[:5]
    if not sigungu_code:
        return None
    stat = RegionStat.objects.filter(
        region_id=sigungu_code,
        product__year=year,
        product__season=season,
        product__product_type="green_mask",
        product__algo_version=ALGO_VERSION,
    ).first()
    return round(stat.green_ratio * 100, 1) if stat else None


def compute_green_stats(building, radius_m: int) -> dict | None:
    """spec 3-2·5-3. None이면 카탈로그에 게시된 green_mask가 전혀 없다는 뜻(= pending)."""
    buffers = building_radius_buffers(building.id, radius_m)
    products = _search_catalog("green_mask", buffers["buffer_4326"])
    if not products:
        return None

    by_period: dict[tuple[int, str], list[RasterProduct]] = {}
    for product in products:
        by_period.setdefault((product.year, product.season), []).append(product)

    series = []
    for (year, season), group in by_period.items():
        total_usable = total_valid = total_within = 0
        for product in group:
            counts = _mask_counts(product.cog_path, buffers["buffer_32652"])
            if counts is None:
                continue
            usable, valid, within = counts
            total_usable += usable
            total_valid += valid
            total_within += within

        coverage_pct = round(total_valid / total_within * 100, 1) if total_within else 0.0
        if total_within == 0 or (total_valid / total_within) < MIN_VALID_RATIO_FOR_RATIO:
            ratio_pct = None  # insufficient_data(spec 5-3)
        else:
            ratio_pct = round(total_usable / total_valid * 100, 1)

        series.append(
            {"year": year, "season": season, "ratio_pct": ratio_pct, "coverage_pct": coverage_pct}
        )

    series.sort(key=lambda item: (item["year"], _SEASON_ORDER[item["season"]]))
    latest = series[-1]

    region_avg_pct = _lookup_region_avg(building, latest["year"], latest["season"])
    ratio_pct = latest["ratio_pct"]
    diff_pp = (
        round(ratio_pct - region_avg_pct, 1)
        if ratio_pct is not None and region_avg_pct is not None
        else None
    )

    return {
        "ratio_pct": ratio_pct,
        "region_avg_pct": region_avg_pct,
        "diff_pp": diff_pp,
        "coverage_pct": latest["coverage_pct"],
        "series": series,
        "product_ids": [p.id for p in products],
    }


def _build_tiles(truecolor_products: list[RasterProduct]) -> dict:
    tiles = {"after": None, "before": {}, "default_compare": None}
    if not truecolor_products:
        return tiles

    current = truecolor_products[0]  # _search_catalog가 period_start DESC로 주므로 최신
    tiles["after"] = build_titiler_url(current.cog_path, TRUECOLOR_TILE_PARAMS)

    for offset, period in zip((1, 2, 3), COMPARE_PERIODS):
        past = next(
            (
                p
                for p in truecolor_products
                if p.year == current.year - offset and p.season == current.season
            ),
            None,
        )
        if past:
            tiles["before"][period] = build_titiler_url(past.cog_path, TRUECOLOR_TILE_PARAMS)

    for period in COMPARE_PERIODS:
        if period in tiles["before"]:
            tiles["default_compare"] = period
            break

    return tiles


def _change_areas_in_radius(building_id: int, buffer_4326_geojson: dict, product_ids: list[int]):
    if not product_ids:
        return []
    with connection.cursor() as cur:
        cur.execute(
            _CHANGE_AREA_SQL,
            {
                "buffer": json.dumps(buffer_4326_geojson),
                "building_id": building_id,
                "product_ids": product_ids,
                "grid_size": _OVERLAY_GRID_SIZE_DEG,
            },
        )
        columns = [col[0] for col in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def compute_change_stats(building, radius_m: int) -> dict | None:
    """spec 3-2·5-4. None이면 truecolor·change_mask 둘 다 카탈로그에 없다는 뜻(= pending)."""
    buffers = building_radius_buffers(building.id, radius_m)

    truecolor_products = _search_catalog("truecolor", buffers["buffer_4326"])
    change_products = _search_catalog("change_mask", buffers["buffer_4326"])

    if not truecolor_products and not change_products:
        return None

    tiles = _build_tiles(truecolor_products)

    change_product_ids = [p.id for p in change_products]
    rows = _change_areas_in_radius(building.id, buffers["buffer_4326"], change_product_ids)

    total_area_m2 = sum(row["area_within_radius_m2"] or 0.0 for row in rows)
    top_rows = sorted(rows, key=lambda r: r["area_within_radius_m2"] or 0.0, reverse=True)[:3]
    areas = [
        {
            "id": row["id"],
            "area_m2": round(row["area_within_radius_m2"], 1),
            "distance_m": round(row["distance_m"], 1),
            "period": row["period"],
            "geometry": json.loads(row["geometry"]),
        }
        for row in top_rows
    ]

    product_ids = [p.id for p in truecolor_products] + change_product_ids
    return {
        "total_area_m2": round(total_area_m2, 1),
        "areas": areas,
        "tiles": tiles,
        "product_ids": product_ids,
    }
