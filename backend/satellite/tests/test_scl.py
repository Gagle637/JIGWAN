import numpy as np

from satellite.scl import MIN_VALID_RATIO, compute_valid_ratio, is_sufficiently_valid, usable_mask


def test_usable_mask_matches_spec_table():
    scl = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
    mask = usable_mask(scl)
    expected = np.array(
        [False, False, True, False, True, True, True, True, False, False, False, False]
    )
    assert (mask == expected).all()


def test_compute_valid_ratio_all_usable():
    scl = np.full((10, 10), 4)  # 식생
    assert compute_valid_ratio(scl) == 1.0


def test_compute_valid_ratio_none_usable():
    scl = np.full((10, 10), 9)  # 구름(높은 확률)
    assert compute_valid_ratio(scl) == 0.0


def test_compute_valid_ratio_boundary_at_20_percent():
    scl = np.zeros(100)
    scl[:20] = 4  # 20% usable
    assert compute_valid_ratio(scl) == 0.2
    assert is_sufficiently_valid(scl) is True  # 20%는 "미만"이 아니므로 포함

    scl2 = np.zeros(100)
    scl2[:19] = 4  # 19% usable
    assert is_sufficiently_valid(scl2) is False


def test_min_valid_ratio_constant():
    assert MIN_VALID_RATIO == 0.2
