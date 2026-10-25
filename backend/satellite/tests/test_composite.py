import numpy as np
import pytest
import rasterio
from django.contrib.gis.geos import MultiPolygon
from django.contrib.gis.geos import Polygon as GEOSPolygon

from buildings.models import Region
from satellite.cog import grid_transform
from satellite.composite import (
    GREEN_NDVI_THRESHOLD,
    build_season_composite,
    compute_ndbi,
    compute_ndvi,
    mask_scene_reflectance,
    median_with_min_observations,
)
from satellite.index_scaling import MASK_NODATA
from satellite.ingest import REFLECTANCE_BANDS
from satellite.models import SatelliteScene


def test_compute_ndvi_known_values():
    b08 = np.array([0.5, 0.2])
    b04 = np.array([0.1, 0.2])
    ndvi = compute_ndvi(b08, b04)
    # (0.5-0.1)/(0.5+0.1)=0.6667, (0.2-0.2)/(0.2+0.2)=0
    assert np.allclose(ndvi, [0.6666667, 0.0], atol=1e-5)


def test_compute_ndbi_known_values():
    b11 = np.array([0.4])
    b08 = np.array([0.1])
    ndbi = compute_ndbi(b11, b08)
    assert np.allclose(ndbi, [0.6])  # (0.4-0.1)/(0.4+0.1)


def test_mask_scene_reflectance_sets_unusable_scl_to_nan():
    bands = {
        "B04": np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32),
        "B08": np.array([[0.5, 0.6], [0.7, 0.8]], dtype=np.float32),
    }
    scl = np.array([[4, 9], [8, 2]])  # 4·2=사용가능, 9·8=구름(제외)
    masked = mask_scene_reflectance(bands, scl)

    # float32라 0.1/0.4의 float64 리터럴과 정확히는 안 맞는다(감사에서 발견) -> approx로 비교.
    assert masked["B04"][0, 0] == pytest.approx(0.1)  # SCL=4, 유지
    assert np.isnan(masked["B04"][0, 1])  # SCL=9, 제외
    assert np.isnan(masked["B04"][1, 0])  # SCL=8, 제외
    assert masked["B04"][1, 1] == pytest.approx(0.4)  # SCL=2, 유지


def test_median_with_min_observations_requires_three():
    # 화소 0: 2개 관측 -> nodata. 화소 1: 3개 관측 -> 중앙값.
    stack = np.array(
        [
            [1.0, 1.0],
            [2.0, 2.0],
            [np.nan, 3.0],
        ]
    )
    result = median_with_min_observations(stack, min_obs=3)
    assert np.isnan(result[0])
    assert result[1] == 2.0


def test_median_with_min_observations_all_nan_block():
    stack = np.full((5, 2, 2), np.nan)
    result = median_with_min_observations(stack)
    assert np.all(np.isnan(result))


def test_green_mask_threshold_constant():
    assert GREEN_NDVI_THRESHOLD == 0.4


# ---- build_season_composite: 맞닿은 두 지역의 겹치는 버퍼 띠에서 이중 계산 방지(5단계) ----


def _sido_region(region_code: str, minx, miny, maxx, maxy) -> Region:
    poly_32652 = GEOSPolygon.from_bbox((minx, miny, maxx, maxy))
    poly_32652.srid = 32652
    geom_4326 = MultiPolygon(poly_32652.transform(4326, clone=True))
    return Region.objects.create(
        region_code=region_code, level="sido", name=f"테스트{region_code}", geom=geom_4326
    )


def _write_reflectance_and_scl(tmp_path, name, grid, value=3000, scl_value=4):
    transform = grid_transform(grid)
    shape = (grid["height"], grid["width"])
    refl_path = tmp_path / f"{name}_refl.tif"
    scl_path = tmp_path / f"{name}_scl.tif"

    with rasterio.open(
        refl_path, "w", driver="GTiff", dtype="uint16", count=len(REFLECTANCE_BANDS),
        width=grid["width"], height=grid["height"], crs=grid["crs"], transform=transform,
    ) as dst:
        for i in range(len(REFLECTANCE_BANDS)):
            dst.write(np.full(shape, value, dtype=np.uint16), i + 1)

    with rasterio.open(
        scl_path, "w", driver="GTiff", dtype="uint8", count=1,
        width=grid["width"], height=grid["height"], crs=grid["crs"], transform=transform,
    ) as dst:
        dst.write(np.full(shape, scl_value, dtype=np.uint8), 1)

    return str(refl_path), str(scl_path)


