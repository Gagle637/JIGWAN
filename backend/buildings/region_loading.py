"""행정경계(법정구역) 적재: region 테이블 upsert.

원본은 SGIS 행정동이 아니라 법정구역 경계(브이월드·국가공간정보포털) — building.bjd_code와
체계를 맞추기 위해 전부 법정동 코드 기준으로 받는다. 실제 원본 파일을 받아보기 전까지는
컬럼명이 추정값이므로 --code-field/--name-field로 덮어쓸 수 있게 둔다.
"""
from datetime import date
from pathlib import Path

import shapely.wkb

from core.gis_load import sync_geotable

from .models import Building, Region

STAGING_TABLE = "region_staging"

# 국가공간정보포털 법정구역 셰이프파일의 통상 컬럼명(실제 파일로 검증 전 추정값)
LEVEL_FIELD_DEFAULTS = {
    "sido": {"code": "CTPRVN_CD", "name": "CTPRVN_KOR_NM"},
    "sigungu": {"code": "SIG_CD", "name": "SIG_KOR_NM"},
    "bjd": {"code": "EMD_CD", "name": "EMD_KOR_NM"},
}

# 한국 행정코드는 접두 구조다: 법정동 10자리 ⊃ 시군구 5자리 ⊃ 시도 2자리.
_PARENT_CODE_LENGTH = {"sido": None, "sigungu": 2, "bjd": 5}

REGION_STAGING_COLUMNS = [
    ("region_code", "text"),
    ("level", "text"),
    ("name", "text"),
    ("parent_code", "text"),
    ("source_date", "date"),
    ("geom_src", "geometry"),
]

FINAL_COLUMNS = [c for c, _ in REGION_STAGING_COLUMNS if c != "geom_src"] + ["geom"]

FINAL_SELECT_SQL = f"""
SELECT
    region_code, level, name, parent_code, source_date,
    ST_Transform(ST_Multi(ST_MakeValid(geom_src)), 4326) AS geom
FROM {STAGING_TABLE}
"""


def resolve_vsi_path(path: Path) -> str:
    if path.suffix.lower() == ".zip":
        shp_name = path.stem + ".shp"
        return f"/vsizip/{path.resolve()}/{shp_name}"
    return str(path.resolve())


def pad_code(code: str, pad_to: int | None) -> str:
    """코드가 pad_to보다 짧으면 뒤에 '0'을 채운다(법정동 코드가 8자리로만 내려오는 경우 대응)."""
    if pad_to and len(code) < pad_to:
        return code.ljust(pad_to, "0")
    return code


def derive_parent_code(region_code: str, level: str) -> str | None:
    length = _PARENT_CODE_LENGTH[level]
    return None if length is None else region_code[:length]


def count_bjd_code_mismatches() -> int:
    """building.bjd_code 중 region(level=bjd)에 없는 코드 수(체계 정합성 확인용)."""
    bjd_codes = set(
        Region.objects.filter(level="bjd").values_list("region_code", flat=True)
    )
    building_codes = set(Building.objects.values_list("bjd_code", flat=True).distinct())
    return len(building_codes - bjd_codes)


def load_regions(
    path: Path,
    level: str,
    source_srid: int,
    code_field: str | None = None,
    name_field: str | None = None,
    pad_to: int | None = None,
    source_date: date | None = None,
) -> dict:
    import pyogrio  # 지연 임포트

    defaults = LEVEL_FIELD_DEFAULTS[level]
    code_field = code_field or defaults["code"]
    name_field = name_field or defaults["name"]

    vsi_path = resolve_vsi_path(path)
    gdf = pyogrio.read_dataframe(vsi_path)
    if len(gdf) == 0:
        raise ValueError(f"{path}에서 읽은 행이 없습니다.")

    rows = []
    for _, row in gdf.iterrows():
        code = pad_code(str(row[code_field]).strip(), pad_to)
        name = str(row[name_field]).strip()
        parent_code = derive_parent_code(code, level)
        geom_hex = shapely.wkb.dumps(row.geometry, hex=True, srid=source_srid)
        rows.append((code, level, name, parent_code, source_date, geom_hex))

    result = sync_geotable(
        staging_table=STAGING_TABLE,
        staging_columns=REGION_STAGING_COLUMNS,
        rows=rows,
        final_table="region",
        final_select_sql=FINAL_SELECT_SQL,
        final_columns=FINAL_COLUMNS,
        conflict_columns=["region_code"],
        soft_delete_column=None,
    )

    summary = {"total_rows": len(rows), "level": level, **result}
    if level == "bjd":
        summary["bjd_code_mismatch_count"] = count_bjd_code_mismatches()
    return summary
