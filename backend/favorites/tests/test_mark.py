import pytest
from rest_framework.test import APIClient

from accounts.models import User
from buildings.models import Building
from favorites.colors import PALETTE_COLORS
from favorites.models import FavoriteFolder, UserBuilding

pytestmark = pytest.mark.django_db


def _square_wkt(lon, lat, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


def _make_building(**overrides):
    defaults = dict(
        building_key="MKB1",
        gis_bldg_id="MKB1",
        pnu="3011010300101530081",
        bjd_code="3011010300",
        use_code="01000",
        use_name="공동주택",
        source_date="2026-10-06",
        geom=_square_wkt(127.385, 36.351),
    )
    defaults.update(overrides)
    return Building.objects.create(**defaults)


def _make_user(email="mark@example.com"):
    return User.objects.create_user(email=email, password="correct-horse-battery")


def test_mark_requires_authentication():
    building = _make_building()
    client = APIClient()

    response = client.put(f"/api/buildings/{building.id}/mark", {"is_favorite": True}, format="json")

    assert response.status_code == 401


def test_put_creates_mark():
    user = _make_user()
    building = _make_building(building_key="MKB2", gis_bldg_id="MKB2", pnu="3011010300101530082")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.put(
        f"/api/buildings/{building.id}/mark",
        {"is_favorite": True, "color": PALETTE_COLORS[0], "label": "후보", "memo": "메모"},
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_favorite"] is True
    assert body["color"] == PALETTE_COLORS[0]
    mark = UserBuilding.objects.get(user=user, building=building)
    assert mark.label == "후보"


def test_put_auto_deletes_when_everything_is_empty():
    user = _make_user()
    building = _make_building(building_key="MKB3", gis_bldg_id="MKB3", pnu="3011010300101530083")
    UserBuilding.objects.create(user=user, building=building, is_favorite=True, label="있음")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.put(
        f"/api/buildings/{building.id}/mark",
        {"is_favorite": False, "color": None, "label": None, "memo": None},
        format="json",
    )

    assert response.status_code == 200
    assert response.json() == {
        "is_favorite": False,
        "folder_id": None,
        "color": None,
        "label": None,
        "memo": None,
    }
    assert not UserBuilding.objects.filter(user=user, building=building).exists()


def test_put_rejects_color_outside_palette():
    user = _make_user()
    building = _make_building(building_key="MKB4", gis_bldg_id="MKB4", pnu="3011010300101530084")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.put(
        f"/api/buildings/{building.id}/mark",
        {"is_favorite": True, "color": "#123456"},
        format="json",
    )

    assert response.status_code == 400


def test_put_rejects_label_too_long():
    user = _make_user()
    building = _make_building(building_key="MKB5", gis_bldg_id="MKB5", pnu="3011010300101530085")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.put(
        f"/api/buildings/{building.id}/mark",
        {"is_favorite": True, "label": "가" * 21},
        format="json",
    )

    assert response.status_code == 400


def test_put_ignores_folder_id_when_not_favorite():
    user = _make_user()
    building = _make_building(building_key="MKB6", gis_bldg_id="MKB6", pnu="3011010300101530086")
    folder = FavoriteFolder.objects.create(user=user, name="폴더")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.put(
        f"/api/buildings/{building.id}/mark",
        {"is_favorite": False, "folder_id": folder.id, "label": "메모만"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["folder_id"] is None
    mark = UserBuilding.objects.get(user=user, building=building)
    assert mark.folder_id is None


def test_put_rejects_folder_owned_by_another_user():
    user = _make_user()
    other = _make_user(email="other@example.com")
    other_folder = FavoriteFolder.objects.create(user=other, name="남의 폴더")
    building = _make_building(building_key="MKB7", gis_bldg_id="MKB7", pnu="3011010300101530087")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.put(
        f"/api/buildings/{building.id}/mark",
        {"is_favorite": True, "folder_id": other_folder.id},
        format="json",
    )

    assert response.status_code == 403


def test_put_rejects_nonexistent_folder():
    user = _make_user()
    building = _make_building(building_key="MKB8", gis_bldg_id="MKB8", pnu="3011010300101530078")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.put(
        f"/api/buildings/{building.id}/mark",
        {"is_favorite": True, "folder_id": 999999},
        format="json",
    )

    assert response.status_code == 404


def test_delete_removes_mark():
    user = _make_user()
    building = _make_building(building_key="MKB9", gis_bldg_id="MKB9", pnu="3011010300101530079")
    UserBuilding.objects.create(user=user, building=building, is_favorite=True)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.delete(f"/api/buildings/{building.id}/mark")

    assert response.status_code == 204
    assert not UserBuilding.objects.filter(user=user, building=building).exists()
