"""map_layer 레지스트리 조회·동기화(spec 10-2·10-5·11-5)."""
import logging

from django.utils import timezone

from core.areas import get_bbox

from .models import MapLayer
from .tile_params import GREEN_MASK_TILE_PARAMS, TRUECOLOR_TILE_PARAMS, build_titiler_url

logger = logging.getLogger(__name__)

COPERNICUS_NOTICE = "Contains modified Copernicus Sentinel data"

# map_layer.slug <-> satellite RasterProduct.product_type 대응(sync_cog_layer가 쓴다).
# name이 아니라 slug로 찾는 이유: name은 "(10m 해상도)" 같은 접미사가 붙어 바뀔 수 있다.
COG_LAYER_SLUGS = {
    "green_mask": "green_mask",
    "truecolor": "before_after",
}


def sync_cog_layer(product) -> bool:
    """catalog_publish가 새로 게시할 때 호출한다. source_params.regions는 지역 코드를 키로
    하는 dict로 관리하고(11-5), product.region_code의 period_start가 그 지역에 이미 기록된
    것보다 최신일 때만 그 지역 항목만 갱신한다 — 다른 지역 항목은 건드리지 않는다(결정
    사항 8을 지역별로 적용)."""
    layer_slug = COG_LAYER_SLUGS.get(product.product_type)
    if layer_slug is None:
        return False

    layer = MapLayer.objects.filter(slug=layer_slug).first()
    if layer is None:
        return False

    region_code = product.region_code
    source_params = dict(layer.source_params or {})
    regions = dict(source_params.get("regions") or {})
    existing = regions.get(region_code)

    # product.period_start는 DB에서 막 읽어온 행이면 date, 아직 저장만 하고 재조회 안 한
    # 메모리 상의 인스턴스면 그 str 그대로다 — Model.save()가 입력값을 date로 되돌려
    # 바꿔주지 않는다.
    new_period_start = product.period_start
    if hasattr(new_period_start, "isoformat"):
        new_period_start = new_period_start.isoformat()
    if existing and existing.get("period_start") and existing["period_start"] >= new_period_start:
        return False

    tile_params = (
        TRUECOLOR_TILE_PARAMS if product.product_type == "truecolor" else GREEN_MASK_TILE_PARAMS
    )
    regions[region_code] = {
        "region_code": region_code,
        "bbox": list(get_bbox(region_code)),
        "tile_url": build_titiler_url(product.cog_path, tile_params),
        "season": f"{product.year}-{product.season}",
        "period_start": new_period_start,
        # 사용자 결정: Copernicus 고지는 연도가 문구의 일부라 각 지역 항목에 연도를 넣는다.
        "attribution": f"{COPERNICUS_NOTICE} {product.year}",
    }
    source_params["regions"] = regions
    layer.source_params = source_params
    layer.synced_at = timezone.now()
    layer.save(update_fields=["source_params", "synced_at"])
    logger.info(
        "map_layer sync slug=%s region=%s period_start=%s", layer_slug, region_code, new_period_start
    )
    return True


def _region_list(layer: MapLayer) -> list[dict]:
    """source_params.regions(내부 dict, region_code 키)를 응답용 리스트로 바꾼다.
    period_start는 sync_cog_layer 내부 갱신 판단용이라 응답엔 안 뺀다."""
    regions = (layer.source_params or {}).get("regions") or {}
    return [
        {
            "region_code": entry["region_code"],
            "bbox": entry["bbox"],
            "tile_url": entry["tile_url"],
            "season": entry["season"],
            "attribution": entry["attribution"],
        }
        for entry in sorted(regions.values(), key=lambda r: r["region_code"])
    ]


def _layer_attribution(layer: MapLayer, regions: list[dict]) -> str | None:
    """녹지 마스크·Before/After는 현재 regions에 들어있는 계절들의 연도 범위로 레이어
    전체 attribution을 계산한다(예: "...Sentinel data 2025–2026", 연도가 하나면 그대로).
    regions가 비어 있거나(아직 게시된 게 없음) 해당 레이어가 아니면 저장된 값을 그대로 쓴다."""
    if layer.slug not in COG_LAYER_SLUGS.values() or not regions:
        return layer.attribution
    years = sorted({int(entry["season"].split("-")[0]) for entry in regions})
    if years[0] == years[-1]:
        return f"{COPERNICUS_NOTICE} {years[0]}"
    return f"{COPERNICUS_NOTICE} {years[0]}–{years[-1]}"


def serialize_layer(layer: MapLayer) -> dict:
    regions = _region_list(layer)
    source_params = dict(layer.source_params or {})
    # 모든 레이어가 같은 모양을 갖게 regions는 항상 내려준다(해당 없으면 빈 리스트).
    source_params["regions"] = regions

    return {
        "id": layer.id,
        "slug": layer.slug,
        "name": layer.name,
        "group": layer.group,
        "kind": layer.kind,
        "order": layer.order,
        "source_type": layer.source_type,
        "source_params": source_params,
        "min_zoom": layer.min_zoom,
        "max_zoom": layer.max_zoom,
        "opacity": layer.opacity,
        "default_visible": layer.default_visible,
        "legend": layer.legend,
        "notice": layer.notice,
        "attribution": _layer_attribution(layer, regions),
        "synced_at": layer.synced_at.isoformat() if layer.synced_at else None,
    }
