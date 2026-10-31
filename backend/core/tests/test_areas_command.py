import zipfile
from datetime import date

import pytest
from django.contrib.gis.geos import Polygon as GEOSPolygon
from django.core.management import call_command
from django.core.management.base import CommandError

import core.management.commands.areas as areas_cmd
from buildings.models import Building, Region
from core.models import IndexRun, ServiceArea
from satellite.composite import ALGO_VERSION
from satellite.models import RasterProduct

pytestmark = pytest.mark.django_db


def _square_wkt(minx, miny, size=0.01):
    maxx, maxy = minx + size, miny + size
    return (
        f"MULTIPOLYGON((({minx} {miny}, {maxx} {miny}, "
        f"{maxx} {maxy}, {minx} {maxy}, {minx} {miny})))"
    )


def _sejong_with_boundary(enabled=False):
    ServiceArea.objects.create(
        sido_code="36", name="세종특별자치시", enabled=enabled, grid={"crs": "EPSG:32652"}
    )
    Region.objects.create(
        region_code="36", level="sido", name="세종특별자치시", geom=_square_wkt(127.0, 36.0)
    )


def _sejong_building():
    Building.objects.create(
        building_key="S1",
        gis_bldg_id="S1",
        pnu="3611010100101530003",
        bjd_code="3611010100",
        source_date=date(2026, 1, 1),
        geom="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        is_active=True,
    )


def _patch_al_d001_resolver(monkeypatch, zip_path):
    """discover_available_areas용 zip 경로 해석을 고정한다 — core.areas.list_available_areas
    (자기 모듈 안에서 resolve_al_d001_zip_path를 부름)와 areas_cmd._sync*/_add(임포트해서
    부름) 양쪽 다 패치해야 한다."""
    monkeypatch.setattr("core.areas.resolve_al_d001_zip_path", lambda explicit_path=None: zip_path)
    monkeypatch.setattr(areas_cmd, "resolve_al_d001_zip_path", lambda explicit_path=None: zip_path)


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


# ---- sync ----


def test_areas_sync_requires_registered_area():
    with pytest.raises(CommandError, match="등록된 지역"):
        call_command("areas", "sync", "--area", "99")


def test_areas_sync_dry_run_calls_nothing(monkeypatch, capsys):
    ServiceArea.objects.create(sido_code="36", name="세종특별자치시", enabled=False)
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [(2026, "summer")])

    for name in (
        "load_regions", "load_buildings", "sync_trades_for_months", "run_backfill", "run_crime_sync",
    ):
        def _fail(*a, _name=name, **k):
            pytest.fail(f"{_name}이 dry-run에서 호출되면 안 됩니다")

        monkeypatch.setattr(areas_cmd, name, _fail)

    call_command("areas", "sync", "--area", "36", "--dry-run")

    out = capsys.readouterr().out
    assert "할 일" in out
    assert ServiceArea.objects.get(sido_code="36").enabled is False


def test_areas_sync_stops_when_boundary_file_missing(monkeypatch, capsys):
    ServiceArea.objects.create(sido_code="36", name="세종특별자치시", enabled=False)
    monkeypatch.setattr(
        areas_cmd,
        "resolve_al_d001_zip_path",
        lambda path: (_ for _ in ()).throw(FileNotFoundError("AL_D001_00 없음")),
    )
    calls = []
    for name in ("load_buildings", "sync_trades_for_months", "run_backfill", "run_crime_sync"):
        monkeypatch.setattr(areas_cmd, name, lambda *a, _n=name, **k: calls.append(_n))

    call_command("areas", "sync", "--area", "36")

    assert calls == []  # 경계가 안 끝나면 뒤 단계는 전부 건너뜀
    out = capsys.readouterr().out
    assert "경계 중단" in out
    run = IndexRun.objects.get(job=areas_cmd.STAGE_BOUNDARY, region_code="36")
    assert run.status == IndexRun.Status.SKIPPED


