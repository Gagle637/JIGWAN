from datetime import date

import pytest

from buildings.models import Region
from core.models import ServiceArea
from satellite.tasks import (
    _season_just_ended,
    build_season_chain,
    satellite_collect,
    trigger_satellite_collect_for_enabled_regions,
    trigger_season_chain_for_last_season,
)


def _square_wkt(minx, miny, size=0.01):
    maxx, maxy = minx + size, miny + size
    return (
        f"MULTIPOLYGON((({minx} {miny}, {maxx} {miny}, "
        f"{maxx} {maxy}, {minx} {maxy}, {minx} {miny})))"
    )


def _make_ready_area(sido_code, name, enabled=True):
    """경계(region level=sido)·grid까지 갖춘 "준비된" 지역을 만든다 — 디스패처가 도는
    enabled_and_ready_sido_codes()의 조건을 만족시킨다(다지역 지원 10단계 중간 점검)."""
    ServiceArea.objects.update_or_create(
        sido_code=sido_code,
        defaults={"name": name, "enabled": enabled, "grid": {"crs": "EPSG:32652"}},
    )
    Region.objects.get_or_create(
        region_code=sido_code,
        defaults={"level": "sido", "name": name, "geom": _square_wkt(127.0, 36.0)},
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
    """지금까지 한 번도 Beat에 등록된 적 없던 satellite_collect가, 활성화되고 경계·격자까지
    준비된 지역마다 하나씩 디스패치되는지 확인한다. 비활성 지역은 건너뛰어야 한다."""
    _make_ready_area("30", "대전광역시")
    _make_ready_area("36", "세종", enabled=True)
    ServiceArea.objects.create(sido_code="41", name="비활성", enabled=False)

    delay_calls = []
    monkeypatch.setattr(satellite_collect, "delay", lambda sido_code: delay_calls.append(sido_code))

    trigger_satellite_collect_for_enabled_regions()

    assert sorted(delay_calls) == ["30", "36"]


@pytest.mark.django_db
def test_trigger_satellite_collect_skips_enabled_but_not_ready_region(monkeypatch, caplog):
    """enabled=True인데 아직 경계·격자가 준비되지 않은 지역(예: service_area가 enabled=True로
    시딩됐지만 load_regions를 아직 안 돌린 경우)은 조용히 건너뛰고 경고를 남겨야 한다 —
    예외로 태스크 전체가 깨지면 안 된다."""
    # 마이그레이션이 이미 "30"을 enabled=True·grid=None으로 시딩해 두지만, 명시적으로 맞춰 둔다.
    ServiceArea.objects.update_or_create(
        sido_code="30", defaults={"name": "대전광역시", "enabled": True, "grid": None}
    )

    delay_calls = []
    monkeypatch.setattr(satellite_collect, "delay", lambda sido_code: delay_calls.append(sido_code))

    with caplog.at_level("WARNING"):
        trigger_satellite_collect_for_enabled_regions()

    assert delay_calls == []
    assert "준비되지 않아" in caplog.text


@pytest.mark.django_db
def test_trigger_season_chain_for_last_season_dispatches_only_enabled_regions(monkeypatch):
    """분기 트리거가 활성화·준비된 지역마다 하나씩 체인을 돌리는지, 비활성 지역은
    건너뛰는지 확인한다."""
    _make_ready_area("30", "대전광역시")
    _make_ready_area("36", "세종", enabled=True)
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
