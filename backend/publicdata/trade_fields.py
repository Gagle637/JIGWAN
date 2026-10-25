"""실거래 8종 응답 태그 -> 공통 중간 dict 정규화(spec 8-7).

molit_client가 XML을 읽을 때 태그를 전부 소문자로 바꿔 주므로, 여기서는 소문자 키만 다룬다.
"""
from datetime import datetime

from .models import Trade
from .pnu import build_pnu_from_apt_sale


def _clean(value) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _to_int(value) -> int | None:
    text = _clean(value)
    return int(text) if text is not None else None


def _to_float(value) -> float | None:
    text = _clean(value)
    return float(text) if text is not None else None


def _to_amount(value) -> int | None:
    """만원 단위, 쉼표 제거 후 정수로(spec 8-7)."""
    text = _clean(value)
    if text is None:
        return None
    return int(text.replace(",", "").strip())


def _deal_ym(raw: dict) -> str | None:
    year = _to_int(raw.get("dealyear"))
    month = _to_int(raw.get("dealmonth"))
    if year is None or month is None:
        return None
    return f"{year:04d}-{month:02d}"


def _parse_cancel(raw: dict) -> tuple[bool, "datetime.date | None"]:
    """해제여부 'O' -> is_canceled=True. 해제사유발생일 'YY.MM.DD' -> date(spec 8-7)."""
    is_canceled = _clean(raw.get("cdealtype")) == "O"
    canceled_at = None
    day_text = _clean(raw.get("cdealday"))
    if day_text:
        try:
            canceled_at = datetime.strptime(day_text, "%y.%m.%d").date()
        except ValueError:
            canceled_at = None
    return is_canceled, canceled_at


def _base(raw: dict, house_type: str, deal_type: str) -> dict:
    return {
        "house_type": house_type,
        "deal_type": deal_type,
        "sgg_code": _clean(raw.get("sggcd")),
        "bjd_name": _clean(raw.get("umdnm")),
        "jibun_raw": _clean(raw.get("jibun")),
        "apt_seq": None,
        "building_name": None,
        "area_m2": None,
        "price": None,
        "deposit": None,
        "monthly_rent": None,
        "deal_ym": _deal_ym(raw),
        "deal_day": _to_int(raw.get("dealday")),
        "is_canceled": False,
        "canceled_at": None,
        "floor": _to_int(raw.get("floor")),
        "build_year": _to_int(raw.get("buildyear")),
        "pnu_hint": None,
    }


def normalize_apt_trade(raw: dict) -> dict:
    """RTMSDataSvcAptTradeDev — PNU를 응답만으로 바로 조립할 수 있다(spec 8-7)."""
    item = _base(raw, Trade.HouseType.APARTMENT, Trade.DealType.SALE)
    is_canceled, canceled_at = _parse_cancel(raw)

    sgg_cd, umd_cd, land_cd = _clean(raw.get("sggcd")), _clean(raw.get("umdcd")), _clean(raw.get("landcd"))
    bonbun, bubun = _clean(raw.get("bonbun")), _clean(raw.get("bubun"))
    pnu_hint = None
    if sgg_cd and umd_cd and land_cd and bonbun and bubun:
        pnu_hint = build_pnu_from_apt_sale(sgg_cd, umd_cd, land_cd, bonbun, bubun)

    item.update(
        apt_seq=_clean(raw.get("aptseq")),
        building_name=_clean(raw.get("aptnm")),
        area_m2=_to_float(raw.get("excluusear")),
        price=_to_amount(raw.get("dealamount")),
        is_canceled=is_canceled,
        canceled_at=canceled_at,
        pnu_hint=pnu_hint,
    )
    return item


def normalize_apt_rent(raw: dict) -> dict:
    """RTMSDataSvcAptRent — 해제 항목 없음, aptSeq로 매매 기록과 먼저 엮는다(spec 8-7)."""
    item = _base(raw, Trade.HouseType.APARTMENT, Trade.DealType.RENT)
    item.update(
        apt_seq=_clean(raw.get("aptseq")),
        building_name=_clean(raw.get("aptnm")),
        area_m2=_to_float(raw.get("excluusear")),
        deposit=_to_amount(raw.get("deposit")),
        monthly_rent=_to_amount(raw.get("monthlyrent")),
    )
    return item


