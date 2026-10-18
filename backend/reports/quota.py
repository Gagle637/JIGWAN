"""사용자별 하루 20건·동시 생성 1건 한도(spec 6-4, 7-4). failed는 차감하지 않는다 —
항상 현재 상태를 다시 세므로 나중에 실패로 끝난 리포트는 자동으로 한도에서 빠진다."""
from django.utils import timezone

from .exceptions import ReportQuotaExceeded
from .models import Report

DAILY_LIMIT = 20


def check_quota(user) -> None:
    if Report.objects.filter(user=user, status=Report.Status.GENERATING).exists():
        raise ReportQuotaExceeded("동시 생성은 1건까지입니다.")

    today_count = Report.objects.filter(user=user, created_at__date=timezone.localdate()).exclude(
        status=Report.Status.FAILED
    ).count()
    if today_count >= DAILY_LIMIT:
        raise ReportQuotaExceeded(f"하루 생성 한도({DAILY_LIMIT}건)를 초과했습니다.")
