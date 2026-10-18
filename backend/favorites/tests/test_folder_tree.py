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
        building_key="FTB1",
        gis_bldg_id="FTB1",
        pnu="3011010300101530070",
        bjd_code="3011010300",
        use_code="01000",
        use_name="공동주택",
        source_date="2026-10-06",
        geom=_square_wkt(127.385, 36.351),
    )
    defaults.update(overrides)
    return Building.objects.create(**defaults)


def _make_user(email="tree@example.com"):
    return User.objects.create_user(email=email, password="correct-horse-battery")


def _authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_get_favorites_returns_nested_tree_and_unclassified_last():
    user = _make_user()
    root = FavoriteFolder.objects.create(user=user, name="대전 후보", color="#e8590c")
    child = FavoriteFolder.objects.create(user=user, parent=root, name="유성구")
    building1 = _make_building(building_key="FTB2", gis_bldg_id="FTB2", pnu="3011010300101530071")
    building2 = _make_building(building_key="FTB3", gis_bldg_id="FTB3", pnu="3011010300101530072")
    UserBuilding.objects.create(user=user, building=building1, is_favorite=True, folder=child)
    UserBuilding.objects.create(user=user, building=building2, is_favorite=True, folder=None)

    client = _authed_client(user)
    response = client.get("/api/me/favorites")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == root.id
    assert body[0]["children"][0]["id"] == child.id
    assert body[0]["children"][0]["building_count"] == 1
    assert body[-1] == {"id": None, "name": "미분류", "building_count": 1, "children": []}


def test_post_creates_folder_under_parent():
    user = _make_user()
    root = FavoriteFolder.objects.create(user=user, name="루트")
    client = _authed_client(user)

    response = client.post("/api/me/favorites", {"name": "하위", "parent_id": root.id}, format="json")

    assert response.status_code == 201
    folder = FavoriteFolder.objects.get(id=response.json()["id"])
    assert folder.parent_id == root.id


def test_post_rejects_depth_beyond_five():
    user = _make_user()
    parent = None
    for _ in range(5):
        parent = FavoriteFolder.objects.create(user=user, parent=parent, name="레벨")
    # parent는 지금 깊이 5(루트=1) — 그 아래(깊이 6)는 거부돼야 한다.
    client = _authed_client(user)

    response = client.post(
        "/api/me/favorites", {"name": "너무 깊음", "parent_id": parent.id}, format="json"
    )

    assert response.status_code == 400


def test_patch_moves_folder_to_new_parent():
    user = _make_user()
    folder_a = FavoriteFolder.objects.create(user=user, name="A")
    folder_b = FavoriteFolder.objects.create(user=user, name="B")
    client = _authed_client(user)

    response = client.patch(
        f"/api/me/favorites/{folder_a.id}", {"parent_id": folder_b.id}, format="json"
    )

    assert response.status_code == 200
    folder_a.refresh_from_db()
    assert folder_a.parent_id == folder_b.id


def test_patch_rejects_moving_into_own_descendant():
    user = _make_user()
    parent = FavoriteFolder.objects.create(user=user, name="부모")
    child = FavoriteFolder.objects.create(user=user, parent=parent, name="자식")
    client = _authed_client(user)

    response = client.patch(
        f"/api/me/favorites/{parent.id}", {"parent_id": child.id}, format="json"
    )

    assert response.status_code == 400
    parent.refresh_from_db()
    assert parent.parent_id is None


def test_patch_rejects_move_that_would_exceed_depth_five():
    user = _make_user()
    # 깊이 5짜리 체인
    deep_chain_tail = None
    for _ in range(5):
        deep_chain_tail = FavoriteFolder.objects.create(user=user, parent=deep_chain_tail, name="L")
    # 자식 하나 있는 별도 폴더(서브트리 높이 1)를 그 체인 끝 아래로 옮기면 깊이 7이 됨
    movable = FavoriteFolder.objects.create(user=user, name="옮길 폴더")
    FavoriteFolder.objects.create(user=user, parent=movable, name="옮길 폴더의 자식")
    client = _authed_client(user)

    response = client.patch(
        f"/api/me/favorites/{movable.id}", {"parent_id": deep_chain_tail.id}, format="json"
    )

    assert response.status_code == 400


