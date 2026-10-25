"""2km(필요 시 4등분, 최소 250m) 격자를 순회해 crime_segment를 채운다(spec 8-4).

중단 후 재개: crime_fetch_progress에 done/split이 아닌 셀이 남아 있으면 그 셀들만 이어서
처리한다(재개). 전부 끝난 상태(또는 첫 실행)면 새 연간 수집으로 보고 격자를 다시 심는다.
"""
import logging
import random
import time

import httpx
from django.conf import settings
from rasterio.warp import transform_geom
from shapely.geometry import shape

from core.exceptions import ExternalCallError
from core.jobs import RETRY_COUNTDOWNS_SECONDS

from . import grid
from .models import CrimeFetchProgress, CrimeSegment
from .safemap_client import REQUESTED_FEATURE_COUNT, fetch_feature_info

logger = logging.getLogger(__name__)

REQUEST_DELAY_RANGE_SECONDS = (1.0, 2.0)  # spec 8-4: 요청 사이 1-2초


class FeatureCapNotConfigured(Exception):
    """CRIME_FEATURE_CAP이 아직 확인되지 않았다 — probe_crime_feature_cap을 먼저 실행해야 한다."""


def _split_threshold() -> int:
    """분할 기준: 내가 요청한 FEATURE_COUNT와 probe로 확인한 서버 숨은 상한 중 더 작은 값."""
    return min(REQUESTED_FEATURE_COUNT, settings.CRIME_FEATURE_CAP)


def _seed_base_grid_if_fully_done(sido_code: str) -> bool:
    """끝나지 않은(= pending/failed) 셀이 있으면 그대로 두고 재개한다. 하나도 없으면(첫 실행 또는
    작년 수집이 전부 끝남) 새 연간 수집으로 보고 격자를 다시 심는다. 반환값은 '새로 심었는지'."""
    unfinished = CrimeFetchProgress.objects.exclude(
        status__in=[CrimeFetchProgress.Status.DONE, CrimeFetchProgress.Status.SPLIT]
    ).exists()
    if unfinished:
        return False

    CrimeFetchProgress.objects.all().delete()
    CrimeFetchProgress.objects.bulk_create(
        [
            CrimeFetchProgress(cell_id=grid.cell_id(minx, miny, size_m))
            for minx, miny, size_m in grid.base_cells(sido_code)
        ]
    )
    return True


def _cell_from_id(cell_id_value: str) -> tuple[float, float, float]:
    minx_s, miny_s, size_s = cell_id_value.split("_")
    return float(minx_s), float(miny_s), float(size_s)


def _save_features(features: list[dict], data_period: str) -> None:
    for feature in features:
        props = feature["properties"]
        geom_4326 = transform_geom("EPSG:3857", "EPSG:4326", feature["geometry"])
        CrimeSegment.objects.update_or_create(
            objt_id=str(props["OBJT_ID"]),
            defaults={
                "grad": int(props["GRAD"]),
                "data_period": data_period,
                "geom": shape(geom_4326).wkt,
            },
        )


