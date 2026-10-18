import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from buildings.models import Building

pytestmark = pytest.mark.django_db


def _square_wkt(lon, lat, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


def _make_building(**overrides):
    defaults = dict(
        building_key="B1",
        gis_bldg_id="B1",
        pnu="3011010300101530003",
        bjd_code="3011010300",
        bjd_name="대전광역시 동구 효동",
        jibun="153-3",
        use_code="01000",
        use_name="단독주택",
        name=None,
        dong_name=None,
        land_area_m2=187.0,
        total_floor_area_m2=135.21,
        bcr_pct=44.58,
        far_pct=72.3,
        approval_date="1977-08-17",
        source_date="2026-10-06",
        geom=_square_wkt(127.385, 36.351),
    )
    defaults.update(overrides)
    return Building.objects.create(**defaults)


# ---- /api/buildings/at ----


def test_at_point_inside_building_returns_match():
    building = _make_building()
    client = APIClient()
    response = client.get("/api/buildings/at", {"lon": 127.3855, "lat": 36.3515})

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == building.id
    assert body["pnu"] == building.pnu
    assert body["geometry"]["type"] == "Polygon"


def test_at_point_outside_any_building_returns_404():
    _make_building()
    client = APIClient()
    response = client.get("/api/buildings/at", {"lon": 0.0, "lat": 0.0})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NO_BUILDING_AT_POINT"


def test_at_missing_params_returns_400():
    client = APIClient()
    response = client.get("/api/buildings/at")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAM"


def test_at_point_prefers_smaller_overlapping_building():
    big = _make_building(
        building_key="BIG", gis_bldg_id="BIG", pnu="1111111111111111111",
        geom=_square_wkt(127.385, 36.351, size=0.01),
    )
    small = _make_building(
        building_key="SMALL", gis_bldg_id="SMALL", pnu="2222222222222222222",
        geom=_square_wkt(127.3895, 36.3555, size=0.0005),
    )
    assert big.id != small.id

    client = APIClient()
    response = client.get("/api/buildings/at", {"lon": 127.3897, "lat": 36.3557})

    assert response.status_code == 200
    assert response.json()["id"] == small.id


# ---- /api/buildings/search ----


def test_search_matches_building_name():
    _make_building(name="효동 다세대주택")
    client = APIClient()
    response = client.get("/api/buildings/search", {"q": "효동 다세대"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert any(r["name"] == "효동 다세대주택" for r in results)


def test_search_matches_bjd_name_and_jibun():
    _make_building(bjd_name="대전광역시 동구 효동", jibun="153-3")
    client = APIClient()
    response = client.get("/api/buildings/search", {"q": "효동 153"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert any(r["address"] == "대전광역시 동구 효동 153-3" for r in results)


def test_search_matches_dong_name():
    _make_building(dong_name="101동")
    client = APIClient()
    response = client.get("/api/buildings/search", {"q": "101동"})

    assert response.status_code == 200
    assert len(response.json()["results"]) >= 1


def test_search_missing_q_returns_400():
    client = APIClient()
    response = client.get("/api/buildings/search")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAM"


def test_search_limits_to_20_results():
    for i in range(25):
        _make_building(
            building_key=f"MANY{i}",
            gis_bldg_id=f"MANY{i}",
            pnu=f"{i:019d}",
            bjd_name="대전광역시 유성구 신성동",
            jibun=f"{i}-1",
            geom=_square_wkt(127.3 + i * 0.001, 36.3),
        )
    client = APIClient()
    response = client.get("/api/buildings/search", {"q": "신성동"})

    assert response.status_code == 200
    assert len(response.json()["results"]) <= 20


# ---- /api/buildings/{id}/insight ----


def test_insight_invalid_radius_returns_400():
    building = _make_building()
    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 300})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAM"


def test_insight_unknown_building_returns_404():
    client = APIClient()
    response = client.get("/api/buildings/999999/insight", {"radius": 500})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BUILDING_NOT_FOUND"


def test_insight_with_registry_data_fills_spec():
    building = _make_building()
    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})

    body = response.json()
    assert response.status_code == 200
    # green·change가 둘 다 null(위성 데이터 전혀 없음)이면 status는 partial이 아니라
    # pending이다(spec 6-2: "해당 범위의 위성 결과가 카탈로그에 없음"). 이 테스트는 위성
    # 데이터를 아예 안 만들어 두니 pending이 맞다 — 예전(3단계, status 로직 생기기 전)
    # 작성 당시 그대로 남아 있던 기대값이었다.
    assert body["status"] == "pending"
    assert body["spec"]["use"] == "단독주택"
    assert body["spec"]["age_years"] is not None
    assert body["green"] is None
    assert body["change"] is None
    assert body["trades"] is None
    assert body["crime"] is None
    assert body["my"] is None
    missing_fields = {m["field"] for m in body["missing"]}
    assert missing_fields == {"green", "change", "trades", "crime"}


def test_insight_without_registry_data_nulls_spec():
    building = _make_building(
        use_code=None, use_name=None, land_area_m2=None, total_floor_area_m2=None,
        bcr_pct=None, far_pct=None, approval_date=None,
    )
    client = APIClient()
    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 1000})

    body = response.json()
    assert body["spec"] is None
    missing_fields = {m["field"] for m in body["missing"]}
    assert "spec" in missing_fields


# ---- 타일 Cache-Control ----


def test_tile_response_has_cache_control_header():
    client = APIClient()
    response = client.get("/api/tiles/buildings/10/0/0.mvt")  # 줌<14 -> 빈 타일

    assert response.status_code == 200
    assert response["Cache-Control"] == "public, max-age=86400"
    assert response.content == b""


# ---- Throttling ----


def test_search_throttled_after_limit(monkeypatch):
    """ScopedRateThrottle(SimpleRateThrottle)의 THROTTLE_RATES는 클래스 바디에서
    api_settings.DEFAULT_THROTTLE_RATES를 "한 번만" 읽어 굳힌 클래스 속성이라,
    override_settings(REST_FRAMEWORK=...)로 settings.REST_FRAMEWORK를 바꿔도 이미 임포트된
    이 클래스 속성은 안 바뀐다(실제 Postgres·실제 DRF로 돌려보니 3번째 요청도 200이 나와
    걸림, 감사에서 발견). 클래스 속성을 직접 패치해야 한다."""
    _make_building(bjd_name="대전광역시 유성구 신성동", jibun="1-1")
    client = APIClient()
    # 같은 Redis 캐시를 다른 테스트들도 "search" scope로 쓰므로, 이 테스트만의 낮은 한도가
    # 앞선 테스트들의 요청 기록과 섞이지 않도록 먼저 비운다.
    cache.clear()

    monkeypatch.setattr(
        ScopedRateThrottle, "THROTTLE_RATES", {"search": "2/min", "insight": "60/min"}
    )

    r1 = client.get("/api/buildings/search", {"q": "신성동"})
    r2 = client.get("/api/buildings/search", {"q": "신성동"})
    r3 = client.get("/api/buildings/search", {"q": "신성동"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert r3.json()["error"]["code"] == "RATE_LIMITED"
