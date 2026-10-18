from celery import shared_task
from django.conf import settings

from core.jobs import TrackedTask, tracked_job
from layers.wms_proxy import clear_tile_cache

from .collect import run_safety_sync
from .registry import crime_layer_id


@shared_task(bind=True, base=TrackedTask, max_retries=3)
@tracked_job(job_name="safety_sync", lock_ttl_seconds=3600 * 8)
def safety_sync(self, region_code="daejeon", data_period=None):
    """spec 5-1: 매년 1월 첫째 주 + 수동, io 큐. 셀 단위 재시도는 collect.py 안에서 처리하므로
    여기서는 index_run 기록·잠금만 담당한다(개별 셀 실패는 전체 잡을 죽이지 않음)."""
    period = data_period or settings.CRIME_DATA_PERIOD
    result = run_safety_sync(period)

    layer_id = crime_layer_id()
    if layer_id is not None:
        clear_tile_cache(layer_id)

    return result
