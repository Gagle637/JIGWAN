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
        indexes = [models.Index(fields=["job", "region_code"])]

    def __str__(self):
        return f"{self.job}:{self.region_code} [{self.status}]"
