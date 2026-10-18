import pytest

from buildings.models import Building, Region
from buildings.region_loading import count_bjd_code_mismatches, derive_parent_code, pad_code


def test_pad_code_pads_short_codes():
    assert pad_code("12345678", 10) == "1234567800"


def test_pad_code_leaves_long_enough_codes_untouched():
    assert pad_code("1234567890", 10) == "1234567890"


def test_pad_code_noop_without_pad_to():
    assert pad_code("12345678", None) == "12345678"


def test_derive_parent_code_by_level():
    assert derive_parent_code("30", "sido") is None
    assert derive_parent_code("30110", "sigungu") == "30"
    assert derive_parent_code("3011010300", "bjd") == "30110"


@pytest.mark.django_db
def test_count_bjd_code_mismatches():
    Region.objects.create(
        region_code="3011010300",
        level="bjd",
        name="효동",
        geom="MULTIPOLYGON(((0 0, 1 0, 1 1, 0 1, 0 0)))",
    )
    Building.objects.create(
        building_key="B1",
        gis_bldg_id="B1",
        pnu="p1",
        bjd_code="3011010300",
        source_date="2026-01-01",
        geom="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
    )
    Building.objects.create(
        building_key="B2",
        gis_bldg_id="B2",
        pnu="p2",
        bjd_code="9999999999",
        source_date="2026-01-01",
        geom="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
    )

    assert count_bjd_code_mismatches() == 1
