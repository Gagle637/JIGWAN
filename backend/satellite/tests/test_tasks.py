from datetime import date

import pytest

from core.models import ServiceArea
from satellite.tasks import (
    _season_just_ended,
    build_season_chain,
    satellite_collect,
    trigger_satellite_collect_for_enabled_regions,
    trigger_season_chain_for_last_season,
)


def _all_signatures(canvas):
    """chain/chord 안의 모든 리프 서명을 모은다.

    Celery는 chain(a, group(b,c), d)를 그대로 두지 않고 chain(a, chord(group(b,c),
    body=d))로 자동 변환한다 — chord.tasks는 header(b,c), chord.body는 다음 단계(d)다.
    body를 안 챙기면 catalog_publish가 조용히 검사에서 빠진다(실제 Postgres/Celery로
    돌려보니 len(sigs)==3이 나와 걸림, 감사에서 발견).
    """
    sigs = []
    for task in canvas.tasks:
        if hasattr(task, "body") and task.body is not None:  # chord
            sigs.extend(task.tasks)
            sigs.append(task.body)
        elif hasattr(task, "tasks"):  # 순수 group(body 없음)
            sigs.extend(task.tasks)
        else:
            sigs.append(task)
    return sigs


def test_build_season_chain_uses_immutable_signatures():
    """체인 서명이 전부 immutable이라 앞 단계 결과/group 결과 리스트가 전달되지 않는지
    확인한다(결정 사항 3)."""
    canvas = build_season_chain(2026, "summer", "30")

    sigs = _all_signatures(canvas)

    assert len(sigs) == 4  # season_composite, change_analysis, region_stat_task, catalog_publish
    assert all(sig.immutable for sig in sigs)


def test_build_season_chain_passes_explicit_args():
    canvas = build_season_chain(2026, "summer", "30")
    sigs = _all_signatures(canvas)
    for sig in sigs:
        assert sig.args == ("30:2026:summer", 2026, "summer", "30")


def test_season_just_ended_winter_is_recorded_under_previous_year():
    assert _season_just_ended(date(2026, 3, 15)) == (2025, "winter")


def test_season_just_ended_other_seasons():
    assert _season_just_ended(date(2026, 6, 15)) == (2026, "spring")
    assert _season_just_ended(date(2026, 9, 15)) == (2026, "summer")
    assert _season_just_ended(date(2026, 12, 15)) == (2026, "fall")


# ---- 다지역 지원 7단계: 디스패처가 활성 지역만 돈다 ----


@pytest.mark.django_db
def test_trigger_satellite_collect_dispatches_only_enabled_regions(monkeypatch):
    """지금까지 한 번도 Beat에 등록된 적 없던 satellite_collect가, 활성 지역(service_area,
    enabled=True)마다 하나씩 디스패치되는지 확인한다. 비활성 지역은 건너뛰어야 한다."""
    ServiceArea.objects.create(sido_code="36", name="세종", enabled=True)
    ServiceArea.objects.create(sido_code="41", name="비활성", enabled=False)

    delay_calls = []
    monkeypatch.setattr(satellite_collect, "delay", lambda sido_code: delay_calls.append(sido_code))

    trigger_satellite_collect_for_enabled_regions()

    assert sorted(delay_calls) == ["30", "36"]


@pytest.mark.django_db
def test_trigger_season_chain_for_last_season_dispatches_only_enabled_regions(monkeypatch):
    """분기 트리거가 활성 지역마다 하나씩 체인을 돌리는지, 비활성 지역은 건너뛰는지 확인한다."""
    ServiceArea.objects.create(sido_code="36", name="세종", enabled=True)
    ServiceArea.objects.create(sido_code="41", name="비활성", enabled=False)

    monkeypatch.setattr("satellite.tasks._season_just_ended", lambda today: (2026, "summer"))

    built_for = []

    class _FakeCanvas:
        def apply_async(self):
            pass

    def fake_build_season_chain(year, season, sido_code):
        built_for.append(sido_code)
        return _FakeCanvas()

    monkeypatch.setattr("satellite.tasks.build_season_chain", fake_build_season_chain)

    trigger_season_chain_for_last_season()

    assert sorted(built_for) == ["30", "36"]