def normalize_offi_trade(raw: dict) -> dict:
    item = _base(raw, Trade.HouseType.OFFICETEL, Trade.DealType.SALE)
    is_canceled, canceled_at = _parse_cancel(raw)
    item.update(
        building_name=_clean(raw.get("offinm")),
        area_m2=_to_float(raw.get("excluusear")),
        price=_to_amount(raw.get("dealamount")),
        is_canceled=is_canceled,
        canceled_at=canceled_at,
    )
    return item


def normalize_offi_rent(raw: dict) -> dict:
    """해제 항목 없음(spec 8-7)."""
    item = _base(raw, Trade.HouseType.OFFICETEL, Trade.DealType.RENT)
    item.update(
        building_name=_clean(raw.get("offinm")),
        area_m2=_to_float(raw.get("excluusear")),
        deposit=_to_amount(raw.get("deposit")),
        monthly_rent=_to_amount(raw.get("monthlyrent")),
    )
    return item


def normalize_rh_trade(raw: dict) -> dict:
    item = _base(raw, Trade.HouseType.ROW_HOUSE, Trade.DealType.SALE)
    is_canceled, canceled_at = _parse_cancel(raw)
    item.update(
        building_name=_clean(raw.get("mhousenm")),
        area_m2=_to_float(raw.get("excluusear")),
        price=_to_amount(raw.get("dealamount")),
        is_canceled=is_canceled,
        canceled_at=canceled_at,
    )
    return item


def normalize_rh_rent(raw: dict) -> dict:
    """해제 항목 없음(spec 8-7)."""
    item = _base(raw, Trade.HouseType.ROW_HOUSE, Trade.DealType.RENT)
    item.update(
        building_name=_clean(raw.get("mhousenm")),
        area_m2=_to_float(raw.get("excluusear")),
        deposit=_to_amount(raw.get("deposit")),
        monthly_rent=_to_amount(raw.get("monthlyrent")),
    )
    return item


def normalize_sh_trade(raw: dict) -> dict:
    """단독다가구 매매 — 지번이 가려지는 경우가 많고, 면적은 연면적(totalFloorAr)로 온다(spec 8-7)."""
    item = _base(raw, Trade.HouseType.DETACHED, Trade.DealType.SALE)
    is_canceled, canceled_at = _parse_cancel(raw)
    item.update(
        area_m2=_to_float(raw.get("totalfloorar")),
        price=_to_amount(raw.get("dealamount")),
        is_canceled=is_canceled,
        canceled_at=canceled_at,
        floor=None,  # 단독다가구는 floor 태그가 없다(spec 8-7)
    )
    return item


def normalize_sh_rent(raw: dict) -> dict:
    """단독다가구 전월세 — 지번 태그가 아예 없다(spec 8-7)."""
    item = _base(raw, Trade.HouseType.DETACHED, Trade.DealType.RENT)
    item.update(
        jibun_raw=None,
        area_m2=_to_float(raw.get("totalfloorar")),
        deposit=_to_amount(raw.get("deposit")),
        monthly_rent=_to_amount(raw.get("monthlyrent")),
        floor=None,
    )
    return item


# 서비스명(spec 8-7) -> 정규화 함수. 수집 순서는 sync.py에서 아파트 매매를 명시적으로 먼저 돌린다.
# RTMSDataSvcRHTrade는 국토부가 RTMSDataSvcRHTrade2로 올려서 예전 이름은 더 이상 등록돼 있지
# 않다(실측 확인: SERVICE_KEY_IS_NOT_REGISTERED_ERROR, 공공데이터포털에서 현재 Base URL 재확인).
SERVICES = {
    "RTMSDataSvcAptTradeDev": normalize_apt_trade,
    "RTMSDataSvcAptRent": normalize_apt_rent,
    "RTMSDataSvcOffiTrade": normalize_offi_trade,
    "RTMSDataSvcOffiRent": normalize_offi_rent,
    "RTMSDataSvcRHTrade2": normalize_rh_trade,
    "RTMSDataSvcRHRent": normalize_rh_rent,
    "RTMSDataSvcSHTrade": normalize_sh_trade,
    "RTMSDataSvcSHRent": normalize_sh_rent,
}
