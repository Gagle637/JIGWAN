import asyncio

import httpx
import pytest
import respx

from core.exceptions import ExternalCallError
from publicdata import molit_client

SUCCESS_XML = """<response>
<header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>
<body>
<items>
<item><sggCd>30110</sggCd><umdNm>효동</umdNm><cdealType> </cdealType></item>
</items>
<numOfRows>10</numOfRows><pageNo>1</pageNo><totalCount>1</totalCount>
</body>
</response>"""

SERVICE_URL = "https://apis.data.go.kr/1613000/TestService/getTestService"


def _error_xml(code: str) -> str:
    return (
        f"<response><header><resultCode>{code}</resultCode>"
        f"<resultMsg>ERR</resultMsg></header></response>"
    )


def test_parse_response_extracts_items_case_insensitively():
    items, total = molit_client.parse_response(SUCCESS_XML, "svc")
    assert total == 1
    assert len(items) == 1
    assert items[0]["sggcd"] == "30110"
    assert items[0]["umdnm"] == "효동"


@pytest.mark.parametrize("code", ["01", "04", "05", "23"])
def test_parse_response_retryable_codes_raise_external_call_error(code):
    with pytest.raises(ExternalCallError):
        molit_client.parse_response(_error_xml(code), "svc")


@pytest.mark.parametrize("code", ["10", "12", "20", "30", "31", "22"])
def test_parse_response_nonretryable_codes_raise_value_error(code):
    with pytest.raises(ValueError):
        molit_client.parse_response(_error_xml(code), "svc")


@respx.mock
def test_fetch_page_sends_expected_params():
    route = respx.get(SERVICE_URL).mock(return_value=httpx.Response(200, text=SUCCESS_XML))

    async def run():
        async with httpx.AsyncClient() as client:
            return await molit_client.fetch_page(
                client, "TestService", "KEY", "30110", "202609", 1
            )

    items, total = asyncio.run(run())

    assert total == 1
    assert route.called
    request = route.calls.last.request
    assert request.url.params["serviceKey"] == "KEY"
    assert request.url.params["LAWD_CD"] == "30110"
    assert request.url.params["DEAL_YMD"] == "202609"


@respx.mock
def test_fetch_page_server_error_is_retryable():
    respx.get(SERVICE_URL).mock(return_value=httpx.Response(500))

    async def run():
        async with httpx.AsyncClient() as client:
            await molit_client.fetch_page(client, "TestService", "KEY", "30110", "202609", 1)

    with pytest.raises(ExternalCallError):
        asyncio.run(run())


@respx.mock
def test_fetch_page_client_error_is_not_retryable():
    respx.get(SERVICE_URL).mock(return_value=httpx.Response(400))

    async def run():
        async with httpx.AsyncClient() as client:
            await molit_client.fetch_page(client, "TestService", "KEY", "30110", "202609", 1)

    with pytest.raises(ValueError):
        asyncio.run(run())


@respx.mock
def test_fetch_page_timeout_is_retryable():
    respx.get(SERVICE_URL).mock(side_effect=httpx.TimeoutException("boom"))

    async def run():
        async with httpx.AsyncClient() as client:
            await molit_client.fetch_page(client, "TestService", "KEY", "30110", "202609", 1)

    with pytest.raises(ExternalCallError):
        asyncio.run(run())


@respx.mock
def test_fetch_all_paginates_until_total_count():
    page_xml = """<response><header><resultCode>000</resultCode></header><body>
    <items><item><sggCd>30110</sggCd></item></items>
    <totalCount>2</totalCount></body></response>"""

    respx.get(SERVICE_URL).mock(
        side_effect=[
            httpx.Response(200, text=page_xml),
            httpx.Response(200, text=page_xml),
        ]
    )

    async def run():
        semaphore = asyncio.Semaphore(5)
        async with httpx.AsyncClient() as client:
            return await molit_client.fetch_all(
                client, semaphore, "TestService", "KEY", "30110", "202609", num_of_rows=1
            )

    items = asyncio.run(run())
    assert len(items) == 2
