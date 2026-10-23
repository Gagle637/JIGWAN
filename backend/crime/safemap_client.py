"""생활안전지도 WMS GetFeatureInfo 클라이언트(spec 8-3·8-4).

WMS 1.1.1, 좌표계는 srs=EPSG:3857, BBOX는 minx,miny,maxx,maxy 순서. 공식 게이트웨이
(openapi2/IF_0087_WMS, serviceKey 필요)는 GetMap만 허용하고 GetFeatureInfo는 서버에서
차단한다(실측 확인: 대소문자 무관 전부 400) — 지도 화면이 내부적으로 쓰는 GeoServer
엔드포인트(인증 불필요)로 호출한다(spec 8-3). TY_NM은 인코딩이 깨져 오므로 쓰지 않고
TY_CD로 판별한다.
"""
import httpx

from core.exceptions import ExternalCallError

WMS_BASE_URL = "https://www.safemap.go.kr/geoserver_pos/safemap/wms"
LAYER_NAME = "A2SM_CRMNLHSPOT_TOT"
STYLE_NAME = "A2SM_CrmnlHspot_Tot_Tot"
TARGET_TY_CD = 10201000  # 전체(spec 8-3)


def _ty_cd_matches(value) -> bool:
    """TY_CD가 정수가 아니라 실수(예: 10201000.0)로 내려오는 게 실측 확인됐다 —
    문자열 비교(str(10201000.0) != "10201000")는 전부 걸러지는 버그가 있었다."""
    try:
        return int(float(value)) == TARGET_TY_CD
    except (TypeError, ValueError):
        return False


# GetFeatureInfo에 쓰는 가상 이미지 크기 — 중앙 클릭 + 전체를 덮는 버퍼로 셀 안 전체 구간을 받는
# 용도일 뿐이라 실제 렌더링과는 무관하다(spec 8-4: "조회 지점은 구역 중앙, 픽셀 버퍼는 구역
# 전체를 덮는 크기").
TILE_PIXELS = 512
REQUESTED_FEATURE_COUNT = 2000


def fetch_feature_info(
    client: httpx.Client, bbox_3857: tuple[float, float, float, float], feature_count: int
) -> list[dict]:
    """bbox(EPSG:3857) 전체를 덮는 GetFeatureInfo 호출 1회. TY_CD==전체만 걸러 돌려준다."""
    minx, miny, maxx, maxy = bbox_3857
    params = {
        "service": "WMS",
        "version": "1.1.1",
        "request": "GetFeatureInfo",
        "layers": LAYER_NAME,
        "query_layers": LAYER_NAME,
        "styles": STYLE_NAME,
        "srs": "EPSG:3857",
        "bbox": f"{minx},{miny},{maxx},{maxy}",
        "width": TILE_PIXELS,
        "height": TILE_PIXELS,
        "x": TILE_PIXELS // 2,
        "y": TILE_PIXELS // 2,
        "buffer": TILE_PIXELS // 2,
        "feature_count": feature_count,
        "info_format": "application/json",
    }
    try:
        response = client.get(WMS_BASE_URL, params=params, timeout=30)
    except httpx.TimeoutException as exc:
        raise ExternalCallError(f"GetFeatureInfo 타임아웃: {exc}") from exc
    except httpx.HTTPError as exc:
        raise ExternalCallError(f"GetFeatureInfo 요청 오류: {exc}") from exc

    if response.status_code in (429, 503) or response.status_code >= 500:
        raise ExternalCallError(f"GetFeatureInfo HTTP {response.status_code}")
    if response.status_code >= 400:
        raise ValueError(f"GetFeatureInfo HTTP {response.status_code}: {response.text[:200]}")

    data = response.json()
    features = data.get("features", [])
    return [f for f in features if _ty_cd_matches(f.get("properties", {}).get("TY_CD"))]
