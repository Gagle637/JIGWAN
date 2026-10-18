"""map_layer 레지스트리 조회·동기화(spec 10-2)."""
import logging

from django.utils import timezone

from .models import MapLayer
from .tile_params import GREEN_MASK_TILE_PARAMS, TRUECOLOR_TILE_PARAMS, build_titiler_url

logger = logging.getLogger(__name__)

# map_layer.name <-> satellite RasterProduct.product_type 대응(sync_cog_layer가 쓴다)
COG_LAYER_NAMES = {
    "green_mask": "녹지 마스크",
    "truecolor": "Before/After 위성 영상",
}


def sync_cog_layer(product) -> bool:
    """catalog_publish가 새로 게시할 때 호출한다. product.period_start가 레이어에 이미
    기록된 것보다 최신일 때만 source_params.cog_path를 갱신한다(결정 사항 8 — 과거 계절
    백필이 지도 레이어를 옛날 결과로 되돌리지 않게)."""
    layer_name = COG_LAYER_NAMES.get(product.product_type)
    if layer_name is None:
        return False

    layer = MapLayer.objects.filter(name=layer_name).first()
    if layer is None:
        return False

    current_period_start = (layer.source_params or {}).get("period_start")
    # product.period_start는 DB에서 막 읽어온 행이면 date, 아직 저장만 하고 재조회 안 한
    # 메모리 상의 인스턴스(예: RasterProduct.objects.create(period_start="2026-06-01", ...)
    # 직후)면 그 str 그대로다 — Model.save()가 입력값을 date로 되돌려 바꿔주지 않는다.
    new_period_start = product.period_start
    if hasattr(new_period_start, "isoformat"):
        new_period_start = new_period_start.isoformat()
    if current_period_start and current_period_start >= new_period_start:
        return False

    tile_params = (
        TRUECOLOR_TILE_PARAMS if product.product_type == "truecolor" else GREEN_MASK_TILE_PARAMS
    )
    layer.source_params = {
        **(layer.source_params or {}),
        "cog_path": product.cog_path,
        "period_start": new_period_start,
        "tile_url": build_titiler_url(product.cog_path, tile_params),
    }
    layer.synced_at = timezone.now()
    layer.save(update_fields=["source_params", "synced_at"])
    logger.info("map_layer sync name=%s period_start=%s", layer_name, new_period_start)
    return True


def serialize_layer(layer: MapLayer) -> dict:
    return {
        "id": layer.id,
        "name": layer.name,
        "group": layer.group,
        "order": layer.order,
        "source_type": layer.source_type,
        "source_params": layer.source_params,
        "min_zoom": layer.min_zoom,
        "max_zoom": layer.max_zoom,
        "opacity": layer.opacity,
        "default_visible": layer.default_visible,
        "legend": layer.legend,
        "notice": layer.notice,
        "attribution": layer.attribution,
        "synced_at": layer.synced_at.isoformat() if layer.synced_at else None,
    }
