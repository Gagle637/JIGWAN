import numpy as np
import pytest

from satellite.composite import (
    GREEN_NDVI_THRESHOLD,
    compute_ndbi,
    compute_ndvi,
    mask_scene_reflectance,
    median_with_min_observations,
)


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