def _process_cell(client: httpx.Client, progress: CrimeFetchProgress, data_period: str) -> None:
    minx, miny, size_m = _cell_from_id(progress.cell_id)
    bbox = grid.cell_bbox(minx, miny, size_m)
    threshold = _split_threshold()

    attempt = 0
    while True:
        try:
            features = fetch_feature_info(client, bbox, REQUESTED_FEATURE_COUNT)
            break
        except ExternalCallError as exc:
            if attempt >= len(RETRY_COUNTDOWNS_SECONDS):
                logger.warning(
                    "crime cell=%s 재시도 소진, failed 처리: %s", progress.cell_id, exc
                )
                progress.status = CrimeFetchProgress.Status.FAILED
                progress.save(update_fields=["status"])
                return
            wait_seconds = RETRY_COUNTDOWNS_SECONDS[attempt]
            logger.warning(
                "crime cell=%s 오류, %s초 뒤 재시도(%s/%s회): %s",
                progress.cell_id,
                wait_seconds,
                attempt + 1,
                len(RETRY_COUNTDOWNS_SECONDS),
                exc,
            )
            time.sleep(wait_seconds)
            attempt += 1

    if len(features) >= threshold and size_m > grid.MIN_CELL_SIZE_M:
        progress.status = CrimeFetchProgress.Status.SPLIT
        progress.feature_count = len(features)
        progress.save(update_fields=["status", "feature_count"])
        CrimeFetchProgress.objects.bulk_create(
            [
                CrimeFetchProgress(cell_id=grid.cell_id(cminx, cminy, csize))
                for cminx, cminy, csize in grid.split_cell(minx, miny, size_m)
            ],
            ignore_conflicts=True,
        )
        return

    if len(features) >= threshold:
        logger.warning(
            "crime cell=%s 최소 크기(%sm)에서도 상한에 걸림 — 잘렸을 수 있는 응답을 그대로 저장",
            progress.cell_id,
            grid.MIN_CELL_SIZE_M,
        )

    _save_features(features, data_period)
    progress.status = CrimeFetchProgress.Status.DONE
    progress.feature_count = len(features)
    progress.save(update_fields=["status", "feature_count"])


def run_safety_sync(data_period: str, sido_code: str = "30") -> dict:
    """spec 8-4: 지역 전체 격자를 순회해 crime_segment를 채운다. 멱등·재개 가능.
    sido_code(다지역 지원 3단계)로 대상 지역 격자를 정한다."""
    if not settings.CRIME_FEATURE_CAP:
        raise FeatureCapNotConfigured(
            "CRIME_FEATURE_CAP이 설정되지 않았습니다. probe_crime_feature_cap을 먼저 실행하세요."
        )

    is_fresh_run = _seed_base_grid_if_fully_done(sido_code)
    logger.info("safety_sync 시작: %s", "새 연간 수집" if is_fresh_run else "이전 실행 재개")

    # failed는 실행 "시작 시" 한 번만 pending으로 되돌린다(spec 8-4: "다음 실행에서 다시
    # 시도"). 루프 안에서 failed를 다시 주워 오면, 계속 실패하는 셀이 있을 때 매번 pending으로
    # 되돌려 끝없이 재시도하게 된다(실제 감사에서 무한 루프로 재현됨) — 이번 실행에서 다시
    # 실패한 셀은 failed로 남겨 두고 다음 호출로 넘긴다.
    CrimeFetchProgress.objects.filter(status=CrimeFetchProgress.Status.FAILED).update(
        status=CrimeFetchProgress.Status.PENDING
    )

    done_count = failed_count = 0
    with httpx.Client() as client:
        while True:
            progress = (
                CrimeFetchProgress.objects.filter(status=CrimeFetchProgress.Status.PENDING)
                .order_by("id")
                .first()
            )
            if progress is None:
                break

            _process_cell(client, progress, data_period)
            progress.refresh_from_db()
            if progress.status == CrimeFetchProgress.Status.DONE:
                done_count += 1
            elif progress.status == CrimeFetchProgress.Status.FAILED:
                failed_count += 1

            time.sleep(random.uniform(*REQUEST_DELAY_RANGE_SECONDS))

    fully_done = not CrimeFetchProgress.objects.exclude(
        status__in=[CrimeFetchProgress.Status.DONE, CrimeFetchProgress.Status.SPLIT]
    ).exists()

    stale_removed = 0
    if fully_done:
        stale_removed, _ = CrimeSegment.objects.exclude(data_period=data_period).delete()
        logger.info("safety_sync 완료: 지난 기간 구간 %s개 정리", stale_removed)

    return {
        "cells_done": done_count,
        "cells_failed": failed_count,
        "fully_done": fully_done,
        "stale_removed": stale_removed,
        "segments_total": CrimeSegment.objects.count(),
    }
