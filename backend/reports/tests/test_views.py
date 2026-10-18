import pytest
from rest_framework.test import APIClient

from accounts.models import User
from buildings.models import Building
from reports import views as reports_views
from reports.models import Report

pytestmark = pytest.mark.django_db


def _square_wkt(lon, lat, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


def _make_building(**overrides):
    defaults = dict(
        building_key="RVB1",
        gis_bldg_id="RVB1",
        pnu="3011010300101530040",
        bjd_code="3011010300",
        use_code="01000",
        use_name="공동주택",
        source_date="2026-10-06",
        geom=_square_wkt(127.385, 36.351),
    )
    defaults.update(overrides)
    return Building.objects.create(**defaults)


def _make_user(email="reports@example.com"):
    return User.objects.create_user(email=email, password="correct-horse-battery")


def _authed(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture(autouse=True)
def _no_real_celery_dispatch(monkeypatch):
    """generate_report.delay가 실제 Celery/Redis로 안 나가게 막는다 — 각 테스트는 필요하면
    직접 다시 monkeypatch해서 호출 여부를 확인한다."""
    monkeypatch.setattr(reports_views.generate_report, "delay", lambda report_id: None)


def test_post_creates_report_and_dispatches_task(monkeypatch):
    dispatched = []
    monkeypatch.setattr(
        reports_views.generate_report, "delay", lambda report_id: dispatched.append(report_id)
    )
    user = _make_user()
    building = _make_building()
    client = _authed(user)

    response = client.post(
        f"/api/buildings/{building.id}/reports",
        {"radius_m": 500, "report_type": "template"},
        format="json",
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "generating"
    assert dispatched == [body["report_id"]]
    report = Report.objects.get(id=body["report_id"])
    assert report.template_version == "v1"
    assert "my" not in report.input_snapshot


def test_post_custom_requires_prompt():
    user = _make_user()
    building = _make_building(building_key="RVB2", gis_bldg_id="RVB2", pnu="3011010300101530041")
    client = _authed(user)

    response = client.post(
        f"/api/buildings/{building.id}/reports",
        {"radius_m": 500, "report_type": "custom"},
        format="json",
    )

    assert response.status_code == 400


def test_post_custom_prompt_too_long_rejected():
    user = _make_user()
    building = _make_building(building_key="RVB3", gis_bldg_id="RVB3", pnu="3011010300101530042")
    client = _authed(user)

    response = client.post(
        f"/api/buildings/{building.id}/reports",
        {"radius_m": 500, "report_type": "custom", "prompt": "가" * 501},
        format="json",
    )

    assert response.status_code == 400


def test_post_rejects_invalid_radius():
    user = _make_user()
    building = _make_building(building_key="RVB4", gis_bldg_id="RVB4", pnu="3011010300101530043")
    client = _authed(user)

    response = client.post(
        f"/api/buildings/{building.id}/reports",
        {"radius_m": 700, "report_type": "template"},
        format="json",
    )

    assert response.status_code == 400


def test_post_rejected_when_already_generating():
    user = _make_user()
    building = _make_building(building_key="RVB5", gis_bldg_id="RVB5", pnu="3011010300101530044")
    Report.objects.create(
        user=user,
        building=building,
        radius_m=500,
        report_type=Report.ReportType.TEMPLATE,
        input_snapshot={},
        status=Report.Status.GENERATING,
    )
    client = _authed(user)

    response = client.post(
        f"/api/buildings/{building.id}/reports",
        {"radius_m": 500, "report_type": "template"},
        format="json",
    )

    assert response.status_code == 429


def test_post_rejected_after_daily_limit():
    user = _make_user()
    building = _make_building(building_key="RVB6", gis_bldg_id="RVB6", pnu="3011010300101530045")
    for _ in range(20):
        Report.objects.create(
            user=user,
            building=building,
            radius_m=500,
            report_type=Report.ReportType.TEMPLATE,
            input_snapshot={},
            status=Report.Status.READY,
        )
    client = _authed(user)

    response = client.post(
        f"/api/buildings/{building.id}/reports",
        {"radius_m": 500, "report_type": "template"},
        format="json",
    )

    assert response.status_code == 429


def test_failed_reports_do_not_count_toward_daily_limit():
    user = _make_user()
    building = _make_building(building_key="RVB7", gis_bldg_id="RVB7", pnu="3011010300101530046")
    for _ in range(20):
        Report.objects.create(
            user=user,
            building=building,
            radius_m=500,
            report_type=Report.ReportType.TEMPLATE,
            input_snapshot={},
            status=Report.Status.FAILED,
        )
    client = _authed(user)

    response = client.post(
        f"/api/buildings/{building.id}/reports",
        {"radius_m": 500, "report_type": "template"},
        format="json",
    )

    assert response.status_code == 202


def test_get_building_reports_lists_only_own_reports_newest_first():
    user = _make_user()
    other = _make_user(email="other@example.com")
    building = _make_building(building_key="RVB8", gis_bldg_id="RVB8", pnu="3011010300101530047")
    older = Report.objects.create(
        user=user,
        building=building,
        radius_m=500,
        report_type=Report.ReportType.TEMPLATE,
        input_snapshot={},
        status=Report.Status.READY,
    )
    newer = Report.objects.create(
        user=user,
        building=building,
        radius_m=500,
        report_type=Report.ReportType.CUSTOM,
        user_prompt="질문",
        input_snapshot={},
        status=Report.Status.GENERATING,
    )
    Report.objects.create(
        user=other,
        building=building,
        radius_m=500,
        report_type=Report.ReportType.TEMPLATE,
        input_snapshot={},
        status=Report.Status.READY,
    )
    client = _authed(user)

    response = client.get(f"/api/buildings/{building.id}/reports")
    ids = [item["id"] for item in response.json()]

    assert ids == [newer.id, older.id]


def test_get_report_detail_ready_includes_result_and_data_as_of():
    user = _make_user()
    building = _make_building(building_key="RVB9", gis_bldg_id="RVB9", pnu="3011010300101530048")
    report = Report.objects.create(
        user=user,
        building=building,
        radius_m=500,
        report_type=Report.ReportType.TEMPLATE,
        template_version="v1",
        input_snapshot={
            "as_of": {
                "satellite_period": "2026-06-01/2026-08-31",
                "trade_synced_at": "2026-10-16T04:12:00+09:00",
            }
        },
        model="gpt-oss-20b",
        payload={
            "summary_3lines": ["a", "b", "c"],
            "living_view": "x",
            "investment_view": "y",
            "risks": [],
            "evidence": [],
        },
        status=Report.Status.READY,
    )
    client = _authed(user)

    response = client.get(f"/api/reports/{report.id}")
    body = response.json()

    assert body["status"] == "ready"
    assert body["data_as_of"]["satellite_period"] == "2026-06-01/2026-08-31"
    assert body["result"]["living_view"] == "x"


def test_get_report_detail_generating_has_no_result():
    user = _make_user()
    building = _make_building(
        building_key="RVBA", gis_bldg_id="RVBA", pnu="3011010300101530049"
    )
    report = Report.objects.create(
        user=user,
        building=building,
        radius_m=500,
        report_type=Report.ReportType.TEMPLATE,
        input_snapshot={},
        status=Report.Status.GENERATING,
    )
    client = _authed(user)

    response = client.get(f"/api/reports/{report.id}")
    body = response.json()

    assert body["status"] == "generating"
    assert "result" not in body


def test_get_report_on_another_users_report_returns_403():
    user = _make_user()
    other = _make_user(email="other2@example.com")
    building = _make_building(
        building_key="RVBB", gis_bldg_id="RVBB", pnu="3011010300101530030"
    )
    report = Report.objects.create(
        user=other,
        building=building,
        radius_m=500,
        report_type=Report.ReportType.TEMPLATE,
        input_snapshot={},
        status=Report.Status.READY,
    )
    client = _authed(user)

    response = client.get(f"/api/reports/{report.id}")

    assert response.status_code == 403


def test_get_nonexistent_report_returns_404():
    user = _make_user()
    client = _authed(user)

    response = client.get("/api/reports/999999")

    assert response.status_code == 404


def test_delete_report_removes_it():
    user = _make_user()
    building = _make_building(
        building_key="RVBC", gis_bldg_id="RVBC", pnu="3011010300101530031"
    )
    report = Report.objects.create(
        user=user,
        building=building,
        radius_m=500,
        report_type=Report.ReportType.TEMPLATE,
        input_snapshot={},
        status=Report.Status.READY,
    )
    client = _authed(user)

    response = client.delete(f"/api/reports/{report.id}")

    assert response.status_code == 204
    assert not Report.objects.filter(id=report.id).exists()
