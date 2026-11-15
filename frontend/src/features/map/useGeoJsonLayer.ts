import { useEffect, useMemo } from 'react';
import type { GeoJSONGeometry } from 'ol/format/GeoJSON';
import type Style from 'ol/style/Style';

import { GeoJsonLayer } from './layers/GeoJsonLayer';
import { useOlLayer } from './useOlLayer';

interface UseGeoJsonLayerOptions {
  zIndex?: number;
  style?: Style | Style[];
}

export function useGeoJsonLayer(
  geometries: GeoJSONGeometry[] | null,
  options: UseGeoJsonLayerOptions = {},
): void {
  const { zIndex, style } = options;
  const layer = useMemo(() => new GeoJsonLayer({ zIndex, style }), [zIndex, style]);
  useOlLayer(layer);

  useEffect(() => {
    layer.setGeoJson(geometries ?? []);
  }, [layer, geometries]);
}
