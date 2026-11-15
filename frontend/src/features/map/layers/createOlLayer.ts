import type BaseLayer from 'ol/layer/Base';
import type Style from 'ol/style/Style';

import { resolveApiUrl } from '@/api/fetch';

import type { MapLayer } from '../types';
import { MvtLayer } from './MvtLayer';
import { XyzLayer } from './XyzLayer';

export type DrawableMapLayer = Extract<MapLayer, { source_type: 'raster_tile' | 'vector_tile' }>;

export interface CreateOlLayerOptions {
  zIndex?: number;
  visibleFromZoom?: number | null;
  style?: Style;
}

export function createOlLayer(def: DrawableMapLayer, options: CreateOlLayerOptions = {}): BaseLayer {
  const attributions = def.attribution ?? undefined;

  switch (def.source_type) {
    case 'raster_tile':
      return new XyzLayer({
        url: resolveApiUrl(def.source_params.url),
        attributions,
        zIndex: options.zIndex,
      });
    case 'vector_tile':
      return new MvtLayer({
        url: resolveApiUrl(def.source_params.url),
        attributions,
        zIndex: options.zIndex,
        visibleFromZoom: options.visibleFromZoom,
        style: options.style,
      });
    default: {
      const exhaustiveCheck: never = def;
      throw new Error(`지원하지 않는 source_type입니다: ${exhaustiveCheck}`);
    }
  }
}
