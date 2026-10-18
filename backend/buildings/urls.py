from django.urls import path

from .views import (
    BuildingAtPointView,
    BuildingInsightView,
    BuildingSearchView,
    BuildingTileView,
)

urlpatterns = [
    path(
        "tiles/buildings/<int:z>/<int:x>/<int:y>.mvt",
        BuildingTileView.as_view(),
        name="building-tile",
    ),
    path("buildings/at", BuildingAtPointView.as_view(), name="building-at"),
    path("buildings/search", BuildingSearchView.as_view(), name="building-search"),
    path(
        "buildings/<int:pk>/insight",
        BuildingInsightView.as_view(),
        name="building-insight",
    ),
]
