"""TiTiler 표시 파라미터(결정 사항 9) — insight.change.tiles와 map_layer.source_params가
같은 값을 쓰도록 한 곳에서 관리한다."""
import json
from pathlib import Path
from urllib.parse import urlencode

TRUECOLOR_TILE_PARAMS = {"bidx": [1, 2, 3], "rescale": "0,3000"}
GREEN_MASK_COLORMAP = {"0": [0, 0, 0, 0], "1": [34, 139, 34, 255]}
GREEN_MASK_TILE_PARAMS = {"nodata": 255, "colormap": json.dumps(GREEN_MASK_COLORMAP)}


def titiler_cog_url(cog_path: str) -> str:
    """API 컨테이너 기준 결과 COG 절대경로를 TiTiler 컨테이너가 보는 경로로 바꾼다 — 둘 다
    같은 호스트 디렉터리(docker/data/cog)를 마운트하지만 마운트 지점이 다르다
    (api=/app/docker/data/cog, titiler=/data/cog)."""
    return f"/data/cog/{Path(cog_path).name}"


def build_titiler_url(cog_path: str, params: dict) -> str:
    """'/tiles/{z}/{x}/{y}?url=...&...' 템플릿을 만든다. urlencode(doseq=True)로 bidx처럼
    리스트 값은 bidx=1&bidx=2&bidx=3 형태로, colormap 같은 JSON 문자열은 그대로 퍼센트
    인코딩된다."""
    query = urlencode({"url": titiler_cog_url(cog_path), **params}, doseq=True)
    return f"/tiles/{{z}}/{{x}}/{{y}}?{query}"
