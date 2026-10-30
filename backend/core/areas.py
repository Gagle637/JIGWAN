"""서비스 지역(service_area) 해석 함수(docs/tasks/multi_area.md 1단계).

buildings를 함수 안에서 지연 임포트하는 이유: core는 모든 앱이 쓰는 기반 앱이라, 모듈
최상단에서 buildings를 임포트하면 순환 임포트 위험이 있다.
"""
import math
from pathlib import Path

from django.conf import settings

from .models import ServiceArea

SNAP_M = 60
RESOLUTION_M = 10
BUFFER_M = 500

DATA_RAW_DIR = Path(settings.BASE_DIR).parent / "data" / "raw"


def _get_area(sido_code: str) -> ServiceArea:
    try:
        return ServiceArea.objects.get(sido_code=sido_code)
    except ServiceArea.DoesNotExist:
        raise ValueError(f"'{sido_code}'는 등록된 지역(service_area)이 아닙니다.") from None


def get_bbox(sido_code: str) -> tuple[float, float, float, float]:
    """저장된 bbox(EPSG:4326)만 읽는다. 없으면 계산하지 않고 에러."""
    area = _get_area(sido_code)
    if area.bbox_minx is None:
        raise ValueError(
            f"'{sido_code}' 지역의 bbox가 아직 없습니다 — compute_and_store_grid를 먼저 실행하세요."
        )
    return (area.bbox_minx, area.bbox_miny, area.bbox_maxx, area.bbox_maxy)


def get_grid(sido_code: str) -> dict:
    """저장된 grid(EPSG:32652 고정 격자)만 읽는다. 없으면 계산하지 않고 에러."""
    area = _get_area(sido_code)
    if area.grid is None:
        raise ValueError(
            f"'{sido_code}' 지역의 grid가 아직 없습니다 — compute_and_store_grid를 먼저 실행하세요."
        )
    return area.grid


def enabled_sido_codes() -> list[str]:
    """활성화된(enabled=True) 지역의 시도 코드 목록(다지역 지원 7단계) — Beat 디스패처
    태스크와, `--sido`를 생략한 관리 명령이 이 목록을 돈다."""
    return list(
        ServiceArea.objects.filter(enabled=True).order_by("sido_code").values_list(
            "sido_code", flat=True
        )
    )


def get_sgg_codes(sido_code: str) -> list[str]:
    """region(level=sigungu)에서 실시간으로 조회한다(저장 안 함 — 다시 적재하면 바로 반영).
    비어 있으면 에러로 알린다(경계 미적재 상태에서 실거래 수집이 조용히 0건으로 끝나지 않게)."""
    from buildings.models import Region

    codes = list(
        Region.objects.filter(level="sigungu", region_code__startswith=sido_code)
        .order_by("region_code")
        .values_list("region_code", flat=True)
    )
    if not codes:
        raise ValueError(
            f"'{sido_code}' 지역의 시군구(region, level=sigungu)가 없습니다 — "
            "load_regions를 먼저 실행하세요."
        )
    return codes


