import json
from urllib.parse import parse_qs, urlparse

from layers.tile_params import (
    GREEN_MASK_COLORMAP,
    GREEN_MASK_TILE_PARAMS,
    TRUECOLOR_TILE_PARAMS,
    build_titiler_url,
    titiler_cog_url,
)


def test_build_titiler_url_uses_titiler_public_url_and_real_cog_tile_path(settings):
    """TiTiler 0.18 실제 REST 경로(/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png)와
    TITILER_PUBLIC_URL(브라우저가 접근하는 주소)을 쓰는지 확인한다(실측 확인 전엔
    존재하지 않는 "/tiles/{z}/{x}/{y}" 경로였다)."""
    settings.TITILER_PUBLIC_URL = "http://localhost:8001"

    url = build_titiler_url("/data/cog/green_2026_summer.tif", GREEN_MASK_TILE_PARAMS)

    assert url.startswith("http://localhost:8001/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?")
    query = urlparse(url).query
    params = parse_qs(query)
    assert params["url"] == [titiler_cog_url("/data/cog/green_2026_summer.tif")]
    assert params["nodata"] == ["255"]


def test_build_titiler_url_colormap_round_trips_to_original_dict():
    """사용자 최종 지시: colormap JSON이 urlencode로 인코딩되고, 디코딩하면 원래 dict와
    같은지 확인한다."""
    url = build_titiler_url("/data/cog/green_2026_summer.tif", GREEN_MASK_TILE_PARAMS)

    query = urlparse(url).query
    params = parse_qs(query)
    decoded_colormap = json.loads(params["colormap"][0])

    assert decoded_colormap == GREEN_MASK_COLORMAP


def test_build_titiler_url_doseq_encodes_list_valued_bidx_as_repeated_keys():
    url = build_titiler_url("/data/cog/truecolor_2026_summer.tif", TRUECOLOR_TILE_PARAMS)

    query = urlparse(url).query
    params = parse_qs(query)

    assert params["bidx"] == ["1", "2", "3"]
    assert params["rescale"] == ["0,3000"]


def test_titiler_cog_url_maps_api_mount_point_to_titiler_mount_point():
    url = titiler_cog_url("/app/docker/data/cog/green_2026_summer.tif")

    assert url == "/data/cog/green_2026_summer.tif"
