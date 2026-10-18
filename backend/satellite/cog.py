"""DAEJEON_GRID로 reproject + 타일 합치기(coalesce) + 원자적 COG 쓰기(결정 사항 10·11·12)."""
import os
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import rasterio
from django.conf import settings
from rasterio.enums import Resampling
from rasterio.shutil import copy as _rio_copy
from rasterio.transform import Affine
from rasterio.warp import reproject
from rasterio.windows import Window

BLOCK_SIZE = 512


def grid_transform() -> Affine:
    grid = settings.DAEJEON_GRID
    return Affine(grid["resolution_m"], 0, grid["minx"], 0, -grid["resolution_m"], grid["maxy"])


def reproject_band_to_grid(
    source_array: np.ndarray,
    source_transform,
    source_crs,
    resampling: Resampling,
    nodata,
) -> np.ndarray:
    """타일 하나의 밴드 배열을 DAEJEON_GRID(고정 격자)로 reproject한다. 격자가 덮지 못하는
    칸은 nodata — 다음 단계(계절 합성)가 화소 정렬을 전제하므로 모든 장면이 같은
    transform·shape를 갖게 된다."""
    grid = settings.DAEJEON_GRID
    destination = np.full((grid["height"], grid["width"]), nodata, dtype=source_array.dtype)
    reproject(
        source=source_array,
        destination=destination,
        src_transform=source_transform,
        src_crs=source_crs,
        dst_transform=grid_transform(),
        dst_crs=grid["crs"],
        resampling=resampling,
        src_nodata=nodata,
        dst_nodata=nodata,
    )
    return destination


def coalesce(*grids: np.ndarray, nodata) -> np.ndarray:
    """여러 타일의 격자를 합친다 — 먼저 나온 것 중 유효한(=nodata가 아닌) 값을 채택한다.
    반사율·SCL 둘 다 nodata=0이라 같은 함수를 그대로 쓴다(결정 사항 12)."""
    merged = grids[0].copy()
    for grid in grids[1:]:
        missing = merged == nodata
        merged[missing] = grid[missing]
    return merged


def write_cog_atomic(
    data: np.ndarray, path, nodata, band_names: list[str] | None = None
) -> None:
    """임시 경로에 쓴 뒤 rename한다 — 중간에 죽어도 반쯤 쓴 COG가 안 남는다(CLAUDE.md 배치 규칙)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")

    grid = settings.DAEJEON_GRID
    count = 1 if data.ndim == 2 else data.shape[0]
    profile = {
        "driver": "COG",
        "dtype": data.dtype,
        "count": count,
        "width": grid["width"],
        "height": grid["height"],
        "crs": grid["crs"],
        "transform": grid_transform(),
        "nodata": nodata,
    }
    try:
        with rasterio.open(tmp_path, "w", **profile) as dst:
            if data.ndim == 2:
                dst.write(data, 1)
            else:
                for i in range(count):
                    dst.write(data[i], i + 1)
                    if band_names:
                        dst.set_band_description(i + 1, band_names[i])
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def iter_grid_blocks(block_size: int = BLOCK_SIZE):
    """DAEJEON_GRID를 block_size×block_size rasterio.windows.Window로 순회한다(결정 사항 8-2)."""
    grid = settings.DAEJEON_GRID
    for row_off in range(0, grid["height"], block_size):
        height = min(block_size, grid["height"] - row_off)
        for col_off in range(0, grid["width"], block_size):
            width = min(block_size, grid["width"] - col_off)
            yield Window(col_off, row_off, width, height)


@contextmanager
def open_cog_writer(path, count: int, dtype, nodata, band_names: list[str] | None = None):
    """블록 단위로 ``dst.write(data, window=...)``할 수 있는 COG 작성기를 연다.

    GDAL COG 드라이버는 CreateCopy 전용이라 증분 쓰기(Create)를 지원하지 않는다 — 그래서
    타일드 GTiff(블록 512×512, DEFLATE 압축)에 블록을 전부 쓴 뒤 닫고,
    ``rasterio.shutil.copy``로 COG를 만들어 최종 경로로 원자적 rename한다(write_cog_atomic과
    같은 "임시 경로에 쓴 뒤 rename" 원칙).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_tiff = path.with_name(path.name + ".tiled.tmp.tif")
    tmp_cog = path.with_name(path.name + ".tmp")

    grid = settings.DAEJEON_GRID
    profile = {
        "driver": "GTiff",
        "dtype": dtype,
        "count": count,
        "width": grid["width"],
        "height": grid["height"],
        "crs": grid["crs"],
        "transform": grid_transform(),
        "nodata": nodata,
        "tiled": True,
        "blockxsize": BLOCK_SIZE,
        "blockysize": BLOCK_SIZE,
        "compress": "DEFLATE",
    }

    dst = rasterio.open(tmp_tiff, "w", **profile)
    try:
        if band_names:
            for i, name in enumerate(band_names, start=1):
                dst.set_band_description(i, name)
        yield dst
    finally:
        dst.close()

    try:
        _rio_copy(str(tmp_tiff), str(tmp_cog), driver="COG", BLOCKSIZE=BLOCK_SIZE)
        os.replace(tmp_cog, path)
    finally:
        if tmp_tiff.exists():
            tmp_tiff.unlink()
        if tmp_cog.exists():
            tmp_cog.unlink()
