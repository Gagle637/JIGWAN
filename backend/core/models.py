from django.db import models


class IndexRun(models.Model):
    """모든 배치 잡의 실행 기록(spec 5-2, 8-2)."""

    class Status(models.TextChoices):
        QUEUED = "queued", "queued"
        RUNNING = "running", "running"
        SUCCEEDED = "succeeded", "succeeded"
        FAILED = "failed", "failed"
        SKIPPED = "skipped", "skipped"

    job = models.CharField(max_length=100)
    region_code = models.CharField(max_length=50)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.QUEUED
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "index_run"
        indexes = [
            models.Index(fields=["job", "region_code"], name="index_run_job_region_code_idx")
        ]

    def __str__(self):
        return f"{self.job}:{self.region_code} [{self.status}]"


class ServiceArea(models.Model):
    """지금 서비스하는 시도 단위 지역(docs/tasks/multi_area.md 1단계). bbox(4326)·grid
    (EPSG:32652 고정 격자)는 지역을 추가할 때 한 번만 계산해 저장하고, 그 뒤로는
    region을 다시 적재해도 재계산하지 않는다(core.areas.compute_and_store_grid) —
    이미 그 격자로 써 둔 위성 COG가 있을 수 있어서다."""

    sido_code = models.CharField(max_length=2, primary_key=True)
    name = models.CharField(max_length=50)
    enabled = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)
    bbox_minx = models.FloatField(null=True, blank=True)
    bbox_miny = models.FloatField(null=True, blank=True)
    bbox_maxx = models.FloatField(null=True, blank=True)
    bbox_maxy = models.FloatField(null=True, blank=True)
    grid = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "service_area"

    def __str__(self):
        return f"{self.sido_code} {self.name}"
