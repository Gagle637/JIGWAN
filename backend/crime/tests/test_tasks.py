import pytest

from core.models import ServiceArea
from crime.tasks import safety_sync, trigger_safety_sync_for_enabled_regions

pytestmark = pytest.mark.django_db


def test_trigger_safety_sync_dispatches_only_enabled_regions(monkeypatch):
    """활성 지역(service_area, enabled=True)마다 safety_sync가 하나씩 디스패치되는지,
    비활성 지역은 건너뛰는지 확인한다(다지역 지원 7단계)."""
    ServiceArea.objects.create(sido_code="36", name="세종", enabled=True)
    ServiceArea.objects.create(sido_code="41", name="비활성", enabled=False)

    delay_calls = []
    monkeypatch.setattr(safety_sync, "delay", lambda sido_code: delay_calls.append(sido_code))

    trigger_safety_sync_for_enabled_regions()

    assert sorted(delay_calls) == ["30", "36"]
