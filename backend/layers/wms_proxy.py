"""외부 WMS 레이어 XYZ 타일 중계(spec 10-3). z/x/y -> EPSG:3857 BBOX -> GetMap, 인증키는
서버에서 붙이고 디스크에 30일 캐시한다. 원천 오류면 투명 타일을 반환한다."""
import math
import shutil
import time
from pathlib import Path

import httpx
from django.conf import settings

TILE_PIXELS = 256
TILE_CACHE_TTL_SECONDS = 30 * 24 * 3600  # spec 10-3: 30일(원천이 연 1회 갱신)
_ORIGIN_SHIFT = 2 * math.pi * 6378137 / 2.0  # 20037508.342789244

# 1x1 투명 PNG(원천 오류 시 그대로 반환 — 타일 크기로 늘려 그려도 투명이라 문제 없음).
TRANSPARENT_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a4944415478da6300010000050001a08257390000000049454e44ae426082"
)

# 인증키를 쿼리에 넣을 서비스(사용자 확인: serviceKey 파라미터). 지금은 safemap뿐이지만,
# 같은 서비스의 다른 레이어가 추가돼도 이 한 곳만 보면 된다(spec 10-1 "2단계 후보").
KEY_PARAM_NAME = "serviceKey"
KEYED_HOSTS = {"safemap.go.kr"}


def tile_to_bbox_3857(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """표준 Web Mercator 슬리피 타일 -> EPSG:3857 BBOX(minx,miny,maxx,maxy)."""
    tile_size = _ORIGIN_SHIFT * 2 / (2**z)
    minx = x * tile_size - _ORIGIN_SHIFT
    maxx = (x + 1) * tile_size - _ORIGIN_SHIFT
    maxy = _ORIGIN_SHIFT - y * tile_size
    miny = _ORIGIN_SHIFT - (y + 1) * tile_size
    return minx, miny, maxx, maxy


def _cache_path(layer_id: int, z: int, x: int, y: int) -> Path:
    return Path(settings.CRIME_TILE_CACHE_DIR) / str(layer_id) / str(z) / str(x) / f"{y}.png"


def clear_tile_cache(layer_id: int) -> None:
    """safety_sync 끝에 호출 — 원천 데이터가 갱신됐으니 그 레이어의 캐시를 통째로 비운다."""
    shutil.rmtree(Path(settings.CRIME_TILE_CACHE_DIR) / str(layer_id), ignore_errors=True)


def _build_get_map_params(layer, bbox: tuple[float, float, float, float]) -> dict:
    params = layer.source_params or {}
    minx, miny, maxx, maxy = bbox
    query = {
        "service": "WMS",
        "version": params.get("version", "1.1.1"),
        "request": "GetMap",
        "layers": params["layers"],
        "styles": params.get("styles", ""),
        "srs": params.get("srs", "EPSG:3857"),
        "bbox": f"{minx},{miny},{maxx},{maxy}",
        "width": TILE_PIXELS,
        "height": TILE_PIXELS,
        "format": params.get("format", "image/png"),
        "transparent": "true" if params.get("transparent", True) else "false",
    }
    service_url = params["service_url"]
    host = httpx.URL(service_url).host
    if host in KEYED_HOSTS:
        query[KEY_PARAM_NAME] = settings.SAFEMAP_API_KEY
    return service_url, query


def fetch_wms_tile(layer, z: int, x: int, y: int) -> bytes:
    path = _cache_path(layer.id, z, x, y)
    if path.exists() and (time.time() - path.stat().st_mtime) < TILE_CACHE_TTL_SECONDS:
        return path.read_bytes()

    bbox = tile_to_bbox_3857(z, x, y)
    service_url, params = _build_get_map_params(layer, bbox)

    try:
        response = httpx.get(service_url, params=params, timeout=10)
    except httpx.HTTPError:
        return TRANSPARENT_PNG_BYTES

    if response.status_code != 200 or not response.headers.get("content-type", "").startswith(
        "image"
    ):
        return TRANSPARENT_PNG_BYTES

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return response.content
