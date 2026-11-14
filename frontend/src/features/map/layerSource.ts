import { resolveApiUrl } from '@/api/fetch';

import type { MapLayer } from './types';

const minZoomEpsilon = 0.0001;

export interface TileLayerOptions {
  url: string;
  attributions: string | null;
  minZoom?: number;
}

export function toOlMinZoom(minZoom: number | null): number | undefined {
  if (minZoom === null) return undefined;
  return minZoom - minZoomEpsilon;
}

export function isAboveMinZoom(currentZoom: number, minZoom: number | null): boolean {
  const olMinZoom = toOlMinZoom(minZoom);
  if (olMinZoom === undefined) return true;
  return currentZoom > olMinZoom;
}

type TiledMapLayer = Extract<MapLayer, { source_type: 'raster_tile' | 'vector_tile' }>;

export function toTileLayerOptions(layer: TiledMapLayer): TileLayerOptions {
  return {
    url: resolveApiUrl(layer.source_params.url),
    attributions: layer.attribution,
    minZoom: toOlMinZoom(layer.min_zoom),
  };
}
