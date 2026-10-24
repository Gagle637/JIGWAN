"""대전 bbox를 EPSG:3857 2km 격자로 나누고, 필요하면 4등분한다(spec 8-4).

DAEJEON_BBOX import만 core.areas.get_bbox로 바꿔 둔다(다지역 지원 2단계) — 범죄 쪽 본격
지역화(시도 코드 파라미터화 등)는 3단계에서 한다."""
import math

from rasterio.warp import transform_bounds

from core.areas import get_bbox

CELL_SIZE_M = 2000
MIN_CELL_SIZE_M = 250


def cell_id(minx: float, miny: float, size_m: float) -> str:
    """(minx, miny, size_m)으로 셀을 고유하게 식별한다 — 부모·자식 셀이 크기가 달라 겹치지 않는다."""
    return f"{int(round(minx))}_{int(round(miny))}_{int(round(size_m))}"


def base_cells() -> list[tuple[float, float, float]]:
    """대전 bbox(4326)를 EPSG:3857로 바꿔 2km 배수로 바깥쪽 스냅한 기본 격자."""
    minx, miny, maxx, maxy = transform_bounds("EPSG:4326", "EPSG:3857", *get_bbox("30"))
    minx = math.floor(minx / CELL_SIZE_M) * CELL_SIZE_M
    miny = math.floor(miny / CELL_SIZE_M) * CELL_SIZE_M

    cells = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            cells.append((x, y, CELL_SIZE_M))
            y += CELL_SIZE_M
        x += CELL_SIZE_M
    return cells


def split_cell(minx: float, miny: float, size_m: float) -> list[tuple[float, float, float]]:
    """셀을 4등분한다(자식 크기 = size_m/2)."""
    half = size_m / 2
    return [
        (minx, miny, half),
        (minx + half, miny, half),
        (minx, miny + half, half),
        (minx + half, miny + half, half),
    ]


def cell_bbox(minx: float, miny: float, size_m: float) -> tuple[float, float, float, float]:
    return (minx, miny, minx + size_m, miny + size_m)
