"""생활안전지도 WMS 클라이언트: 요청 URL·파라미터, 상태코드별 예외 분기를 httpx(respx)로
검증한다(spec 9-5: "외부 API는 녹화한 응답으로 목 처리")."""
import httpx
import pytest
import respx

from core.exceptions import ExternalCallError
from crime import safemap_client

BBOX = (100.0, 200.0, 2100.0, 2200.0)


def _feature(objt_id, grad, ty_cd="10201000"):
    return {
        "type": "Feature",
        "properties": {"OBJT_ID": objt_id, "TY_CD": ty_cd, "GRAD": grad},
        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
    }


@pytest.fixture(autouse=True)
def _service_key(settings):
    settings.SAFEMAP_API_KEY = "test-service-key"


def test_requires_service_key_configured(settings):
    settings.SAFEMAP_API_KEY = ""

    with httpx.Client() as client, pytest.raises(ValueError):
        safemap_client.fetch_feature_info(client, BBOX, 100)


@respx.mock
def test_sends_wms_1_1_1_request_with_service_key_and_bbox_order():
    route = respx.get(safemap_client.WMS_BASE_URL).mock(
        return_value=httpx.Response(200, json={"features": []})
    )

    with httpx.Client() as client:
        safemap_client.fetch_feature_info(client, BBOX, 2000)

    sent = route.calls.last.request.url.params
    assert sent["service"] == "WMS"
    assert sent["version"] == "1.1.1"
    assert sent["request"] == "GetFeatureInfo"
    assert sent["layers"] == safemap_client.LAYER_NAME
    assert sent["query_layers"] == safemap_client.LAYER_NAME
    assert sent["styles"] == safemap_client.STYLE_NAME
    assert sent["srs"] == "EPSG:3857"
    assert sent["bbox"] == "100.0,200.0,2100.0,2200.0"  # minx,miny,maxx,maxy
    assert sent["feature_count"] == "2000"
    assert sent["info_format"] == "application/json"
    assert sent["serviceKey"] == "test-service-key"


@respx.mock
def test_filters_out_features_with_other_ty_cd():
    respx.get(safemap_client.WMS_BASE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "features": [
                    _feature("A1", 7, ty_cd="10201000"),
                    _feature("A2", 3, ty_cd="99999999"),  # 다른 유형 -> 제외
                ]
            },
        )
    )

    with httpx.Client() as client:
        features = safemap_client.fetch_feature_info(client, BBOX, 2000)

    assert [f["properties"]["OBJT_ID"] for f in features] == ["A1"]


@pytest.mark.parametrize("status_code", [429, 500, 502, 503])
@respx.mock
def test_retryable_status_codes_raise_external_call_error(status_code):
    respx.get(safemap_client.WMS_BASE_URL).mock(return_value=httpx.Response(status_code))

    with httpx.Client() as client, pytest.raises(ExternalCallError):
        safemap_client.fetch_feature_info(client, BBOX, 2000)


@pytest.mark.parametrize("status_code", [400, 401, 404])
@respx.mock
def test_non_retryable_status_codes_raise_value_error(status_code):
    respx.get(safemap_client.WMS_BASE_URL).mock(
        return_value=httpx.Response(status_code, text="bad request")
    )

    with httpx.Client() as client, pytest.raises(ValueError):
        safemap_client.fetch_feature_info(client, BBOX, 2000)


@respx.mock
def test_timeout_raises_external_call_error():
    respx.get(safemap_client.WMS_BASE_URL).mock(side_effect=httpx.TimeoutException("timed out"))

    with httpx.Client() as client, pytest.raises(ExternalCallError):
        safemap_client.fetch_feature_info(client, BBOX, 2000)


@respx.mock
def test_connection_error_raises_external_call_error():
    respx.get(safemap_client.WMS_BASE_URL).mock(side_effect=httpx.ConnectError("refused"))

    with httpx.Client() as client, pytest.raises(ExternalCallError):
        safemap_client.fetch_feature_info(client, BBOX, 2000)
