import zipfile
from datetime import date

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from buildings.models import Building, Region
from core.models import ServiceArea

pytestmark = pytest.mark.django_db


def _square_wkt(minx, miny, size=0.01):
    maxx, maxy = minx + size, miny + size
    return (
        f"MULTIPOLYGON((({minx} {miny}, {maxx} {miny}, "
        f"{maxx} {maxy}, {minx} {maxy}, {minx} {miny})))"
    )


def _make_al_d001_zip(path, entries: dict[str, bytes]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def _make_sejong_discoverable(monkeypatch, tmp_path):
    """core/tests/test_areas.py의 discover_available_areas 테스트와 같은 방식으로,
    "36 세종특별자치시"가 들어있는 AL_D001_00 zip을 합성한다."""
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Polygon

    square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    gdf = gpd.GeoDataFrame(
        {"A1": ["36110"], "A2": ["세종특별자치시 조치원읍"]}, geometry=[square]
    )

    inner_path = tmp_path / "_inner_sig.zip"
    _make_al_d001_zip(inner_path, {"dummy.shp": b"x"})
    outer_path = tmp_path / "AL_D001_00_20261009.zip"
    with zipfile.ZipFile(outer_path, "w") as outer:
        outer.write(inner_path, arcname="AL_D001_00_SIG.zip")

    monkeypatch.setattr("pyogrio.read_dataframe", lambda *a, **k: gdf)
    return outer_path


# ---- list ----


def test_areas_list_shows_daejeon(capsys):
    call_command("areas", "list")
    out = capsys.readouterr().out
    assert "30" in out
    assert "대전광역시" in out


# ---- available ----


def test_areas_available_shows_discovered_areas_with_status(monkeypatch, tmp_path, capsys):
    zip_path = _make_sejong_discoverable(monkeypatch, tmp_path)

    call_command("areas", "available", "--path", str(zip_path))

    out = capsys.readouterr().out
    assert "36" in out
    assert "세종특별자치시" in out
    assert "미등록" in out


def test_areas_available_marks_already_registered_areas(monkeypatch, tmp_path, capsys):
    zip_path = _make_sejong_discoverable(monkeypatch, tmp_path)
    ServiceArea.objects.create(sido_code="36", name="세종특별자치시", enabled=False)

    call_command("areas", "available", "--path", str(zip_path))

    out = capsys.readouterr().out
    assert "비활성" in out


# ---- add ----


def test_areas_add_registers_disabled_without_collecting_anything(monkeypatch, tmp_path):
    """완료 기준: areas add 36이 세종을 비활성 상태로 추가하고, 실제 수집은 하지 않는다."""
    zip_path = _make_sejong_discoverable(monkeypatch, tmp_path)

    call_command("areas", "add", "36", "--path", str(zip_path))

    area = ServiceArea.objects.get(sido_code="36")
    assert area.name == "세종특별자치시"
    assert area.enabled is False
    assert area.grid is None
    assert area.bbox_minx is None
    assert not Region.objects.filter(region_code__startswith="36").exists()


def test_areas_add_rejects_already_registered_code(monkeypatch, tmp_path):
    zip_path = _make_sejong_discoverable(monkeypatch, tmp_path)
    ServiceArea.objects.create(sido_code="36", name="세종특별자치시", enabled=False)

    with pytest.raises(CommandError, match="이미 등록"):
        call_command("areas", "add", "36", "--path", str(zip_path))


def test_areas_add_rejects_code_not_found_in_zip(monkeypatch, tmp_path):
    zip_path = _make_sejong_discoverable(monkeypatch, tmp_path)

    with pytest.raises(CommandError, match="찾지 못했습니다"):
        call_command("areas", "add", "99", "--path", str(zip_path))


# ---- enable / disable ----


def test_areas_enable_requires_region_and_grid():
    ServiceArea.objects.create(sido_code="36", name="세종특별자치시", enabled=False)

    with pytest.raises(CommandError, match="먼저 경계를 적재하세요"):
        call_command("areas", "enable", "36")


def test_areas_enable_succeeds_once_region_and_grid_exist():
    ServiceArea.objects.create(
        sido_code="36",
        name="세종특별자치시",
        enabled=False,
        grid={"crs": "EPSG:32652"},
    )
    Region.objects.create(region_code="36", level="sido", name="세종특별자치시", geom=_square_wkt(127.0, 36.0))

    call_command("areas", "enable", "36")

    area = ServiceArea.objects.get(sido_code="36")
    assert area.enabled is True


def test_areas_disable_turns_off_without_checking_region():
    ServiceArea.objects.create(sido_code="36", name="세종특별자치시", enabled=True)

    call_command("areas", "disable", "36")

    assert ServiceArea.objects.get(sido_code="36").enabled is False


def test_areas_enable_disable_unknown_code_raises():
    with pytest.raises(CommandError, match="등록된 지역"):
        call_command("areas", "enable", "99")
    with pytest.raises(CommandError, match="등록된 지역"):
        call_command("areas", "disable", "99")


# ---- status ----


def test_areas_status_counts_building_and_region(capsys):
    Region.objects.create(region_code="30", level="sido", name="대전광역시", geom=_square_wkt(127.0, 36.0))
    Region.objects.create(
        region_code="30110", level="sigungu", name="대전광역시 동구", geom=_square_wkt(127.0, 36.0)
    )
    Building.objects.create(
        building_key="B1",
        gis_bldg_id="B1",
        pnu="3011010300101530003",
        bjd_code="3011010300",
        source_date=date(2026, 1, 1),
        geom="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        is_active=True,
    )

    call_command("areas", "status", "30")

    out = capsys.readouterr().out
    assert "시도 1" in out
    assert "시군구 1" in out
    assert "1개(활성)" in out


def test_areas_status_unknown_code_raises():
    with pytest.raises(CommandError, match="등록된 지역"):
        call_command("areas", "status", "99")
