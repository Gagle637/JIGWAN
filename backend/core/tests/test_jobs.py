from unittest.mock import MagicMock

import pytest

from core.exceptions import ExternalCallError
from core.jobs import JobSkipped, SkipJob, tracked_job, tracked_run
from core.models import IndexRun


class FakeRequest:
    def __init__(self, retries):
        self.retries = retries


class FakeBoundTask:
    """Celery의 bound task(self)를 흉내 낸 테스트 더블.

    real self.retry()는 호출 즉시 예외를 던지고 반환하지 않으므로 동일하게 동작시킨다.
    """

    def __init__(self, retries=0):
        self.request = FakeRequest(retries)
        self.retry_calls = []

    def retry(self, exc=None, countdown=None):
        self.retry_calls.append((exc, countdown))
        raise exc


pytestmark = pytest.mark.django_db


def test_lock_held_skips_body_and_records_skipped(monkeypatch):
    monkeypatch.setattr("core.jobs.acquire_lock", lambda *a, **k: None)
    body = MagicMock()

    @tracked_job(job_name="t_skip", lock_ttl_seconds=60)
    def wrapped(self, region_code):
        body()
        return "ran"

    result = wrapped(FakeBoundTask(), "region-a")

    assert result is None
    body.assert_not_called()
    run = IndexRun.objects.get(job="t_skip", region_code="region-a")
    assert run.status == IndexRun.Status.SKIPPED


def test_success_records_succeeded(monkeypatch):
    fake_lock = MagicMock()
    monkeypatch.setattr("core.jobs.acquire_lock", lambda *a, **k: fake_lock)
    release = MagicMock()
    monkeypatch.setattr("core.jobs.release_lock", release)

    @tracked_job(job_name="t_ok", lock_ttl_seconds=60)
    def wrapped(self, region_code):
        return "ran"

    result = wrapped(FakeBoundTask(), "region-b")

    assert result == "ran"
    release.assert_called_once_with(fake_lock)
    run = IndexRun.objects.get(job="t_ok", region_code="region-b")
    assert run.status == IndexRun.Status.SUCCEEDED
    assert run.started_at is not None
    assert run.finished_at is not None
    assert run.started_at <= run.finished_at


def test_external_call_error_retries_with_backoff(monkeypatch):
    monkeypatch.setattr("core.jobs.acquire_lock", lambda *a, **k: MagicMock())
    monkeypatch.setattr("core.jobs.release_lock", MagicMock())

    @tracked_job(job_name="t_retry", lock_ttl_seconds=60)
    def wrapped(self, region_code):
        raise ExternalCallError("CDSE 503")

    task = FakeBoundTask(retries=0)
    with pytest.raises(ExternalCallError):
        wrapped(task, "region-c")

    assert task.retry_calls == [(task.retry_calls[0][0], 60)]  # 1분
    run = IndexRun.objects.get(job="t_retry", region_code="region-c")
    assert run.status == IndexRun.Status.RUNNING  # 재시도 대기 중, 아직 최종 상태 아님


@pytest.mark.parametrize("retries,expected_countdown", [(1, 300), (2, 1500)])
def test_external_call_error_backoff_schedule(monkeypatch, retries, expected_countdown):
    monkeypatch.setattr("core.jobs.acquire_lock", lambda *a, **k: MagicMock())
    monkeypatch.setattr("core.jobs.release_lock", MagicMock())

    @tracked_job(job_name="t_retry_n", lock_ttl_seconds=60)
    def wrapped(self, region_code):
        raise ExternalCallError("boom")

    task = FakeBoundTask(retries=retries)
    with pytest.raises(ExternalCallError):
        wrapped(task, "region-d")

    assert task.retry_calls[0][1] == expected_countdown


def test_external_call_error_exhausted_retries_fails(monkeypatch):
    monkeypatch.setattr("core.jobs.acquire_lock", lambda *a, **k: MagicMock())
    monkeypatch.setattr("core.jobs.release_lock", MagicMock())

    @tracked_job(job_name="t_exhausted", lock_ttl_seconds=60)
    def wrapped(self, region_code):
        raise ExternalCallError("still failing")

    task = FakeBoundTask(retries=3)  # 이미 3회 재시도 소진
    with pytest.raises(ExternalCallError):
        wrapped(task, "region-e")

    assert task.retry_calls == []  # 더 이상 재시도하지 않음
    run = IndexRun.objects.get(job="t_exhausted", region_code="region-e")
    assert run.status == IndexRun.Status.FAILED
    assert "still failing" in run.error


def test_data_error_fails_immediately_without_retry(monkeypatch):
    monkeypatch.setattr("core.jobs.acquire_lock", lambda *a, **k: MagicMock())
    monkeypatch.setattr("core.jobs.release_lock", MagicMock())

    @tracked_job(job_name="t_data_error", lock_ttl_seconds=60)
    def wrapped(self, region_code):
        raise ValueError("bad input")

    task = FakeBoundTask(retries=0)
    with pytest.raises(ValueError):
        wrapped(task, "region-f")

    assert task.retry_calls == []
    run = IndexRun.objects.get(job="t_data_error", region_code="region-f")
    assert run.status == IndexRun.Status.FAILED
    assert "bad input" in run.error


# ---- tracked_run: Celery 없이 동기 실행되는 관리 명령용 컨텍스트 매니저 ----


def test_tracked_run_lock_held_raises_job_skipped(monkeypatch):
    monkeypatch.setattr("core.jobs.acquire_lock", lambda *a, **k: None)

    with pytest.raises(JobSkipped):
        with tracked_run("t_run_skip", "region-x"):
            pytest.fail("잠금이 있으면 본문이 실행되면 안 됨")

    run = IndexRun.objects.get(job="t_run_skip", region_code="region-x")
    assert run.status == IndexRun.Status.SKIPPED


def test_tracked_run_skip_job_records_skipped_without_propagating(monkeypatch):
    monkeypatch.setattr("core.jobs.acquire_lock", lambda *a, **k: MagicMock())
    monkeypatch.setattr("core.jobs.release_lock", MagicMock())

    with tracked_run("t_run_noop", "region-y") as run:
        raise SkipJob("이미 최신")

    run.refresh_from_db()
    assert run.status == IndexRun.Status.SKIPPED
    assert run.error == "이미 최신"


def test_tracked_run_success_records_succeeded(monkeypatch):
    monkeypatch.setattr("core.jobs.acquire_lock", lambda *a, **k: MagicMock())
    monkeypatch.setattr("core.jobs.release_lock", MagicMock())

    with tracked_run("t_run_ok", "region-z") as run:
        pass

    run.refresh_from_db()
    assert run.status == IndexRun.Status.SUCCEEDED
    assert run.finished_at is not None


def test_tracked_run_failure_records_failed_and_propagates(monkeypatch):
    monkeypatch.setattr("core.jobs.acquire_lock", lambda *a, **k: MagicMock())
    monkeypatch.setattr("core.jobs.release_lock", MagicMock())

    with pytest.raises(ValueError):
        with tracked_run("t_run_fail", "region-w") as run:
            raise ValueError("boom")

    run.refresh_from_db()
    assert run.status == IndexRun.Status.FAILED
    assert "boom" in run.error