def test_areas_sync_building_file_missing_skips_trades_but_continues_satellite_and_crime(
    monkeypatch, settings, capsys
):
    _sejong_with_boundary()
    monkeypatch.setattr(
        areas_cmd,
        "resolve_building_zip_path",
        lambda path, sido_code: (_ for _ in ()).throw(FileNotFoundError("AL_D010 없음")),
    )
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [(2026, "summer")])
    satellite_calls = []
    monkeypatch.setattr(
        areas_cmd, "run_backfill", lambda seasons, sido_code: satellite_calls.append(seasons) or []
    )
    crime_calls = []
    monkeypatch.setattr(
        areas_cmd, "run_crime_sync", lambda period, sido_code: crime_calls.append(sido_code)
    )
    settings.CRIME_FEATURE_CAP = 100
    settings.CRIME_DATA_PERIOD = "2023-07/2024-06"
    settings.CDSE_S3_ACCESS_KEY = "k"
    settings.CDSE_S3_SECRET_KEY = "k"
    settings.CDSE_S3_ENDPOINT = "https://example.test"

    call_command("areas", "sync", "--area", "36")

    assert satellite_calls == [[(2026, "summer")]]
    assert crime_calls == ["36"]
    out = capsys.readouterr().out
    assert "실거래 건너뜀" in out
    assert "건물 파일을 넣고 다시 실행하면 실거래부터" in out
    trades_run = IndexRun.objects.get(job=areas_cmd.STAGE_TRADES, region_code="36")
    assert trades_run.status == IndexRun.Status.SKIPPED


def test_areas_sync_satellite_only_processes_missing_seasons(monkeypatch, settings):
    """위성 13계절 중 일부만 게시된 상태에서 다시 실행하면 빠진 계절만 처리한다."""
    _sejong_with_boundary(enabled=True)
    _sejong_building()
    monkeypatch.setattr(areas_cmd, "sync_trades_for_months", lambda *a, **k: None)
    monkeypatch.setattr(
        areas_cmd, "target_seasons", lambda: [(2026, "summer"), (2026, "fall")]
    )
    settings.CRIME_FEATURE_CAP = None
    settings.DATA_GO_KR_API_KEY = "k"
    settings.CDSE_S3_ACCESS_KEY = "k"
    settings.CDSE_S3_SECRET_KEY = "k"
    settings.CDSE_S3_ENDPOINT = "https://example.test"

    bbox = GEOSPolygon.from_bbox((127.0, 36.0, 127.1, 36.1))
    for product_type in ("ndvi", "ndbi", "green_mask", "truecolor"):
        RasterProduct.objects.create(
            region_code="36",
            product_type=product_type,
            year=2026,
            season="summer",
            period_start="2026-06-01",
            period_end="2026-08-31",
            bbox=bbox,
            cog_path=f"/tmp/{product_type}.tif",
            algo_version=ALGO_VERSION,
            scene_ids=[],
            is_published=True,
        )

    satellite_calls = []
    monkeypatch.setattr(
        areas_cmd, "run_backfill", lambda seasons, sido_code: satellite_calls.append(seasons) or []
    )

    call_command("areas", "sync", "--area", "36")

    assert satellite_calls == [[(2026, "fall")]]  # summer는 이미 게시됐으니 fall만 처리


def test_areas_sync_skipped_crime_stage_is_retried_once_config_is_fixed(monkeypatch, settings):
    """건너뛴 단계(설정 없음)가 다음 실행에서 다시 시도되는지 확인한다."""
    _sejong_with_boundary(enabled=True)
    _sejong_building()
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [])
    monkeypatch.setattr(areas_cmd, "sync_trades_for_months", lambda *a, **k: None)
    settings.CRIME_FEATURE_CAP = None
    settings.CRIME_DATA_PERIOD = None
    settings.DATA_GO_KR_API_KEY = "k"

    call_command("areas", "sync", "--area", "36")

    run = IndexRun.objects.filter(job=areas_cmd.STAGE_CRIME, region_code="36").latest("id")
    assert run.status == IndexRun.Status.SKIPPED

    settings.CRIME_FEATURE_CAP = 100
    settings.CRIME_DATA_PERIOD = "2023-07/2024-06"
    crime_calls = []
    monkeypatch.setattr(
        areas_cmd, "run_crime_sync", lambda period, sido_code: crime_calls.append((period, sido_code))
    )

    call_command("areas", "sync", "--area", "36")

    assert crime_calls == [("2023-07/2024-06", "36")]


