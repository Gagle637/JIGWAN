import pytest
from django.core.management import call_command

from layers.models import MapLayer

pytestmark = pytest.mark.django_db


def test_seed_map_layers_fills_crime_layer_legend_and_source_params():
    call_command("seed_map_layers")

    layer = MapLayer.objects.get(name="범죄주의구간(전체)")

    assert layer.source_type == MapLayer.SourceType.WMS
    assert layer.source_params["service_url"] == "https://safemap.go.kr/openapi2/IF_0087_WMS"
    assert layer.source_params["layers"] == "A2SM_CRMNLHSPOT_TOT"
    assert layer.notice.startswith("경찰청의 요청으로")

    assert len(layer.legend) == 10
    # LGD_NO 기준으로 정렬돼 있어야 한다(사용자 확인: 실제 응답은 순서가 섞여 있음).
    assert [item["no"] for item in layer.legend] == list(range(1, 11))
    assert layer.legend[0] == {"no": 1, "label": "1등급", "color": "#ffffb2"}
    assert layer.legend[-1] == {"no": 10, "label": "10등급", "color": "#bd0026"}


def test_seed_map_layers_is_idempotent_on_rerun():
    call_command("seed_map_layers")
    first_count = MapLayer.objects.count()

    call_command("seed_map_layers")

    assert MapLayer.objects.count() == first_count
