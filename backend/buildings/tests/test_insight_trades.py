import pytest
from rest_framework.test import APIClient

from buildings.models import Building
from publicdata.models import Trade

pytestmark = pytest.mark.django_db


def _square_wkt(lon, lat, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


def _make_building(**overrides):
    defaults = dict(
        building_key="TB1",
        gis_bldg_id="TB1",
        pnu="3011010300101530003",
        bjd_code="3011010300",
        use_code="01000",
        use_name="공동주택",
        source_date="2026-10-06",
        geom=_square_wkt(127.385, 36.351),
    )
    defaults.update(overrides)
    return Building.objects.create(**defaults)


def _make_trade(**overrides):
    defaults = dict(
        sgg_code="30110",
        pnu="OTHER_PNU",
        house_type=Trade.HouseType.APARTMENT,
        deal_type=Trade.DealType.SALE,
        deal_ym="2026-09",
        area_m2=100.0,
        price=50000,  # 만원
        is_canceled=False,
        geom="SRID=4326;POINT(127.3851 36.3511)",  # 건물과 거의 같은 위치
    )
    defaults.update(overrides)
    return Trade.objects.create(**defaults)


def test_trades_house_type_unmapped():
    building = _make_building(use_name="종교시설")
    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})

    body = response.json()
    assert body["trades"] is None
    reasons = {m["field"]: m["reason"] for m in body["missing"]}
    assert reasons["trades"] == "house_type_unmapped"


def test_trades_detached_not_implemented():
    building = _make_building(use_name="단독주택")
    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})

    body = response.json()
    assert body["trades"] is None
    reasons = {m["field"]: m["reason"] for m in body["missing"]}
    assert reasons["trades"] == "detached_house_district_not_implemented"


def test_trades_aggregates_nearby_matched_sales():
    building = _make_building()
    _make_trade(price=50000, area_m2=100.0)  # 500만원/㎡
    _make_trade(price=60000, area_m2=100.0)  # 600만원/㎡

    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["trades"] is not None
    assert body["trades"]["months"] == 24
    assert body["trades"]["count"] == 2
    monthly = body["trades"]["monthly"]
    assert len(monthly) == 1
    assert monthly[0]["ym"] == "2026-09"
    assert monthly[0]["median_price_per_m2"] == 550.0
    assert "trades" not in {m["field"] for m in body["missing"]}


def test_trades_excludes_far_away_sales():
    building = _make_building()
    _make_trade(geom="SRID=4326;POINT(127.5 36.5)")  # 수 km 떨어짐

    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["trades"]["count"] == 0


def test_trades_excludes_unmatched_and_canceled_and_rent():
    building = _make_building()
    _make_trade(pnu=None)  # 매칭 실패
    _make_trade(is_canceled=True)  # 해제
    _make_trade(deal_type=Trade.DealType.RENT, deposit=10000, monthly_rent=0)  # 전월세(단가 집계 제외)

    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["trades"]["count"] == 0


def test_trades_apartment_building_also_includes_row_house_when_unmatched_directly():
    building = _make_building(use_name="공동주택")  # 매칭된 거래 없음 -> 대분류 추정
    _make_trade(house_type=Trade.HouseType.ROW_HOUSE)

    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["trades"]["count"] == 1
