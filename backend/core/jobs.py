from contextlib import contextmanager
from functools import wraps

from celery import Task
from django.utils import timezone

from .exceptions import ExternalCallError
from .locks import acquire_lock, release_lock
from .models import IndexRun

# 재시도 간격 1·5·25분(spec 5-2)
RETRY_COUNTDOWNS_SECONDS = [60, 300, 1500]


class TrackedTask(Task):
    """tracked_job 데코레이터와 함께 쓰는 Celery Task 베이스.

    재시도 여부는 tracked_job이 직접 판단하므로, Celery 자체 자동재시도는 쓰지 않는다.
    """

    autoretry_for = ()


def tracked_job(job_name: str, lock_ttl_seconds: int = 3600):
    """배치 잡 본문을 index_run 기록·Redis 잠금·재시도 규칙으로 감싼다(spec 5-2).

    - index_run에 queued → running → succeeded/failed/skipped 기록
    - Redis 잠금 lock:{job}:{region_code}, 이미 잠겨 있으면 skipped
    - 본문에서 raise한 ExternalCallError만 1·5·25분 간격 최대 3회 재시도
      (TrackedTask를 base로 쓰고 바인딩된 task의 max_retries가 3이어야 한다)
    - 그 외 예외는 재시도 없이 즉시 failed
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, region_code, *args, **kwargs):
            run = IndexRun.objects.create(
                job=job_name,
                region_code=region_code,
                status=IndexRun.Status.QUEUED,
            )

            lock = acquire_lock(job_name, region_code, lock_ttl_seconds)
            if lock is None:
                run.status = IndexRun.Status.SKIPPED
                run.save(update_fields=["status"])
                return None

            run.status = IndexRun.Status.RUNNING
            run.started_at = timezone.now()
            run.save(update_fields=["status", "started_at"])

            try:
                result = func(self, region_code, *args, **kwargs)
            except ExternalCallError as exc:
                release_lock(lock)
                retries = self.request.retries
                if retries < len(RETRY_COUNTDOWNS_SECONDS):
                    raise self.retry(exc=exc, countdown=RETRY_COUNTDOWNS_SECONDS[retries])
                run.status = IndexRun.Status.FAILED
                run.error = str(exc)
                run.finished_at = timezone.now()
                run.save(update_fields=["status", "error", "finished_at"])
                raise
            except Exception as exc:
                run.status = IndexRun.Status.FAILED
                run.error = str(exc)
                run.finished_at = timezone.now()
                run.save(update_fields=["status", "error", "finished_at"])
                release_lock(lock)
                raise
            else:
                run.status = IndexRun.Status.SUCCEEDED
                run.finished_at = timezone.now()
                run.save(update_fields=["status", "finished_at"])
                release_lock(lock)
                return result

        return wrapper

    return decorator


class JobSkipped(Exception):
    """잠금을 이미 다른 실행이 쥐고 있어 본문을 실행하지 못했다(tracked_run 진입 전)."""


class SkipJob(Exception):
    """본문이 스스로 '더 할 일 없음'을 선언할 때 쓴다. failed가 아니라 skipped로 기록된다."""


@contextmanager
def tracked_run(job_name: str, region_code: str, lock_ttl_seconds: int = 3600):
    """Celery 없이 동기로 실행되는 관리 명령 등에서 쓰는 index_run 기록 + 잠금 컨텍스트.

    tracked_job과 달리 Celery bound task를 전제하지 않으므로 재시도 로직이 없다
    (실패하면 운영자가 다시 실행하는 것을 전제로 한다).
    """
    run = IndexRun.objects.create(
        job=job_name, region_code=region_code, status=IndexRun.Status.QUEUED
    )

    lock = acquire_lock(job_name, region_code, lock_ttl_seconds)
    if lock is None:
        run.status = IndexRun.Status.SKIPPED
        run.save(update_fields=["status"])
        raise JobSkipped(job_name, region_code)

    run.status = IndexRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])

    try:
        yield run
    except SkipJob as exc:
        run.status = IndexRun.Status.SKIPPED
        run.error = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        release_lock(lock)
        # 의도된 조기 종료이므로 호출자에게 전파하지 않는다.
    except BaseException as exc:
        # Ctrl+C(KeyboardInterrupt)는 Exception이 아니라 BaseException이라 except
        # Exception으로는 안 잡힌다 — 그러면 락이 안 풀려 다음 실행이 계속 skipped된다
        # (실제 재현됨). SystemExit도 같은 이유로 여기서 같이 잡는다.
        run.status = IndexRun.Status.FAILED
        run.error = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        release_lock(lock)
        raise
    else:
        run.status = IndexRun.Status.SUCCEEDED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
        release_lock(lock)
