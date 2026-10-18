"""건물 반경 범죄 지표(spec 8-5) — 조회 시 반경과 겹치는 crime_segment로 계산한다."""
from django.db import connection

NEAR_RADIUS_M = 50
HIGH_GRAD_THRESHOLD = 8  # spec 8-5: 적색 계열(8~10등급)을 고등급으로 둔다

_SEGMENTS_IN_RADIUS_SQL = """
WITH b AS (SELECT geom FROM building WHERE id = %(building_id)s),
     radius AS (SELECT ST_Buffer(geom::geography, %(radius)s)::geometry AS g FROM b),
     near AS (SELECT ST_Buffer(geom::geography, %(near_radius)s)::geometry AS g FROM b)
SELECT
    cs.grad,
    ST_Length(ST_Intersection(cs.geom, radius.g)::geography) AS length_m,
    ST_Intersects(cs.geom, near.g) AS within_near
FROM crime_segment cs, radius, near
WHERE ST_Intersects(cs.geom, radius.g)
"""


def compute_crime_stats(building, radius_m: int) -> dict | None:
    """spec 8-5. None이면 반경과 겹치는 범죄주의구간이 전혀 없다는 뜻('주의구간 미지정')."""
    with connection.cursor() as cur:
        cur.execute(
            _SEGMENTS_IN_RADIUS_SQL,
            {"building_id": building.id, "radius": radius_m, "near_radius": NEAR_RADIUS_M},
        )
        rows = cur.fetchall()

    if not rows:
        return None

    max_grad = max(grad for grad, _, _ in rows)
    near_grads = [grad for grad, _, within_near in rows if within_near]
    near_grad = max(near_grads) if near_grads else None

    flagged_length_m = sum(length_m or 0.0 for _, length_m, _ in rows)
    high_length_m = sum(
        length_m or 0.0 for grad, length_m, _ in rows if grad >= HIGH_GRAD_THRESHOLD
    )
    high_share_pct = (
        round(high_length_m / flagged_length_m * 100, 1) if flagged_length_m else 0.0
    )

    return {
        "max_grad": max_grad,
        "near_grad": near_grad,
        "flagged_length_m": round(flagged_length_m, 1),
        "high_share_pct": high_share_pct,
    }
