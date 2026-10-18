import pytest

from buildings.models import Region
from publicdata.pnu import build_pnu, build_pnu_from_apt_sale, lookup_bjd_code, parse_jibun


def test_parse_jibun_plain():
    assert parse_jibun("202-3") == (False, 202, 3)


def test_parse_jibun_without_bubun():
    assert parse_jibun("202") == (False, 202, 0)


def test_parse_jibun_san():
    assert parse_jibun("산12-3") == (True, 12, 3)
    assert parse_jibun("산12") == (True, 12, 0)


def test_parse_jibun_san_with_space():
    assert parse_jibun("산 12-3") == (True, 12, 3)


def test_parse_jibun_date_like_is_failure():
    # 지번이 날짜로 둔갑한 사례(spec 8-7)
    assert parse_jibun("1952-5-1") is None
    assert parse_jibun("2024-01-05") is None


def test_parse_jibun_blank_is_failure():
    assert parse_jibun("") is None
    assert parse_jibun(None) is None
    assert parse_jibun("   ") is None


def test_parse_jibun_garbage_is_failure():
    assert parse_jibun("abc") is None


def test_build_pnu_length_and_format():
    pnu = build_pnu("3011010300", False, 153, 3)
    assert len(pnu) == 19
    assert pnu == "3011010300" + "1" + "0153" + "0003"


def test_build_pnu_san():
    pnu = build_pnu("3011010300", True, 12, 0)
    assert pnu == "3011010300" + "2" + "0012" + "0000"


def test_build_pnu_from_apt_sale():
    pnu = build_pnu_from_apt_sale("30110", "10300", "1", "153", "3")
    assert len(pnu) == 19
    assert pnu == "3011010300" + "1" + "0153" + "0003"


@pytest.mark.django_db
def test_lookup_bjd_code_found():
    Region.objects.create(
        region_code="3011010300", level="bjd", name="효동",
        geom="MULTIPOLYGON(((0 0, 1 0, 1 1, 0 1, 0 0)))",
    )
    assert lookup_bjd_code("30110", "효동") == "3011010300"


@pytest.mark.django_db
def test_lookup_bjd_code_not_found():
    assert lookup_bjd_code("30110", "존재하지않는동") is None


@pytest.mark.django_db
def test_lookup_bjd_code_scoped_to_sgg():
    Region.objects.create(
        region_code="3014011600", level="bjd", name="효동",  # 다른 구에 같은 이름(가상)
        geom="MULTIPOLYGON(((0 0, 1 0, 1 1, 0 1, 0 0)))",
    )
    assert lookup_bjd_code("30110", "효동") is None  # 30110 구에는 없음
    assert lookup_bjd_code("30140", "효동") == "3014011600"
