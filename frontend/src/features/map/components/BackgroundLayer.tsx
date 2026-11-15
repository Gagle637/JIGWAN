import { useMemo } from 'react';

import { createOlLayer } from '@/features/map/layers/createOlLayer';
import { backgroundZIndexBase } from '@/features/map/layers/zIndex';
import { useLayersQuery } from '@/features/map/queries';
import type { MapLayer } from '@/features/map/types';
import { useOlLayer } from '@/features/map/useOlLayer';

function isBackgroundRasterLayer(
  layer: MapLayer,
): layer is Extract<MapLayer, { source_type: 'raster_tile' }> {
  return layer.kind === 'background' && layer.source_type === 'raster_tile';
}

function selectBackgroundRasterLayers(layers: MapLayer[]) {
  return layers.filter(isBackgroundRasterLayer).sort((a, b) => a.order - b.order);
}

export function BackgroundLayer() {
  const { data: layerDefs } = useLayersQuery(selectBackgroundRasterLayers);

  const olLayers = useMemo(
    () =>
      layerDefs?.map((def) =>
        createOlLayer(def, { zIndex: backgroundZIndexBase + def.order })) ?? null,
    [layerDefs],
  );

  useOlLayer(olLayers);

  return null;
}
