"""SCL(Scene Classification Layer) 마스킹(spec 2-3)."""
import numpy as np

# 2(어두운 화소)·4(식생)·5(비식생)·6(물)·7(미분류)만 사용. 0·1(nodata·포화결함), 3(구름그림자),
# 8·9(구름), 10(얇은 권운), 11(눈·얼음)은 제외.
USABLE_SCL_VALUES = frozenset({2, 4, 5, 6, 7})

MIN_VALID_RATIO = 0.2  # 지역 내 유효 화소 비율이 이보다 낮으면 합성에서 제외(spec 2-3)


def usable_mask(scl: np.ndarray) -> np.ndarray:
    return np.isin(scl, list(USABLE_SCL_VALUES))


def compute_valid_ratio(scl: np.ndarray) -> float:
    """지역(대전 격자) 내 유효 화소 비율 = 사용 가능 SCL 화소 수 / 전체 화소 수(spec 2-3)."""
    scl = np.asarray(scl)
    if scl.size == 0:
        return 0.0
    return float(np.count_nonzero(usable_mask(scl)) / scl.size)


def is_sufficiently_valid(scl: np.ndarray) -> bool:
    return compute_valid_ratio(scl) >= MIN_VALID_RATIO
