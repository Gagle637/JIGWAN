from datetime import date, timedelta

from celery import chain, group, shared_task

from core.areas import enabled_sido_codes
from core.jobs import TrackedTask, tracked_job

from .catalog import run_catalog_publish
from .change_detection import run_change_analysis
from .collect import collect_scenes
from .composite import run_season_composite
from .region_stats import run_region_stat
from .retention import cleanup_old_scene_cogs

# 5일 주기지만, 늦게 등록되는 장면을 놓치지 않으려고 더 넓게 훑는다(이미 있는 scene_id는 건너뜀).
LOOKBACK_DAYS = 30


@shared_task(bind=True, base=TrackedTask, max_retries=3)
@tracked_job(job_name="satellite_collect", lock_ttl_seconds=3600 * 6)
def satellite_collect(self, sido_code):
    """spec 5-1: 5일마다 02:00, io 큐. 직전 실행 이후 등록된 장면만 처리."""
    today = date.today()
    return collect_scenes(today - timedelta(days=LOOKBACK_DAYS), today, sido_code=sido_code)


@shared_task
def trigger_satellite_collect_for_enabled_regions():
    """Beat가 5일마다 02:00(spec 5-1) 호출하는 디스패처 — 활성 지역마다 satellite_collect를
    하나씩 돌린다(다지역 지원 7단계). 지금까지 이 작업은 Beat에 등록된 적이 없었다."""
    for sido_code in enabled_sido_codes():
        satellite_collect.delay(sido_code)


def _region_code(year: int, season: str, sido_code: str) -> str:
    """index_run/Redis 잠금 키에 sido_code·year·season을 실어 보낸다."""
    return f"{sido_code}:{year}:{season}"


@shared_task(bind=True, base=TrackedTask, max_retries=3)
@tracked_job(job_name="season_composite", lock_ttl_seconds=3600 * 4)
def season_composite(self, region_code, year, season, sido_code):
    return run_season_composite(year, season, sido_code)


@shared_task(bind=True, base=TrackedTask, max_retries=3)
@tracked_job(job_name="change_analysis", lock_ttl_seconds=3600 * 2)
def change_analysis(self, region_code, year, season, sido_code):
    return run_change_analysis(year, season, sido_code)


@shared_task(bind=True, base=TrackedTask, max_retries=3)
@tracked_job(job_name="region_stat", lock_ttl_seconds=3600)
def region_stat_task(self, region_code, year, season, sido_code):
    return run_region_stat(year, season, sido_code)


@shared_task(bind=True, base=TrackedTask, max_retries=3)
@tracked_job(job_name="catalog_publish", lock_ttl_seconds=3600)
def catalog_publish(self, region_code, year, season, sido_code):
    return run_catalog_publish(year, season, sido_code)


@shared_task(bind=True, base=TrackedTask, max_retries=3)
@tracked_job(job_name="cleanup_scene_cogs", lock_ttl_seconds=3600)
def cleanup_scene_cogs_task(self, region_code="global"):
    """spec 5-4: 장면별 COG는 계절 합성에 쓰인 지 90일 지나면 삭제. 주 1회(Beat, cpu 큐).

    지역별 작업이 아니다(모든 지역의 오래된 장면 COG를 한 번에 정리) — region_code는 실제
    지역이 아니라 이 전역 잡의 잠금/index_run 식별자일 뿐이다."""
    return cleanup_old_scene_cogs()


def build_season_chain(year: int, season: str, sido_code: str):
    """season_composite → group(change_analysis, region_stat) → catalog_publish(spec 5-2).

    전부 immutable(.si()) 서명이라 앞 단계 반환값이나 group 결과 리스트가 다음 태스크로
    전달되지 않는다 — 체인은 순서·실패 전파만 담당한다(결정 사항 3)."""
    rc = _region_code(year, season, sido_code)
    return chain(
        season_composite.si(rc, year, season, sido_code),
        group(
            change_analysis.si(rc, year, season, sido_code),
            region_stat_task.si(rc, year, season, sido_code),
        ),
        catalog_publish.si(rc, year, season, sido_code),
    )


def _season_just_ended(today: date) -> tuple[int, str]:
    """실행일(3/15,6/15,9/15,12/15) 기준으로 방금 끝난 계절을 돌려준다(spec 3-3).

    겨울은 Y년 12월~Y+1년 2월이고 기록 연도는 Y다 — 3/15에 끝나는 겨울은 작년(Y=today.year-1)."""
    month = today.month
    if month == 3:
        return today.year - 1, "winter"
    if month == 6:
        return today.year, "spring"
    if month == 9:
        return today.year, "summer"
    if month == 12:
        return today.year, "fall"
    raise ValueError(f"계절 종료 트리거가 아닌 날짜: {today}")


@shared_task
def trigger_season_chain_for_last_season():
    """Beat가 분기 4번(spec 5-1) 호출하는 얇은 디스패처 — 실제 작업은 build_season_chain의
    각 태스크(이미 tracked_job으로 감싸져 있음)가 한다. 활성 지역마다 하나씩 체인을
    돌린다(다지역 지원 7단계)."""
    year, season = _season_just_ended(date.today())
    for sido_code in enabled_sido_codes():
        build_season_chain(year, season, sido_code).apply_async()
