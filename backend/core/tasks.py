import logging

from celery import shared_task

from .jobs import TrackedTask, tracked_job
from .retention import cleanup_old_index_runs

logger = logging.getLogger(__name__)


@shared_task(bind=True, base=TrackedTask, max_retries=3)
@tracked_job(job_name="healthcheck_ping", lock_ttl_seconds=3600)
def healthcheck_ping(self, region_code):
    """스캐폴딩 단계의 데모 잡: tracked_job 래퍼가 실제로 동작하는지 증명한다."""
    logger.info("healthcheck_ping ok region_code=%s", region_code)
    return "ok"


@shared_task(bind=True, base=TrackedTask, max_retries=3)
@tracked_job(job_name="cleanup_index_runs", lock_ttl_seconds=3600)
def cleanup_index_runs_task(self, region_code="global"):
    """spec 5-4: index_run 1년 보관. 주 1회(Beat, cpu 큐).

    지역별 작업이 아니다 — region_code는 실제 지역이 아니라 이 전역 잡의 잠금/index_run
    식별자일 뿐이다(다지역 지원 7단계: "daejeon"은 오해를 줄 수 있어 "global"로 바꿈)."""
    return {"deleted": cleanup_old_index_runs()}
