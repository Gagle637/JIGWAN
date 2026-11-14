// backend/layers/models.py MapLayer.SourceType·Kind, backend/layers/registry.py serialize_layer
// 그대로 — 추측해서 적지 않았다.

export type MapLayerSourceType = 'vector_tile' | 'geojson' | 'titiler' | 'wms' | 'raster_tile'
export type MapLayerKind = 'background' | 'analysis'

export interface MapLayerRegion {
  region_code: string
  bbox: [number, number, number, number]
  tile_url: string
  season: string
  attribution: string | null
}

export interface MapLayer {
  id: number
  slug: string
  name: string
  group: string
  kind: MapLayerKind
  order: number
  source_type: MapLayerSourceType
  // regions는 COG 레이어(green_mask·before_after)만 채워지고, 나머지는 항상 빈 배열이다.
  source_params: Record<string, unknown> & { regions: MapLayerRegion[] }
  min_zoom: number | null
  max_zoom: number | null
  opacity: number
  default_visible: boolean
  legend: { no: number; label: string; color: string }[] | null
  notice: string | null
  attribution: string | null
  synced_at: string | null
}
