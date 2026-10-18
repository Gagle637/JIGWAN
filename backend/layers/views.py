from django.http import HttpResponse
from django.views import View
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MapLayer
from .registry import serialize_layer
from .wms_proxy import fetch_wms_tile

TILE_CACHE_CONTROL = "public, max-age=86400"


class MapLayerListView(APIView):
    """GET /api/layers — 인증 불필요(spec 9-1, 레이어는 비로그인 허용)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        layers = MapLayer.objects.order_by("order")
        return Response([serialize_layer(layer) for layer in layers])


class LayerTileProxyView(View):
    """GET /api/layers/{id}/tiles/{z}/{x}/{y}.png — 외부 WMS 중계(spec 10-3).

    인증 불필요(지도 레이어와 같은 접근 권한). source_type이 wms가 아니면 404.
    """

    def get(self, request, layer_id: int, z: int, x: int, y: int):
        layer = MapLayer.objects.filter(id=layer_id, source_type=MapLayer.SourceType.WMS).first()
        if layer is None:
            return HttpResponse(status=404)

        content = fetch_wms_tile(layer, z, x, y)
        response = HttpResponse(content, content_type="image/png")
        response["Cache-Control"] = TILE_CACHE_CONTROL
        return response
