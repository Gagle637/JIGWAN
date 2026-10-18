from django.contrib.gis.db import models as gis_models
from django.db import models


class Building(models.Model):
    """GIS건물통합정보(spec 8-6) 매핑. A0, A6·A7, A10, A19, A21, A23, A28은 적재하지 않는다."""

    building_key = models.CharField(max_length=40, unique=True)
    gis_bldg_id = models.CharField(max_length=28, db_index=True)  # A1
    pnu = models.CharField(max_length=19, db_index=True)  # A2
    bjd_code = models.CharField(max_length=10)  # A3
    bjd_name = models.CharField(max_length=100, null=True, blank=True)  # A4
    jibun = models.CharField(max_length=20, null=True, blank=True)  # A5
    use_code = models.CharField(max_length=5, null=True, blank=True)  # A8
    use_name = models.CharField(max_length=100, null=True, blank=True)  # A9
    structure = models.CharField(max_length=100, null=True, blank=True)  # A11
    building_area_m2 = models.FloatField(null=True, blank=True)  # A12
    approval_date = models.DateField(null=True, blank=True)  # A13
    total_floor_area_m2 = models.FloatField(null=True, blank=True)  # A14
    land_area_m2 = models.FloatField(null=True, blank=True)  # A15
    height_m = models.FloatField(null=True, blank=True)  # A16
    bcr_pct = models.FloatField(null=True, blank=True)  # A17
    far_pct = models.FloatField(null=True, blank=True)  # A18
    is_violation = models.BooleanField(null=True, blank=True)  # A20
    name = models.CharField(max_length=150, null=True, blank=True)  # A24
    dong_name = models.CharField(max_length=100, null=True, blank=True)  # A25
    floors_above = models.SmallIntegerField(null=True, blank=True)  # A26
    floors_below = models.SmallIntegerField(null=True, blank=True)  # A27
    source_date = models.DateField()  # A22
    is_active = models.BooleanField(default=True)
    geom = gis_models.PolygonField(srid=4326)

    class Meta:
        db_table = "building"
        indexes = [models.Index(fields=["bjd_code"])]

    def __str__(self):
        return self.building_key


class Region(models.Model):
    """법정구역 경계(plan.md 8-2). region_code가 PK이고, 한국 행정코드의 접두 구조를 그대로
    parent에 반영한다(시도 2자리 ⊂ 시군구 5자리 ⊂ 법정동 10자리)."""

    LEVEL_CHOICES = [
        ("sido", "시도"),
        ("sigungu", "시군구"),
        ("bjd", "법정동"),
    ]

    region_code = models.CharField(max_length=10, primary_key=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_column="parent_code",
        to_field="region_code",
        related_name="children",
    )
    source_date = models.DateField(null=True, blank=True)
    geom = gis_models.MultiPolygonField(srid=4326)

    class Meta:
        db_table = "region"
        indexes = [models.Index(fields=["level"])]

    def __str__(self):
        return f"{self.region_code} {self.name}"
