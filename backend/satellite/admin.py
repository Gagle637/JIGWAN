from django.contrib import admin

from .models import ChangeArea, RasterProduct, RegionStat, SatelliteScene


@admin.register(SatelliteScene)
class SatelliteSceneAdmin(admin.ModelAdmin):
    list_display = (
        "scene_id", "mgrs_tile", "sensed_at", "cloud_pct", "processing_baseline",
        "valid_ratio", "status",
    )
    list_filter = ("status", "mgrs_tile")
    search_fields = ("scene_id",)


@admin.register(RasterProduct)
class RasterProductAdmin(admin.ModelAdmin):
    list_display = (
        "id", "product_type", "year", "season", "compare_period",
        "algo_version", "valid_ratio", "is_published",
    )
    list_filter = ("product_type", "year", "season", "is_published", "algo_version")


@admin.register(ChangeArea)
class ChangeAreaAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "period", "area_m2", "delta_ndbi", "delta_ndvi")
    list_filter = ("period",)


@admin.register(RegionStat)
class RegionStatAdmin(admin.ModelAdmin):
    list_display = ("id", "region", "product", "green_ratio")
