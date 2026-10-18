"""건물 벡터 타일(ST_AsMVT). 줌 14 미만은 DB를 건드리지 않고 바로 빈 타일을 돌려준다."""
import logging
import time

from django.db import connection

logger = logging.getLogger(__name__)

MIN_ZOOM = 14

_TILE_SQL = """
WITH bounds AS (
    SELECT ST_TileEnvelope(%s, %s, %s) AS tile_3857
),
mvtgeom AS (
    SELECT
        ST_AsMVTGeom(ST_Transform(b.geom, 3857), bounds.tile_3857) AS geom,
        b.id, b.use_name, b.floors_above
    FROM building b, bounds
    WHERE b.is_active
      AND ST_Intersects(b.geom, ST_Transform(bounds.tile_3857, 4326))
)
SELECT ST_AsMVT(mvtgeom, 'buildings') FROM mvtgeom
"""


def render_building_tile(z: int, x: int, y: int) -> bytes:
    started = time.perf_counter()
    if z < MIN_ZOOM:
        tile = b""
    else:
        with connection.cursor() as cur:
            cur.execute(_TILE_SQL, [z, x, y])
            row = cur.fetchone()
            tile = bytes(row[0]) if row and row[0] else b""

    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info("building tile z=%s x=%s y=%s bytes=%s ms=%.1f", z, x, y, len(tile), elapsed_ms)
    return tile
