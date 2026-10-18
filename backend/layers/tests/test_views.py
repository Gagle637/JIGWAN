import pytest
from rest_framework.test import APIClient

from layers.models import MapLayer

pytestmark = pytest.mark.django_db


def test_layers_endpoint_requires_no_auth_and_orders_by_order():
    MapLayer.objects.create(
        name="레이어B", group="satellite", order=2, source_type=MapLayer.SourceType.TITILER
    )
    MapLayer.objects.create(
        name="레이어A", group="base", order=1, source_type=MapLayer.SourceType.RASTER_TILE
    )

    client = APIClient()  # 로그인 없이 호출(spec 9-1: 레이어는 비로그인 허용)
    response = client.get("/api/layers")

    assert response.status_code == 200
    names = [row["name"] for row in response.json()]
    assert names == ["레이어A", "레이어B"]


def test_layers_endpoint_serializes_all_fields():
    layer = MapLayer.objects.create(
        name="녹지 마스크",
        group="satellite",
        order=5,
        source_type=MapLayer.SourceType.TITILER,
        source_params={"cog_path": "/tmp/x.tif"},
        min_zoom=10,
        max_zoom=18,
        opacity=0.8,
        default_visible=True,
        legend={"0": "없음", "1": "녹지"},
        notice="격자 업데이트 중",
        attribution="JIGWAN",
    )

    client = APIClient()
    response = client.get("/api/layers")
    row = response.json()[0]

    assert row["id"] == layer.id
    assert row["group"] == "satellite"
    assert row["order"] == 5
    assert row["source_type"] == "titiler"
    assert row["source_params"] == {"cog_path": "/tmp/x.tif"}
    assert row["min_zoom"] == 10
    assert row["max_zoom"] == 18
    assert row["opacity"] == 0.8
    assert row["default_visible"] is True
    assert row["legend"] == {"0": "없음", "1": "녹지"}
    assert row["notice"] == "격자 업데이트 중"
    assert row["attribution"] == "JIGWAN"
    assert row["synced_at"] is None
