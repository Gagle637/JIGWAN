"""insight 응답 계약(JSON 스키마) 테스트 — spec 6-2 pending/partial 모양을 그대로 지키는지 확인한다."""
import jsonschema
import pytest
from rest_framework.test import APIClient

from .test_insight_green_change import _make_building

pytestmark = pytest.mark.django_db

_MISSING_ENTRY_SCHEMA = {
    "type": "object",
    "required": ["field", "reason"],
    "properties": {
        "field": {"type": "string"},
        "reason": {"type": "string"},
    },
    "additionalProperties": False,
}

_GREEN_SCHEMA = {
    "type": ["object", "null"],
    "required": ["ratio_pct", "region_avg_pct", "diff_pp", "coverage_pct", "series"],
    "properties": {
        "ratio_pct": {"type": ["number", "null"]},
        "region_avg_pct": {"type": ["number", "null"]},
        "diff_pp": {"type": ["number", "null"]},
        "coverage_pct": {"type": "number"},
        "series": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["year", "season", "ratio_pct", "coverage_pct"],
                "properties": {
                    "year": {"type": "integer"},
                    "season": {"enum": ["spring", "summer", "fall", "winter"]},
                    "ratio_pct": {"type": ["number", "null"]},
                    "coverage_pct": {"type": "number"},
                },
            },
        },
    },
}

_CHANGE_SCHEMA = {
    "type": ["object", "null"],
    "required": ["total_area_m2", "areas", "tiles"],
    "properties": {
        "total_area_m2": {"type": "number"},
        "areas": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "required": ["id", "area_m2", "distance_m", "period", "geometry"],
                "properties": {
                    "id": {"type": "integer"},
                    "area_m2": {"type": "number"},
                    "distance_m": {"type": "number"},
                    "period": {"enum": ["1y", "2y", "3y"]},
                    "geometry": {"type": "object"},
                },
            },
        },
        "tiles": {
            "type": "object",
            "required": ["after", "before", "default_compare"],
            "properties": {
                "after": {"type": ["string", "null"]},
                "before": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "default_compare": {"type": ["string", "null"]},
            },
        },
    },
}

_CRIME_SCHEMA = {
    "type": ["object", "null"],
    "required": ["max_grad", "near_grad", "flagged_length_m", "high_share_pct"],
    "properties": {
        "max_grad": {"type": "integer"},
        "near_grad": {"type": ["integer", "null"]},
        "flagged_length_m": {"type": "number"},
        "high_share_pct": {"type": "number"},
    },
}

INSIGHT_RESPONSE_SCHEMA = {
    "type": "object",
    "required": [
        "status",
        "building",
        "radius_m",
        "as_of",
        "green",
        "change",
        "spec",
        "trades",
        "crime",
        "my",
        "missing",
    ],
    "properties": {
        "status": {"enum": ["pending", "partial", "ready"]},
        "building": {
            "type": "object",
            "required": ["id", "pnu", "name", "address", "use_type", "geometry"],
        },
        "radius_m": {"enum": [500, 1000]},
        "as_of": {
            "type": "object",
            "required": [
                "satellite_period",
                "trade_synced_at",
                "register_synced_at",
                "crime_data_period",
            ],
        },
        "green": _GREEN_SCHEMA,
        "change": _CHANGE_SCHEMA,
        "spec": {"type": ["object", "null"]},
        "trades": {"type": ["object", "null"]},
        "crime": _CRIME_SCHEMA,
        "my": {"type": ["object", "null"]},
        "missing": {"type": "array", "items": _MISSING_ENTRY_SCHEMA},
    },
    "additionalProperties": False,
}


def test_pending_response_matches_contract():
    building = _make_building(building_key="CTB1", gis_bldg_id="CTB1", pnu="3011010300101530097")
    client = APIClient()

    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["status"] == "pending"
    jsonschema.validate(body, INSIGHT_RESPONSE_SCHEMA)


def test_partial_response_matches_contract(tmp_path):
    from django.core.cache import cache

    from .test_insight_green_change import _make_green_product, _write_all_green_covering_building

    cache.clear()
    building = _make_building(building_key="CTB2", gis_bldg_id="CTB2", pnu="3011010300101530096")
    _write_all_green_covering_building(tmp_path / "green.tif")
    _make_green_product(tmp_path, "green")

    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["status"] == "partial"
    jsonschema.validate(body, INSIGHT_RESPONSE_SCHEMA)


def test_ready_response_matches_contract(tmp_path):
    from django.core.cache import cache

    from crime.models import CrimeSegment
    from publicdata.models import Trade

    from .test_insight_green_change import (
        _make_green_product,
        _make_truecolor_product,
        _write_all_green_covering_building,
    )

    cache.clear()
    building = _make_building(
        building_key="CTB3",
        gis_bldg_id="CTB3",
        pnu="3011010300101530088",
        use_code="01000",
        use_name="공동주택",
    )
    Trade.objects.create(
        sgg_code="30110",
        pnu="OTHER_PNU",
        house_type=Trade.HouseType.APARTMENT,
        deal_type=Trade.DealType.SALE,
        deal_ym="2026-09",
        area_m2=100.0,
        price=50000,
        is_canceled=False,
        geom="SRID=4326;POINT(127.3851 36.3511)",
    )
    _write_all_green_covering_building(tmp_path / "green.tif")
    _make_green_product(tmp_path, "green")
    _make_truecolor_product(tmp_path, "cur", 2026, "summer")
    CrimeSegment.objects.create(
        objt_id="CTB3SEG",
        grad=5,
        data_period="2023-07/2024-06",
        geom="LINESTRING(127.385 36.351, 127.3852 36.351)",
    )

    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    body = response.json()

    assert body["status"] == "ready"
    jsonschema.validate(body, INSIGHT_RESPONSE_SCHEMA)
