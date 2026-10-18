"""건물 반경(spec 3-2) raw SQL 헬퍼 — 4326(카탈로그 bbox 교차 검색용)과
32652(실제 마스킹용) 버퍼를 한 번에 뽑는다."""
import json

from django.db import connection

_BUFFER_SQL = """
SELECT
    ST_AsGeoJSON(ST_Buffer(geom::geography, %(radius)s)::geometry) AS buffer_4326,
    ST_AsGeoJSON(ST_Transform(ST_Buffer(geom::geography, %(radius)s)::geometry, 32652)) AS buffer_32652
FROM building WHERE id = %(building_id)s
"""


def building_radius_buffers(building_id: int, radius_m: int) -> dict:
    """{"buffer_4326": <GeoJSON dict>, "buffer_32652": <GeoJSON dict>}."""
    with connection.cursor() as cur:
        cur.execute(_BUFFER_SQL, {"radius": radius_m, "building_id": building_id})
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"건물 {building_id}을 찾을 수 없습니다.")
    buffer_4326, buffer_32652 = row
    return {
        "buffer_4326": json.loads(buffer_4326),
        "buffer_32652": json.loads(buffer_32652),
    }
