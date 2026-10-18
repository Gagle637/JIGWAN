from django.db import models


class MapLayer(models.Model):
    """레이어 레지스트리(spec 10-2). 프론트는 /api/layers 목록만 받아 그린다."""

    class SourceType(models.TextChoices):
        VECTOR_TILE = "vector_tile", "vector_tile"
        GEOJSON = "geojson", "geojson"
        TITILER = "titiler", "titiler"
        WMS = "wms", "wms"
        # spec 10-2 표엔 4종만 있지만, "배경지도"(OSM 래스터 타일) 행을 등록하려면 하나가
        # 더 필요해서 추가했다(문서에 없는 값, 이번 플랜 리뷰에서 확정).
        RASTER_TILE = "raster_tile", "raster_tile"

    name = models.CharField(max_length=100, unique=True)
    group = models.CharField(max_length=50)
    order = models.IntegerField(default=0)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    source_params = models.JSONField(default=dict, blank=True)
    min_zoom = models.IntegerField(null=True, blank=True)
    max_zoom = models.IntegerField(null=True, blank=True)
    opacity = models.FloatField(default=1.0)
    default_visible = models.BooleanField(default=False)
    legend = models.JSONField(null=True, blank=True)
    notice = models.TextField(null=True, blank=True)
    attribution = models.CharField(max_length=255, null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "map_layer"
        ordering = ["order"]

    def __str__(self):
        return self.name
