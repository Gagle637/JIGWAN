from django.contrib import admin

from .models import IndexRun


@admin.register(IndexRun)
class IndexRunAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "region_code", "status", "started_at", "finished_at")
    list_filter = ("job", "status")
