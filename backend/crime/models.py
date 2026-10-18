from django.contrib.gis.db import models as gis_models
from django.db import models


class CrimeSegment(models.Model):
    """생활안전지도 범죄주의구간(전체) 도로 구간(spec 8-3·8-4)."""

    objt_id = models.CharField(max_length=40, unique=True)
    grad = models.SmallIntegerField()
    data_period = models.CharField(max_length=20)  # 예: "2023-07/2024-06"
    geom = gis_models.LineStringField(srid=4326)

    class Meta:
        db_table = "crime_segment"
        indexes = [models.Index(fields=["grad"])]

    def __str__(self):
        return f"{self.objt_id} (grad={self.grad})"


class CrimeFetchProgress(models.Model):
    """2km(필요 시 4등분, 최소 250m) 구역별 수집 진행 상황(spec 8-4) — 중단 후 재개에 쓴다."""

    class Status(models.TextChoices):
        PENDING = "pending", "pending"
        DONE = "done", "done"
        SPLIT = "split", "split"  # 상한에 걸려 4등분하고 자식 셀에 넘김(자신은 완료로 취급)
        FAILED = "failed", "failed"

    cell_id = models.CharField(max_length=60, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    feature_count = models.IntegerField(null=True, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "crime_fetch_progress"

    def __str__(self):
        return f"{self.cell_id} ({self.status})"
