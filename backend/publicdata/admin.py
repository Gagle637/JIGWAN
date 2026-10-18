from django.contrib import admin

from .models import Trade


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = (
        "id", "house_type", "deal_type", "sgg_code", "deal_ym", "pnu",
        "price", "deposit", "monthly_rent", "match_failure_reason", "is_canceled",
    )
    list_filter = ("house_type", "deal_type", "sgg_code", "is_canceled")
    search_fields = ("pnu", "apt_seq", "building_name", "raw_bjd_name")
