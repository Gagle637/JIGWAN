from datetime import date

from satellite.tasks import _season_just_ended, build_season_chain


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
    canvas = build_season_chain(2026, "summer")

    sigs = _all_signatures(canvas)

    assert len(sigs) == 4  # season_composite, change_analysis, region_stat_task, catalog_publish
    assert all(sig.immutable for sig in sigs)


def test_build_season_chain_passes_explicit_args():
    canvas = build_season_chain(2026, "summer")
    sigs = _all_signatures(canvas)
    for sig in sigs:
        assert sig.args == ("30:2026:summer", 2026, "summer", "30")


def test_season_just_ended_winter_is_recorded_under_previous_year():
    assert _season_just_ended(date(2026, 3, 15)) == (2025, "winter")


def test_season_just_ended_other_seasons():
    assert _season_just_ended(date(2026, 6, 15)) == (2026, "spring")
    assert _season_just_ended(date(2026, 9, 15)) == (2026, "summer")
    assert _season_just_ended(date(2026, 12, 15)) == (2026, "fall")
