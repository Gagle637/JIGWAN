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


def test_without_folder_id_returns_favorited_and_memo_only_buildings():
    user = _make_user()
    favorited = _make_building(building_key="MBB2", gis_bldg_id="MBB2", pnu="3011010300101530061")
    memo_only = _make_building(building_key="MBB3", gis_bldg_id="MBB3", pnu="3011010300101530062")
    untouched = _make_building(building_key="MBBG", gis_bldg_id="MBBG", pnu="3011010300101530082")
    UserBuilding.objects.create(user=user, building=favorited, is_favorite=True)
    UserBuilding.objects.create(user=user, building=memo_only, is_favorite=False, memo="메모만")
    client = _authed_client(user)

    response = client.get("/api/me/buildings")
    ids = {f["properties"]["building_id"] for f in response.json()["features"]}

    assert ids == {favorited.id, memo_only.id}
    assert untouched.id not in ids


def test_memo_only_building_has_no_color_and_is_not_favorite():
    user = _make_user()
    folder = FavoriteFolder.objects.create(user=user, name="색 있는 폴더", color="#1971c2")
    memo_only = _make_building(building_key="MBBH", gis_bldg_id="MBBH", pnu="3011010300101483")
    UserBuilding.objects.create(
        user=user, building=memo_only, is_favorite=False, memo="메모만", folder=None
    )
    client = _authed_client(user)

    response = client.get("/api/me/buildings")
    feature = next(
        f for f in response.json()["features"] if f["properties"]["building_id"] == memo_only.id
    )

    assert feature["properties"]["is_favorite"] is False
    assert feature["properties"]["color"] is None
    assert feature["properties"]["has_memo"] is True


def test_color_only_building_keeps_its_own_color_without_inheriting_folder_color():
    user = _make_user()
    FavoriteFolder.objects.create(user=user, name="색 있는 폴더", color="#1971c2")
    color_only = _make_building(building_key="MBBI", gis_bldg_id="MBBI", pnu="3011010300101484")
    UserBuilding.objects.create(
        user=user, building=color_only, is_favorite=False, color="#e03131"
    )
    client = _authed_client(user)

    response = client.get("/api/me/buildings")
    feature = next(
        f for f in response.json()["features"] if f["properties"]["building_id"] == color_only.id
    )

    assert feature["properties"]["color"] == "#e03131"
    assert feature["properties"]["is_favorite"] is False


def test_folder_id_null_excludes_non_favorited_buildings():
    user = _make_user()
    favorited_unfiled = _make_building(
        building_key="MBBJ", gis_bldg_id="MBBJ", pnu="3011010300101485"
    )
    memo_only = _make_building(building_key="MBBK", gis_bldg_id="MBBK", pnu="3011010300101486")
    UserBuilding.objects.create(user=user, building=favorited_unfiled, is_favorite=True)
    UserBuilding.objects.create(user=user, building=memo_only, is_favorite=False, memo="메모만")
    client = _authed_client(user)

    response = client.get("/api/me/buildings", {"folder_id": "null"})
    ids = {f["properties"]["building_id"] for f in response.json()["features"]}

    assert ids == {favorited_unfiled.id}


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


def test_has_memo_reflects_whether_favorited_building_has_memo():
    user = _make_user()
    with_memo = _make_building(building_key="MBBE", gis_bldg_id="MBBE", pnu="3011010300101480")
    without_memo = _make_building(building_key="MBBF", gis_bldg_id="MBBF", pnu="3011010300101481")
    UserBuilding.objects.create(user=user, building=with_memo, is_favorite=True, memo="메모 있음")
    UserBuilding.objects.create(user=user, building=without_memo, is_favorite=True)
    client = _authed_client(user)

    response = client.get("/api/me/buildings")
    has_memo = {
        f["properties"]["building_id"]: f["properties"]["has_memo"]
        for f in response.json()["features"]
    }

    assert has_memo[with_memo.id] is True
    assert has_memo[without_memo.id] is False
