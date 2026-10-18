from datetime import date

from satellite.tasks import _season_just_ended, build_season_chain


def _all_signatures(canvas):
    """chain/group 안의 모든 리프 서명을 모은다."""
    sigs = []
    for task in canvas.tasks:
        if hasattr(task, "tasks"):  # group
            sigs.extend(task.tasks)
        else:
            sigs.append(task)
    return sigs


def test_build_season_chain_uses_immutable_signatures():
    """체인 서명이 전부 immutable이라 앞 단계 결과/group 결과 리스트가 전달되지 않는지
    확인한다(결정 사항 3)."""
    canvas = build_season_chain(2026, "summer")

    sigs = _all_signatures(canvas)

    assert len(sigs) == 4  # season_composite, change_analysis, region_stat_task, catalog_publish
    assert all(sig.immutable for sig in sigs)


def test_build_season_chain_passes_explicit_args():
    canvas = build_season_chain(2026, "summer")
    sigs = _all_signatures(canvas)
    for sig in sigs:
        assert sig.args == ("daejeon:2026:summer", 2026, "summer")


def test_season_just_ended_winter_is_recorded_under_previous_year():
    assert _season_just_ended(date(2026, 3, 15)) == (2025, "winter")


def test_season_just_ended_other_seasons():
    assert _season_just_ended(date(2026, 6, 15)) == (2026, "spring")
    assert _season_just_ended(date(2026, 9, 15)) == (2026, "summer")
    assert _season_just_ended(date(2026, 12, 15)) == (2026, "fall")
