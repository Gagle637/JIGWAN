from celery import shared_task
from django.conf import settings

from core.areas import enabled_and_ready_sido_codes
from core.jobs import TrackedTask, tracked_job
from layers.wms_proxy import clear_tile_cache

from .collect import run_safety_sync
from .registry import crime_layer_id


@shared_task(bind=True, base=TrackedTask, max_retries=3)
@tracked_job(job_name="safety_sync", lock_ttl_seconds=3600 * 8)
def safety_sync(self, sido_code, data_period=None):
    """spec 5-1: 매년 1월 첫째 주 + 수동, io 큐. 셀 단위 재시도는 collect.py 안에서 처리하므로
    여기서는 index_run 기록·잠금만 담당한다(개별 셀 실패는 전체 잡을 죽이지 않음).

    sido_code가 잠금/index_run 키와 실제 수집 대상 지역을 겸한다(다지역 지원 7단계 —
    지금까지는 잠금 키("daejeon")와 지역(sido_code)이 따로였는데, 잠금 체계 자체가
    지역 기반으로 바뀌면서 하나로 합쳤다)."""
    period = data_period or settings.CRIME_DATA_PERIOD
    result = run_safety_sync(period, sido_code=sido_code)

    layer_id = crime_layer_id()
    if layer_id is not None:
        clear_tile_cache(layer_id)

    return result


@shared_task
def trigger_safety_sync_for_enabled_regions():
    """Beat가 매년 1월 첫째 주(spec 5-1) 호출하는 디스패처 — 활성 지역마다 safety_sync를
    하나씩 돌린다(다지역 지원 7단계)."""
    for sido_code in enabled_and_ready_sido_codes():
        safety_sync.delay(sido_code)
