import redis
from django.conf import settings

_client = None


def get_redis_client():
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_CACHE_URL)
    return _client


def build_lock_key(job: str, region_code: str) -> str:
    return f"lock:{job}:{region_code}"


def acquire_lock(job: str, region_code: str, ttl_seconds: int):
    """비차단 잠금 획득. 이미 잠겨 있으면 None을 반환한다(spec 5-2)."""
    client = get_redis_client()
    lock = client.lock(build_lock_key(job, region_code), timeout=ttl_seconds)
    return lock if lock.acquire(blocking=False) else None


def release_lock(lock) -> None:
    if lock is None:
        return
    try:
        lock.release()
    except redis.exceptions.LockError:
        pass
