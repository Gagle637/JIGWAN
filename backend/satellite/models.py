from django.contrib.gis.db import models as gis_models
from django.db import models


class SatelliteScene(models.Model):
    """Sentinel-2 L2A 장면(spec 2장, plan.md 8-2 기본 목록 + 추가 컬럼, 6단계 플랜에서 확정)."""

    class Status(models.TextChoices):
        LISTED = "listed", "listed"  # 백필 dry run이 STAC 검색만 하고 아직 다운로드 전(spec 4장)
        READY = "ready", "ready"
        EXCLUDED = "excluded", "excluded"  # 유효 화소 20% 미만(spec 2-3)
        FAILED = "failed", "failed"

    scene_id = models.CharField(max_length=80, unique=True)  # STAC item.id
    sensed_at = models.DateTimeField()
    mgrs_tile = models.CharField(max_length=10)
    cloud_pct = models.FloatField()
    processing_baseline = models.CharField(max_length=10)  # 예: "N0512"

    # MTD_MSIL2A.xml에서 읽은 반사율 변환 파라미터(spec 2-2). 구형 제품은 band_offsets가 전부 0.
    # listed 상태(다운로드 전)는 아직 MTD를 안 읽어서 null이다.
    band_offsets = models.JSONField(null=True, blank=True)  # {"B02": -1000, "B03": -1000, ...}
    boa_quantification_value = models.IntegerField(null=True, blank=True)

    valid_ratio = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    cog_path = models.CharField(max_length=255, null=True, blank=True)  # 반사율 5밴드(B02,B03,B04,B08,B11)
    scl_cog_path = models.CharField(max_length=255, null=True, blank=True)  # SCL 단일 밴드
    error = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "satellite_scene"
        indexes = [
            models.Index(fields=["mgrs_tile", "sensed_at"], name="satellite_tile_sensed_idx")
        ]

    def __str__(self):
        return self.scene_id


class RasterProduct(models.Model):
    """결과 카탈로그(spec 3-1). 계절 합성·변화 분석이 만드는 모든 결과 COG를 여기 등록한다."""

    class ProductType(models.TextChoices):
        NDVI = "ndvi", "ndvi"
        NDBI = "ndbi", "ndbi"
        GREEN_MASK = "green_mask", "green_mask"
        TRUECOLOR = "truecolor", "truecolor"
        CHANGE_MASK = "change_mask", "change_mask"

    class Season(models.TextChoices):
        SPRING = "spring", "spring"
        SUMMER = "summer", "summer"
        FALL = "fall", "fall"
        WINTER = "winter", "winter"

    # 기본값을 일부러 안 둔다(다지역 지원 5단계) — 지역 코드 없이 저장하면 안 되므로, 기존
    # 행을 채우는 "30"은 마이그레이션에만 있고(preserve_default=False) 모델에는 없다.
    region_code = models.CharField(max_length=2)
    product_type = models.CharField(max_length=20, choices=ProductType.choices)
    year = models.IntegerField()
    season = models.CharField(max_length=10, choices=Season.choices)
    period_start = models.DateField()
    period_end = models.DateField()
    compare_period = models.CharField(max_length=5, null=True, blank=True)  # "1y"/"2y"/"3y", change_mask만
    bbox = gis_models.PolygonField(srid=4326)
    crs = models.CharField(max_length=20, default="EPSG:32652")
    resolution_m = models.IntegerField(default=10)
    cog_path = models.CharField(max_length=255)
    algo_version = models.CharField(max_length=20)
    scene_ids = models.JSONField()
    valid_ratio = models.FloatField(null=True, blank=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        db_table = "raster_product"
        indexes = [
            models.Index(
                fields=["region_code", "product_type", "period_start"],
                name="raster_product_type_period_idx",
            )
        ]

    def __str__(self):
        return f"{self.product_type} {self.year} {self.season} ({self.algo_version})"


class ChangeArea(models.Model):
    """변화 분석이 만드는 변화 폴리곤(spec 3-1·5-4, plan.md 8-2)."""

    product = models.ForeignKey(
        RasterProduct, on_delete=models.CASCADE, related_name="change_areas"
    )
    period = models.CharField(max_length=5)  # "1y"/"2y"/"3y"
    area_m2 = models.FloatField()
    delta_ndbi = models.FloatField()
    delta_ndvi = models.FloatField()
    geom = gis_models.PolygonField(srid=4326)

    class Meta:
        db_table = "change_area"

    def __str__(self):
        return f"change_area#{self.pk} ({self.period})"


class RegionStat(models.Model):
    """구·시 평균 녹지율(지역 기준선, plan.md 8-2). region은 buildings 앱의 Region을 참조한다."""

    region = models.ForeignKey(
        "buildings.Region",
        on_delete=models.CASCADE,
        db_column="region_code",
        to_field="region_code",
    )
    product = models.ForeignKey(RasterProduct, on_delete=models.CASCADE)
    green_ratio = models.FloatField()

    class Meta:
        db_table = "region_stat"
        constraints = [
            models.UniqueConstraint(
                fields=["region", "product"], name="uq_region_stat_region_product"
            )
        ]

    def __str__(self):
        return f"{self.region_id} / {self.product_id}: {self.green_ratio}"
