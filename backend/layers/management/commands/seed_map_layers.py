import json
from pathlib import Path

from django.core.management.base import BaseCommand

from layers.models import MapLayer
from layers.registry import COPERNICUS_NOTICE

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
#
# slug는 name이 바뀌어도 변하지 않는 upsert 키다(name은 "(10m 해상도)" 같은 접미사가
# 붙어 바뀔 수 있다 — layers/migrations/0003이 기존 행에 이 slug를 한 번 채워 넣는다).
LAYERS = [
    {
        "slug": "osm_basemap",
        "name": "배경지도",
        "group": "기본",
        "kind": MapLayer.Kind.BACKGROUND,
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
        "slug": "building_footprint",
        "name": "건물 풋프린트",
        "group": "기본",
        "kind": MapLayer.Kind.BACKGROUND,
        "order": 2,
        "source_type": MapLayer.SourceType.VECTOR_TILE,
        "source_params": {"url": "/api/tiles/buildings/{z}/{x}/{y}.mvt"},
        "min_zoom": 14,
        "max_zoom": 20,
        "opacity": 1.0,
        "default_visible": True,
        "attribution": "브이월드 GIS건물통합정보",
    },
    {
        "slug": "my_buildings",
        "name": "내 표시 건물",
        "group": "내 건물",
        "kind": MapLayer.Kind.ANALYSIS,
        "order": 3,
        "source_type": MapLayer.SourceType.GEOJSON,
        "source_params": {"url": "/api/me/buildings"},
        "opacity": 1.0,
        "default_visible": True,
        "notice": "로그인 사용자 본인 것만. 즐겨찾기 기능이 아직 없어 당장은 비어 있다.",
        # 사용자 결정: 외부 출처가 없는 자체 데이터라 비워 둔다(테스트는 "외부 데이터
        # 레이어만" attribution 비어있지 않음을 확인한다).
        "attribution": None,
    },
    {
        "slug": "analysis_radius",
        "name": "분석 반경",
        "group": "분석",
        "kind": MapLayer.Kind.ANALYSIS,
        "order": 4,
        "source_type": MapLayer.SourceType.GEOJSON,
        "source_params": {},
        "opacity": 0.5,
        "default_visible": False,
        "notice": "건물 선택 시 클라이언트가 직접 그린다(500m·1km). 별도 조회 API는 없다.",
        "attribution": None,
    },
    {
        "slug": "green_mask",
        "name": "녹지 마스크 (10m 해상도)",
        "group": "환경",
        "kind": MapLayer.Kind.ANALYSIS,
        "order": 5,
        "source_type": MapLayer.SourceType.TITILER,
        "source_params": {},
        "min_zoom": None,
        "max_zoom": 15,
        "opacity": 0.6,
        "default_visible": False,
        "legend": [{"no": 1, "label": "녹지", "color": "#228B22"}],
        "notice": "catalog_publish가 게시할 때마다 활성 지역별로 최신 계절로 자동 갱신된다.",
        # sync_cog_layer가 지역·계절별로 연도를 넣어 다시 계산한다(regions가 비어있을 때의
        # 대체값). source_type=titiler, min_zoom은 TiTiler COG 범위를 그대로 따른다.
        "attribution": COPERNICUS_NOTICE,
    },
    {
        "slug": "change_area",
        "name": "개발 변화 구역",
        "group": "개발",
        "kind": MapLayer.Kind.ANALYSIS,
        "order": 6,
        "source_type": MapLayer.SourceType.GEOJSON,
        "source_params": {},
        "opacity": 0.6,
        "default_visible": False,
        "notice": "건물별 insight.change.areas로만 제공, 지도 범위 조회 API는 아직 없다.",
        # Sentinel 파생 결과라 같은 고지가 필요하다(사용자 결정). 다만 이 레이어는 지역별
        # 목록 동기화 대상이 아니라서(2번 작업은 녹지 마스크·Before/After 두 개만) 연도를
        # 동적으로 못 넣는다 — 연도 없는 정적 문구로 둔다.
        "attribution": COPERNICUS_NOTICE,
    },
    {
        "slug": "before_after",
        "name": "Before/After 위성 영상 (10m 해상도)",
        "group": "개발",
        "kind": MapLayer.Kind.ANALYSIS,
        "order": 7,
        "source_type": MapLayer.SourceType.TITILER,
        "source_params": {},
        "min_zoom": None,
        "max_zoom": 15,
        "opacity": 1.0,
        "default_visible": False,
        "notice": "catalog_publish가 게시할 때마다 활성 지역별로 최신 계절로 자동 갱신된다.",
        "attribution": COPERNICUS_NOTICE,
    },
    {
        "slug": "trade_location",
        "name": "실거래 위치",
        "group": "시세",
        "kind": MapLayer.Kind.ANALYSIS,
        "order": 8,
        "source_type": MapLayer.SourceType.GEOJSON,
        "source_params": {},
        "opacity": 0.8,
        "default_visible": False,
        "notice": "지도 범위 조회 API는 아직 없다. insight.trades로만 제공.",
        "attribution": "국토교통부 실거래가 공개시스템(공공데이터포털)",
    },
    {
        "slug": "crime_hotspot",
        "name": "범죄주의구간(전체)",
        "group": "안전",
        "kind": MapLayer.Kind.ANALYSIS,
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
        "attribution": "경찰청 생활안전지도",
    },
]


class Command(BaseCommand):
    help = "spec 10-1의 지도 레이어 9개를 map_layer에 slug 기준으로 upsert한다."

    def handle(self, *args, **options):
        for entry in LAYERS:
            slug = entry["slug"]
            defaults = {key: value for key, value in entry.items() if key != "slug"}
            layer, created = MapLayer.objects.update_or_create(slug=slug, defaults=defaults)
            verb = "생성" if created else "갱신"
            self.stdout.write(self.style.SUCCESS(f"{verb}: {layer.name} ({slug})"))
