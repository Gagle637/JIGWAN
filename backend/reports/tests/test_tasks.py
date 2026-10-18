import pytest

from buildings.models import Building
from accounts.models import User
from reports import tasks as tasks_module
from reports.generation import ReportGenerationFailed
from reports.models import Report

pytestmark = pytest.mark.django_db


def _square_wkt(lon, lat, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


def _make_report(**overrides):
    user = User.objects.create_user(email="task@example.com", password="correct-horse-battery")
    building = Building.objects.create(
        building_key="TASKB1",
        gis_bldg_id="TASKB1",
        pnu="3011010300101530011",
        bjd_code="3011010300",
        use_code="01000",
        use_name="공동주택",
        source_date="2026-10-06",
        geom=_square_wkt(127.385, 36.351),
    )
    defaults = dict(
        user=user,
        building=building,
        radius_m=500,
        report_type=Report.ReportType.TEMPLATE,
        input_snapshot={"green": {"ratio_pct": 1.0}},
        status=Report.Status.GENERATING,
    )
    defaults.update(overrides)
    return Report.objects.create(**defaults)


def test_generate_report_saves_status_model_payload_on_success(monkeypatch):
    report = _make_report()
    payload = {
        "summary_3lines": ["a", "b", "c"],
        "living_view": "x",
        "investment_view": "y",
        "risks": [],
        "evidence": [],
    }
    monkeypatch.setattr(
        tasks_module, "run_generation", lambda r: (payload, "gpt-oss-20b")
    )

    tasks_module.generate_report(report.id)

    report.refresh_from_db()
    assert report.status == Report.Status.READY
    assert report.model == "gpt-oss-20b"
    assert report.payload == payload


def test_generate_report_saves_failed_status_and_error_on_generation_failure(monkeypatch):
    report = _make_report()

    def fake_run_generation(r):
        raise ReportGenerationFailed("검증 3회 실패: 금지어 포함")

    monkeypatch.setattr(tasks_module, "run_generation", fake_run_generation)

    tasks_module.generate_report(report.id)

    report.refresh_from_db()
    assert report.status == Report.Status.FAILED
    assert report.model is None
    assert report.payload == {"error": "검증 3회 실패: 금지어 포함"}
