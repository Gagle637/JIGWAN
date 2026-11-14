import type { MapLayer } from '../../api/types'

export interface TileLayerOptions {
  url: string
  attributions: string | null
  /** OpenLayers 레이어 minZoom(exclusive) — 해당 없으면 undefined. */
  minZoom?: number
}

/**
 * 백엔드의 min_zoom(그 값 포함, "줌 14 이상에서 보인다")을 OpenLayers의 minZoom(그 값을
 * 포함하지 않는 exclusive 경계, "그 값보다 커야 보인다")으로 바꾼다. 그대로 넣으면 줌이
 * 정확히 min_zoom일 때 레이어가 안 보이므로 1을 빼 경계를 맞춘다.
 */
export function toOlMinZoom(backendMinZoom: number | null): number | undefined {
  if (backendMinZoom === null) return undefined
  return backendMinZoom - 1
}

/** MapCanvas의 줌 안내 문구가 레이어 실제 가시성과 같은 경계를 쓰도록 하는 판정 함수. */
export function isAboveMinZoom(currentZoom: number, backendMinZoom: number | null): boolean {
  const olMinZoom = toOlMinZoom(backendMinZoom)
  if (olMinZoom === undefined) return true
  return currentZoom > olMinZoom
}

function resolveUrl(rawUrl: string, apiBase: string): string {
  if (!rawUrl || rawUrl.startsWith('http')) return rawUrl
  return `${apiBase}${rawUrl}`
}

/** MapLayer(source_params.url이 있는 raster_tile·vector_tile 레이어) → OpenLayers 소스 옵션. */
export function toTileLayerOptions(layer: MapLayer, apiBase: string): TileLayerOptions {
  const rawUrl = typeof layer.source_params.url === 'string' ? layer.source_params.url : ''
  return {
    url: resolveUrl(rawUrl, apiBase),
    attributions: layer.attribution,
    minZoom: toOlMinZoom(layer.min_zoom),
  }
}
