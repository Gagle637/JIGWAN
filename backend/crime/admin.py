from django.contrib import admin

from .models import CrimeFetchProgress, CrimeSegment


@admin.register(CrimeSegment)
class CrimeSegmentAdmin(admin.ModelAdmin):
    list_display = ("objt_id", "grad", "data_period")
    list_filter = ("grad", "data_period")
    search_fields = ("objt_id",)


@admin.register(CrimeFetchProgress)
class CrimeFetchProgressAdmin(admin.ModelAdmin):
    list_display = ("cell_id", "status", "feature_count", "fetched_at")
    list_filter = ("status",)
