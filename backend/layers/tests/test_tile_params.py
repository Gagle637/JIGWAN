import json
from urllib.parse import parse_qs, urlparse

from layers.tile_params import (
    GREEN_MASK_COLORMAP,
    GREEN_MASK_TILE_PARAMS,
    TRUECOLOR_TILE_PARAMS,
    build_titiler_url,
    titiler_cog_url,
)


def test_build_titiler_url_uses_urlencode_for_query_string():
    url = build_titiler_url("/data/cog/green_2026_summer.tif", GREEN_MASK_TILE_PARAMS)

    assert url.startswith("/tiles/{z}/{x}/{y}?")
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