def compute_and_store_grid(sido_code: str) -> None:
    """region(level=sido)의 경계로 grid·bbox를 딱 한 번 계산해 저장한다(멱등 — 이미 있으면
    아무것도 안 한다). 순서(사용자 결정): sido 경계를 32652로 변환 → 500m 여유(미터 단위) →
    60m 배수 바깥 스냅 → grid 저장 → grid 범위를 4326으로 되돌려 bbox 저장(bbox가 grid를
    항상 덮게)."""
    from django.contrib.gis.geos import Polygon as GEOSPolygon

    from buildings.models import Region

    area = _get_area(sido_code)
    if area.grid is not None:
        return

    region = Region.objects.filter(level="sido", region_code=sido_code).first()
    if region is None:
        raise ValueError(
            f"region(level=sido, region_code={sido_code})이 아직 없습니다 — "
            "load_regions --level sido를 먼저 실행하세요."
        )

    geom_32652 = region.geom.transform(32652, clone=True)
    minx, miny, maxx, maxy = geom_32652.extent
    minx, miny = minx - BUFFER_M, miny - BUFFER_M
    maxx, maxy = maxx + BUFFER_M, maxy + BUFFER_M

    minx = math.floor(minx / SNAP_M) * SNAP_M
    miny = math.floor(miny / SNAP_M) * SNAP_M
    maxx = math.ceil(maxx / SNAP_M) * SNAP_M
    maxy = math.ceil(maxy / SNAP_M) * SNAP_M

    grid = {
        "crs": "EPSG:32652",
        "resolution_m": RESOLUTION_M,
        "minx": minx,
        "miny": miny,
        "maxx": maxx,
        "maxy": maxy,
        "width": round((maxx - minx) / RESOLUTION_M),
        "height": round((maxy - miny) / RESOLUTION_M),
    }

    grid_box_32652 = GEOSPolygon.from_bbox((minx, miny, maxx, maxy))
    grid_box_32652.srid = 32652
    bbox_minx, bbox_miny, bbox_maxx, bbox_maxy = grid_box_32652.transform(4326, clone=True).extent

    area.bbox_minx, area.bbox_miny = bbox_minx, bbox_miny
    area.bbox_maxx, area.bbox_maxy = bbox_maxx, bbox_maxy
    area.grid = grid
    area.save(
        update_fields=["bbox_minx", "bbox_miny", "bbox_maxx", "bbox_maxy", "grid"]
    )


def discover_available_areas(path: Path) -> list[dict]:
    """AL_D001_00_*.zip(국가공간정보포털 전국 행정경계)의 SIG(시군구) 레이어에서 시도 코드별
    이름(A2 첫 단어)·시군구 수를 뽑는다. 실제 적재 없이 "추가 가능한 지역" 목록용."""
    import pyogrio

    from buildings.region_loading import resolve_vsi_path

    vsi_path = resolve_vsi_path(Path(path), "sigungu")
    gdf = pyogrio.read_dataframe(vsi_path, encoding="cp949")

    groups: dict[str, dict] = {}
    for _, row in gdf.iterrows():
        code = str(row["A1"]).strip()
        name_full = str(row["A2"]).strip()
        sido_code = code[:2]
        sido_name = name_full.split()[0] if name_full else sido_code
        entry = groups.setdefault(
            sido_code, {"sido_code": sido_code, "name": sido_name, "sigungu_count": 0}
        )
        entry["sigungu_count"] += 1

    return sorted(groups.values(), key=lambda g: g["sido_code"])


def resolve_al_d001_zip_path(explicit_path: str | Path | None = None) -> Path:
    """AL_D001_00_*.zip 경로를 고른다(생략하면 data/raw/에서 파일명 날짜가 가장 최신인
    것) — `areas add`·`areas available` 명령과 10단계 대화형 메뉴가 같이 쓴다."""
    if explicit_path:
        path = Path(explicit_path)
        if not path.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
        return path

    candidates = sorted(DATA_RAW_DIR.glob("AL_D001_00_*.zip"))
    if not candidates:
        raise FileNotFoundError(
            f"{DATA_RAW_DIR}에서 AL_D001_00_*.zip 파일을 찾지 못했습니다."
        )
    return candidates[-1]


def list_available_areas(explicit_path: str | Path | None = None) -> list[dict]:
    """discover_available_areas 결과에 이미 등록된 지역의 상태("사용 중"/"비활성"/"미등록")를
    더한다(다지역 지원 8단계) — `areas available` 명령과 10단계 대화형 메뉴가 같이 쓴다."""
    path = resolve_al_d001_zip_path(explicit_path)
    existing = {area.sido_code: area for area in ServiceArea.objects.all()}

    results = []
    for entry in discover_available_areas(path):
        area = existing.get(entry["sido_code"])
        if area is None:
            status = "미등록"
        elif area.enabled:
            status = "사용 중"
        else:
            status = "비활성"
        results.append({**entry, "status": status})
    return results