def test_areas_sync_auto_enables_once_boundary_and_buildings_done(monkeypatch, settings):
    area = ServiceArea.objects.create(
        sido_code="36", name="세종특별자치시", enabled=False, grid={"crs": "EPSG:32652"}
    )
    Region.objects.create(
        region_code="36", level="sido", name="세종특별자치시", geom=_square_wkt(127.0, 36.0)
    )
    _sejong_building()
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [])
    monkeypatch.setattr(areas_cmd, "sync_trades_for_months", lambda *a, **k: None)
    settings.DATA_GO_KR_API_KEY = "k"
    settings.CRIME_FEATURE_CAP = None

    call_command("areas", "sync", "--area", "36")

    area.refresh_from_db()
    assert area.enabled is True


# ---- 대화형 메뉴 ----


def _answer_sequence(*answers):
    it = iter(answers)
    return lambda prompt="": next(it)


def test_areas_menu_selecting_registered_area_skips_add(monkeypatch, tmp_path, capsys):
    """이미 등록된 지역을 고르면 add 없이 바로 동기화 상태(dry-run) 흐름으로 간다."""
    zip_path = _make_sejong_discoverable(monkeypatch, tmp_path)
    _patch_al_d001_resolver(monkeypatch, zip_path)
    ServiceArea.objects.create(sido_code="36", name="세종특별자치시", enabled=False)

    add_calls = []
    monkeypatch.setattr(
        areas_cmd.Command, "_add", lambda self, code, path: add_calls.append(code)
    )
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [])

    monkeypatch.setattr("builtins.input", _answer_sequence("1", "3"))

    call_command("areas")

    assert add_calls == []  # 이미 등록돼 있으니 add가 호출되면 안 됨
    out = capsys.readouterr().out
    assert "동기화 상태" in out


def test_areas_menu_selecting_unregistered_area_calls_add(monkeypatch, tmp_path):
    zip_path = _make_sejong_discoverable(monkeypatch, tmp_path)
    _patch_al_d001_resolver(monkeypatch, zip_path)
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [])

    monkeypatch.setattr("builtins.input", _answer_sequence("1", "3"))

    call_command("areas")

    assert ServiceArea.objects.filter(sido_code="36").exists()


def test_areas_menu_dry_run_report_shown_before_choice(monkeypatch, tmp_path, capsys):
    zip_path = _make_sejong_discoverable(monkeypatch, tmp_path)
    _patch_al_d001_resolver(monkeypatch, zip_path)
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [])

    monkeypatch.setattr("builtins.input", _answer_sequence("1", "3"))

    call_command("areas")

    out = capsys.readouterr().out
    assert "[1/5]" in out and "[5/5]" in out  # 5단계 dry-run 보고가 전부 출력됨


def test_areas_menu_choice_1_runs_sync_now(monkeypatch, tmp_path, settings):
    """[1] 지금 실행을 고르면 실제로 _sync(dry_run=False)가 돈다."""
    _sejong_with_boundary(enabled=True)
    _sejong_building()
    zip_path = _make_sejong_discoverable(monkeypatch, tmp_path)
    _patch_al_d001_resolver(monkeypatch, zip_path)
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [])
    settings.DATA_GO_KR_API_KEY = "k"
    settings.CRIME_FEATURE_CAP = None  # 실제 .env 값과 무관하게 범죄 단계는 건너뛰도록 고정

    trade_calls = []
    monkeypatch.setattr(
        areas_cmd, "sync_trades_for_months", lambda *a, **k: trade_calls.append(a)
    )

    monkeypatch.setattr("builtins.input", _answer_sequence("1", "1"))

    call_command("areas")

    assert len(trade_calls) == 1  # 실거래 단계까지 실제로 실행됨


