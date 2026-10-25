import pytest
from django.core.management import call_command

import crime.management.commands.run_safety_sync as cmd_module
from core.locks import acquire_lock
from core.models import ServiceArea

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _no_tile_cache(monkeypatch):
    monkeypatch.setattr(cmd_module, "crime_layer_id", lambda: None)


def test_loops_over_enabled_regions_when_sido_omitted(monkeypatch, settings):
    """--sido를 생략하면 활성화된 지역(service_area) 전체를 돈다(다지역 지원 7단계)."""
    settings.CRIME_FEATURE_CAP = 100
    settings.CRIME_DATA_PERIOD = "2023-07/2024-06"
    ServiceArea.objects.create(sido_code="36", name="세종", enabled=True)
    ServiceArea.objects.create(sido_code="41", name="비활성", enabled=False)

    called = []

    def fake_run_safety_sync(data_period, sido_code):
        called.append(sido_code)
        return {"cells_done": 1, "cells_failed": 0, "fully_done": True, "segments_total": 1}

    monkeypatch.setattr(cmd_module, "run_safety_sync", fake_run_safety_sync)

    call_command("run_safety_sync")

    assert sorted(called) == ["30", "36"]


def test_one_regions_lock_being_held_does_not_block_other_regions(monkeypatch, settings):
    """대전(30)이 이미 다른 실행 중(잠금 보유)이어도, 세종(36)은 그대로 실행돼야 한다 —
    한 지역의 건너뜀이 다른 지역을 막으면 안 된다."""
    settings.CRIME_FEATURE_CAP = 100
    settings.CRIME_DATA_PERIOD = "2023-07/2024-06"
    ServiceArea.objects.create(sido_code="36", name="세종", enabled=True)

    lock = acquire_lock("safety_sync", "30", ttl_seconds=60)
    assert lock is not None  # 대전 잠금을 미리 쥐고 있다고 흉내

    called = []

    def fake_run_safety_sync(data_period, sido_code):
        called.append(sido_code)
        return {"cells_done": 1, "cells_failed": 0, "fully_done": True, "segments_total": 1}

    monkeypatch.setattr(cmd_module, "run_safety_sync", fake_run_safety_sync)

    call_command("run_safety_sync")

    assert called == ["36"]
