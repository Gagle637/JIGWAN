from django.contrib import admin

from .models import FavoriteFolder, UserBuilding


@admin.register(FavoriteFolder)
class FavoriteFolderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "parent", "name", "is_hidden", "sort_order")
    list_filter = ("is_hidden",)


@admin.register(UserBuilding)
class UserBuildingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "building", "is_favorite", "folder", "updated_at")
    list_filter = ("is_favorite",)
