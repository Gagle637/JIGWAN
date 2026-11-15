import { useEffect } from 'react';
import type BaseLayer from 'ol/layer/Base';

import { useMapInstance } from './mapContext';

export function useOlLayer(layer: BaseLayer | BaseLayer[] | null): void {
  const map = useMapInstance();

  useEffect(() => {
    if (!map || !layer) return;

    const layers = Array.isArray(layer) ? layer : [layer];
    layers.forEach((item) => map.addLayer(item));

    return () => {
      layers.forEach((item) => map.removeLayer(item));
    };
  }, [map, layer]);
}
