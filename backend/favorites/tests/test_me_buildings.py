import pytest
from rest_framework.test import APIClient

from accounts.models import User
from buildings.models import Building
from favorites.colors import DEFAULT_FAVORITE_COLOR
from favorites.models import FavoriteFolder, UserBuilding

pytestmark = pytest.mark.django_db


def _square_wkt(lon, lat, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


def _make_building(lon=127.385, lat=36.351, **overrides):
    defaults = dict(
        building_key="MBB1",
        gis_bldg_id="MBB1",
        pnu="3011010300101530060",
        bjd_code="3011010300",
        use_code="01000",
        use_name="공동주택",
        source_date="2026-10-06",
        geom=_square_wkt(lon, lat),
    )
    defaults.update(overrides)
    return Building.objects.create(**defaults)


def _make_user(email="mebuildings@example.com"):
    return User.objects.create_user(email=email, password="correct-horse-battery")


def _authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_only_favorited_buildings_returned():
    user = _make_user()
    favorited = _make_building(building_key="MBB2", gis_bldg_id="MBB2", pnu="3011010300101530061")
    not_favorited = _make_building(
        building_key="MBB3", gis_bldg_id="MBB3", pnu="3011010300101530062"
    )
    UserBuilding.objects.create(user=user, building=favorited, is_favorite=True)
    UserBuilding.objects.create(user=user, building=not_favorited, is_favorite=False, memo="메모만")
    client = _authed_client(user)

    response = client.get("/api/me/buildings")
    ids = {f["properties"]["building_id"] for f in response.json()["features"]}

    assert ids == {favorited.id}


def test_bbox_filters_buildings_outside_range():
    user = _make_user()
    inside = _make_building(
        lon=127.385, lat=36.351, building_key="MBB4", gis_bldg_id="MBB4", pnu="3011010300101530063"
    )
    outside = _make_building(
        lon=128.5, lat=37.5, building_key="MBB5", gis_bldg_id="MBB5", pnu="3011010300101530064"
    )
    UserBuilding.objects.create(user=user, building=inside, is_favorite=True)
    UserBuilding.objects.create(user=user, building=outside, is_favorite=True)
    client = _authed_client(user)

    response = client.get("/api/me/buildings", {"bbox": "127.0,36.0,127.6,36.6"})
    ids = {f["properties"]["building_id"] for f in response.json()["features"]}

    assert ids == {inside.id}


def test_folder_id_filter_includes_descendant_folders():
    user = _make_user()
    root = FavoriteFolder.objects.create(user=user, name="루트")
    child = FavoriteFolder.objects.create(user=user, parent=root, name="자식")
    in_root = _make_building(building_key="MBB6", gis_bldg_id="MBB6", pnu="3011010300101530065")
    in_child = _make_building(building_key="MBB7", gis_bldg_id="MBB7", pnu="3011010300101530066")
    elsewhere = _make_building(building_key="MBB8", gis_bldg_id="MBB8", pnu="3011010300101530067")
    UserBuilding.objects.create(user=user, building=in_root, is_favorite=True, folder=root)
    UserBuilding.objects.create(user=user, building=in_child, is_favorite=True, folder=child)
    UserBuilding.objects.create(user=user, building=elsewhere, is_favorite=True, folder=None)
    client = _authed_client(user)

    response = client.get("/api/me/buildings", {"folder_id": str(root.id)})
    ids = {f["properties"]["building_id"] for f in response.json()["features"]}

    assert ids == {in_root.id, in_child.id}


def test_hidden_folder_excludes_its_buildings_and_descendants():
    user = _make_user()
    hidden_root = FavoriteFolder.objects.create(user=user, name="숨김 폴더", is_hidden=True)
    child = FavoriteFolder.objects.create(user=user, parent=hidden_root, name="그 아래")
    in_hidden_child = _make_building(
        building_key="MBB9", gis_bldg_id="MBB9", pnu="3011010300101530068"
    )
    visible = _make_building(building_key="MBBA", gis_bldg_id="MBBA", pnu="3011010300101530069")
    UserBuilding.objects.create(
        user=user, building=in_hidden_child, is_favorite=True, folder=child
    )
    UserBuilding.objects.create(user=user, building=visible, is_favorite=True, folder=None)
    client = _authed_client(user)

    response = client.get("/api/me/buildings")
    ids = {f["properties"]["building_id"] for f in response.json()["features"]}

    assert ids == {visible.id}


def test_color_priority_building_over_folder_over_default():
    user = _make_user()
    folder = FavoriteFolder.objects.create(user=user, name="색 있는 폴더", color="#1971c2")
    with_own_color = _make_building(
        building_key="MBBB", gis_bldg_id="MBBB", pnu="3011010300101477"
    )
    inherits_folder_color = _make_building(
        building_key="MBBC", gis_bldg_id="MBBC", pnu="3011010300101478"
    )
    no_folder_no_color = _make_building(
        building_key="MBBD", gis_bldg_id="MBBD", pnu="3011010300101479"
    )
    UserBuilding.objects.create(
        user=user, building=with_own_color, is_favorite=True, folder=folder, color="#e03131"
    )
    UserBuilding.objects.create(
        user=user, building=inherits_folder_color, is_favorite=True, folder=folder
    )
    UserBuilding.objects.create(user=user, building=no_folder_no_color, is_favorite=True)
    client = _authed_client(user)

    response = client.get("/api/me/buildings")
    colors = {
        f["properties"]["building_id"]: f["properties"]["color"]
        for f in response.json()["features"]
    }

    assert colors[with_own_color.id] == "#e03131"
    assert colors[inherits_folder_color.id] == "#1971c2"
    assert colors[no_folder_no_color.id] == DEFAULT_FAVORITE_COLOR
