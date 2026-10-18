import pytest
from rest_framework.test import APIClient

from accounts.models import User
from buildings.models import Building
from favorites.models import FavoriteFolder, UserBuilding

pytestmark = pytest.mark.django_db


def _square_wkt(lon, lat, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


def _make_building(**overrides):
    defaults = dict(
        building_key="AUB1",
        gis_bldg_id="AUB1",
        pnu="3011010300101530080",
        bjd_code="3011010300",
        use_code="01000",
        use_name="공동주택",
        source_date="2026-10-06",
        geom=_square_wkt(127.385, 36.351),
    )
    defaults.update(overrides)
    return Building.objects.create(**defaults)


def test_register_success():
    client = APIClient()
    response = client.post(
        "/api/auth/register",
        {"email": "new@example.com", "password": "correct-horse-battery", "privacy_consent": True},
        format="json",
    )

    assert response.status_code == 201
    user = User.objects.get(email="new@example.com")
    assert user.privacy_consent_at is not None
    assert user.check_password("correct-horse-battery")


def test_register_rejects_missing_consent():
    client = APIClient()
    response = client.post(
        "/api/auth/register",
        {"email": "noconsent@example.com", "password": "correct-horse-battery"},
        format="json",
    )

    assert response.status_code == 400
    assert not User.objects.filter(email="noconsent@example.com").exists()


def test_register_rejects_weak_password():
    client = APIClient()
    response = client.post(
        "/api/auth/register",
        {"email": "weak@example.com", "password": "123", "privacy_consent": True},
        format="json",
    )

    assert response.status_code == 400
    assert not User.objects.filter(email="weak@example.com").exists()


def test_register_rejects_duplicate_email():
    User.objects.create_user(email="dup@example.com", password="correct-horse-battery")
    client = APIClient()

    response = client.post(
        "/api/auth/register",
        {"email": "dup@example.com", "password": "correct-horse-battery-2", "privacy_consent": True},
        format="json",
    )

    assert response.status_code == 400


def test_login_returns_access_and_refresh_tokens():
    User.objects.create_user(email="login@example.com", password="correct-horse-battery")
    client = APIClient()

    response = client.post(
        "/api/auth/login",
        {"email": "login@example.com", "password": "correct-horse-battery"},
        format="json",
    )

    assert response.status_code == 200
    assert "access" in response.json()
    assert "refresh" in response.json()


def test_login_rejects_wrong_password():
    User.objects.create_user(email="login2@example.com", password="correct-horse-battery")
    client = APIClient()

    response = client.post(
        "/api/auth/login",
        {"email": "login2@example.com", "password": "wrong"},
        format="json",
    )

    assert response.status_code == 401


def test_refresh_returns_new_access_token():
    User.objects.create_user(email="refresh@example.com", password="correct-horse-battery")
    client = APIClient()
    login = client.post(
        "/api/auth/login",
        {"email": "refresh@example.com", "password": "correct-horse-battery"},
        format="json",
    )
    refresh_token = login.json()["refresh"]

    response = client.post("/api/auth/refresh", {"refresh": refresh_token}, format="json")

    assert response.status_code == 200
    assert "access" in response.json()


def test_delete_me_cascades_favorites_and_marks():
    user = User.objects.create_user(email="withdraw@example.com", password="correct-horse-battery")
    building = _make_building()
    folder = FavoriteFolder.objects.create(user=user, name="테스트 폴더")
    UserBuilding.objects.create(user=user, building=building, is_favorite=True, folder=folder)

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.delete("/api/auth/me")

    assert response.status_code == 204
    assert not User.objects.filter(email="withdraw@example.com").exists()
    assert not FavoriteFolder.objects.filter(id=folder.id).exists()
    assert not UserBuilding.objects.filter(building=building).exists()
