import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.windows import Window

from satellite.cog import (
    coalesce,
    grid_transform,
    iter_grid_blocks,
    open_cog_writer,
    reproject_band_to_grid,
    write_cog_atomic,
)

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


def test_grid_transform_matches_grid():
    transform = grid_transform(_GRID)
    assert transform.a == _GRID["resolution_m"]
    assert transform.e == -_GRID["resolution_m"]
    assert transform.c == _GRID["minx"]
    assert transform.f == _GRID["maxy"]


def test_reproject_band_to_grid_output_shape_matches_grid():
    grid = _GRID
    src_res = 1000  # 빠른 테스트를 위해 훨씬 큰 픽셀의 가짜 소스
    src_width = int((grid["maxx"] - grid["minx"]) / src_res) + 1
    src_height = int((grid["maxy"] - grid["miny"]) / src_res) + 1
    src_transform = Affine(src_res, 0, grid["minx"], 0, -src_res, grid["maxy"])
    src_array = np.full((src_height, src_width), 5000, dtype=np.uint16)

    result = reproject_band_to_grid(
        src_array, src_transform, grid["crs"], Resampling.bilinear, nodata=0, grid=grid
    )

    assert result.shape == (grid["height"], grid["width"])


def test_two_scene_cogs_share_identical_transform_and_shape(tmp_path):
    """다음 단계(계절 합성)가 화소 정렬을 전제하므로, 서로 다른 장면의 COG도 transform·shape가
    완전히 같아야 한다(6단계 플랜 결정 사항 10)."""
    grid = _GRID
    data_a = np.full((1, grid["height"], grid["width"]), 1234, dtype=np.uint16)
    data_b = np.full((1, grid["height"], grid["width"]), 5678, dtype=np.uint16)

    path_a = tmp_path / "scene_a.tif"
    path_b = tmp_path / "scene_b.tif"
    write_cog_atomic(data_a, path_a, nodata=0, grid=grid)
    write_cog_atomic(data_b, path_b, nodata=0, grid=grid)

    with rasterio.open(path_a) as ds_a, rasterio.open(path_b) as ds_b:
        assert ds_a.transform == ds_b.transform
        assert ds_a.shape == ds_b.shape
        assert ds_a.crs == ds_b.crs


def test_write_cog_atomic_leaves_no_tmp_file(tmp_path):
    grid = _GRID
    data = np.zeros((grid["height"], grid["width"]), dtype=np.uint8)
    path = tmp_path / "scl.tif"

    write_cog_atomic(data, path, nodata=0, grid=grid)

    assert path.exists()
    assert not path.with_name(path.name + ".tmp").exists()


def test_coalesce_prefers_first_nonzero_value():
    a = np.array([0, 5, 0, 7])
    b = np.array([1, 2, 0, 9])
    merged = coalesce(a, b, nodata=0)
    # 첫 유효값(스택 순서상 앞쪽 배열) 우선: pos0(a=0=nodata)->b=1, pos1(a=5)->a=5,
    # pos2(둘 다 0=nodata)->0, pos3(a=7, 유효)->a=7(뒤에 있는 b=9는 안 씀).
    assert list(merged) == [1, 5, 0, 7]


def test_iter_grid_blocks_covers_grid_without_overlap():
    grid = {
        "crs": "EPSG:32652", "resolution_m": 10,
        "minx": 0, "miny": 0, "maxx": 2500, "maxy": 2500,
        "width": 25, "height": 25,
    }
    windows = list(iter_grid_blocks(grid, block_size=10))
    # 25를 10단위로 쪼개면 3x3=9개(10,10,5 x 10,10,5)
    assert len(windows) == 9
    total_pixels = sum(w.width * w.height for w in windows)
    assert total_pixels == 25 * 25


def test_open_cog_writer_blocks_do_not_bleed_and_result_is_a_real_cog(tmp_path):
    """GDAL COG 드라이버는 CreateCopy 전용이라 open_cog_writer가 타일드 GTiff에 블록을 쓴 뒤
    COG로 복사해야 한다(7단계 결정 사항) — 결과 파일이 실제로 타일·오버뷰를 갖는 COG인지,
    블록끼리 값이 안 섞이는지 확인한다."""
    size = 2048  # 오버뷰가 실제로 생기도록 블록(512)보다 충분히 크게
    grid = {
        "crs": "EPSG:32652", "resolution_m": 10,
        "minx": 300000, "miny": 4000000,
        "maxx": 300000 + size * 10, "maxy": 4000000 + size * 10,
        "width": size, "height": size,
    }
    path = tmp_path / "block_write.tif"

    with open_cog_writer(path, count=1, dtype="uint8", nodata=0, grid=grid) as dst:
        for i, window in enumerate(iter_grid_blocks(grid, block_size=512)):
            value = (i % 200) + 1  # 0(=nodata)과 겹치지 않게
            block = np.full((window.height, window.width), value, dtype=np.uint8)
            dst.write(block, 1, window=window)

    assert path.exists()
    assert not path.with_name(path.name + ".tmp").exists()
    assert not path.with_name(path.name + ".tiled.tmp.tif").exists()

    with rasterio.open(path) as ds:
        assert ds.width == size
        assert ds.height == size
        assert ds.profile.get("blockxsize") == 512
        assert ds.profile.get("blockysize") == 512
        assert len(ds.overviews(1)) > 0  # COG 드라이버가 실제로 오버뷰를 만들었는지

        first_block = ds.read(1, window=Window(0, 0, 1, 1))
        second_block = ds.read(1, window=Window(512, 0, 1, 1))
        assert first_block[0, 0] == 1
        assert second_block[0, 0] == 2
