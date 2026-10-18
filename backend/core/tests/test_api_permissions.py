"""공개/비공개 API 목록이 의도대로인지 확인한다(감사 결과: DEFAULT_PERMISSION_CLASSES를
IsAuthenticated로 바꾸고 공개 API만 AllowAny로 명시했다 — 새 뷰가 깜빡하면 기본은 닫힘)."""
import pytest
from rest_framework.test import APIClient

from accounts.models import User
from buildings.models import Building

pytestmark = pytest.mark.django_db


def _square_wkt(lon, lat, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


@pytest.fixture
def building():
    return Building.objects.create(
        building_key="PERMB1",
        gis_bldg_id="PERMB1",
        pnu="3011010300101530010",
        bjd_code="3011010300",
        use_code="01000",
        use_name="공동주택",
        source_date="2026-10-06",
        geom=_square_wkt(127.385, 36.351),
    )


# ---- 공개 API: 로그인 없이도 401이면 안 된다 ----------------------------------------


def test_health_is_public():
    response = APIClient().get("/api/health")

    assert response.status_code != 401


def test_building_tile_is_public():
    response = APIClient().get("/api/tiles/buildings/10/500/500.mvt")

    assert response.status_code != 401


def test_building_at_point_is_public(building):
    response = APIClient().get("/api/buildings/at", {"lon": 127.3855, "lat": 36.3515})

    assert response.status_code != 401


def test_building_search_is_public(building):
    response = APIClient().get("/api/buildings/search", {"q": "아무거나"})

    assert response.status_code != 401


def test_building_insight_is_public(building):
    response = APIClient().get(f"/api/buildings/{building.id}/insight", {"radius": 500})

    assert response.status_code != 401


def test_layers_list_is_public():
    response = APIClient().get("/api/layers")

    assert response.status_code != 401


def test_layer_tile_proxy_is_public():
    response = APIClient().get("/api/layers/999999/tiles/1/1/1.png")

    assert response.status_code != 401


def test_register_is_public():
    response = APIClient().post(
        "/api/auth/register",
        {
            "email": "permcheck@example.com",
            "password": "correct-horse-battery",
            "privacy_consent": True,
        },
        format="json",
    )

    assert response.status_code != 401


def test_login_is_public_and_actually_issues_tokens():
    """permission_classes가 잘못 걸리면 틀린 비밀번호와 똑같이 401이 나올 수 있어, 실제로
    토큰 발급까지 성공하는지로 AllowAny가 제대로 적용됐는지 확인한다."""
    User.objects.create_user(email="permlogin@example.com", password="correct-horse-battery")

    response = APIClient().post(
        "/api/auth/login",
        {"email": "permlogin@example.com", "password": "correct-horse-battery"},
        format="json",
    )

    assert response.status_code == 200
    assert "access" in response.json()
    assert "refresh" in response.json()


def test_refresh_is_public_and_actually_works():
    User.objects.create_user(email="permrefresh@example.com", password="correct-horse-battery")
    client = APIClient()
    login = client.post(
        "/api/auth/login",
        {"email": "permrefresh@example.com", "password": "correct-horse-battery"},
        format="json",
    )
    refresh_token = login.json()["refresh"]

    response = client.post("/api/auth/refresh", {"refresh": refresh_token}, format="json")

    assert response.status_code == 200
    assert "access" in response.json()


def test_login_still_rejects_wrong_password_with_401():
    """AllowAny는 '로그인 시도를 받아준다'는 뜻이지, 틀린 비밀번호까지 통과시키진 않는다."""
    User.objects.create_user(email="permlogin2@example.com", password="correct-horse-battery")

    response = APIClient().post(
        "/api/auth/login",
        {"email": "permlogin2@example.com", "password": "wrong-password"},
        format="json",
    )

    assert response.status_code == 401


# ---- 비공개 API: 로그인 없이는 전부 401이어야 한다 -------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("delete", "/api/auth/me"),
        ("put", "/api/buildings/1/mark"),
        ("delete", "/api/buildings/1/mark"),
        ("get", "/api/me/favorites"),
        ("post", "/api/me/favorites"),
        ("patch", "/api/me/favorites/1"),
        ("delete", "/api/me/favorites/1"),
        ("post", "/api/me/favorites/1/buildings"),
        ("get", "/api/me/buildings"),
        ("get", "/api/buildings/1/reports"),
        ("post", "/api/buildings/1/reports"),
        ("get", "/api/reports/1"),
        ("delete", "/api/reports/1"),
    ],
)
def test_private_endpoints_require_authentication(method, path):
    response = getattr(APIClient(), method)(path, {}, format="json")

    assert response.status_code == 401