def test_areas_menu_choice_2_prints_background_command_and_does_not_run_sync(
    monkeypatch, tmp_path, capsys
):
    _sejong_with_boundary(enabled=True)
    _sejong_building()
    zip_path = _make_sejong_discoverable(monkeypatch, tmp_path)
    _patch_al_d001_resolver(monkeypatch, zip_path)
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [])

    def _fail(*a, **k):
        pytest.fail("백그라운드를 고르면 sync_trades_for_months이 호출되면 안 됩니다")

    monkeypatch.setattr(areas_cmd, "sync_trades_for_months", _fail)

    monkeypatch.setattr("builtins.input", _answer_sequence("1", "2"))

    call_command("areas")

    out = capsys.readouterr().out
    assert "--background" in out
    assert "areas.sh logs 36" in out
    assert "areas.ps1 logs 36" in out


def test_areas_menu_choice_3_cancels(monkeypatch, tmp_path):
    _sejong_with_boundary(enabled=True)
    _sejong_building()
    zip_path = _make_sejong_discoverable(monkeypatch, tmp_path)
    _patch_al_d001_resolver(monkeypatch, zip_path)
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [])

    def _fail(*a, **k):
        pytest.fail("취소했는데 sync_trades_for_months이 호출되면 안 됩니다")

    monkeypatch.setattr(areas_cmd, "sync_trades_for_months", _fail)

    monkeypatch.setattr("builtins.input", _answer_sequence("1", "3"))

    call_command("areas")  # 예외 없이 끝나야 함


def test_areas_menu_empty_choice_exits_without_second_prompt(monkeypatch, tmp_path):
    zip_path = _make_sejong_discoverable(monkeypatch, tmp_path)
    _patch_al_d001_resolver(monkeypatch, zip_path)

    monkeypatch.setattr("builtins.input", _answer_sequence(""))  # 두 번째 input()을 부르면 StopIteration

    call_command("areas")  # 예외 없이 바로 끝나야 함


def test_areas_menu_falls_back_to_registered_list_when_zip_missing(monkeypatch, capsys):
    """AL_D001 zip이 없으면 이미 등록된 지역만이라도 고를 수 있어야 한다."""
    ServiceArea.objects.create(sido_code="36", name="세종특별자치시", enabled=True)

    def _raise(explicit_path=None):
        raise FileNotFoundError("zip 없음")

    monkeypatch.setattr("core.areas.resolve_al_d001_zip_path", _raise)
    monkeypatch.setattr(areas_cmd, "resolve_al_d001_zip_path", _raise)

    monkeypatch.setattr("builtins.input", _answer_sequence(""))

    call_command("areas")

    out = capsys.readouterr().out
    assert "36" in out


# ---- 최종 점검: 3~5단계 예외가 sync 전체를 죽이지 않고 failed로 기록됨 ----


def test_areas_sync_stage_exception_is_recorded_as_failed_and_later_stages_still_run(
    monkeypatch, settings, capsys
):
    """실거래 단계에서 예상 못한 예외가 나도(예: 네트워크 오류) sync 전체가 트레이스백으로
    끝나지 않고, failed로 기록한 뒤 위성·범죄 단계를 계속 진행해야 한다."""
    _sejong_with_boundary(enabled=True)
    _sejong_building()
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [])
    settings.DATA_GO_KR_API_KEY = "k"
    settings.CRIME_FEATURE_CAP = 100
    settings.CRIME_DATA_PERIOD = "2023-07/2024-06"

    def _boom(*a, **k):
        raise ValueError("공공데이터포털 서버 오류")

    monkeypatch.setattr(areas_cmd, "sync_trades_for_months", _boom)
    crime_calls = []
    monkeypatch.setattr(
        areas_cmd, "run_crime_sync", lambda period, sido_code: crime_calls.append(sido_code)
    )

    with pytest.raises(CommandError, match="일부 단계가 실패"):
        call_command("areas", "sync", "--area", "36")

    assert crime_calls == ["36"]  # 실거래가 failed여도 범죄 단계는 계속 실행됨
    out = capsys.readouterr().out
    assert "실거래 실패" in out
    assert "실거래: failed" in out


