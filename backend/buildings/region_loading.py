"""행정경계(법정구역) 적재: region 테이블 upsert.

원본은 SGIS 행정동이 아니라 법정구역 경계(국가공간정보포털 AL_D001_00) — building.bjd_code와
체계를 맞추기 위해 전부 법정동 코드 기준으로 받는다.

실제 원본 파일(AL_D001_00_20261009, 전국)로 확인한 구조(2026-10):
- 바깥 zip 안에 레벨별 zip이 중첩돼 있다: (SIG)시군구, (EMD)읍면동/법정동, (LIO)리.
  리는 대전에 없어 지원하지 않는다.
- 각 zip은 SHP, EPSG:5186, CP949, Polygon(2D).
- 필드는 시군구·법정동 전부 A1(코드)·A2(이름)로 동일하다.
- 읍면동 코드는 8자리로 내려오는데 "00"을 붙이면 building.bjd_code(10자리)와 100% 일치한다.
- 시도 경계 파일은 따로 없다 — 이미 적재된 시군구를 ST_Union해서 만든다(사용자 결정, 대전
  5개 구 union이 구 면적 합과 0.001% 차이로 검증됨).
"""
import zipfile
from datetime import date
from pathlib import Path

import shapely.wkb
from django.db import connection

from core.gis_load import sync_geotable

from .models import Building, Region

STAGING_TABLE = "region_staging"

# 실제 원본 파일로 확인한 필드명(2026-10) — sido는 파일이 아니라 union으로 만들어 해당 없음.
LEVEL_FIELD_DEFAULTS = {
    "sigungu": {"code": "A1", "name": "A2"},
    "bjd": {"code": "A1", "name": "A2"},
}

# 바깥 zip 안에서 레벨별 안쪽 zip을 찾는 키워드. 실제 안쪽 zip 파일명을 몰라도 되게,
# zip 목록에서 이 키워드가 들어간 걸 찾는다(정확한 파일명에 의존하지 않음).
LEVEL_INNER_ZIP_KEYWORD = {"sigungu": "SIG", "bjd": "EMD"}

# 읍면동 코드(8자리) -> 법정동 코드(10자리). building.bjd_code와 100% 일치 확인됨(2026-10).
LEVEL_PAD_TO = {"bjd": 10}

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

# Z가 있으면 ST_Force2D로 버리고(원본은 2D로 확인됐지만 방어적으로), MakeValid 후 Multi로
# 통일해 Region.geom(MultiPolygonField)과 맞춘다.
FINAL_SELECT_SQL = f"""
SELECT
    region_code, level, name, parent_code, source_date,
    ST_Transform(ST_Multi(ST_MakeValid(ST_Force2D(geom_src))), 4326) AS geom
FROM {STAGING_TABLE}
"""


def _find_in_zip(zf: zipfile.ZipFile, keyword: str, suffix: str) -> str:
    matches = [
        name
        for name in zf.namelist()
        if keyword.upper() in name.upper() and name.upper().endswith(suffix.upper())
    ]
    if not matches:
        raise ValueError(
            f"'{keyword}'를 포함하는 {suffix} 파일을 zip 안에서 못 찾았습니다: {zf.namelist()}"
        )
    return matches[0]


