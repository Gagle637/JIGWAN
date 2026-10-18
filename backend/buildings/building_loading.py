"""building 적재: data/raw/AL_D010_30_*.zip → building 테이블 upsert (spec 8-6)."""
import logging
import re
from pathlib import Path

import shapely.wkb
from django.conf import settings
from django.db.models import Max

from core.gis_load import sync_geotable
from core.jobs import SkipJob

from .mapping import map_building_row
from .models import Building

logger = logging.getLogger(__name__)

SOURCE_SRID = 5186
STAGING_TABLE = "building_staging"

DATA_RAW_DIR = Path(settings.BASE_DIR).parent / "data" / "raw"
_ZIP_NAME_RE = re.compile(r"AL_D010_30_(\d{8})\.zip$")

# geom_src(원본 5186 지오메트리)는 마지막에 둔다 — load_buildings의 row 조립이 이 순서에 의존한다.
BUILDING_STAGING_COLUMNS = [
    ("building_key", "text"),
    ("gis_bldg_id", "text"),
    ("pnu", "text"),
    ("bjd_code", "text"),
    ("bjd_name", "text"),
    ("jibun", "text"),
    ("use_code", "text"),
    ("use_name", "text"),
    ("structure", "text"),
    ("building_area_m2", "double precision"),
    ("approval_date", "date"),
    ("total_floor_area_m2", "double precision"),
    ("land_area_m2", "double precision"),
    ("height_m", "double precision"),
    ("bcr_pct", "double precision"),
    ("far_pct", "double precision"),
    ("is_violation", "boolean"),
    ("name", "text"),
    ("dong_name", "text"),
    ("floors_above", "smallint"),
    ("floors_below", "smallint"),
    ("source_date", "date"),
    ("geom_src", "geometry"),
]

FINAL_COLUMNS = [c for c, _ in BUILDING_STAGING_COLUMNS if c != "geom_src"] + [
    "is_active",
    "geom",
]

FINAL_SELECT_SQL = f"""
SELECT
    building_key, gis_bldg_id, pnu, bjd_code, bjd_name, jibun, use_code, use_name,
    structure, building_area_m2, approval_date, total_floor_area_m2, land_area_m2,
    height_m, bcr_pct, far_pct, is_violation, name, dong_name, floors_above, floors_below,
    source_date,
    true AS is_active,
    ST_Transform(
        CASE WHEN GeometryType(ST_MakeValid(geom_src)) = 'POLYGON'
             THEN ST_MakeValid(geom_src)
             ELSE (
                SELECT d.geom FROM ST_Dump(ST_MakeValid(geom_src)) AS d
                WHERE GeometryType(d.geom) = 'POLYGON'
                ORDER BY ST_Area(d.geom) DESC
                LIMIT 1
             )
        END,
        4326
    ) AS geom
FROM {STAGING_TABLE}
"""


def resolve_building_zip_path(explicit_path: str | None = None) -> Path:
    """explicit_path가 있으면 그대로, 없으면 data/raw/AL_D010_30_*.zip 중
    파일명 끝 8자리 날짜(YYYYMMDD)가 가장 큰 파일을 고른다."""
    if explicit_path:
        path = Path(explicit_path)
        if not path.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
        return path

    candidates = []
    for candidate in DATA_RAW_DIR.glob("AL_D010_30_*.zip"):
        match = _ZIP_NAME_RE.search(candidate.name)
        if match:
            candidates.append((match.group(1), candidate))
    if not candidates:
        raise FileNotFoundError(
            f"{DATA_RAW_DIR}에서 AL_D010_30_*.zip 파일을 찾지 못했습니다."
        )
    candidates.sort(key=lambda pair: pair[0])
    return candidates[-1][1]


def resolve_vsizip_shp_path(zip_path: Path) -> str:
    shp_name = zip_path.stem + ".shp"
    return f"/vsizip/{zip_path.resolve()}/{shp_name}"


def assign_building_keys(records: list[dict]) -> None:
    """gis_bldg_id로 그룹핑. 그룹 크기 1이면 building_key=gis_bldg_id.
    그룹 크기>1이면 (building_area_m2 desc, pnu, jibun, gis_bldg_id)로 완전히 결정적인
    순번을 매겨 gis_bldg_id_1, gis_bldg_id_2, ...로 부여한다(spec: A1 약 460행 중복)."""
    groups: dict[str, list[dict]] = {}
    for record in records:
        groups.setdefault(record["gis_bldg_id"], []).append(record)

    for gis_bldg_id, group in groups.items():
        if len(group) == 1:
            group[0]["building_key"] = gis_bldg_id
            continue
        group.sort(
            key=lambda r: (
                -(r["building_area_m2"] or 0.0),
                r.get("pnu") or "",
                r.get("jibun") or "",
                r["gis_bldg_id"],
            )
        )
        for ordinal, record in enumerate(group, start=1):
            record["building_key"] = f"{gis_bldg_id}_{ordinal}"


def load_buildings(zip_path: Path) -> dict:
    import pyogrio  # 지연 임포트: mapping.py 단위 테스트는 GDAL 없이도 돌게 하기 위함

    vsi_path = resolve_vsizip_shp_path(zip_path)
    gdf = pyogrio.read_dataframe(vsi_path, encoding="cp949")
    if len(gdf) == 0:
        raise ValueError(f"{zip_path}에서 읽은 행이 없습니다.")

    records = []
    approval_date_parse_failed = 0
    missing_pnu = 0
    missing_registry = 0
    invalid_geometry = 0

    for _, row in gdf.iterrows():
        mapped = map_building_row(row)
        if mapped.pop("_approval_date_parse_failed"):
            approval_date_parse_failed += 1
        if not mapped["pnu"]:
            missing_pnu += 1
        if not mapped["use_code"]:
            missing_registry += 1

        geom = row.geometry
        if not geom.is_valid:
            invalid_geometry += 1
        mapped["_geom"] = geom
        records.append(mapped)

    new_source_dates = {r["source_date"] for r in records if r["source_date"]}
    new_source_date = max(new_source_dates) if new_source_dates else None
    current_source_date = Building.objects.aggregate(Max("source_date"))[
        "source_date__max"
    ]
    if (
        new_source_date is not None
        and current_source_date is not None
        and current_source_date == new_source_date
    ):
        raise SkipJob(f"source_date={new_source_date} 이미 적재됨")

    assign_building_keys(records)

    rows = []
    for record in records:
        geom_hex = shapely.wkb.dumps(record.pop("_geom"), hex=True, srid=SOURCE_SRID)
        ordered = [
            record[col] for col, _ in BUILDING_STAGING_COLUMNS if col != "geom_src"
        ]
        ordered.append(geom_hex)
        rows.append(tuple(ordered))

    result = sync_geotable(
        staging_table=STAGING_TABLE,
        staging_columns=BUILDING_STAGING_COLUMNS,
        rows=rows,
        final_table="building",
        final_select_sql=FINAL_SELECT_SQL,
        final_columns=FINAL_COLUMNS,
        conflict_columns=["building_key"],
        soft_delete_column="is_active",
    )

    total = len(records)
    return {
        "total_rows": total,
        "source_date": new_source_date,
        "missing_pnu": missing_pnu,
        "missing_registry": missing_registry,
        "missing_registry_pct": round(missing_registry / total * 100, 1) if total else 0.0,
        "invalid_geometry_fixed": invalid_geometry,
        "approval_date_parse_failed": approval_date_parse_failed,
        **result,
    }
