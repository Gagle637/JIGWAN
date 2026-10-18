import pytest

from buildings.models import Building
from demo.snapshots import apply_demo_overlay, get_demo_snapshot, load_demo_snapshots

pytestmark = pytest.mark.django_db


def _make_building(**overrides):
    defaults = dict(
        building_key="DEMOB1",
        gis_bldg_id="DEMOB1",
        pnu="DEMO000000000000001",
        bjd_code="3011010300",
        bjd_name="대전 유성구 예시동",
        jibun="123",
        name="예시아파트 101동",
        use_code="01000",
        use_name="공동주택",
        source_date="2026-10-06",
        geom=(
            "POLYGON((127.385 36.351, 127.386 36.351, "
            "127.386 36.352, 127.385 36.352, 127.385 36.351))"
        ),
    )
    defaults.update(overrides)
    return Building.objects.create(**defaults)


def test_load_demo_snapshots_has_five_entries():
    snapshots = load_demo_snapshots()

    assert len(snapshots) == 5
    for entry in snapshots.values():
        assert "insight" in entry
        assert "reports" in entry
        assert "template" in entry["reports"]
        assert "custom" in entry["reports"]


def test_get_demo_snapshot_returns_none_for_unknown_pnu():
    assert get_demo_snapshot("NOT-A-DEMO-PNU") is None


def test_get_demo_snapshot_returns_entry_for_known_pnu():
    snapshot = get_demo_snapshot("DEMO000000000000001")

    assert snapshot is not None
    assert snapshot["insight"]["status"] == "ready"


def test_apply_demo_overlay_uses_real_building_identity():
    building = _make_building()
    demo = get_demo_snapshot("DEMO000000000000001")

    overlaid = apply_demo_overlay(demo["insight"], building)

    assert overlaid["building"]["id"] == building.id
    assert overlaid["building"]["pnu"] == building.pnu
    assert overlaid["building"]["geometry"]["type"] == "Polygon"
    # 분석 섹션(green 등)은 데모 고정값 그대로여야 한다
    assert overlaid["green"] == demo["insight"]["green"]
