from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("core.urls")),
    path("api/", include("accounts.urls")),
    path("api/", include("buildings.urls")),
    path("api/", include("favorites.urls")),
    path("api/", include("layers.urls")),
    path("api/", include("reports.urls")),
    # Swagger UI. DEFAULT_PERMISSION_CLASSES가 fail-closed(IsAuthenticated)라 다른 공개
    # 뷰들과 같은 패턴(authentication_classes=[], permission_classes=[AllowAny])으로 연다
    # — 스키마 자체엔 URL 경로·파라미터 이름뿐이라 민감정보 없음.
    path(
        "api/schema/",
        SpectacularAPIView.as_view(authentication_classes=[], permission_classes=[AllowAny]),
        name="schema",
    ),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema", authentication_classes=[], permission_classes=[AllowAny]
        ),
        name="swagger-ui",
    ),
]
