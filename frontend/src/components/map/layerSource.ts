import { resolveApiUrl } from '@/api/fetch'
import type { MapLayer } from '@/api/types'

export interface TileLayerOptions {
  url: string
  attributions: string | null
}

export function isAboveMinZoom(currentZoom: number, minZoom: number | null): boolean {
  if (minZoom === null) return true
  return currentZoom >= minZoom
}

export function toTileLayerOptions(layer: MapLayer): TileLayerOptions {
  const rawUrl = typeof layer.source_params.url === 'string' ? layer.source_params.url : ''
  return {
    url: resolveApiUrl(rawUrl),
    attributions: layer.attribution,
  }
}
