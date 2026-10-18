"""생활안전지도 WMS GetFeatureInfo 클라이언트(spec 8-3·8-4).

WMS 1.1.1, 좌표계는 srs=EPSG:3857, BBOX는 minx,miny,maxx,maxy 순서, 인증은 serviceKey
쿼리 파라미터(사용자 확인). TY_NM은 인코딩이 깨져 오므로 쓰지 않고 TY_CD로 판별한다(spec 8-3).
"""
import httpx
from django.conf import settings

from core.exceptions import ExternalCallError

WMS_BASE_URL = "https://safemap.go.kr/openapi2/IF_0087_WMS"
LAYER_NAME = "A2SM_CRMNLHSPOT_TOT"
STYLE_NAME = "A2SM_CrmnlHspot_Tot_Tot"
TARGET_TY_CD = "10201000"  # 전체(spec 8-3)

# GetFeatureInfo에 쓰는 가상 이미지 크기 — 중앙 클릭 + 전체를 덮는 버퍼로 셀 안 전체 구간을 받는
# 용도일 뿐이라 실제 렌더링과는 무관하다(spec 8-4: "조회 지점은 구역 중앙, 픽셀 버퍼는 구역
# 전체를 덮는 크기").
TILE_PIXELS = 512
REQUESTED_FEATURE_COUNT = 2000


def fetch_feature_info(
    client: httpx.Client, bbox_3857: tuple[float, float, float, float], feature_count: int
) -> list[dict]:
    """bbox(EPSG:3857) 전체를 덮는 GetFeatureInfo 호출 1회. TY_CD==전체만 걸러 돌려준다."""
    if not settings.SAFEMAP_API_KEY:
        raise ValueError("SAFEMAP_API_KEY가 설정되지 않았습니다.")

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
        "serviceKey": settings.SAFEMAP_API_KEY,
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
    return [
        f for f in features if str(f.get("properties", {}).get("TY_CD")) == TARGET_TY_CD
    ]
