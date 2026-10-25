import logging

from celery import shared_task

from core.jobs import TrackedTask, tracked_job

from .sync import current_and_previous_month, sync_trades_for_months

logger = logging.getLogger(__name__)


@shared_task(bind=True, base=TrackedTask, max_retries=3)
@tracked_job(job_name="trade_sync", lock_ttl_seconds=3600)
def trade_sync(self, sido_code="30"):
    """당월·전월 실거래를 재수집한다(spec 5-1: 매일 04:00, io 큐).

    sido_code 기본값 "30"(대전)은 다지역 지원 7단계에서 지역 반복으로 바꿀 때 없앤다
    (위성 쪽 satellite_collect와 같은 패턴) — 지금은 잠금/index_run 키로도 쓰인다."""
    months = current_and_previous_month()
    return sync_trades_for_months(months, sido_code=sido_code)
