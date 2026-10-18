"""index_run 보관 기한 정리(spec 5-4: "index_run | 1년")."""
import logging
from datetime import timedelta

from django.utils import timezone

from .models import IndexRun

logger = logging.getLogger(__name__)

INDEX_RUN_RETENTION_DAYS = 365


def cleanup_old_index_runs(now=None) -> int:
    """finished_at이 365일보다 오래된 행을 지운다.

    finished_at이 없는 행(skipped, 또는 멈춰 있는 running)은 "1년 지났다"를 판단할 기준이
    없어 그대로 둔다 — 잘못 지우는 것보다 사람이 보고 판단하는 쪽이 안전하다.
    """
    cutoff = (now or timezone.now()) - timedelta(days=INDEX_RUN_RETENTION_DAYS)
    deleted, _ = IndexRun.objects.filter(finished_at__lt=cutoff).delete()
    logger.info("cleanup_old_index_runs: %s개 삭제(cutoff=%s)", deleted, cutoff)
    return deleted
