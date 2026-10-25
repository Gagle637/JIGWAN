from datetime import date

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from buildings.models import Building
from buildings.tests.test_building_loading import _make_zip, _tiny_gdf

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
