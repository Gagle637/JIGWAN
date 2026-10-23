"""건물 반경 범죄 지표(spec 8-5) — 조회 시 반경과 겹치는 crime_segment로 계산한다."""
from django.db import connection

NEAR_RADIUS_M = 50
HIGH_GRAD_THRESHOLD = 8  # spec 8-5: 적색 계열(8~10등급)을 고등급으로 둔다

# GEOS 3.9.0(PostGIS 3.4.3이 쓰는 버전)의 OverlayNG가 한 지오메트리가 다른 지오메트리에
# 완전히 포함되는(경계를 안 건너는) 경우 ST_Intersection을 빈 지오메트리로 돌리는 버그가 있다
# (실측 확인됨: ST_Within/ST_Covers는 true인데 ST_Intersection(a,b)는 빈 지오메트리).
# 3번째 인자로 gridSize를 주면 안정적인 FixedPrecision 오버레이 경로를 타 정확한 결과가 나온다.
_OVERLAY_GRID_SIZE_DEG = 0.0000001  # 약 1cm — 면적(㎡) 계산에 영향 없는 정밀도

_SEGMENTS_IN_RADIUS_SQL = """
WITH b AS (SELECT geom FROM building WHERE id = %(building_id)s),
     radius AS (SELECT ST_Buffer(geom::geography, %(radius)s)::geometry AS g FROM b),
     near AS (SELECT ST_Buffer(geom::geography, %(near_radius)s)::geometry AS g FROM b)
SELECT
    cs.grad,
    ST_Area(ST_Intersection(cs.geom, radius.g, %(grid_size)s)::geography) AS area_m2,
    ST_Intersects(cs.geom, near.g) AS within_near
FROM crime_segment cs, radius, near
WHERE ST_Intersects(cs.geom, radius.g)
"""


def compute_crime_stats(building, radius_m: int) -> dict | None:
    """spec 8-5. None이면 반경과 겹치는 범죄주의구간이 전혀 없다는 뜻('주의구간 미지정')."""
    with connection.cursor() as cur:
        cur.execute(
            _SEGMENTS_IN_RADIUS_SQL,
            {
                "building_id": building.id,
                "radius": radius_m,
                "near_radius": NEAR_RADIUS_M,
                "grid_size": _OVERLAY_GRID_SIZE_DEG,
            },
        )
        rows = cur.fetchall()

    if not rows:
        return None

    max_grad = max(grad for grad, _, _ in rows)
    near_grads = [grad for grad, _, within_near in rows if within_near]
    near_grad = max(near_grads) if near_grads else None

    flagged_area_m2 = sum(area_m2 or 0.0 for _, area_m2, _ in rows)
    high_area_m2 = sum(
        area_m2 or 0.0 for grad, area_m2, _ in rows if grad >= HIGH_GRAD_THRESHOLD
    )
    high_share_pct = (
        round(high_area_m2 / flagged_area_m2 * 100, 1) if flagged_area_m2 else 0.0
    )

    return {
        "max_grad": max_grad,
        "near_grad": near_grad,
        "flagged_area_m2": round(flagged_area_m2, 1),
        "high_share_pct": high_share_pct,
    }
