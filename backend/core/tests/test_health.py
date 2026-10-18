from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_health_ok_when_db_and_redis_up(monkeypatch):
    monkeypatch.setattr("django.db.connection.ensure_connection", lambda: None)
    fake_redis = MagicMock()
    monkeypatch.setattr("core.views.get_redis_client", lambda: fake_redis)

    response = APIClient().get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"db": "ok", "redis": "ok"}}


def test_health_503_when_db_down(monkeypatch):
    def boom():
        raise Exception("db down")

    monkeypatch.setattr("django.db.connection.ensure_connection", boom)
    fake_redis = MagicMock()
    monkeypatch.setattr("core.views.get_redis_client", lambda: fake_redis)

    response = APIClient().get("/api/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_health_503_when_redis_down(monkeypatch):
    monkeypatch.setattr("django.db.connection.ensure_connection", lambda: None)
    fake_redis = MagicMock()
    fake_redis.ping.side_effect = Exception("redis down")
    monkeypatch.setattr("core.views.get_redis_client", lambda: fake_redis)

    response = APIClient().get("/api/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
