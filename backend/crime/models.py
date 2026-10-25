from django.contrib.gis.db import models as gis_models
from django.db import models


class CrimeSegment(models.Model):
    """생활안전지도 범죄주의구간(전체) 밀도분석 구역(spec 8-3·8-4). 실측 확인: 도로 선이
    아니라 MultiPolygon 구역이다."""

    objt_id = models.CharField(max_length=40, unique=True)
    grad = models.SmallIntegerField()
    data_period = models.CharField(max_length=20)  # 예: "2023-07/2024-06"
    geom = gis_models.MultiPolygonField(srid=4326)

    class Meta:
        db_table = "crime_segment"
        indexes = [models.Index(fields=["grad"], name="crime_segment_grad_idx")]

    def __str__(self):
        return f"{self.objt_id} (grad={self.grad})"


class CrimeFetchProgress(models.Model):
    """2km(필요 시 4등분, 최소 250m) 구역별 수집 진행 상황(spec 8-4) — 중단 후 재개에 쓴다."""

    class Status(models.TextChoices):
        PENDING = "pending", "pending"
        DONE = "done", "done"
        SPLIT = "split", "split"  # 상한에 걸려 4등분하고 자식 셀에 넘김(자신은 완료로 취급)
        FAILED = "failed", "failed"

    # 기본값을 일부러 안 둔다(다지역 지원 6단계, raster_product.region_code와 같은 이유).
    # 셀 좌표가 두 지역 bbox에 모두 걸릴 수 있어(격자 여유 때문에) cell_id만으로는 더 이상
    # 유일하지 않다 — 유일 제약을 (cell_id, region_code)로 바꿨다.
    region_code = models.CharField(max_length=2)
    cell_id = models.CharField(max_length=60)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    feature_count = models.IntegerField(null=True, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "crime_fetch_progress"
        constraints = [
            models.UniqueConstraint(
                fields=["cell_id", "region_code"], name="crime_fetch_progress_cell_region_uniq"
            )
        ]

    def __str__(self):
        return f"{self.cell_id} ({self.region_code}, {self.status})"
