import numpy as np

from satellite.reflectance import dn_to_reflectance, reflectance_to_uint16, uint16_to_reflectance


def test_dn_to_reflectance_with_offset():
    dn = np.array([2000, 5000], dtype=np.uint16)
    result = dn_to_reflectance(dn, offset=-1000, quantification_value=10000)
    # (2000-1000)/10000=0.1, (5000-1000)/10000=0.4
    assert np.allclose(result, [0.1, 0.4])


def test_dn_to_reflectance_without_offset():
    dn = np.array([1000, 3000], dtype=np.uint16)
    result = dn_to_reflectance(dn, offset=0, quantification_value=10000)
    assert np.allclose(result, [0.1, 0.3])


def test_dn_zero_is_nodata():
    dn = np.array([0, 1000], dtype=np.uint16)
    result = dn_to_reflectance(dn, offset=-1000, quantification_value=10000)
    assert np.isnan(result[0])
    assert np.allclose(result[1], 0.0)  # (1000-1000)/10000 = 0.0


def test_negative_reflectance_clipped_to_zero():
    dn = np.array([500], dtype=np.uint16)  # (500-1000)/10000 = -0.05
    result = dn_to_reflectance(dn, offset=-1000, quantification_value=10000)
    assert result[0] == 0.0


def test_reflectance_to_uint16_scales_and_clips():
    reflectance = np.array([0.0, 0.5, 1.5, np.nan], dtype=np.float32)
    scaled = reflectance_to_uint16(reflectance)
    assert scaled.dtype == np.uint16
    assert list(scaled) == [0, 5000, 10000, 0]  # 1.5 -> clip to 10000, NaN -> 0


def test_uint16_to_reflectance_round_trip():
    original = np.array([0.0, 0.1234, 0.9999], dtype=np.float32)
    scaled = reflectance_to_uint16(original)
    restored = uint16_to_reflectance(scaled)
    assert np.isnan(restored[0])  # 0 -> nodata
    assert np.allclose(restored[1:], original[1:], atol=1e-3)


def test_uint16_zero_is_nodata_on_read_back():
    values = np.array([0, 10000], dtype=np.uint16)
    restored = uint16_to_reflectance(values)
    assert np.isnan(restored[0])
    assert restored[1] == 1.0
