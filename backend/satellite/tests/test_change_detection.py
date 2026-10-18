import numpy as np
from rasterio.transform import Affine

from satellite.change_detection import detect_change, vectorize_change


def test_detect_change_removes_small_blob_keeps_large_one():
    past_ndvi = np.full((10, 10), 0.5)
    past_ndbi = np.full((10, 10), -0.2)
    current_ndvi = np.full((10, 10), 0.5)
    current_ndbi = np.full((10, 10), -0.2)

    # 작은 덩어리(3x3=9화소) — 임계값은 통과하지만 10화소 미만이라 제거돼야 함(spec 3-4).
    current_ndvi[0:3, 0:3] = 0.3  # delta_ndvi = -0.2 < -0.15
    current_ndbi[0:3, 0:3] = -0.05  # delta_ndbi = 0.15 > 0.1

    # 큰 덩어리(3x4=12화소) — 10화소 이상이라 남아야 함.
    current_ndvi[5:8, 0:4] = 0.3
    current_ndbi[5:8, 0:4] = -0.05

    mask = detect_change(current_ndvi, current_ndbi, past_ndvi, past_ndbi)

    assert not mask[0:3, 0:3].any()
    assert mask[5:8, 0:4].all()
    assert mask.sum() == 12


def test_detect_change_no_candidates_when_thresholds_not_met():
    past_ndvi = np.full((5, 5), 0.5)
    past_ndbi = np.full((5, 5), -0.2)
    current_ndvi = np.full((5, 5), 0.5)
    current_ndbi = np.full((5, 5), -0.2)

    mask = detect_change(current_ndvi, current_ndbi, past_ndvi, past_ndbi)

    assert not mask.any()


def test_detect_change_requires_both_thresholds():
    past_ndvi = np.full((5, 5), 0.5)
    past_ndbi = np.full((5, 5), -0.2)
    current_ndvi = np.full((5, 5), 0.5)
    current_ndbi = np.full((5, 5), -0.2)

    # ΔNDBI만 통과, ΔNDVI는 임계값 미달
    current_ndbi[:, :] = -0.05  # delta_ndbi = 0.15 > 0.1
    # current_ndvi 변화 없음 -> delta_ndvi = 0, 임계값(< -0.15) 미달

    mask = detect_change(current_ndvi, current_ndbi, past_ndvi, past_ndbi)

    assert not mask.any()


def test_detect_change_excludes_nan_pixels():
    past_ndvi = np.full((4, 4), 0.5)
    past_ndbi = np.full((4, 4), -0.2)
    current_ndvi = np.full((4, 4), 0.3)
    current_ndbi = np.full((4, 4), -0.05)
    current_ndvi[0, 0] = np.nan  # 관측 부족 등으로 nodata인 화소

    mask = detect_change(current_ndvi, current_ndbi, past_ndvi, past_ndbi)

    assert not mask[0, 0]


def test_vectorize_change_computes_area_and_mean_deltas():
    mask = np.zeros((5, 5), dtype=bool)
    mask[1:3, 1:3] = True  # 2x2 = 4화소
    transform = Affine(10, 0, 300000, 0, -10, 4000000)  # 10m 화소
    delta_ndbi = np.full((5, 5), 0.2)
    delta_ndvi = np.full((5, 5), -0.3)

    results = vectorize_change(mask, transform, delta_ndbi, delta_ndvi)

    assert len(results) == 1
    assert results[0]["area_m2"] == 4 * 100.0  # 4화소 * (10m*10m)
    assert results[0]["delta_ndbi"] == 0.2
    assert results[0]["delta_ndvi"] == -0.3
    assert results[0]["geom"]["type"] == "Polygon"


def test_vectorize_change_empty_mask_returns_no_areas():
    mask = np.zeros((5, 5), dtype=bool)
    transform = Affine(10, 0, 300000, 0, -10, 4000000)
    results = vectorize_change(mask, transform, np.zeros((5, 5)), np.zeros((5, 5)))
    assert results == []
