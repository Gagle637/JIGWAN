import logging

from celery import shared_task

from core.jobs import TrackedTask, tracked_job

from .sync import current_and_previous_month, sync_trades_for_months

logger = logging.getLogger(__name__)


@shared_task(bind=True, base=TrackedTask, max_retries=3)
@tracked_job(job_name="trade_sync", lock_ttl_seconds=3600)
def trade_sync(self, region_code="daejeon"):
    """당월·전월 실거래를 재수집한다(spec 5-1: 매일 04:00, io 큐)."""
    months = current_and_previous_month()
    return sync_trades_for_months(months)
