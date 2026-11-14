import { useEffect } from 'react';

import TileLayer from 'ol/layer/Tile';
import XYZ from 'ol/source/XYZ';

import { toTileLayerOptions } from '@/features/map/layerSource';
import { useLayersQuery } from '@/features/map/queries';
import type { MapLayer } from '@/features/map/types';
import { backgroundZIndexBase } from '@/features/map/zIndex';

import { useMapInstance } from './mapContext';

function isBackgroundRasterLayer(
  layer: MapLayer,
): layer is Extract<MapLayer, { source_type: 'raster_tile' }> {
  return layer.kind === 'background' && layer.source_type === 'raster_tile';
}

function selectBackgroundRasterLayers(layers: MapLayer[]) {
  return layers.filter(isBackgroundRasterLayer).sort((a, b) => a.order - b.order);
}

export function BackgroundLayer() {
  const map = useMapInstance();
  const { data: layerDefs } = useLayersQuery(selectBackgroundRasterLayers);

  useEffect(() => {
    if (!map || !layerDefs) return;

    const olLayers = layerDefs.map((layerDef) => {
      const options = toTileLayerOptions(layerDef);
      return new TileLayer({
        source: new XYZ({ url: options.url, attributions: options.attributions ?? undefined }),
        zIndex: backgroundZIndexBase + layerDef.order,
      });
    });

    olLayers.forEach((layer) => map.addLayer(layer));
    return () => {
      olLayers.forEach((layer) => map.removeLayer(layer));
    };
  }, [map, layerDefs]);

  return null;
}
