import pytest

from buildings.models import Building, Region
from publicdata.matching import (
    build_apt_seq_cache,
    determine_house_types_for_building,
    match_trade,
)
from publicdata.models import Trade


def _square_wkt(lon=127.38, lat=36.35, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


def test_match_trade_detached_is_not_a_failure():
    normalized = {"house_type": Trade.HouseType.DETACHED, "pnu_hint": None}
    pnu, reason = match_trade(normalized, {})
    assert pnu is None
    assert reason is None


def test_match_trade_uses_pnu_hint_first():
    normalized = {"house_type": Trade.HouseType.APARTMENT, "pnu_hint": "PNUHINT", "apt_seq": "1"}
    pnu, reason = match_trade(normalized, {"1": "OTHER_PNU"})
    assert pnu == "PNUHINT"
    assert reason is None


def test_match_trade_apartment_rent_uses_apt_seq_cache():
    normalized = {
        "house_type": Trade.HouseType.APARTMENT, "pnu_hint": None,
        "apt_seq": "SEQ1", "jibun_raw": None, "sgg_code": "30110", "bjd_name": None,
    }
    pnu, reason = match_trade(normalized, {"SEQ1": "CACHED_PNU"})
    assert pnu == "CACHED_PNU"
    assert reason is None


@pytest.mark.django_db
def test_match_trade_falls_back_to_region_and_jibun():
    Region.objects.create(
        region_code="3011010300", level="bjd", name="효동", geom="MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))"
    )
    normalized = {
        "house_type": Trade.HouseType.OFFICETEL, "pnu_hint": None,
        "apt_seq": None, "jibun_raw": "153-3", "sgg_code": "30110", "bjd_name": "효동",
    }
    pnu, reason = match_trade(normalized, {})
    assert pnu == "3011010300" + "1" + "0153" + "0003"
    assert reason is None


def test_match_trade_jibun_parse_failure():
    normalized = {
        "house_type": Trade.HouseType.OFFICETEL, "pnu_hint": None,
        "apt_seq": None, "jibun_raw": "2024-01-05", "sgg_code": "30110", "bjd_name": "효동",
    }
    pnu, reason = match_trade(normalized, {})
    assert pnu is None
    assert reason == "jibun_parse_failed"


@pytest.mark.django_db
def test_match_trade_region_not_found():
    normalized = {
        "house_type": Trade.HouseType.OFFICETEL, "pnu_hint": None,
        "apt_seq": None, "jibun_raw": "153-3", "sgg_code": "30110", "bjd_name": "존재하지않는동",
    }
    pnu, reason = match_trade(normalized, {})
    assert pnu is None
    assert reason == "region_not_found"


@pytest.mark.django_db
def test_build_apt_seq_cache_reads_existing_apartment_sales():
    Trade.objects.create(
        sgg_code="30110", pnu="PNU1", house_type=Trade.HouseType.APARTMENT,
        deal_type=Trade.DealType.SALE, deal_ym="2026-09", apt_seq="SEQX",
    )
    Trade.objects.create(  # 매칭 실패한 매매는 캐시에 안 들어가야 함
        sgg_code="30110", pnu=None, house_type=Trade.HouseType.APARTMENT,
        deal_type=Trade.DealType.SALE, deal_ym="2026-09", apt_seq="SEQY",
        match_failure_reason="region_not_found",
    )
    cache = build_apt_seq_cache()
    assert cache == {"SEQX": "PNU1"}


@pytest.mark.django_db
def test_determine_house_types_majority_from_matched_trades():
    building = Building.objects.create(
        building_key="B1", gis_bldg_id="B1", pnu="PNU1", bjd_code="3011010300",
        use_name="공동주택", source_date="2026-01-01", geom=_square_wkt(),
    )
    for _ in range(3):
        Trade.objects.create(
            sgg_code="30110", pnu="PNU1", house_type=Trade.HouseType.APARTMENT,
            deal_type=Trade.DealType.SALE, deal_ym="2026-09",
        )
    Trade.objects.create(
        sgg_code="30110", pnu="PNU1", house_type=Trade.HouseType.ROW_HOUSE,
        deal_type=Trade.DealType.SALE, deal_ym="2026-09",
    )

    representative, search_types = determine_house_types_for_building(building)
    assert representative == Trade.HouseType.APARTMENT
    assert search_types == [Trade.HouseType.APARTMENT]


@pytest.mark.django_db
def test_determine_house_types_falls_back_to_use_name_apartment_bucket():
    building = Building.objects.create(
        building_key="B2", gis_bldg_id="B2", pnu="PNU2", bjd_code="3011010300",
        use_name="공동주택", source_date="2026-01-01", geom=_square_wkt(),
    )
    representative, search_types = determine_house_types_for_building(building)
    assert representative == Trade.HouseType.APARTMENT
    assert set(search_types) == {Trade.HouseType.APARTMENT, Trade.HouseType.ROW_HOUSE}


@pytest.mark.django_db
def test_determine_house_types_office_bucket():
    building = Building.objects.create(
        building_key="B3", gis_bldg_id="B3", pnu="PNU3", bjd_code="3011010300",
        use_name="업무시설", source_date="2026-01-01", geom=_square_wkt(),
    )
    representative, search_types = determine_house_types_for_building(building)
    assert representative == Trade.HouseType.OFFICETEL
    assert search_types == [Trade.HouseType.OFFICETEL]


@pytest.mark.django_db
def test_determine_house_types_detached_bucket():
    building = Building.objects.create(
        building_key="B4", gis_bldg_id="B4", pnu="PNU4", bjd_code="3011010300",
        use_name="단독주택", source_date="2026-01-01", geom=_square_wkt(),
    )
    representative, search_types = determine_house_types_for_building(building)
    assert representative == Trade.HouseType.DETACHED
    assert search_types == [Trade.HouseType.DETACHED]


@pytest.mark.django_db
def test_determine_house_types_unmapped():
    building = Building.objects.create(
        building_key="B5", gis_bldg_id="B5", pnu="PNU5", bjd_code="3011010300",
        use_name="종교시설", source_date="2026-01-01", geom=_square_wkt(),
    )
    representative, search_types = determine_house_types_for_building(building)
    assert representative is None
    assert search_types == []