def test_patch_rejects_parent_owned_by_another_user():
    user = _make_user()
    other = _make_user(email="other2@example.com")
    other_folder = FavoriteFolder.objects.create(user=other, name="남의 폴더")
    my_folder = FavoriteFolder.objects.create(user=user, name="내 폴더")
    client = _authed_client(user)

    response = client.patch(
        f"/api/me/favorites/{my_folder.id}", {"parent_id": other_folder.id}, format="json"
    )

    assert response.status_code == 403


def test_patch_on_another_users_folder_returns_403():
    user = _make_user()
    other = _make_user(email="other3@example.com")
    other_folder = FavoriteFolder.objects.create(user=other, name="남의 폴더")
    client = _authed_client(user)

    response = client.patch(f"/api/me/favorites/{other_folder.id}", {"name": "수정"}, format="json")

    assert response.status_code == 403


def test_patch_on_nonexistent_folder_returns_404():
    user = _make_user()
    client = _authed_client(user)

    response = client.patch("/api/me/favorites/999999", {"name": "수정"}, format="json")

    assert response.status_code == 404


def test_delete_reparents_children_and_buildings_then_removes_folder():
    user = _make_user()
    root = FavoriteFolder.objects.create(user=user, name="루트")
    middle = FavoriteFolder.objects.create(user=user, parent=root, name="중간")
    leaf = FavoriteFolder.objects.create(user=user, parent=middle, name="말단")
    building = _make_building(building_key="FTB4", gis_bldg_id="FTB4", pnu="3011010300101530073")
    mark = UserBuilding.objects.create(
        user=user, building=building, is_favorite=True, folder=middle
    )
    client = _authed_client(user)

    response = client.delete(f"/api/me/favorites/{middle.id}")

    assert response.status_code == 204
    assert not FavoriteFolder.objects.filter(id=middle.id).exists()
    leaf.refresh_from_db()
    assert leaf.parent_id == root.id  # 하위 폴더는 삭제된 폴더의 부모로 승격
    mark.refresh_from_db()
    assert mark.folder_id == root.id  # 건물도 같이 승격
    assert mark.is_favorite is True  # 즐겨찾기 자체는 해제되지 않음


def test_bulk_move_buildings_into_folder():
    user = _make_user()
    folder = FavoriteFolder.objects.create(user=user, name="대상 폴더")
    building1 = _make_building(building_key="FTB5", gis_bldg_id="FTB5", pnu="3011010300101530074")
    building2 = _make_building(building_key="FTB6", gis_bldg_id="FTB6", pnu="3011010300101530075")
    UserBuilding.objects.create(user=user, building=building1, is_favorite=True)
    UserBuilding.objects.create(user=user, building=building2, is_favorite=True)
    client = _authed_client(user)

    response = client.post(
        f"/api/me/favorites/{folder.id}/buildings",
        {"building_ids": [building1.id, building2.id]},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["moved"] == 2
    assert UserBuilding.objects.filter(building=building1).first().folder_id == folder.id


def test_bulk_move_to_unclassified_with_null_literal():
    user = _make_user()
    folder = FavoriteFolder.objects.create(user=user, name="원래 폴더")
    building = _make_building(building_key="FTB7", gis_bldg_id="FTB7", pnu="3011010300101530076")
    UserBuilding.objects.create(user=user, building=building, is_favorite=True, folder=folder)
    client = _authed_client(user)

    response = client.post(
        "/api/me/favorites/null/buildings", {"building_ids": [building.id]}, format="json"
    )

    assert response.status_code == 200
    assert UserBuilding.objects.get(building=building).folder_id is None
