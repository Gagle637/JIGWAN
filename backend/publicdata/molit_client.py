"""국토부 실거래가 8종 httpx 비동기 클라이언트(spec 8-7).

XML 태그는 문서마다 대소문자가 섞여 있어(예: roadnm, cdealtype) 전부 소문자로 통일해 다룬다.
전부 https로 호출한다.
"""
import xml.etree.ElementTree as ET

import httpx

from core.exceptions import ExternalCallError

BASE_URL = "https://apis.data.go.kr/1613000/{service}/get{service}"

# 재시도할 오류: 01(내부 오류), 04(HTTP), 05(타임아웃), 23(초당 한도 초과). 나머지는 즉시 실패(spec 8-7).
RETRYABLE_RESULT_CODES = {"01", "04", "05", "23"}


def _find_ci(root: ET.Element, tag_lower: str) -> ET.Element | None:
    for el in root.iter():
        if el.tag.lower() == tag_lower:
            return el
    return None


def _item_to_dict(item: ET.Element) -> dict:
    return {child.tag.lower(): child.text for child in item}


def parse_response(text: str, service: str) -> tuple[list[dict], int]:
    """XML 응답 -> (item dict 리스트(태그 소문자 키), totalCount). 비정상 resultCode는 예외로 알린다."""
    root = ET.fromstring(text)

    result_code_el = _find_ci(root, "resultcode")
    result_code = (result_code_el.text or "").strip() if result_code_el is not None else None

    if result_code != "000":
        message_el = _find_ci(root, "resultmsg")
        message = (message_el.text or "").strip() if message_el is not None else "알 수 없는 오류"
        if result_code in RETRYABLE_RESULT_CODES:
            raise ExternalCallError(f"{service} resultCode={result_code} {message}")
        raise ValueError(f"{service} resultCode={result_code} {message}")

    total_count_el = _find_ci(root, "totalcount")
    total_count = (
        int(total_count_el.text) if total_count_el is not None and total_count_el.text else 0
    )

    items = [_item_to_dict(el) for el in root.iter() if el.tag.lower() == "item"]
    return items, total_count


async def fetch_page(
    client: httpx.AsyncClient,
    service: str,
    service_key: str,
    lawd_cd: str,
    deal_ymd: str,
    page_no: int,
    num_of_rows: int = 1000,
) -> tuple[list[dict], int]:
    url = BASE_URL.format(service=service)
    params = {
        "serviceKey": service_key,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
    }
    try:
        response = await client.get(url, params=params, timeout=30)
    except httpx.TimeoutException as exc:
        raise ExternalCallError(f"{service} 타임아웃: {exc}") from exc
    except httpx.HTTPError as exc:
        raise ExternalCallError(f"{service} 요청 오류: {exc}") from exc

    if response.status_code >= 500:
        raise ExternalCallError(f"{service} HTTP {response.status_code}")
    if response.status_code >= 400:
        raise ValueError(f"{service} HTTP {response.status_code}")

    return parse_response(response.text, service)


async def fetch_all(
    client: httpx.AsyncClient,
    semaphore,
    service: str,
    service_key: str,
    lawd_cd: str,
    deal_ymd: str,
    num_of_rows: int = 1000,
) -> list[dict]:
    """totalCount까지 페이지를 순회해 전부 모은다. 세마포어로 동시 호출 수를 제한한다."""
    async with semaphore:
        items, total_count = await fetch_page(
            client, service, service_key, lawd_cd, deal_ymd, 1, num_of_rows
        )

    all_items = list(items)
    page_no = 2
    while len(all_items) < total_count:
        async with semaphore:
            items, _ = await fetch_page(
                client, service, service_key, lawd_cd, deal_ymd, page_no, num_of_rows
            )
        if not items:
            break
        all_items.extend(items)
        page_no += 1

    return all_items
