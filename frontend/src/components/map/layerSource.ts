import { resolveApiUrl } from '@/api/fetch';
import type { MapLayer } from '@/api/types';

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

export function toTileLayerOptions(layer: MapLayer): TileLayerOptions {
  const rawUrl = typeof layer.source_params.url === 'string' ? layer.source_params.url : '';
  return {
    url: resolveApiUrl(rawUrl),
    attributions: layer.attribution,
    minZoom: toOlMinZoom(layer.min_zoom),
  };
}
