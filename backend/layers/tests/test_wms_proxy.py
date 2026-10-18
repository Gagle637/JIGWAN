import time
from types import SimpleNamespace

import httpx
import pytest

from layers import wms_proxy
from layers.wms_proxy import (
    TRANSPARENT_PNG_BYTES,
    clear_tile_cache,
    fetch_wms_tile,
    tile_to_bbox_3857,
)


def _safemap_layer(**source_param_overrides):
    source_params = {
        "service_url": "https://safemap.go.kr/openapi2/IF_0087_WMS",
        "layers": "A2SM_CRMNLHSPOT_TOT",
        "styles": "A2SM_CrmnlHspot_Tot_Tot",
        "version": "1.1.1",
        "srs": "EPSG:3857",
        "format": "image/png",
        "transparent": True,
    }
    source_params.update(source_param_overrides)
    return SimpleNamespace(id=1, source_params=source_params)


def test_tile_to_bbox_3857_whole_world_at_zoom_zero():
    minx, miny, maxx, maxy = tile_to_bbox_3857(0, 0, 0)

    assert minx == pytest.approx(-wms_proxy._ORIGIN_SHIFT)
    assert miny == pytest.approx(-wms_proxy._ORIGIN_SHIFT)
    assert maxx == pytest.approx(wms_proxy._ORIGIN_SHIFT)
    assert maxy == pytest.approx(wms_proxy._ORIGIN_SHIFT)


def test_tile_to_bbox_3857_is_half_size_one_zoom_level_deeper():
    z, x, y = 5, 10, 7
    bbox_z = tile_to_bbox_3857(z, x, y)
    bbox_deeper = tile_to_bbox_3857(z + 1, x * 2, y * 2)

    width_z = bbox_z[2] - bbox_z[0]
    width_deeper = bbox_deeper[2] - bbox_deeper[0]
    assert width_deeper == pytest.approx(width_z / 2)


def test_build_get_map_params_adds_service_key_for_safemap_host(settings):
    settings.SAFEMAP_API_KEY = "test-key"
    layer = _safemap_layer()

    service_url, params = wms_proxy._build_get_map_params(layer, (0, 0, 100, 100))

    assert service_url == "https://safemap.go.kr/openapi2/IF_0087_WMS"
    assert params["serviceKey"] == "test-key"
    assert params["layers"] == "A2SM_CRMNLHSPOT_TOT"
    assert params["bbox"] == "0,0,100,100"
    assert params["transparent"] == "true"


def test_build_get_map_params_omits_key_for_other_hosts():
    layer = _safemap_layer(service_url="https://example.com/wms")

    _, params = wms_proxy._build_get_map_params(layer, (0, 0, 100, 100))

    assert "serviceKey" not in params


def test_fetch_wms_tile_writes_disk_cache_and_reuses_it(monkeypatch, settings, tmp_path):
    settings.CRIME_TILE_CACHE_DIR = str(tmp_path)
    layer = _safemap_layer()
    calls = {"count": 0}

    def fake_get(url, params=None, timeout=None):
        calls["count"] += 1
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"PNGDATA")

    monkeypatch.setattr(httpx, "get", fake_get)

    first = fetch_wms_tile(layer, 10, 5, 5)
    second = fetch_wms_tile(layer, 10, 5, 5)

    assert first == b"PNGDATA"
    assert second == b"PNGDATA"
    assert calls["count"] == 1  # 두 번째는 디스크 캐시에서 바로 읽는다


def test_fetch_wms_tile_refetches_after_ttl_expires(monkeypatch, settings, tmp_path):
    settings.CRIME_TILE_CACHE_DIR = str(tmp_path)
    layer = _safemap_layer()
    calls = {"count": 0}

    def fake_get(url, params=None, timeout=None):
        calls["count"] += 1
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"PNGDATA")

    monkeypatch.setattr(httpx, "get", fake_get)
    fetch_wms_tile(layer, 10, 5, 5)

    cache_path = wms_proxy._cache_path(layer.id, 10, 5, 5)
    old_time = time.time() - wms_proxy.TILE_CACHE_TTL_SECONDS - 10
    import os

    os.utime(cache_path, (old_time, old_time))

    fetch_wms_tile(layer, 10, 5, 5)

    assert calls["count"] == 2


def test_fetch_wms_tile_returns_transparent_png_on_http_error(monkeypatch, settings, tmp_path):
    settings.CRIME_TILE_CACHE_DIR = str(tmp_path)
    layer = _safemap_layer()

    def fake_get(url, params=None, timeout=None):
        raise httpx.ConnectError("연결 실패")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_wms_tile(layer, 10, 5, 5)

    assert result == TRANSPARENT_PNG_BYTES
    assert not wms_proxy._cache_path(layer.id, 10, 5, 5).exists()  # 실패 응답은 캐시에 안 남는다


def test_fetch_wms_tile_returns_transparent_png_on_non_image_response(
    monkeypatch, settings, tmp_path
):
    settings.CRIME_TILE_CACHE_DIR = str(tmp_path)
    layer = _safemap_layer()

    def fake_get(url, params=None, timeout=None):
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_wms_tile(layer, 10, 5, 5)

    assert result == TRANSPARENT_PNG_BYTES


def test_clear_tile_cache_removes_layer_directory(settings, tmp_path):
    settings.CRIME_TILE_CACHE_DIR = str(tmp_path)
    layer_dir = tmp_path / "1" / "10" / "5"
    layer_dir.mkdir(parents=True)
    (layer_dir / "5.png").write_bytes(b"PNGDATA")

    clear_tile_cache(1)

    assert not (tmp_path / "1").exists()
