"""대량 GIS 데이터를 staging 테이블 COPY 후 upsert로 반영하는 공용 헬퍼.

building(소프트 삭제 있음)과 region(소프트 삭제 없음) 둘 다 이 함수 하나로 처리한다.
"교체"(TRUNCATE) 모드는 두 경우 모두 upsert로 바뀌어 쓰이지 않으므로 만들지 않았다.
"""
from collections.abc import Iterable, Sequence

from django.db import connection, transaction


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sync_geotable(
    *,
    staging_table: str,
    staging_columns: Sequence[tuple[str, str]],
    rows: Iterable[Sequence],
    final_table: str,
    final_select_sql: str,
    final_columns: Sequence[str],
    conflict_columns: Sequence[str],
    soft_delete_column: str | None = None,
    soft_delete_scope_sql: str | None = None,
    soft_delete_scope_params: Sequence = (),
) -> dict:
    """staging 테이블에 COPY 적재 후, 한 트랜잭션에서 final_table에 upsert로 반영한다.

    - staging_columns: [(컬럼명, SQL 타입), ...]. 지오메트리 컬럼은 원본 SRID를 포함한
      hex EWKB 문자열(`shapely.wkb.dumps(geom, hex=True, srid=...)`)을 그대로 담을 수 있는
      `geometry` 타입으로 선언한다 — COPY는 PostGIS geometry의 텍스트 입력 함수(hex EWKB)를
      그대로 받아들이므로 SQL 함수 호출이 필요 없다.
    - final_select_sql: staging에서 읽어 final_columns 순서로 값을 만드는 SELECT 본문
      (ST_MakeValid/ST_Transform 등을 여기서 수행).
    - conflict_columns가 있는 그대로 ON CONFLICT 대상이 된다(building_key 또는 region_code).
    - soft_delete_column을 주면, staging에 없는 기존 행을 삭제 대신 그 컬럼을 false로 바꾼다.
      None이면 없어진 행은 그대로 둔다(region).
    - soft_delete_scope_sql/soft_delete_scope_params: soft_delete_column을 쓸 때, 비활성화
      대상을 더 좁히는 WHERE 조건 조각(예: "LEFT(f.bjd_code, 2) = %s", [sido_code]) — building처럼
      지역별로 따로 적재하면, staging에 한 지역만 담겨 있어도 다른 지역 행까지 비활성화되는 걸
      막는다(다지역 지원 4단계). None이면 전체 테이블을 기준으로 한다(region은 지역 구분이
      필요 없어 그대로 둔다).

    실패하면 트랜잭션 전체가 롤백되어 staging 테이블도 남지 않고 final_table도 그대로다.
    """
    staging_ident = _quote_ident(staging_table)
    final_ident = _quote_ident(final_table)
    col_names = [name for name, _ in staging_columns]

    with transaction.atomic(), connection.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {staging_ident}")
        col_defs = ", ".join(
            f"{_quote_ident(name)} {sql_type}" for name, sql_type in staging_columns
        )
        cur.execute(f"CREATE TABLE {staging_ident} ({col_defs})")

        copy_sql = (
            f"COPY {staging_ident} ({', '.join(_quote_ident(c) for c in col_names)}) "
            "FROM STDIN"
        )
        loaded_rows = 0
        with cur.copy(copy_sql) as copy:
            for row in rows:
                copy.write_row(row)
                loaded_rows += 1

        conflict_index_cols = ", ".join(_quote_ident(c) for c in conflict_columns)
        cur.execute(f"CREATE INDEX ON {staging_ident} ({conflict_index_cols})")

        if soft_delete_column:
            join_cond = " AND ".join(
                f"s.{_quote_ident(c)} = f.{_quote_ident(c)}" for c in conflict_columns
            )
            scope_clause = f" AND {soft_delete_scope_sql}" if soft_delete_scope_sql else ""
            cur.execute(
                f"""
                UPDATE {final_ident} f
                SET {_quote_ident(soft_delete_column)} = false
                WHERE f.{_quote_ident(soft_delete_column)} = true
                  AND NOT EXISTS (
                    SELECT 1 FROM {staging_ident} s WHERE {join_cond}
                  ){scope_clause}
                """,
                soft_delete_scope_params,
            )

        insert_cols = ", ".join(_quote_ident(c) for c in final_columns)
        update_cols = [c for c in final_columns if c not in conflict_columns]
        update_set = ", ".join(
            f"{_quote_ident(c)} = EXCLUDED.{_quote_ident(c)}" for c in update_cols
        )
        conflict_target = ", ".join(_quote_ident(c) for c in conflict_columns)
        cur.execute(
            f"""
            INSERT INTO {final_ident} ({insert_cols})
            {final_select_sql}
            ON CONFLICT ({conflict_target}) DO UPDATE SET {update_set}
            """
        )
        affected_rows = cur.rowcount

        cur.execute(f"DROP TABLE {staging_ident}")

    return {"loaded_rows": loaded_rows, "affected_rows": affected_rows}
