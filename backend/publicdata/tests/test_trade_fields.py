from datetime import date

from publicdata.models import Trade
from publicdata.trade_fields import (
    _to_amount,
    normalize_apt_rent,
    normalize_apt_trade,
    normalize_offi_rent,
    normalize_offi_trade,
    normalize_rh_rent,
    normalize_rh_trade,
    normalize_sh_rent,
    normalize_sh_trade,
)


def test_to_amount_strips_commas():
    assert _to_amount("35,000") == 35000
    assert _to_amount("500") == 500
    assert _to_amount(" ") is None
    assert _to_amount(None) is None


def test_normalize_apt_trade_builds_pnu_hint_and_parses_cancel():
    raw = {
        "sggcd": "30110",
        "umdcd": "10300",
        "landcd": "1",
        "bonbun": "153",
        "bubun": "3",
        "umdnm": "효동",
        "jibun": "153-3",
        "aptnm": "효동아파트",
        "aptseq": "11111111",
        "excluusear": "84.95",
        "dealamount": "35,000",
        "dealyear": "2026",
        "dealmonth": "9",
        "dealday": "12",
        "floor": "7",
        "buildyear": "2009",
        "cdealtype": "O",
        "cdealday": "26.09.20",
    }
    item = normalize_apt_trade(raw)

    assert item["house_type"] == Trade.HouseType.APARTMENT
    assert item["deal_type"] == Trade.DealType.SALE
    assert item["pnu_hint"] == "3011010300" + "1" + "0153" + "0003"
    assert item["price"] == 35000
    assert item["area_m2"] == 84.95
    assert item["deal_ym"] == "2026-09"
    assert item["deal_day"] == 12
    assert item["apt_seq"] == "11111111"
    assert item["is_canceled"] is True
    assert item["canceled_at"] == date(2026, 9, 20)


def test_normalize_apt_trade_blank_cdealtype_is_not_canceled():
    raw = {
        "sggcd": "30110", "umdcd": "10300", "landcd": "1", "bonbun": "153", "bubun": "3",
        "umdnm": "효동", "jibun": "153-3", "aptnm": "효동아파트", "aptseq": "1",
        "excluusear": "84.95", "dealamount": "35,000", "dealyear": "2026", "dealmonth": "9",
        "cdealtype": " ", "cdealday": " ",
    }
    item = normalize_apt_trade(raw)
    assert item["is_canceled"] is False
    assert item["canceled_at"] is None


def test_normalize_apt_rent_has_no_cancel_fields():
    raw = {
        "sggcd": "30110", "umdnm": "효동", "jibun": "153-3", "aptnm": "효동아파트",
        "aptseq": "11111111", "excluusear": "84.95", "deposit": "20,000",
        "monthlyrent": "50", "dealyear": "2026", "dealmonth": "9",
    }
    item = normalize_apt_rent(raw)
    assert item["house_type"] == Trade.HouseType.APARTMENT
    assert item["deal_type"] == Trade.DealType.RENT
    assert item["pnu_hint"] is None
    assert item["apt_seq"] == "11111111"
    assert item["deposit"] == 20000
    assert item["monthly_rent"] == 50
    assert item["is_canceled"] is False


def test_normalize_offi_trade():
    raw = {
        "sggcd": "30140", "umdnm": "은행동", "jibun": "10-1", "offinm": "센트럴오피스텔",
        "excluusear": "45.2", "dealamount": "12,000", "dealyear": "2026", "dealmonth": "8",
        "cdealtype": "O", "cdealday": "26.08.15",
    }
    item = normalize_offi_trade(raw)
    assert item["house_type"] == Trade.HouseType.OFFICETEL
    assert item["building_name"] == "센트럴오피스텔"
    assert item["is_canceled"] is True


def test_normalize_offi_rent_no_apt_seq():
    raw = {
        "sggcd": "30140", "umdnm": "은행동", "jibun": "10-1", "offinm": "센트럴오피스텔",
        "excluusear": "45.2", "deposit": "5,000", "monthlyrent": "40",
        "dealyear": "2026", "dealmonth": "8",
    }
    item = normalize_offi_rent(raw)
    assert item["apt_seq"] is None
    assert item["deposit"] == 5000


def test_normalize_rh_trade():
    raw = {
        "sggcd": "30170", "umdnm": "용문동", "jibun": "5-2", "mhousenm": "행복다세대",
        "excluusear": "59.8", "dealamount": "20,500", "dealyear": "2026", "dealmonth": "7",
    }
    item = normalize_rh_trade(raw)
    assert item["house_type"] == Trade.HouseType.ROW_HOUSE
    assert item["building_name"] == "행복다세대"
    assert item["price"] == 20500


def test_normalize_rh_rent():
    raw = {
        "sggcd": "30170", "umdnm": "용문동", "jibun": "5-2", "mhousenm": "행복다세대",
        "excluusear": "59.8", "deposit": "8,000", "monthlyrent": "0",
        "dealyear": "2026", "dealmonth": "7",
    }
    item = normalize_rh_rent(raw)
    assert item["deal_type"] == Trade.DealType.RENT
    assert item["monthly_rent"] == 0


def test_normalize_sh_trade_uses_total_floor_area_and_has_no_floor():
    raw = {
        "sggcd": "30200", "umdnm": "신성동", "jibun": "99-1",
        "totalfloorar": "120.3", "dealamount": "45,000",
        "dealyear": "2026", "dealmonth": "6", "buildyear": "1998",
        "cdealtype": "O", "cdealday": "26.06.01",
    }
    item = normalize_sh_trade(raw)
    assert item["house_type"] == Trade.HouseType.DETACHED
    assert item["area_m2"] == 120.3
    assert item["floor"] is None
    assert item["build_year"] == 1998
    assert item["is_canceled"] is True


def test_normalize_sh_rent_has_no_jibun():
    raw = {
        "sggcd": "30230", "umdnm": "오정동", "jibun": "안옴",
        "totalfloorar": "95.0", "deposit": "3,000", "monthlyrent": "30",
        "dealyear": "2026", "dealmonth": "5",
    }
    item = normalize_sh_rent(raw)
    assert item["house_type"] == Trade.HouseType.DETACHED
    assert item["deal_type"] == Trade.DealType.RENT
    assert item["jibun_raw"] is None  # spec 8-7: 단독다가구 전월세엔 지번 태그가 아예 없다
