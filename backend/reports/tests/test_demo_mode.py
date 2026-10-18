import pytest
from rest_framework.test import APIClient

from accounts.models import User
from buildings.models import Building
from reports import views as reports_views
from reports.models import Report

pytestmark = pytest.mark.django_db

DEMO_PNU = "DEMO000000000000001"


def _square_wkt(lon, lat, size=0.001):
    return (
        f"POLYGON(({lon} {lat}, {lon + size} {lat}, "
        f"{lon + size} {lat + size}, {lon} {lat + size}, {lon} {lat}))"
    )


def _make_building(**overrides):
    defaults = dict(
        building_key="DMRB1",
        gis_bldg_id="DMRB1",
        pnu=DEMO_PNU,
        bjd_code="3011010300",
        use_code="01000",
        use_name="공동주택",
        source_date="2026-10-06",
        geom=_square_wkt(127.385, 36.351),
    )
    defaults.update(overrides)
    return Building.objects.create(**defaults)


def _make_user(email="demoreports@example.com"):
    return User.objects.create_user(email=email, password="correct-horse-battery")


def _authed(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture(autouse=True)
def _no_real_celery_dispatch(monkeypatch):
    monkeypatch.setattr(reports_views.generate_report, "delay", lambda report_id: None)


def test_demo_mode_post_returns_ready_immediately_without_dispatch(settings, monkeypatch):
    settings.DEMO_MODE = True
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
    assert body["status"] == "ready"
    assert dispatched == []  # GPU 큐로 안 나갔어야 한다

    report = Report.objects.get(id=body["report_id"])
    assert report.status == Report.Status.READY
    assert report.model == "demo"
    assert report.payload["summary_3lines"][0].startswith("반경 500m 녹지율은 23.4%")
    assert "my" not in report.input_snapshot


def test_demo_mode_get_detail_shows_fixed_result(settings):
    settings.DEMO_MODE = True
    user = _make_user()
    building = _make_building(
        building_key="DMRB2", gis_bldg_id="DMRB2", pnu=DEMO_PNU
    )
    client = _authed(user)

    create = client.post(
        f"/api/buildings/{building.id}/reports",
        {"radius_m": 500, "report_type": "custom", "prompt": "녹지 위주로 봐줘"},
        format="json",
    )
    report_id = create.json()["report_id"]

    response = client.get(f"/api/reports/{report_id}")
    body = response.json()

    assert body["status"] == "ready"
    assert body["result"]["title"]
    assert body["model"] == "demo"


def test_demo_mode_off_uses_real_generation_path(settings, monkeypatch):
    settings.DEMO_MODE = False
    dispatched = []
    monkeypatch.setattr(
        reports_views.generate_report, "delay", lambda report_id: dispatched.append(report_id)
    )
    user = _make_user()
    building = _make_building(
        building_key="DMRB3", gis_bldg_id="DMRB3", pnu=DEMO_PNU
    )
    client = _authed(user)

    response = client.post(
        f"/api/buildings/{building.id}/reports",
        {"radius_m": 500, "report_type": "template"},
        format="json",
    )

    assert response.status_code == 202
    assert response.json()["status"] == "generating"
    assert len(dispatched) == 1


def test_demo_mode_rejects_report_type_missing_from_fixture_with_400(settings, monkeypatch):
    """데모 fixture에 해당 report_type 예시가 없으면 500이 아니라 400으로 응답해야 한다."""
    settings.DEMO_MODE = True
    monkeypatch.setattr(
        reports_views,
        "get_demo_snapshot",
        lambda pnu: {"insight": {"status": "ready"}, "reports": {"template": {}}},
    )
    user = _make_user()
    building = _make_building(
        building_key="DMRB4", gis_bldg_id="DMRB4", pnu=DEMO_PNU
    )
    client = _authed(user)

    response = client.post(
        f"/api/buildings/{building.id}/reports",
        {"radius_m": 500, "report_type": "custom", "prompt": "질문"},
        format="json",
    )

    assert response.status_code == 400