def test_areas_sync_prints_stage_summary_and_exits_zero_when_nothing_failed(
    monkeypatch, settings, capsys
):
    """모든 단계가 ok/skipped면(failed 없음) 요약을 출력하고 CommandError 없이 끝난다."""
    _sejong_with_boundary(enabled=True)
    _sejong_building()
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [])
    monkeypatch.setattr(areas_cmd, "sync_trades_for_months", lambda *a, **k: None)
    settings.DATA_GO_KR_API_KEY = "k"
    settings.CRIME_FEATURE_CAP = None  # 범죄는 설정 없어서 skipped

    call_command("areas", "sync", "--area", "36")  # CommandError가 나면 테스트 실패

    out = capsys.readouterr().out
    assert "결과 요약" in out
    assert "경계: ok" in out
    assert "건물: ok" in out
    assert "실거래: ok" in out
    assert "범죄: skipped" in out


def test_areas_sync_trades_skipped_when_data_go_kr_api_key_missing(monkeypatch, settings, capsys):
    """DATA_GO_KR_API_KEY가 없으면 예외 대신 skipped로 기록하고 안내를 출력하며,
    sync_trades_for_months는 호출되지 않는다."""
    _sejong_with_boundary(enabled=True)
    _sejong_building()
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [])
    settings.DATA_GO_KR_API_KEY = ""
    settings.CRIME_FEATURE_CAP = None

    def _fail(*a, **k):
        pytest.fail("DATA_GO_KR_API_KEY가 없으면 sync_trades_for_months이 호출되면 안 됩니다")

    monkeypatch.setattr(areas_cmd, "sync_trades_for_months", _fail)

    call_command("areas", "sync", "--area", "36")

    out = capsys.readouterr().out
    assert "실거래 건너뜀" in out
    assert "DATA_GO_KR_API_KEY" in out
    run = IndexRun.objects.filter(job=areas_cmd.STAGE_TRADES, region_code="36").latest("id")
    assert run.status == IndexRun.Status.SKIPPED


def test_areas_sync_satellite_skipped_when_cdse_keys_missing(monkeypatch, settings, capsys):
    """CDSE S3 키가 없으면 예외 대신 skipped로 기록하고 안내를 출력하며,
    run_backfill은 호출되지 않는다."""
    _sejong_with_boundary(enabled=True)
    _sejong_building()
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [(2026, "summer")])
    monkeypatch.setattr(areas_cmd, "sync_trades_for_months", lambda *a, **k: None)
    settings.DATA_GO_KR_API_KEY = "k"
    settings.CDSE_S3_ACCESS_KEY = ""
    settings.CDSE_S3_SECRET_KEY = ""
    settings.CDSE_S3_ENDPOINT = ""
    settings.CRIME_FEATURE_CAP = None

    def _fail(*a, **k):
        pytest.fail("CDSE 키가 없으면 run_backfill이 호출되면 안 됩니다")

    monkeypatch.setattr(areas_cmd, "run_backfill", _fail)

    call_command("areas", "sync", "--area", "36")

    out = capsys.readouterr().out
    assert "위성 건너뜀" in out
    assert "CDSE_S3" in out
    run = IndexRun.objects.filter(job=areas_cmd.STAGE_SATELLITE, region_code="36").latest("id")
    assert run.status == IndexRun.Status.SKIPPED


def test_areas_sync_dry_run_warns_when_trade_and_satellite_keys_missing(
    monkeypatch, settings, capsys
):
    """dry-run에서도 DATA_GO_KR_API_KEY·CDSE 키가 없으면(설정 안내) 그 사실을 보여줘야 한다."""
    _sejong_with_boundary(enabled=True)
    _sejong_building()
    monkeypatch.setattr(areas_cmd, "target_seasons", lambda: [(2026, "summer")])
    settings.DATA_GO_KR_API_KEY = ""
    settings.CDSE_S3_ACCESS_KEY = ""
    settings.CDSE_S3_SECRET_KEY = ""
    settings.CDSE_S3_ENDPOINT = ""

    call_command("areas", "sync", "--area", "36", "--dry-run")

    out = capsys.readouterr().out
    assert "DATA_GO_KR_API_KEY" in out
    assert "CDSE_S3" in out
