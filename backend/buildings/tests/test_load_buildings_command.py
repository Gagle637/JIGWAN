from datetime import date

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from buildings import building_loading
from buildings.models import Building
from buildings.tests.test_building_loading import _make_zip, _tiny_gdf
from core.models import ServiceArea

pytestmark = pytest.mark.django_db


def test_load_buildings_command_reports_region_mismatch_without_traceback(monkeypatch, tmp_path):
    """load_buildings()가 던지는 지역 불일치 ValueError를 명령이 CommandError로 바꿔야
    한다 — Django는 CommandError를 트레이스백 없이 안내 문구만 찍고 종료 코드 1로 끝낸다."""
    monkeypatch.setattr(
        "pyogrio.read_dataframe",
        lambda *a, **k: _tiny_gdf(date(2026, 4, 1), bjd_code="3611010100"),
    )
    zip_path = _make_zip(tmp_path / "AL_D010_30_20260401.zip")

    with pytest.raises(CommandError, match="지정한 지역"):
        call_command("load_buildings", str(zip_path), "--sido", "30")

    assert not Building.objects.exists()


def test_load_buildings_command_loops_over_enabled_regions_when_sido_omitted(monkeypatch, tmp_path):
    """--sido를 생략하면 활성화된 지역(service_area) 전체를 돌며, 각 지역에 맞는 zip을
    DATA_RAW_DIR에서 찾아 적재한다(다지역 지원 7단계)."""
    ServiceArea.objects.create(sido_code="36", name="세종", enabled=True)
    monkeypatch.setattr(building_loading, "DATA_RAW_DIR", tmp_path)

    _make_zip(tmp_path / "AL_D010_30_20260101.zip")
    _make_zip(tmp_path / "AL_D010_36_20260101.zip")

    calls = []

    def fake_read_dataframe(vsi_path, **kwargs):
        sido_code = "30" if "AL_D010_30_" in vsi_path else "36"
        calls.append(sido_code)
        return _tiny_gdf(
            date(2026, 1, 1),
            gis_bldg_id=f"GIS_{sido_code}",
            pnu=f"{sido_code}11010300101530003",
            bjd_code=f"{sido_code}11010300",
        )

    monkeypatch.setattr("pyogrio.read_dataframe", fake_read_dataframe)

    call_command("load_buildings")

    assert sorted(calls) == ["30", "36"]
    assert Building.objects.filter(building_key="GIS_30").exists()
    assert Building.objects.filter(building_key="GIS_36").exists()
