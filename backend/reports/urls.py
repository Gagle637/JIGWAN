from django.urls import path

from .views import BuildingReportsView, ReportDetailView

urlpatterns = [
    path(
        "buildings/<int:building_id>/reports",
        BuildingReportsView.as_view(),
        name="building-reports",
    ),
    path("reports/<int:report_id>", ReportDetailView.as_view(), name="report-detail"),
]
