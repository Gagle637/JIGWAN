import json
from pathlib import Path

from django.core.management.base import BaseCommand

from layers.models import MapLayer

CRIME_LEGEND_FIXTURE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "crime_legend_tot.json"


def _load_crime_legend_and_notice() -> tuple[list[dict], str]:
    """9단계: 범례는 런타임 API로 받지 않고 고정 fixture를 쓴다(사용자 확인). 응답 배열 순서가
    섞여 있을 수 있어 LGD_NO 기준으로 정렬한다."""
    items = json.loads(CRIME_LEGEND_FIXTURE.read_text(encoding="utf-8"))
    items = sorted(items, key=lambda item: int(item["LGD_NO"]))
    legend = [{"no": int(item["LGD_NO"]), "label": item["LGD_NM"], "color": item["IMAGE"]} for item in items]
    notice = items[0]["WARN"]
    return legend, notice


_CRIME_LEGEND, _CRIME_NOTICE = _load_crime_legend_and_notice()

# spec 10-1 MVP 레이어 9개. 아직 조회 API가 없는 레이어(실거래 위치·개발 변화 구역·
# 내 표시 건물)는 source_params를 비워 두고 notice에 현재 상태를 적어 둔다.
LAYERS = [
    {
        "name": "배경지도",
        "group": "기본",
        "order": 1,
        "source_type": MapLayer.SourceType.RASTER_TILE,
        "source_params": {"url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png"},
        "min_zoom": 0,
        "max_zoom": 19,
        "opacity": 1.0,
        "default_visible": True,
        "attribution": "© OpenStreetMap contributors",
    },
    {
        "name": "건물 풋프린트",
        "group": "기본",
        "order": 2,
        "source_type": MapLayer.SourceType.VECTOR_TILE,
        "source_params": {"url": "/api/tiles/buildings/{z}/{x}/{y}.mvt"},
        "min_zoom": 14,
        "max_zoom": 20,
        "opacity": 1.0,
        "default_visible": True,
    },
    {
        "name": "내 표시 건물",
        "group": "내 건물",
        "order": 3,
        "source_type": MapLayer.SourceType.GEOJSON,
        "source_params": {"url": "/api/me/buildings"},
        "opacity": 1.0,
        "default_visible": True,
        "notice": "로그인 사용자 본인 것만. 즐겨찾기 기능이 아직 없어 당장은 비어 있다.",
    },
    {
        "name": "분석 반경",
        "group": "분석",
        "order": 4,
        "source_type": MapLayer.SourceType.GEOJSON,
        "source_params": {},
        "opacity": 0.5,
        "default_visible": False,
        "notice": "건물 선택 시 클라이언트가 직접 그린다(500m·1km). 별도 조회 API는 없다.",
    },
    {
        "name": "녹지 마스크",
        "group": "환경",
        "order": 5,
        "source_type": MapLayer.SourceType.TITILER,
        "source_params": {},
        "opacity": 0.6,
        "default_visible": False,
        "legend": [{"no": 1, "label": "녹지", "color": "#228B22"}],
        "notice": "catalog_publish가 게시할 때마다 최신 계절로 자동 갱신된다.",
    },
    {
        "name": "개발 변화 구역",
        "group": "개발",
        "order": 6,
        "source_type": MapLayer.SourceType.GEOJSON,
        "source_params": {},
        "opacity": 0.6,
        "default_visible": False,
        "notice": "건물별 insight.change.areas로만 제공, 지도 범위 조회 API는 아직 없다.",
    },
    {
        "name": "Before/After 위성 영상",
        "group": "개발",
        "order": 7,
        "source_type": MapLayer.SourceType.TITILER,
        "source_params": {},
        "opacity": 1.0,
        "default_visible": False,
        "notice": "catalog_publish가 게시할 때마다 최신 계절로 자동 갱신된다.",
    },
    {
        "name": "실거래 위치",
        "group": "시세",
        "order": 8,
        "source_type": MapLayer.SourceType.GEOJSON,
        "source_params": {},
        "opacity": 0.8,
        "default_visible": False,
        "notice": "지도 범위 조회 API는 아직 없다. insight.trades로만 제공.",
    },
    {
        "name": "범죄주의구간(전체)",
        "group": "안전",
        "order": 9,
        "source_type": MapLayer.SourceType.WMS,
        "source_params": {
            "service_url": "https://safemap.go.kr/openapi2/IF_0087_WMS",
            "layers": "A2SM_CRMNLHSPOT_TOT",
            "styles": "A2SM_CrmnlHspot_Tot_Tot",
            "version": "1.1.1",
            "srs": "EPSG:3857",
            "format": "image/png",
            "transparent": True,
        },
        "opacity": 0.5,
        "default_visible": False,
        "legend": _CRIME_LEGEND,
        "notice": _CRIME_NOTICE,
        "attribution": "경찰청·생활안전지도",
    },
]


class Command(BaseCommand):
    help = "spec 10-1의 지도 레이어 9개를 map_layer에 upsert한다."

    def handle(self, *args, **options):
        for entry in LAYERS:
            name = entry["name"]
            defaults = {key: value for key, value in entry.items() if key != "name"}
            layer, created = MapLayer.objects.update_or_create(name=name, defaults=defaults)
            verb = "생성" if created else "갱신"
            self.stdout.write(self.style.SUCCESS(f"{verb}: {name}"))
