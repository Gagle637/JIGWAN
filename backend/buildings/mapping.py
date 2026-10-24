"""GIS건물통합정보 한 행(A0~A28)을 building 컬럼 dict로 바꾸는 순수 함수들.

DB·GDAL에 의존하지 않아 단위 테스트가 가볍다. pyogrio가 돌려주는 값은 dbf 필드 타입에 따라
C(문자)는 str, N(숫자)는 float, D(날짜)는 이미 date 객체로 들어온다고 가정한다 — 단, A13은
dbf 타입이 Character(C,10)라서 날짜가 아니라 문자열로 들어온다(직접 확인함).
"""
import math
from datetime import date, datetime
from typing import Mapping

# A8(용도코드)이 비면 '정보 없음' placeholder로 0이 채워져 있는 수치 컬럼들(spec 8-6)
_REGISTRY_ONLY_NUMERIC_FIELDS = (
    "building_area_m2",
    "total_floor_area_m2",
    "land_area_m2",
    "height_m",
    "bcr_pct",
    "far_pct",
    "floors_above",
    "floors_below",
)


def _clean_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_float(value) -> float | None:
    # GDAL/pyogrio는 수치 컬럼(N)의 결측값을 None이 아니라 float NaN으로 줄 때가 있다
    # (실제 적재 중 재현됨: str(nan)="nan"이라 _clean_str을 그대로 통과해버린다).
    if isinstance(value, float) and math.isnan(value):
        return None
    text = _clean_str(value)
    if text is None:
        return None
    parsed = float(text)
    return None if math.isnan(parsed) else parsed


def _to_int(value) -> int | None:
    as_float = _to_float(value)
    return None if as_float is None else int(as_float)


def parse_flexible_date(value) -> date | None:
    """'YYYY-MM-DD' 먼저, 실패하면 'YYYYMMDD'. 둘 다 실패하거나 빈 값이면 None."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = _clean_str(value)
    if text is None:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def map_building_row(row: Mapping) -> dict:
    """row: {"A0": ..., ..., "A28": ...}. building_key/is_active/geom은 여기서 채우지 않는다
    (building_key는 gis_bldg_id 중복 그룹을 본 뒤 로딩 서비스가 일괄 부여).

    반환 dict에는 내부용 "_approval_date_parse_failed" 키가 포함된다(원본 A13이 값은 있는데
    파싱에 실패한 경우 True) — 로딩 서비스가 요약 집계 후 제거하고 저장한다.
    """
    use_code = _clean_str(row.get("A8"))
    has_registry = use_code is not None

    raw_approval_date = row.get("A13")
    approval_date = parse_flexible_date(raw_approval_date)
    approval_date_parse_failed = (
        _clean_str(raw_approval_date) is not None and approval_date is None
    )

    fields = {
        "gis_bldg_id": _clean_str(row.get("A1")),
        "pnu": _clean_str(row.get("A2")),
        "bjd_code": _clean_str(row.get("A3")),
        "bjd_name": _clean_str(row.get("A4")),
        "jibun": _clean_str(row.get("A5")),
        "use_code": use_code,
        "use_name": _clean_str(row.get("A9")),
        "structure": _clean_str(row.get("A11")),
        "building_area_m2": _to_float(row.get("A12")),
        "approval_date": approval_date,
        "total_floor_area_m2": _to_float(row.get("A14")),
        "land_area_m2": _to_float(row.get("A15")),
        "height_m": _to_float(row.get("A16")),
        "bcr_pct": _to_float(row.get("A17")),
        "far_pct": _to_float(row.get("A18")),
        "is_violation": _parse_yn(row.get("A20")),
        "name": _clean_str(row.get("A24")),
        "dong_name": _clean_str(row.get("A25")),
        "floors_above": _to_int(row.get("A26")),
        "floors_below": _to_int(row.get("A27")),
        "source_date": parse_flexible_date(row.get("A22")),
    }

    if not has_registry:
        for field_name in _REGISTRY_ONLY_NUMERIC_FIELDS:
            fields[field_name] = None

    fields["_approval_date_parse_failed"] = approval_date_parse_failed
    return fields


def _parse_yn(value) -> bool | None:
    text = _clean_str(value)
    if text is None:
        return None
    upper = text.upper()
    if upper == "Y":
        return True
    if upper == "N":
        return False
    return None
