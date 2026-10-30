import logging

from celery import shared_task

from core.areas import enabled_and_ready_sido_codes
from core.jobs import TrackedTask, tracked_job

from .sync import current_and_previous_month, sync_trades_for_months

logger = logging.getLogger(__name__)


@shared_task(bind=True, base=TrackedTask, max_retries=3)
@tracked_job(job_name="trade_sync", lock_ttl_seconds=3600)
def trade_sync(self, sido_code):
    """당월·전월 실거래를 재수집한다(spec 5-1: 매일 04:00, io 큐). sido_code는 잠금/
    index_run 키로도 쓰인다(위성 쪽 satellite_collect와 같은 패턴)."""
    months = current_and_previous_month()
    return sync_trades_for_months(months, sido_code=sido_code)


@shared_task
def trigger_trade_sync_for_enabled_regions():
    """Beat가 매일 04:00(spec 5-1) 호출하는 디스패처 — 활성 지역마다 trade_sync를 하나씩
    돌린다(다지역 지원 7단계)."""
    for sido_code in enabled_and_ready_sido_codes():
        trade_sync.delay(sido_code)
