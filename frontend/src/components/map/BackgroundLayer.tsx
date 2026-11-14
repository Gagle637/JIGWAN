import { useEffect } from 'react';

import TileLayer from 'ol/layer/Tile';
import XYZ from 'ol/source/XYZ';

import { useLayersQuery } from '@/api/layers';
import type { MapLayer } from '@/api/types';

import { toTileLayerOptions } from './layerSource';
import { useMapInstance } from './mapContext';
import { backgroundZIndexBase } from './zIndex';

function selectBackgroundRasterLayers(layers: MapLayer[]): MapLayer[] {
  return layers
    .filter((layer) => layer.kind === 'background' && layer.source_type === 'raster_tile')
    .sort((a, b) => a.order - b.order);
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
