"""DN -> 반사율 변환(spec 2-2)과 저장용 uint16 스케일링(결정 사항 12). numpy만 쓰는 순수 함수."""
import numpy as np


def dn_to_reflectance(dn: np.ndarray, offset: int, quantification_value: int) -> np.ndarray:
    """ρ = (DN + BOA_ADD_OFFSET) / BOA_QUANTIFICATION_VALUE(spec 2-2).

    DN==0은 nodata(NaN)로 둔다. 변환 후 음수 반사율은 0으로 자른다. 오프셋이 없는(0인) 구형
    제품도 그대로 동작한다.
    """
    dn = np.asarray(dn).astype(np.float32)
    reflectance = (dn + offset) / quantification_value
    reflectance = np.clip(reflectance, 0.0, None)
    reflectance = np.where(dn == 0, np.nan, reflectance)
    return reflectance.astype(np.float32)


def reflectance_to_uint16(reflectance: np.ndarray) -> np.ndarray:
    """저장용: 반사율×10000을 0~10000으로 clip한 uint16. NaN(nodata)은 0(결정 사항 12)."""
    scaled = np.nan_to_num(reflectance.astype(np.float64) * 10000, nan=0.0)
    scaled = np.clip(scaled, 0, 10000)
    return scaled.astype(np.uint16)


def uint16_to_reflectance(values: np.ndarray) -> np.ndarray:
    """저장된 uint16 반사율을 다시 float32 반사율로 되돌린다(÷10000). 0은 nodata -> NaN."""
    values = np.asarray(values)
    reflectance = values.astype(np.float32) / 10000.0
    reflectance = np.where(values == 0, np.nan, reflectance)
    return reflectance.astype(np.float32)
