import { useMemo } from 'react';

import { createOlLayer } from '@/features/map/layers/createOlLayer';
import { buildingStyle } from '@/features/map/layers/mapStyle';
import { buildingZIndex } from '@/features/map/layers/zIndex';
import { layerSlugs } from '@/features/map/layerSlugs';
import { useLayersQuery } from '@/features/map/queries';
import { useOlLayer } from '@/features/map/useOlLayer';
import type { MapLayer } from '@/types/layer';

function isBuildingFootprintLayer(
  layer: MapLayer,
): layer is Extract<MapLayer, { source_type: 'vector_tile' }> {
  return layer.slug === layerSlugs.buildingFootprint && layer.source_type === 'vector_tile';
}

function selectBuildingFootprint(layers: MapLayer[]) {
  return layers.find(isBuildingFootprintLayer);
}

export function BuildingLayer() {
  const { data: layerDef } = useLayersQuery(selectBuildingFootprint);

  const olLayer = useMemo(
    () =>
      layerDef
        ? createOlLayer(layerDef, {
            zIndex: buildingZIndex,
            visibleFromZoom: layerDef.min_zoom,
            style: buildingStyle,
          })
        : null,
    [layerDef],
  );

  useOlLayer(olLayer);

  return null;
}
