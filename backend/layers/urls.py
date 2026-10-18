from django.urls import path

from .views import LayerTileProxyView, MapLayerListView

urlpatterns = [
    path("layers", MapLayerListView.as_view(), name="map-layer-list"),
    path(
        "layers/<int:layer_id>/tiles/<int:z>/<int:x>/<int:y>.png",
        LayerTileProxyView.as_view(),
        name="map-layer-tile",
    ),
]
