from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import IndexRun
from core.retention import cleanup_old_index_runs

pytestmark = pytest.mark.django_db


def test_cleanup_deletes_runs_finished_over_a_year_ago():
    now = timezone.now()
    old = IndexRun.objects.create(
        job="trade_sync",
        region_code="daejeon",
        status=IndexRun.Status.SUCCEEDED,
        finished_at=now - timedelta(days=400),
    )
    recent = IndexRun.objects.create(
        job="trade_sync",
        region_code="daejeon",
        status=IndexRun.Status.SUCCEEDED,
        finished_at=now - timedelta(days=10),
    )

    deleted = cleanup_old_index_runs(now=now)

    assert deleted == 1
    assert not IndexRun.objects.filter(id=old.id).exists()
    assert IndexRun.objects.filter(id=recent.id).exists()


def test_cleanup_keeps_runs_exactly_at_the_boundary():
    now = timezone.now()
    # 정확히 365일(경계)은 "지난"에 포함 안 된다(<, 미만) — 안전하게 보수적인 쪽으로.
    boundary = IndexRun.objects.create(
        job="trade_sync",
        region_code="daejeon",
        status=IndexRun.Status.SUCCEEDED,
        finished_at=now - timedelta(days=365),
    )

    cleanup_old_index_runs(now=now)

    assert IndexRun.objects.filter(id=boundary.id).exists()


def test_cleanup_keeps_runs_without_finished_at():
    skipped = IndexRun.objects.create(
        job="trade_sync", region_code="daejeon", status=IndexRun.Status.SKIPPED
    )

    cleanup_old_index_runs()

    assert IndexRun.objects.filter(id=skipped.id).exists()
