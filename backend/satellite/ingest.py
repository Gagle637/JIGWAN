"""한 날짜(1~2개 타일)를 받아 다운로드~반사율 변환~격자 합치기~COG 쓰기~DB 기록까지 처리한다."""
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from django.conf import settings
from rasterio.enums import Resampling

from .cdse_client import download_scene_files
from .cog import coalesce, reproject_band_to_grid, write_cog_atomic
from .models import SatelliteScene
from .mtd import parse_mtd
from .reflectance import dn_to_reflectance, reflectance_to_uint16
from .scl import MIN_VALID_RATIO, compute_valid_ratio
from .stac_search import processing_baseline, sensed_at, tile_code

REFLECTANCE_BANDS = ["B02", "B03", "B04", "B08", "B11"]
ASSET_KEY_FOR_BAND = {
    "B02": "B02_10m",
    "B03": "B03_10m",
    "B04": "B04_10m",
    "B08": "B08_10m",
    "B11": "B11_20m",
}


def _read_band(path) -> tuple[np.ndarray, object, object]:
    with rasterio.open(path) as ds:
        return ds.read(1), ds.transform, ds.crs


def _process_tile(local_paths: dict[str, Path], grid: dict) -> dict:
    """타일 하나를 그 타일 자신의 MTD 오프셋으로 반사율 변환 후 grid(지역별 고정 격자)에
    올린다(결정 사항 11 — 합치기 전에 타일별로 끝내야 함)."""
    mtd = parse_mtd(local_paths["MTD"])
    band_offsets = mtd["band_offsets"]
    quant_value = mtd["boa_quantification_value"]

    reflectance_bands_uint16 = []
    for band in REFLECTANCE_BANDS:
        dn, transform, crs = _read_band(local_paths[ASSET_KEY_FOR_BAND[band]])
        reflectance = dn_to_reflectance(dn, band_offsets.get(band, 0), quant_value)
        reflectance_grid = reproject_band_to_grid(
            reflectance, transform, crs, Resampling.bilinear, nodata=np.nan, grid=grid
        )
        reflectance_bands_uint16.append(reflectance_to_uint16(reflectance_grid))

    scl_dn, scl_transform, scl_crs = _read_band(local_paths["SCL_20m"])
    scl_grid = reproject_band_to_grid(
        scl_dn.astype(np.uint8), scl_transform, scl_crs, Resampling.nearest, nodata=0, grid=grid
    )

    return {"mtd": mtd, "reflectance_bands": reflectance_bands_uint16, "scl_grid": scl_grid}


def ingest_date_group(items_same_date: list, grid: dict) -> list[SatelliteScene]:
    """1~2개 타일(같은 날짜)을 처리해 SatelliteScene 행 목록을 돌려준다. grid는
    core.areas.get_grid(sido_code)(다지역 지원 2단계)."""
    tile_results = []
    with tempfile.TemporaryDirectory(prefix="satellite_") as tmp_dir:
        for item in items_same_date:
            local_paths = download_scene_files(item, Path(tmp_dir) / item.id)
            tile_results.append((item, _process_tile(local_paths, grid)))
        # with 블록이 끝나면 다운로드한 JP2·MTD xml이 전부 삭제된다(spec: "JP2는 변환 직후 삭제").

    merged_reflectance = np.stack(
        [
            coalesce(*(result["reflectance_bands"][i] for _, result in tile_results), nodata=0)
            for i in range(len(REFLECTANCE_BANDS))
        ],
        axis=0,
    )
    merged_scl = coalesce(*(result["scl_grid"] for _, result in tile_results), nodata=0)

    valid_ratio = compute_valid_ratio(merged_scl)
    status = (
        SatelliteScene.Status.READY
        if valid_ratio >= MIN_VALID_RATIO
        else SatelliteScene.Status.EXCLUDED
    )

    first_item = items_same_date[0]
    date_str = sensed_at(first_item).strftime("%Y%m%dT%H%M%S")
    tile_codes = "-".join(sorted({tile_code(item) for item in items_same_date}))
    base_name = f"{date_str}_{tile_codes}"
    cog_dir = Path(settings.SATELLITE_SCENE_COG_DIR)
    cog_path = cog_dir / f"{base_name}_REFL.tif"
    scl_cog_path = cog_dir / f"{base_name}_SCL.tif"

    write_cog_atomic(merged_reflectance, cog_path, nodata=0, grid=grid, band_names=REFLECTANCE_BANDS)
    write_cog_atomic(merged_scl, scl_cog_path, nodata=0, grid=grid)

    scenes = []
    for item, result in tile_results:
        # 백필 dry run이 미리 status=listed로 적어둔 행이 있을 수 있어 create 대신
        # update_or_create로 그 행을 ready/excluded로 올려 쓴다(4장).
        scene, _created = SatelliteScene.objects.update_or_create(
            scene_id=item.id,
            defaults={
                "sensed_at": sensed_at(item),
                "mgrs_tile": tile_code(item),
                "cloud_pct": item.properties.get("eo:cloud_cover", 0.0),
                "processing_baseline": processing_baseline(item),
                "band_offsets": result["mtd"]["band_offsets"],
                "boa_quantification_value": result["mtd"]["boa_quantification_value"],
                "valid_ratio": valid_ratio,
                "status": status,
                "cog_path": str(cog_path),
                "scl_cog_path": str(scl_cog_path),
            },
        )
        scenes.append(scene)
    return scenes
