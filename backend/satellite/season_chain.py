"""season_composite → group(change_analysis, region_stat) → catalog_publish를 동기로
실행하는 공유 로직(spec 5-2). run_season_chain 관리 명령과 백필(4장)이 함께 쓴다."""
import logging

from core.jobs import JobSkipped, tracked_run

from .catalog import run_catalog_publish
from .change_detection import run_change_analysis
from .composite import run_season_composite
from .region_stats import run_region_stat

logger = logging.getLogger(__name__)


def run_season_chain_sync(year: int, season: str, sido_code: str = "30") -> dict:
    """반환: 단계별 결과 문자열("ok"/"skipped"/"failed: ...")을 담은 dict.

    season_composite가 실패·건너뜀이면 뒤 단계는 실행하지 않는다(spec 5-2: "앞 단계가
    실패하면 뒤 단계는 실행하지 않음"). change_analysis·region_stat은 서로 독립이라
    하나가 실패해도 나머지는 계속 진행한다.
    """
    region_code = f"{sido_code}:{year}:{season}"
    result: dict = {}

    try:
        with tracked_run("season_composite", region_code, lock_ttl_seconds=3600 * 4):
            run_season_composite(year, season, sido_code)
        result["season_composite"] = "ok"
    except JobSkipped:
        result["season_composite"] = "skipped"
        return result
    except Exception as exc:  # noqa: BLE001 — 배치 결과를 요약해 돌려주려고 넓게 잡음
        logger.exception("season_composite 실패 year=%s season=%s", year, season)
        result["season_composite"] = f"failed: {exc}"
        return result

    try:
        with tracked_run("change_analysis", region_code, lock_ttl_seconds=3600 * 2):
            run_change_analysis(year, season)
        result["change_analysis"] = "ok"
    except JobSkipped:
        result["change_analysis"] = "skipped"
    except Exception as exc:  # noqa: BLE001
        logger.exception("change_analysis 실패 year=%s season=%s", year, season)
        result["change_analysis"] = f"failed: {exc}"

    try:
        with tracked_run("region_stat", region_code):
            run_region_stat(year, season)
        result["region_stat"] = "ok"
    except JobSkipped:
        result["region_stat"] = "skipped"
    except Exception as exc:  # noqa: BLE001
        logger.exception("region_stat 실패 year=%s season=%s", year, season)
        result["region_stat"] = f"failed: {exc}"

    try:
        with tracked_run("catalog_publish", region_code):
            summary = run_catalog_publish(year, season, sido_code)
        result["catalog_publish"] = "ok"
        result["catalog_summary"] = summary
    except JobSkipped:
        result["catalog_publish"] = "skipped"
    except Exception as exc:  # noqa: BLE001
        logger.exception("catalog_publish 실패 year=%s season=%s", year, season)
        result["catalog_publish"] = f"failed: {exc}"

    return result
