import logging

from celery import shared_task

from .generation import ReportGenerationFailed, run_generation
from .models import Report

logger = logging.getLogger(__name__)


@shared_task
def generate_report(report_id: int):
    """gpu 큐. 재시도는 generation.py 안에서 셀(시도) 단위로 처리하므로 Celery 자동재시도는
    쓰지 않는다 — index_run 기반 배치 잡이 아니라 사용자 요청 1건을 다루는 작업이라
    core.jobs.tracked_job도 쓰지 않는다(플랜 리뷰에서 결정)."""
    report = Report.objects.get(id=report_id)

    try:
        payload, model_name = run_generation(report)
    except ReportGenerationFailed as exc:
        report.status = Report.Status.FAILED
        report.payload = {"error": str(exc)}
        report.save(update_fields=["status", "payload"])
        logger.warning("report#%s 생성 실패: %s", report_id, exc)
        return

    report.status = Report.Status.READY
    report.model = model_name
    report.payload = payload
    report.save(update_fields=["status", "model", "payload"])
    logger.info("report#%s 생성 완료", report_id)
