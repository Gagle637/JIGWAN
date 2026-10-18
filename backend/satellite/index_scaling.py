"""NDVI/NDBI·마스크류 COG 저장 인코딩(6단계 결정 사항 6).

반사율(uint16, nodata=0)과 달리 NDVI/NDBI는 0이 정상적인 값이라 0을 nodata로 못 쓴다.
"""
import numpy as np

INDEX_SCALE = 10000
INDEX_NODATA = -32768  # int16 최솟값, 정상 스케일(-10000..10000) 밖이라 nodata로 안전하게 씀
MASK_NODATA = 255  # uint8 0/1 마스크의 0(=해당 없음)과 구분하기 위한 nodata


def scale_index_to_int16(value: np.ndarray) -> np.ndarray:
    """NDVI/NDBI(float, NaN=nodata) -> int16(×10000, clip -10000..10000, NaN -> INDEX_NODATA)."""
    scaled = np.nan_to_num(value.astype(np.float64) * INDEX_SCALE, nan=float(INDEX_NODATA))
    scaled = np.where(np.isnan(value), INDEX_NODATA, np.clip(scaled, -10000, 10000))
    return scaled.astype(np.int16)


def int16_to_index(values: np.ndarray) -> np.ndarray:
    """저장된 int16을 다시 float32 NDVI/NDBI로(÷10000). INDEX_NODATA는 NaN."""
    values = np.asarray(values)
    index = values.astype(np.float32) / INDEX_SCALE
    return np.where(values == INDEX_NODATA, np.nan, index).astype(np.float32)


def encode_mask(mask: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
    """bool 마스크(0/1) -> uint8. valid(화소가 평가 가능했는지)가 False인 곳은 MASK_NODATA."""
    encoded = mask.astype(np.uint8)
    if valid is not None:
        encoded = np.where(valid, encoded, MASK_NODATA).astype(np.uint8)
    return encoded


def decode_mask(values: np.ndarray) -> np.ndarray:
    """저장된 uint8 마스크를 float(0.0/1.0/NaN)로 되돌린다. MASK_NODATA는 NaN."""
    values = np.asarray(values)
    return np.where(values == MASK_NODATA, np.nan, values.astype(np.float32))
