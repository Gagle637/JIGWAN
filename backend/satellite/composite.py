"""계절 합성: SCL 재마스킹 → 장면별 NDVI·NDBI·RGB → 화소별 중앙값 → green_mask (spec 3-3)."""
import json
import logging
import warnings
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features
from django.conf import settings
from django.contrib.gis.geos import Polygon
from django.db import transaction
from django.utils import timezone

from buildings.models import Region
from core.areas import get_bbox, get_grid

from .cog import grid_transform, iter_grid_blocks, open_cog_writer
from .index_scaling import INDEX_NODATA, MASK_NODATA, encode_mask, scale_index_to_int16
from .ingest import REFLECTANCE_BANDS
from .models import RasterProduct, SatelliteScene
from .reflectance import reflectance_to_uint16, uint16_to_reflectance
from .scl import usable_mask
from .seasons import parse_season

logger = logging.getLogger(__name__)

MIN_OBSERVATIONS = 3
GREEN_NDVI_THRESHOLD = 0.4
ALGO_VERSION = "green_v1"
BAND_INDEX = {name: i for i, name in enumerate(REFLECTANCE_BANDS)}


def mask_scene_reflectance(
    reflectance_bands: dict[str, np.ndarray], scl: np.ndarray
) -> dict[str, np.ndarray]:
    """SCL 사용 불가 화소를 각 반사율 밴드에서 NaN으로(spec 2-3 규칙을 합성 때 다시 적용)."""
    unusable = ~usable_mask(scl)
    masked = {}
    for name, array in reflectance_bands.items():
        arr = array.copy()
        arr[unusable] = np.nan
        masked[name] = arr
    return masked


