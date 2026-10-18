import json

from django.contrib.gis.geos import Polygon
from django.db.models import Count
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from buildings.exceptions import BuildingNotFound
from buildings.models import Building

from . import tree as tree_utils
from .colors import DEFAULT_FAVORITE_COLOR, PALETTE_COLORS
from .models import FavoriteFolder, UserBuilding


def _get_owned_folder(folder_id, user) -> FavoriteFolder:
    """폴더를 사용자 필터 없이 조회해 404/403을 구분한다(spec 9-5: 남의 데이터는 403)."""
    folder = FavoriteFolder.objects.filter(pk=folder_id).first()
    if folder is None:
        raise NotFound("폴더를 찾을 수 없습니다.")
    if folder.user_id != user.id:
        raise PermissionDenied("다른 사용자의 폴더입니다.")
    return folder


def _validate_color(color):
    if color is not None and color not in PALETTE_COLORS:
        raise ValidationError("color는 팔레트 8색 중 하나 또는 null이어야 합니다.")


def _serialize_folder(folder: FavoriteFolder) -> dict:
    return {
        "id": folder.id,
        "parent_id": folder.parent_id,
        "name": folder.name,
        "color": folder.color,
        "is_hidden": folder.is_hidden,
        "sort_order": folder.sort_order,
    }


def _serialize_mark(mark: UserBuilding) -> dict:
    return {
        "is_favorite": mark.is_favorite,
        "folder_id": mark.folder_id,
        "color": mark.color,
        "label": mark.label,
        "memo": mark.memo,
    }


def _empty_mark() -> dict:
    return {"is_favorite": False, "folder_id": None, "color": None, "label": None, "memo": None}


class MarkBuildingView(APIView):
    """PUT·DELETE /api/buildings/{id}/mark (spec 6-4)."""

    permission_classes = [IsAuthenticated]

    def _get_building(self, building_id) -> Building:
        building = Building.objects.filter(is_active=True, pk=building_id).first()
        if building is None:
            raise BuildingNotFound()
        return building

    def put(self, request, building_id):
        building = self._get_building(building_id)

        is_favorite = bool(request.data.get("is_favorite", False))
        color = request.data.get("color")
        label = request.data.get("label") or None
        memo = request.data.get("memo") or None
        folder_id = request.data.get("folder_id")

        _validate_color(color)
        if label is not None and len(label) > 20:
            raise ValidationError("label은 20자 이내여야 합니다.")
        if memo is not None and len(memo) > 2000:
            raise ValidationError("memo는 2,000자 이내여야 합니다.")

        # folder_id는 즐겨찾기일 때만 의미가 있다(spec 6-4) — 아니면 항상 null로 저장.
        folder = None
        if is_favorite and folder_id is not None:
            folder = _get_owned_folder(folder_id, request.user)

        if not is_favorite and color is None and label is None and memo is None:
            UserBuilding.objects.filter(user=request.user, building=building).delete()
            return Response(_empty_mark())

        mark, _ = UserBuilding.objects.update_or_create(
            user=request.user,
            building=building,
            defaults={
                "is_favorite": is_favorite,
                "folder": folder,
                "color": color,
                "label": label,
                "memo": memo,
            },
        )
        return Response(_serialize_mark(mark))

    def delete(self, request, building_id):
        building = self._get_building(building_id)
        UserBuilding.objects.filter(user=request.user, building=building).delete()
        return Response(status=204)


