"""CDSE STAC 검색(spec 2-1 예제 코드 그대로) + baseline 중복 제거(결정 사항 7-①)."""
from datetime import date, datetime

from pystac_client import Client

STAC_URL = "https://stac.dataspace.copernicus.eu/v1/"


def search_scenes(start: date, end: date, bbox, max_cloud: int = 30) -> list:
    """spec 2-1 예제 코드 그대로 pystac-client로 검색한다. bbox는 core.areas.get_bbox(sido_code)
    (EPSG:4326, 다지역 지원 2단계)로 호출부가 넘긴다."""
    catalog = Client.open(STAC_URL)
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=f"{start.isoformat()}/{end.isoformat()}",
        filter=f"eo:cloud_cover <= {max_cloud}",
        filter_lang="cql2-text",
    )
    return list(search.items())


def tile_code(item) -> str:
    """item.id.split('_')[5] (예: 'T52SCF') — spec 2-1 예제 그대로."""
    return item.id.split("_")[5]


def processing_baseline(item) -> str:
    """item.id.split('_')[3] (예: 'N0512') — item.id 명명 규칙에서 바로 뽑는다."""
    return item.id.split("_")[3]


def baseline_number(item) -> int:
    return int(processing_baseline(item).lstrip("N"))


def sensed_at(item) -> datetime:
    """item.properties['datetime'](STAC 표준 필드)."""
    value = item.properties["datetime"]
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def dedupe_latest_baseline(items: list) -> list:
    """(mgrs_tile, 촬영일자)별로 processing_baseline이 가장 높은 것만 남긴다(①)."""
    groups: dict[tuple[str, date], list] = {}
    for item in items:
        key = (tile_code(item), sensed_at(item).date())
        groups.setdefault(key, []).append(item)
    return [max(group, key=baseline_number) for group in groups.values()]


def group_by_date(items: list) -> dict[date, list]:
    """baseline 중복 제거 후, 같은 날짜에 걸친 타일들을 모은다(②로 넘길 그룹)."""
    groups: dict[date, list] = {}
    for item in items:
        groups.setdefault(sensed_at(item).date(), []).append(item)
    return groups
