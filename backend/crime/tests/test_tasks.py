import pytest

from buildings.models import Region
from core.models import ServiceArea
from crime.tasks import safety_sync, trigger_safety_sync_for_enabled_regions

pytestmark = pytest.mark.django_db


def _square_wkt(minx, miny, size=0.01):
    maxx, maxy = minx + size, miny + size
    return (
        f"MULTIPOLYGON((({minx} {miny}, {maxx} {miny}, "
        f"{maxx} {maxy}, {minx} {maxy}, {minx} {miny})))"
    )


def _make_ready_area(sido_code, name, enabled=True):
    ServiceArea.objects.update_or_create(
        sido_code=sido_code,
        defaults={"name": name, "enabled": enabled, "grid": {"crs": "EPSG:32652"}},
    )
    Region.objects.get_or_create(
        region_code=sido_code,
        defaults={"level": "sido", "name": name, "geom": _square_wkt(127.0, 36.0)},
    )


def test_trigger_safety_sync_dispatches_only_enabled_regions(monkeypatch):
    """활성화되고 경계·격자까지 준비된 지역마다 safety_sync가 하나씩 디스패치되는지,
    비활성 지역은 건너뛰는지 확인한다(다지역 지원 7단계)."""
    _make_ready_area("30", "대전광역시")
    _make_ready_area("36", "세종", enabled=True)
    ServiceArea.objects.create(sido_code="41", name="비활성", enabled=False)

    delay_calls = []
    monkeypatch.setattr(safety_sync, "delay", lambda sido_code: delay_calls.append(sido_code))

    trigger_safety_sync_for_enabled_regions()

    assert sorted(delay_calls) == ["30", "36"]


def test_trigger_safety_sync_skips_enabled_but_not_ready_region(monkeypatch, caplog):
    """enabled=True인데 경계·격자가 아직 준비되지 않은 지역은 예외 없이 건너뛰고 경고를
    남겨야 한다(다지역 지원 10단계 중간 점검)."""
    ServiceArea.objects.update_or_create(
        sido_code="30", defaults={"name": "대전광역시", "enabled": True, "grid": None}
    )

    delay_calls = []
    monkeypatch.setattr(safety_sync, "delay", lambda sido_code: delay_calls.append(sido_code))

    with caplog.at_level("WARNING"):
        trigger_safety_sync_for_enabled_regions()

    assert delay_calls == []
    assert "준비되지 않아" in caplog.text
