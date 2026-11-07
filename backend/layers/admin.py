from django.contrib import admin

from .models import MapLayer


@admin.register(MapLayer)
class MapLayerAdmin(admin.ModelAdmin):
    list_display = ("order", "name", "slug", "group", "kind", "source_type", "default_visible", "synced_at")
    list_filter = ("group", "kind", "source_type", "default_visible")
