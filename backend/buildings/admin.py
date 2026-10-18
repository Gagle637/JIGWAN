from django.contrib import admin

from .models import Building, Region


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ("building_key", "pnu", "bjd_code", "name", "source_date", "is_active")
    list_filter = ("is_active", "source_date")
    search_fields = ("building_key", "gis_bldg_id", "pnu", "bjd_code")


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("region_code", "level", "name", "parent", "source_date")
    list_filter = ("level",)
    search_fields = ("region_code", "name")
