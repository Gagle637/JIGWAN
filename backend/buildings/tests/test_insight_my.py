import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts.models import User
from favorites.colors import PALETTE_COLORS
from favorites.models import FavoriteFolder, UserBuilding

from .test_insight_green_change import _make_building

pytestmark = pytest.mark.django_db


def _make_user(email="insightmy@example.com"):
    return User.objects.create_user(email=email, password="correct-horse-battery")


def test_my_is_null_when_not_logged_in():
    cache.clear()
    building = _make_building(building_key="IMB1", gis_bldg_id="IMB1", pnu="3011010300101530050")
    client = APIClient()

    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})

    assert response.json()["my"] is None


def test_my_has_defaults_when_logged_in_but_not_marked():
    cache.clear()
    building = _make_building(building_key="IMB2", gis_bldg_id="IMB2", pnu="3011010300101530051")
    user = _make_user()
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    my = response.json()["my"]

    assert my == {
        "is_favorite": False,
        "color": None,
        "label": None,
        "folder_id": None,
        "report_count": 0,
    }


def test_my_reflects_existing_mark():
    cache.clear()
    building = _make_building(building_key="IMB3", gis_bldg_id="IMB3", pnu="3011010300101530052")
    user = _make_user()
    folder = FavoriteFolder.objects.create(user=user, name="내 폴더")
    UserBuilding.objects.create(
        user=user,
        building=building,
        is_favorite=True,
        folder=folder,
        color=PALETTE_COLORS[1],
        label="후보",
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    my = response.json()["my"]

    assert my["is_favorite"] is True
    assert my["color"] == PALETTE_COLORS[1]
    assert my["label"] == "후보"
    assert my["folder_id"] == folder.id


def test_my_does_not_leak_between_different_users():
    cache.clear()
    building = _make_building(building_key="IMB4", gis_bldg_id="IMB4", pnu="3011010300101530053")
    user_a = _make_user(email="a@example.com")
    user_b = _make_user(email="b@example.com")
    UserBuilding.objects.create(user=user_a, building=building, is_favorite=True, label="A만 표시")

    client_a = APIClient()
    client_a.force_authenticate(user=user_a)
    client_b = APIClient()
    client_b.force_authenticate(user=user_b)

    response_a = client_a.get(f"/api/buildings/{building.id}/insight", {"radius": 500})
    response_b = client_b.get(f"/api/buildings/{building.id}/insight", {"radius": 500})

    assert response_a.json()["my"]["is_favorite"] is True
    assert response_b.json()["my"]["is_favorite"] is False
    # my 제외 나머지(캐시로부터 옴)는 동일해야 한다
    a_body = response_a.json()
    b_body = response_b.json()
    assert {k: v for k, v in a_body.items() if k != "my"} == {
        k: v for k, v in b_body.items() if k != "my"
    }
