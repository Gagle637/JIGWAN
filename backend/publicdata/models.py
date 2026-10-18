from django.contrib.gis.db import models as gis_models
from django.db import models


class Trade(models.Model):
    """국토부 실거래가(plan.md 8-2 기본 컬럼 + 매칭/모니터링에 필요한 컬럼, spec 8-1·8-7)."""

    class HouseType(models.TextChoices):
        APARTMENT = "apartment", "아파트"
        OFFICETEL = "officetel", "오피스텔"
        ROW_HOUSE = "row_house", "연립다세대"
        DETACHED = "detached", "단독다가구"

    class DealType(models.TextChoices):
        SALE = "sale", "매매"
        RENT = "rent", "전월세"

    sgg_code = models.CharField(max_length=5)
    pnu = models.CharField(max_length=19, null=True, blank=True, db_index=True)
    house_type = models.CharField(max_length=20, choices=HouseType.choices)
    deal_type = models.CharField(max_length=10, choices=DealType.choices)
    deal_ym = models.CharField(max_length=7)  # "YYYY-MM"
    deal_day = models.SmallIntegerField(null=True, blank=True)
    area_m2 = models.FloatField(null=True, blank=True)
    price = models.IntegerField(null=True, blank=True)  # 매매, 만원
    deposit = models.IntegerField(null=True, blank=True)  # 전월세 보증금, 만원
    monthly_rent = models.IntegerField(null=True, blank=True)  # 전월세 월세, 만원

    # 매칭·모니터링용(plan.md 8-2 기본 목록에 없던 추가 컬럼, 4단계 플랜에서 확정)
    apt_seq = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    building_name = models.CharField(max_length=150, null=True, blank=True)
    floor = models.SmallIntegerField(null=True, blank=True)
    build_year = models.SmallIntegerField(null=True, blank=True)
    is_canceled = models.BooleanField(default=False)
    canceled_at = models.DateField(null=True, blank=True)
    match_failure_reason = models.CharField(max_length=50, null=True, blank=True)
    raw_bjd_name = models.CharField(max_length=100, null=True, blank=True)
    raw_jibun = models.CharField(max_length=50, null=True, blank=True)

    geom = gis_models.PointField(srid=4326, null=True, blank=True)

    class Meta:
        db_table = "trade"
        indexes = [
            models.Index(fields=["pnu", "deal_ym"], name="trade_pnu_deal_ym_idx"),
            models.Index(
                fields=["house_type", "deal_type", "sgg_code", "deal_ym"],
                name="trade_type_sgg_ym_idx",
            ),
        ]

    def __str__(self):
        return f"{self.house_type}:{self.deal_type} {self.sgg_code} {self.deal_ym}"