class FavoritesListCreateView(APIView):
    """GET·POST /api/me/favorites (spec 6-5)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        folders = list(FavoriteFolder.objects.filter(user=request.user))
        counts_qs = (
            UserBuilding.objects.filter(user=request.user, is_favorite=True)
            .values("folder_id")
            .annotate(count=Count("id"))
        )
        counts = {row["folder_id"]: row["count"] for row in counts_qs}
        return Response(tree_utils.build_tree(folders, counts))

    def post(self, request):
        name = (request.data.get("name") or "").strip()
        if not name:
            raise ValidationError("name은 필수입니다.")
        color = request.data.get("color")
        _validate_color(color)
        parent_id = request.data.get("parent_id")

        folders = list(FavoriteFolder.objects.filter(user=request.user))
        folders_by_id = {f.id: f for f in folders}

        parent = None
        if parent_id is not None:
            parent = folders_by_id.get(parent_id) or _get_owned_folder(parent_id, request.user)
            new_depth = tree_utils.depth_of(parent_id, folders_by_id) + 1
        else:
            new_depth = 1
        if new_depth > tree_utils.MAX_DEPTH:
            raise ValidationError("폴더 깊이가 최대 5를 넘습니다.")

        sibling_count = FavoriteFolder.objects.filter(user=request.user, parent_id=parent_id).count()
        folder = FavoriteFolder.objects.create(
            user=request.user, parent=parent, name=name, color=color, sort_order=sibling_count
        )
        return Response({"id": folder.id}, status=201)


class FavoriteFolderDetailView(APIView):
    """PATCH·DELETE /api/me/favorites/{folder_id} (spec 6-5)."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, folder_id):
        folder = _get_owned_folder(folder_id, request.user)
        folders = list(FavoriteFolder.objects.filter(user=request.user))
        folders_by_id = {f.id: f for f in folders}
        data = request.data

        if "name" in data:
            name = (data["name"] or "").strip()
            if not name:
                raise ValidationError("name은 비어 있을 수 없습니다.")
            folder.name = name
        if "color" in data:
            _validate_color(data["color"])
            folder.color = data["color"]
        if "is_hidden" in data:
            folder.is_hidden = bool(data["is_hidden"])
        if "sort_order" in data:
            folder.sort_order = int(data["sort_order"])
        if "parent_id" in data:
            new_parent_id = data["parent_id"]
            if new_parent_id is not None:
                new_parent = folders_by_id.get(new_parent_id) or _get_owned_folder(
                    new_parent_id, request.user
                )
                if tree_utils.is_descendant_or_self(new_parent_id, folder.id, folders_by_id):
                    raise ValidationError("폴더를 자기 하위로 옮길 수 없습니다.")
                new_depth = tree_utils.depth_of(new_parent_id, folders_by_id) + 1
            else:
                new_parent = None
                new_depth = 1
            height = tree_utils.subtree_height(folder.id, folders_by_id)
            if new_depth + height > tree_utils.MAX_DEPTH:
                raise ValidationError("이동하면 폴더 깊이가 최대 5를 넘습니다.")
            folder.parent = new_parent

        folder.save()
        return Response(_serialize_folder(folder))

    def delete(self, request, folder_id):
        folder = _get_owned_folder(folder_id, request.user)
        folders = list(FavoriteFolder.objects.filter(user=request.user))

        child_ids = [f.id for f in folders if f.parent_id == folder.id]
        # 하위 폴더·건물을 상위 폴더로 옮긴 뒤 삭제(spec 6-5, 즐겨찾기는 해제하지 않음).
        FavoriteFolder.objects.filter(id__in=child_ids).update(parent_id=folder.parent_id)
        UserBuilding.objects.filter(user=request.user, folder_id=folder.id).update(
            folder_id=folder.parent_id
        )
        folder.delete()
        return Response(status=204)


class FavoriteFolderBuildingsView(APIView):
    """POST /api/me/favorites/{folder_id}/buildings — 여러 건물을 한 번에 이동(spec 6-5).

    folder_id가 문자열 "null"이면 미분류로 이동(docs에 없어 정한 규칙).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, folder_id):
        if folder_id == "null":
            target_folder = None
        else:
            try:
                target_id = int(folder_id)
            except ValueError:
                raise ValidationError("folder_id는 정수 또는 'null'이어야 합니다.")
            target_folder = _get_owned_folder(target_id, request.user)

        building_ids = request.data.get("building_ids")
        if not isinstance(building_ids, list):
            raise ValidationError("building_ids는 배열이어야 합니다.")

        moved = UserBuilding.objects.filter(
            user=request.user, building_id__in=building_ids, is_favorite=True
        ).update(folder=target_folder)
        return Response({"moved": moved})


class MeBuildingsView(APIView):
    """GET /api/me/buildings?bbox=&folder_id= — 내가 표시한 건물(spec 6-4, 10-4)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        folders = list(FavoriteFolder.objects.filter(user=request.user))
        folders_by_id = {f.id: f for f in folders}

        qs = UserBuilding.objects.filter(user=request.user, is_favorite=True).select_related(
            "building"
        )

        folder_id_param = request.query_params.get("folder_id")
        if folder_id_param is not None:
            if folder_id_param == "null":
                qs = qs.filter(folder_id=None)
            else:
                try:
                    target_id = int(folder_id_param)
                except ValueError:
                    raise ValidationError("folder_id는 정수 또는 'null'이어야 합니다.")
                _get_owned_folder(target_id, request.user)
                ids = [target_id] + tree_utils.descendant_ids(target_id, folders_by_id)
                qs = qs.filter(folder_id__in=ids)

        bbox_param = request.query_params.get("bbox")
        if bbox_param:
            try:
                minx, miny, maxx, maxy = (float(v) for v in bbox_param.split(","))
            except ValueError:
                raise ValidationError("bbox는 minx,miny,maxx,maxy 형식이어야 합니다.")
            envelope = Polygon.from_bbox((minx, miny, maxx, maxy))
            envelope.srid = 4326
            qs = qs.filter(building__geom__intersects=envelope)

        features = []
        for mark in qs:
            if tree_utils.is_hidden(mark.folder_id, folders_by_id):
                continue
            color = mark.color or tree_utils.nearest_color(
                mark.folder_id, folders_by_id, DEFAULT_FAVORITE_COLOR
            )
            features.append(
                {
                    "type": "Feature",
                    "geometry": json.loads(mark.building.geom.geojson),
                    "properties": {
                        "building_id": mark.building_id,
                        "is_favorite": mark.is_favorite,
                        "color": color,
                        "label": mark.label,
                        "folder_id": mark.folder_id,
                    },
                }
            )
        return Response({"type": "FeatureCollection", "features": features})
