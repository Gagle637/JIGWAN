from django.urls import path

from .views import (
    FavoriteFolderBuildingsView,
    FavoriteFolderDetailView,
    FavoritesListCreateView,
    MarkBuildingView,
    MeBuildingsView,
)

urlpatterns = [
    path("buildings/<int:building_id>/mark", MarkBuildingView.as_view(), name="building-mark"),
    path("me/favorites", FavoritesListCreateView.as_view(), name="favorites-list-create"),
    path(
        "me/favorites/<int:folder_id>",
        FavoriteFolderDetailView.as_view(),
        name="favorites-detail",
    ),
    path(
        "me/favorites/<str:folder_id>/buildings",
        FavoriteFolderBuildingsView.as_view(),
        name="favorites-buildings-move",
    ),
    path("me/buildings", MeBuildingsView.as_view(), name="me-buildings"),
]
