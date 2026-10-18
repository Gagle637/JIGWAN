from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    path("api/", include("accounts.urls")),
    path("api/", include("buildings.urls")),
    path("api/", include("favorites.urls")),
    path("api/", include("layers.urls")),
    path("api/", include("reports.urls")),
]