def compute_ndvi(b08: np.ndarray, b04: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (b08 - b04) / (b08 + b04)
    return ndvi.astype(np.float32)


def compute_ndbi(b11: np.ndarray, b08: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        ndbi = (b11 - b08) / (b11 + b08)
    return ndbi.astype(np.float32)


def median_with_min_observations(stack: np.ndarray, min_obs: int = MIN_OBSERVATIONS) -> np.ndarray:
    """stack: (N,H,W), NaN=nodata. 유효 개수<min_obs인 화소는 NaN(spec 3-3)."""
    valid_count = np.sum(~np.isnan(stack), axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        median = np.nanmedian(stack, axis=0)
    return np.where(valid_count >= min_obs, median, np.nan).astype(np.float32)


def _read_scene_block(refl_ds, scl_ds, window) -> dict[str, np.ndarray]:
    refl_block = refl_ds.read(window=window)
    scl_block = scl_ds.read(1, window=window)
    bands = {
        name: uint16_to_reflectance(refl_block[BAND_INDEX[name]]) for name in REFLECTANCE_BANDS
    }
    return mask_scene_reflectance(bands, scl_block)


def _sido_inside_mask(grid: dict, sido_code: str) -> np.ndarray:
    """격자 전체 크기의 bool 배열(True=그 시도 경계 안) — 격자에는 500m 여유가 있어 이웃
    지역과 겹치므로(대전·세종처럼 실제로 맞닿은 경우), 경계 밖 화소를 nodata로 잘라내는 데
    쓴다(다지역 지원 5단계) — 안 그러면 반경 통계가 경계 근처에서 이중 계산된다."""
    region = Region.objects.filter(level="sido", region_code=sido_code).first()
    if region is None:
        raise ValueError(
            f"region(level=sido, region_code={sido_code})이 없습니다 — load_regions를 먼저 실행하세요."
        )
    geom_32652 = region.geom.transform(32652, clone=True)
    geom_mapping = json.loads(geom_32652.geojson)
    return rasterio.features.geometry_mask(
        [geom_mapping],
        out_shape=(grid["height"], grid["width"]),
        transform=grid_transform(grid),
        invert=True,
    )


def _dedupe_scenes_by_cog_path(scenes: list[SatelliteScene]) -> list[SatelliteScene]:
    """같은 cog_path를 공유하는 장면(2타일 병합, 결정 사항 11)은 물리적으로 한 파일이므로
    한 번만 읽는다 — 안 그러면 관측 수(median_with_min_observations 기준)가 중복으로
    두 배 집계된다. RasterProduct.scene_ids 기록(보존 정책·추적용)은 이 중복 제거와
    별개로 원본 scenes 전부를 그대로 쓴다(run_season_composite 참고)."""
    seen_cog_paths: set[str] = set()
    deduped = []
    for scene in scenes:
        if scene.cog_path in seen_cog_paths:
            continue
        seen_cog_paths.add(scene.cog_path)
        deduped.append(scene)
    return deduped


def build_season_composite(
    scenes: list[SatelliteScene], year: int, season: str, grid: dict, sido_code: str
) -> dict:
    """장면 목록을 512×512 블록 단위로 읽어 ndvi·ndbi·green_mask·truecolor COG를 만든다
    (결정 사항 8-2 — 전체 스택을 메모리에 올리지 않는다). sido_code 경계 밖 화소는
    nodata로 자른다(다지역 지원 5단계, _sido_inside_mask 참고)."""
    if not scenes:
        raise ValueError("합성할 장면이 없습니다(status=ready 장면 0건).")

    unique_scenes = _dedupe_scenes_by_cog_path(scenes)
    inside_mask = _sido_inside_mask(grid, sido_code)

    out_dir = Path(settings.RESULT_COG_DIR)
    base = f"{sido_code}_{year}_{season}_{ALGO_VERSION}"
    paths = {
        "ndvi": out_dir / f"{base}_ndvi.tif",
        "ndbi": out_dir / f"{base}_ndbi.tif",
        "green_mask": out_dir / f"{base}_green_mask.tif",
        "truecolor": out_dir / f"{base}_truecolor.tif",
    }

    reflectance_datasets = [rasterio.open(s.cog_path) for s in unique_scenes]
    scl_datasets = [rasterio.open(s.scl_cog_path) for s in unique_scenes]

    total_pixels = 0
    valid_pixels = {"ndvi": 0, "ndbi": 0, "green_mask": 0, "truecolor": 0}

    try:
        with open_cog_writer(
            paths["ndvi"], 1, "int16", INDEX_NODATA, grid=grid
        ) as ndvi_dst, open_cog_writer(
            paths["ndbi"], 1, "int16", INDEX_NODATA, grid=grid
        ) as ndbi_dst, open_cog_writer(
            paths["green_mask"], 1, "uint8", MASK_NODATA, grid=grid
        ) as green_dst, open_cog_writer(
            paths["truecolor"], 3, "uint16", 0, grid=grid, band_names=["B04", "B03", "B02"]
        ) as rgb_dst:
            for window in iter_grid_blocks(grid):
                ndvi_stack = []
                ndbi_stack = []
                rgb_stacks = {"B04": [], "B03": [], "B02": []}

                for refl_ds, scl_ds in zip(reflectance_datasets, scl_datasets):
                    masked = _read_scene_block(refl_ds, scl_ds, window)
                    ndvi_stack.append(compute_ndvi(masked["B08"], masked["B04"]))
                    ndbi_stack.append(compute_ndbi(masked["B11"], masked["B08"]))
                    for name in ("B04", "B03", "B02"):
                        rgb_stacks[name].append(masked[name])

                ndvi_block = median_with_min_observations(np.stack(ndvi_stack, axis=0))
                ndbi_block = median_with_min_observations(np.stack(ndbi_stack, axis=0))
                green_valid = ~np.isnan(ndvi_block)
                green_block = (ndvi_block >= GREEN_NDVI_THRESHOLD) & green_valid

                rgb_block = np.stack(
                    [
                        median_with_min_observations(np.stack(rgb_stacks[name], axis=0))
                        for name in ("B04", "B03", "B02")
                    ],
                    axis=0,
                )

                outside = ~inside_mask[
                    window.row_off : window.row_off + window.height,
                    window.col_off : window.col_off + window.width,
                ]
                ndvi_block[outside] = np.nan
                ndbi_block[outside] = np.nan
                green_valid[outside] = False
                rgb_block[:, outside] = np.nan

                ndvi_dst.write(scale_index_to_int16(ndvi_block), 1, window=window)
                ndbi_dst.write(scale_index_to_int16(ndbi_block), 1, window=window)
                green_dst.write(encode_mask(green_block, valid=green_valid), 1, window=window)
                for i in range(3):
                    rgb_dst.write(reflectance_to_uint16(rgb_block[i]), i + 1, window=window)

                total_pixels += window.width * window.height
                valid_pixels["ndvi"] += int(np.count_nonzero(~np.isnan(ndvi_block)))
                valid_pixels["ndbi"] += int(np.count_nonzero(~np.isnan(ndbi_block)))
                valid_pixels["green_mask"] += int(np.count_nonzero(green_valid))
                valid_pixels["truecolor"] += int(np.count_nonzero(~np.isnan(rgb_block[0])))
    finally:
        for ds in reflectance_datasets + scl_datasets:
            ds.close()

    valid_ratio = {
        key: (count / total_pixels if total_pixels else 0.0) for key, count in valid_pixels.items()
    }
    return {
        "paths": {key: str(value) for key, value in paths.items()},
        "scene_ids": [scene.scene_id for scene in scenes],
        "valid_ratio": valid_ratio,
    }


def _check_scene_files_or_flag_for_recollection(
    scenes: list[SatelliteScene], year: int, season: str, sido_code: str
) -> None:
    """합성 직전에 cog_path·scl_cog_path가 실제로 존재하는지 확인한다. 하나라도 없으면
    (예: 90일 정리로 지워진 뒤 그 계절을 다시 합성하려는 경우) 조용히 빠뜨리거나 어느
    장면 때문인지 알 수 없는 rasterio 예외로 죽는 대신, 그 장면들을 status=listed로
    되돌려 다음 collect_scenes가 자동으로 다시 받게 표시하고 바로 멈춘다. 정기 수집
    (satellite_collect, 30일 lookback)은 오래된 날짜를 다시 안 보므로 수동 재수집이
    필요하다는 것까지 에러 메시지에 명시한다."""
    missing = [
        scene
        for scene in scenes
        if not scene.cog_path
        or not scene.scl_cog_path
        or not Path(scene.cog_path).exists()
        or not Path(scene.scl_cog_path).exists()
    ]
    if not missing:
        return

    SatelliteScene.objects.filter(id__in=[scene.id for scene in missing]).update(
        status=SatelliteScene.Status.LISTED, cog_path=None, scl_cog_path=None
    )
    missing_ids = [scene.scene_id for scene in missing]
    logger.error(
        "season_composite 중단: 파일 없는 ready 장면 %s개를 listed로 되돌림 scene_id=%s",
        len(missing),
        missing_ids,
    )
    raise RuntimeError(
        f"{sido_code} {year}-{season} 합성을 멈췄습니다 — 장면 파일이 없습니다: {missing_ids}. "
        f"해당 장면을 재수집하도록 status=listed로 되돌려놨습니다. 정기 수집은 최근 30일만 "
        f"보므로 자동으로 다시 받히지 않습니다 — 아래 순서로 복구하세요:\n"
        f"  python manage.py collect_scenes --season {year}-{season} --sido {sido_code}\n"
        f"  python manage.py run_season_chain --season {year}-{season} --sido {sido_code}"
    )


def run_season_composite(year: int, season: str, sido_code: str) -> dict:
    """status=ready 장면만 모아 합성하고, raster_product 4행(ndvi·ndbi·green_mask·truecolor)을
    "교체"(같은 product_type·year·season·algo_version 삭제 후 재생성)로 등록한다(spec 5-2).
    sido_code(다지역 지원 2단계)로 격자·bbox를 정한다."""
    period_start, period_end = parse_season(f"{year}-{season}")
    scenes = list(
        SatelliteScene.objects.filter(
            region_code=sido_code,
            status=SatelliteScene.Status.READY,
            sensed_at__date__gte=period_start,
            sensed_at__date__lte=period_end,
        )
    )

    _check_scene_files_or_flag_for_recollection(scenes, year, season, sido_code)

    grid = get_grid(sido_code)
    result = build_season_composite(scenes, year, season, grid=grid, sido_code=sido_code)
    bbox = Polygon.from_bbox(get_bbox(sido_code))
    bbox.srid = 4326

    product_types = ["ndvi", "ndbi", "green_mask", "truecolor"]
    composited_at = timezone.now()
    with transaction.atomic():
        RasterProduct.objects.filter(
            region_code=sido_code,
            product_type__in=product_types,
            year=year,
            season=season,
            algo_version=ALGO_VERSION,
        ).delete()

        for product_type in product_types:
            RasterProduct.objects.create(
                region_code=sido_code,
                product_type=product_type,
                year=year,
                season=season,
                period_start=period_start,
                period_end=period_end,
                bbox=bbox,
                cog_path=result["paths"][product_type],
                algo_version=ALGO_VERSION,
                scene_ids=result["scene_ids"],
                valid_ratio=result["valid_ratio"][product_type],
                is_published=False,
                composited_at=composited_at,
            )

    logger.info(
        "season_composite year=%s season=%s scenes=%s valid_ratio=%s",
        year, season, len(scenes), result["valid_ratio"],
    )
    return result
