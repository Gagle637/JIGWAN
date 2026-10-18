"""건물명·동명·'법정동명 지번' 검색(pg_trgm). 건물명은 6.9%만 있어 지번 검색이 기본 경로다."""
from django.db import connection

SEARCH_LIMIT = 20

_SEARCH_SQL = """
SELECT
    id, pnu, name, bjd_name, jibun,
    ST_X(ST_Centroid(geom)) AS lon, ST_Y(ST_Centroid(geom)) AS lat,
    GREATEST(
        similarity(coalesce(name, ''), %(q)s),
        similarity(coalesce(dong_name, ''), %(q)s),
        similarity(coalesce(bjd_name, '') || ' ' || coalesce(jibun, ''), %(q)s)
    ) AS score
FROM building
WHERE is_active AND (
    name ILIKE '%%' || %(q)s || '%%'
    OR dong_name ILIKE '%%' || %(q)s || '%%'
    OR (coalesce(bjd_name, '') || ' ' || coalesce(jibun, '')) ILIKE '%%' || %(q)s || '%%'
)
ORDER BY score DESC
LIMIT %(limit)s
"""


def search_buildings(q: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    with connection.cursor() as cur:
        cur.execute(_SEARCH_SQL, {"q": q, "limit": limit})
        columns = [col[0] for col in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    results = []
    for row in rows:
        address = f"{row['bjd_name'] or ''} {row['jibun'] or ''}".strip() or None
        results.append(
            {
                "id": row["id"],
                "pnu": row["pnu"],
                "address": address,
                "name": row["name"],
                "center": {"lon": row["lon"], "lat": row["lat"]},
            }
        )
    return results