def _make_scenes(tmp_path, name_prefix, grid, count=3):
    """median_with_min_observations가 최소 3개 관측을 요구하므로(MIN_OBSERVATIONS) 똑같은
    장면을 3개 만든다 — 값 자체는 중요하지 않고, 격자 전체(버퍼 포함)가 유효해야 한다."""
    scenes = []
    for i in range(count):
        refl_path, scl_path = _write_reflectance_and_scl(tmp_path, f"{name_prefix}_{i}", grid)
        scenes.append(
            SatelliteScene(scene_id=f"{name_prefix}_{i}", cog_path=refl_path, scl_cog_path=scl_path)
        )
    return scenes


def _pixel_value(path, grid, x, y, resolution_m):
    row = int((grid["maxy"] - y) / resolution_m)
    col = int((x - grid["minx"]) / resolution_m)
    with rasterio.open(path) as ds:
        return ds.read(1)[row, col]


@pytest.mark.django_db
def test_build_season_composite_clips_to_sido_boundary_to_avoid_double_counting_at_shared_border(
    tmp_path,
):
    """격자에는 버퍼(여유)가 있어 맞닿은 두 지역의 격자가 겹친다(대전·세종처럼 실제로 맞닿은
    경우) — 각 지역의 합성 결과는 자기 시도 경계 밖을 nodata로 잘라야, 반경 통계가 같은 기간의
    여러 COG 픽셀을 합산할 때 겹치는 띠에서 두 번 세지 않는다."""
    resolution_m = 10
    buffer_m = 40
    # 시도 A: x[341700,341900], 시도 B: x[341900,342100] — y는 공통, 서로 맞닿아 있다.
    _sido_region("91", 341700, 4004820, 341900, 4004920)
    _sido_region("92", 341900, 4004820, 342100, 4004920)

    def _grid(minx, miny, maxx, maxy):
        g = {
            "crs": "EPSG:32652", "resolution_m": resolution_m,
            "minx": minx - buffer_m, "miny": miny - buffer_m,
            "maxx": maxx + buffer_m, "maxy": maxy + buffer_m,
        }
        g["width"] = round((g["maxx"] - g["minx"]) / resolution_m)
        g["height"] = round((g["maxy"] - g["miny"]) / resolution_m)
        return g

    grid_a = _grid(341700, 4004820, 341900, 4004920)
    grid_b = _grid(341900, 4004820, 342100, 4004920)

    result_a = build_season_composite(
        _make_scenes(tmp_path, "a", grid_a), 2026, "summer", grid_a, sido_code="91"
    )
    result_b = build_season_composite(
        _make_scenes(tmp_path, "b", grid_b), 2026, "summer", grid_b, sido_code="92"
    )

    # 겹치는 버퍼 띠 안, B 쪽 진짜 영역(x=341920) — A의 결과는 자기 경계 밖이라 nodata여야
    # 하고, B의 결과만 유효해야 한다(둘 다 유효하면 반경 통계가 이중 계산됨).
    a_at_b_side = _pixel_value(result_a["paths"]["green_mask"], grid_a, 341920, 4004870, resolution_m)
    b_at_b_side = _pixel_value(result_b["paths"]["green_mask"], grid_b, 341920, 4004870, resolution_m)
    assert a_at_b_side == MASK_NODATA
    assert b_at_b_side != MASK_NODATA

    # 대칭: A 쪽 진짜 영역(x=341880) — B의 결과는 nodata, A의 결과만 유효해야 한다.
    a_at_a_side = _pixel_value(result_a["paths"]["green_mask"], grid_a, 341880, 4004870, resolution_m)
    b_at_a_side = _pixel_value(result_b["paths"]["green_mask"], grid_b, 341880, 4004870, resolution_m)
    assert a_at_a_side != MASK_NODATA
    assert b_at_a_side == MASK_NODATA
