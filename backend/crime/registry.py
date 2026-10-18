"""map_layer의 '범죄주의구간(전체)' 행을 찾는 작은 헬퍼(safety_sync가 타일 캐시를 비울 때 쓴다)."""
from layers.models import MapLayer

CRIME_LAYER_NAME = "범죄주의구간(전체)"


def crime_layer_id() -> int | None:
    return MapLayer.objects.filter(name=CRIME_LAYER_NAME).values_list("id", flat=True).first()
