from django.conf import settings
from django.db import models


class Report(models.Model):
    """사용자 요청으로 생성하는 gpt-oss 리포트(spec 6-4, 7장, plan.md 8-2)."""

    class ReportType(models.TextChoices):
        TEMPLATE = "template", "template"
        CUSTOM = "custom", "custom"

    class Status(models.TextChoices):
        GENERATING = "generating", "generating"
        READY = "ready", "ready"
        FAILED = "failed", "failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    building = models.ForeignKey("buildings.Building", on_delete=models.CASCADE)
    radius_m = models.IntegerField()
    report_type = models.CharField(max_length=10, choices=ReportType.choices)
    template_version = models.CharField(max_length=20, null=True, blank=True)
    prompt_version = models.CharField(max_length=20, null=True, blank=True)
    user_prompt = models.TextField(max_length=500, null=True, blank=True)
    input_snapshot = models.JSONField()
    model = models.CharField(max_length=100, null=True, blank=True)
    # ready: 검증된 출력(7-3/7-6 스키마). failed: {"error": "실패 사유"}(plan.md엔 별도
    # error 컬럼이 없어 payload를 재사용 — 9단계·10단계와 같은 "문서 컬럼 그대로" 원칙).
    payload = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.GENERATING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "report"
        indexes = [models.Index(fields=["user", "building", "created_at"])]

    def __str__(self):
        return f"report#{self.pk} ({self.status})"
