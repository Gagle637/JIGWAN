import numpy as np

from satellite.index_scaling import (
    INDEX_NODATA,
    MASK_NODATA,
    decode_mask,
    encode_mask,
    int16_to_index,
    scale_index_to_int16,
)


def test_scale_index_to_int16_scales_and_clips():
    values = np.array([0.0, 0.5, -0.5, 1.5, -1.5, np.nan], dtype=np.float32)
    scaled = scale_index_to_int16(values)
    assert scaled.dtype == np.int16
    assert list(scaled) == [0, 5000, -5000, 10000, -10000, INDEX_NODATA]


def test_int16_to_index_round_trip():
    original = np.array([0.0, 0.1234, -0.9999], dtype=np.float32)
    scaled = scale_index_to_int16(original)
    restored = int16_to_index(scaled)
    assert np.allclose(restored, original, atol=1e-3)


def test_int16_nodata_round_trip_is_nan():
    scaled = scale_index_to_int16(np.array([np.nan], dtype=np.float32))
    restored = int16_to_index(scaled)
    assert np.isnan(restored[0])


def test_encode_mask_without_valid_mask():
    mask = np.array([True, False, True])
    encoded = encode_mask(mask)
    assert list(encoded) == [1, 0, 1]
    assert encoded.dtype == np.uint8


def test_encode_mask_with_invalid_positions():
    mask = np.array([True, False, True])
    valid = np.array([True, False, True])
    encoded = encode_mask(mask, valid=valid)
    assert list(encoded) == [1, MASK_NODATA, 1]


def test_decode_mask_nodata_is_nan():
    values = np.array([0, 1, MASK_NODATA], dtype=np.uint8)
    decoded = decode_mask(values)
    assert decoded[0] == 0.0
    assert decoded[1] == 1.0
    assert np.isnan(decoded[2])
