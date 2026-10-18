from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


class UserAdmin(DjangoUserAdmin):
    model = User
    ordering = ("email",)
    list_display = ("email", "is_staff", "is_active", "privacy_consent_at")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("권한", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (
            "기타",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "last_login",
                    "date_joined",
                    "privacy_consent_at",
                )
            },
        ),
    )
    add_fieldsets = (
        (None, {"fields": ("email", "password1", "password2")}),
    )
    search_fields = ("email",)


admin.site.register(User, UserAdmin)