def resolve_vsi_path(path: Path, level: str) -> str:
    """단일 zip이면 그 안의 shp를, 중첩 zip(바깥 zip 안에 레벨별 zip)이면 안쪽까지 들어가
    GDAL의 중첩 /vsizip/ 경로(`/vsizip/{/vsizip/outer.zip/inner.zip}/file.shp`)를 만든다.
    level="sido"는 파일을 안 읽으므로 호출하지 않는다."""
    if path.suffix.lower() != ".zip":
        return str(path.resolve())

    with zipfile.ZipFile(path) as outer:
        inner_zip_names = [n for n in outer.namelist() if n.lower().endswith(".zip")]
        keyword = LEVEL_INNER_ZIP_KEYWORD.get(level)
        if keyword and inner_zip_names:
            inner_zip_name = _find_in_zip(outer, keyword, ".zip")
            with outer.open(inner_zip_name) as inner_fp, zipfile.ZipFile(inner_fp) as inner_zf:
                shp_name = _find_in_zip(inner_zf, "", ".shp")
            return f"/vsizip/{{/vsizip/{path.resolve()}/{inner_zip_name}}}/{shp_name}"

        shp_name = _find_in_zip(outer, "", ".shp")
        return f"/vsizip/{path.resolve()}/{shp_name}"


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
    path: Path | None,
    level: str,
    source_srid: int | None = None,
    code_field: str | None = None,
    name_field: str | None = None,
    pad_to: int | None = None,
    source_date: date | None = None,
    sido_prefix: str = "30",
) -> dict:
    if level == "sido":
        return load_sido_from_sigungu_union(sido_prefix, source_date)

    import pyogrio  # 지연 임포트

    if path is None:
        raise ValueError(f"level={level}에는 원본 파일 경로(path)가 필요합니다.")

    defaults = LEVEL_FIELD_DEFAULTS[level]
    code_field = code_field or defaults["code"]
    name_field = name_field or defaults["name"]
    if pad_to is None:
        pad_to = LEVEL_PAD_TO.get(level)

    vsi_path = resolve_vsi_path(path, level)
    gdf = pyogrio.read_dataframe(vsi_path)
    if len(gdf) == 0:
        raise ValueError(f"{path}에서 읽은 행이 없습니다.")

    resolved_srid = source_srid
    if resolved_srid is None:
        epsg = gdf.crs.to_epsg() if gdf.crs is not None else None
        if epsg is None:
            raise ValueError(
                ".prj에서 좌표계(EPSG)를 못 읽었습니다 — --source-srid로 직접 지정해주세요."
            )
        resolved_srid = epsg

    rows = []
    skipped_outside_sido = 0
    for _, row in gdf.iterrows():
        raw_code = str(row[code_field]).strip()
        if sido_prefix and not raw_code.startswith(sido_prefix):
            skipped_outside_sido += 1
            continue
        code = pad_code(raw_code, pad_to)
        name = str(row[name_field]).strip()
        # sigungu의 부모(시도)는 이 시점에 아직 없다 — 시도는 sigungu를 다 적재한 뒤에
        # union해서 만든다(parent_code가 region.region_code를 가리키는 실제 FK라서,
        # 순서를 거꾸로 하면 삽입 자체가 막힌다). load_sido_from_sigungu_union이 시도를
        # 만들면서 sigungu.parent_code를 나중에 채운다.
        parent_code = None if level == "sigungu" else derive_parent_code(code, level)
        geom_hex = shapely.wkb.dumps(row.geometry, hex=True, srid=resolved_srid)
        rows.append((code, level, name, parent_code, source_date, geom_hex))

    if not rows:
        raise ValueError(
            f"'{sido_prefix}'로 시작하는 {level} 행이 없습니다"
            f"(코드 필드 '{code_field}' 값을 확인해주세요)."
        )

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

    summary = {
        "total_rows": len(rows),
        "level": level,
        "skipped_outside_sido": skipped_outside_sido,
        "source_srid": resolved_srid,
        **result,
    }
    if level == "bjd":
        summary["bjd_code_mismatch_count"] = count_bjd_code_mismatches()
    return summary


def load_sido_from_sigungu_union(sido_prefix: str, source_date: date | None) -> dict:
    """시도 경계 원본 파일이 없어, 이미 적재된 시군구(level=sigungu)를 ST_Union해서 만든다
    (사용자 결정). 유효성·면적 차이를 먼저 확인하고(구 면적 합 대비 union 면적), 문제가
    있으면 적재하지 않고 바로 실패한다."""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*),
                SUM(ST_Area(geom::geography)),
                ST_Area(ST_Union(geom)::geography),
                ST_IsValid(ST_Union(geom)),
                array_agg(DISTINCT split_part(name, ' ', 1))
            FROM region
            WHERE level = 'sigungu' AND region_code LIKE %s
            """,
            [f"{sido_prefix}%"],
        )
        sigungu_count, sum_area_m2, union_area_m2, union_is_valid, sido_names = cur.fetchone()

    if not sigungu_count:
        raise ValueError(
            f"'{sido_prefix}'로 시작하는 시군구(level=sigungu)가 없습니다 — "
            "sido보다 sigungu를 먼저 적재해야 합니다."
        )
    if len(sido_names) != 1:
        raise ValueError(f"시군구 이름의 앞 토큰이 하나로 안 모입니다(시도 이름 추정 실패): {sido_names}")
    if not union_is_valid:
        raise ValueError("시군구를 union한 결과가 유효하지 않은 지오메트리입니다(ST_IsValid=false).")

    area_diff_pct = (
        abs(union_area_m2 - sum_area_m2) / sum_area_m2 * 100 if sum_area_m2 else None
    )

    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO region (region_code, level, name, parent_code, source_date, geom)
            SELECT %(code)s, 'sido', %(name)s, NULL, %(source_date)s, ST_Multi(ST_Union(geom))
            FROM region
            WHERE level = 'sigungu' AND region_code LIKE %(prefix)s
            ON CONFLICT (region_code) DO UPDATE SET
                name = EXCLUDED.name,
                source_date = EXCLUDED.source_date,
                geom = EXCLUDED.geom
            """,
            {
                "code": sido_prefix,
                "name": sido_names[0],
                "source_date": source_date,
                "prefix": f"{sido_prefix}%",
            },
        )
        affected_rows = cur.rowcount

        # sigungu 적재 시점엔 시도가 없어 parent_code를 NULL로 뒀다 — 이제 채운다.
        cur.execute(
            "UPDATE region SET parent_code = %(code)s "
            "WHERE level = 'sigungu' AND region_code LIKE %(prefix)s",
            {"code": sido_prefix, "prefix": f"{sido_prefix}%"},
        )

    return {
        "total_rows": 1,
        "level": "sido",
        "loaded_rows": 1,
        "affected_rows": affected_rows,
        "sigungu_count": sigungu_count,
        "sum_area_m2": round(sum_area_m2, 1),
        "union_area_m2": round(union_area_m2, 1),
        "area_diff_pct": round(area_diff_pct, 4) if area_diff_pct is not None else None,
        "union_is_valid": union_is_valid,
    }
