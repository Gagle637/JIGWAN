from django.conf import settings
from django.db import models


class FavoriteFolder(models.Model):
    """즐겨찾기 폴더 트리(spec 6-5). parent는 자기 참조, 최대 깊이 5."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children"
    )
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, null=True, blank=True)
    is_hidden = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "favorite_folder"
        # 이름이 30자를 넘으면 안 됨(Django Index.max_name_length, models.E034).
        indexes = [models.Index(fields=["user", "parent"], name="fav_folder_user_parent_idx")]

    def __str__(self):
        return self.name


class UserBuilding(models.Model):
    """즐겨찾기·색상·라벨·메모(spec 6-4). 건물당 폴더 하나, 건물당 사용자 행 하나."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    building = models.ForeignKey("buildings.Building", on_delete=models.CASCADE)
    is_favorite = models.BooleanField(default=False)
    folder = models.ForeignKey(FavoriteFolder, on_delete=models.PROTECT, null=True, blank=True)
    color = models.CharField(max_length=7, null=True, blank=True)
    label = models.CharField(max_length=20, null=True, blank=True)
    memo = models.TextField(max_length=2000, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_building"
        constraints = [
            models.UniqueConstraint(fields=["user", "building"], name="uq_user_building")
        ]
        indexes = [
            models.Index(fields=["user", "folder"], name="user_building_user_folder_idx")
        ]

    def __str__(self):
        return f"{self.user_id}:{self.building_id}"
