import math
from datetime import date

from buildings.mapping import map_building_row, parse_flexible_date


def _base_row(**overrides):
    row = {
        "A1": "GISID001",
        "A2": "3011010300101530003",
        "A3": "3011010300",
        "A4": "대전광역시 동구 효동",
        "A5": "153-3",
        "A8": "01000",
        "A9": "단독주택",
        "A11": "벽돌구조",
        "A12": 83.37,
        "A13": "1977-08-17",
        "A14": 135.21,
        "A15": 187.0,
        "A16": 8.0,
        "A17": 44.58,
        "A18": 72.3,
        "A20": "N",
        "A24": "",
        "A25": "",
        "A26": 2,
        "A27": 0,
        "A22": date(2026, 10, 6),
    }
    row.update(overrides)
    return row


def test_registry_present_keeps_real_zero_values():
    row = _base_row(A26=0, A27=0)
    fields = map_building_row(row)
    assert fields["floors_above"] == 0
    assert fields["floors_below"] == 0
    assert fields["building_area_m2"] == 83.37


def test_registry_blank_forces_numeric_fields_to_none():
    row = _base_row(A8="", A9="", A11="", A12=0.0, A14=0.0, A15=0.0, A16=0.0, A17=0.0, A18=0.0, A26=0, A27=0)
    fields = map_building_row(row)
    assert fields["use_code"] is None
    for field_name in (
        "building_area_m2",
        "total_floor_area_m2",
        "land_area_m2",
        "height_m",
        "bcr_pct",
        "far_pct",
        "floors_above",
        "floors_below",
    ):
        assert fields[field_name] is None, field_name


def test_numeric_nan_becomes_none():
    # 실제 적재 중 재현됨: GDAL/pyogrio가 수치(N) 컬럼의 결측값을 None이 아니라 float NaN으로
    # 주면 str(nan)="nan"이 _clean_str을 그대로 통과해 int(nan)에서 ValueError가 났다.
    row = _base_row(A14=math.nan, A26=math.nan, A27=math.nan)
    fields = map_building_row(row)
    assert fields["total_floor_area_m2"] is None
    assert fields["floors_above"] is None
    assert fields["floors_below"] is None


def test_blank_strings_become_none():
    row = _base_row(A24="", A25="  ", A4=None)
    fields = map_building_row(row)
    assert fields["name"] is None
    assert fields["dong_name"] is None
    assert fields["bjd_name"] is None


def test_is_violation_yn_mapping():
    assert map_building_row(_base_row(A20="Y"))["is_violation"] is True
    assert map_building_row(_base_row(A20="N"))["is_violation"] is False
    assert map_building_row(_base_row(A20=""))["is_violation"] is None


def test_approval_date_parses_iso_and_compact_formats():
    assert map_building_row(_base_row(A13="1977-08-17"))["approval_date"] == date(1977, 8, 17)
    assert map_building_row(_base_row(A13="19770817"))["approval_date"] == date(1977, 8, 17)


def test_approval_date_parse_failure_is_flagged():
    fields = map_building_row(_base_row(A13="알수없음"))
    assert fields["approval_date"] is None
    assert fields["_approval_date_parse_failed"] is True


def test_approval_date_blank_is_not_a_parse_failure():
    fields = map_building_row(_base_row(A13=""))
    assert fields["approval_date"] is None
    assert fields["_approval_date_parse_failed"] is False


def test_parse_flexible_date_direct():
    assert parse_flexible_date("1977-08-17") == date(1977, 8, 17)
    assert parse_flexible_date("19770817") == date(1977, 8, 17)
    assert parse_flexible_date("") is None
    assert parse_flexible_date(None) is None
    assert parse_flexible_date("garbage") is None
