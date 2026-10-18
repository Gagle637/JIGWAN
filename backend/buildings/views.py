import json

from django.db import connection
from django.http import HttpResponse
from django.views import View
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .exceptions import BuildingNotFound, NoBuildingAtPoint
from .insight import ALLOWED_RADIUS_M, build_insight_for_request
from .models import Building
from .search import search_buildings
from .tiles import render_building_tile

TILE_CACHE_CONTROL = "public, max-age=86400"

_AT_POINT_SQL = """
SELECT id, pnu, ST_AsGeoJSON(geom) AS geometry
FROM building
WHERE is_active AND ST_Intersects(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
ORDER BY ST_Area(geom::geography) ASC
LIMIT 1
"""


class BuildingTileView(View):
    """GET /api/tiles/buildings/{z}/{x}/{y}.mvt — 인증 불필요(spec 9-1: 레이어는 비로그인 허용)."""

    def get(self, request, z: int, x: int, y: int):
        tile = render_building_tile(z, x, y)
        response = HttpResponse(tile, content_type="application/vnd.mapbox-vector-tile")
        response["Cache-Control"] = TILE_CACHE_CONTROL
        return response


class BuildingAtPointView(APIView):
    """GET /api/buildings/at?lon=&lat= — 인증 불필요(spec 9-1: 비로그인 API)."""

    permission_classes = [AllowAny]

    def get(self, request):
        lon_raw = request.query_params.get("lon")
        lat_raw = request.query_params.get("lat")
        try:
            lon = float(lon_raw)
            lat = float(lat_raw)
        except (TypeError, ValueError):
            raise ValidationError("lon·lat는 숫자로 줘야 합니다.")

        with connection.cursor() as cur:
            cur.execute(_AT_POINT_SQL, [lon, lat])
            row = cur.fetchone()

        if row is None:
            raise NoBuildingAtPoint()

        building_id, pnu, geometry_json = row
        return Response(
            {"id": building_id, "pnu": pnu, "geometry": json.loads(geometry_json)}
        )


class BuildingSearchView(APIView):
    """GET /api/buildings/search?q= — 인증 불필요, IP당 분당 30회(spec 9-1)."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "search"

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if not q:
            raise ValidationError("q는 필수입니다.")
        return Response({"results": search_buildings(q)})


class BuildingInsightView(APIView):
    """GET /api/buildings/{id}/insight?radius=500 — 인증 불필요, IP당 분당 60회(spec 9-1).

    AllowAny지만 JWTAuthentication은 그대로 켜져 있어, 토큰을 보내면 request.user가 채워져
    my 섹션이 로그인 사용자 기준으로 나온다(비로그인이면 my=null).
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "insight"

    def get(self, request, pk: int):
        radius_raw = request.query_params.get("radius", "500")
        try:
            radius_m = int(radius_raw)
        except ValueError:
            radius_m = None
        if radius_m not in ALLOWED_RADIUS_M:
            raise ValidationError("radius는 500 또는 1000만 허용합니다.")

        building = Building.objects.filter(is_active=True, pk=pk).first()
        if building is None:
            raise BuildingNotFound()

        return Response(build_insight_for_request(building, radius_m, request.user))
