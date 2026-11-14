import { useEffect } from 'react';

import MVT from 'ol/format/MVT';
import VectorTileLayer from 'ol/layer/VectorTile';
import VectorTileSource from 'ol/source/VectorTile';
import Fill from 'ol/style/Fill';
import Stroke from 'ol/style/Stroke';
import Style from 'ol/style/Style';

import { useLayersQuery } from '@/api/layers';
import type { MapLayer } from '@/api/types';
import { useMapViewStore } from '@/stores/mapViewStore';

import { isAboveMinZoom, toTileLayerOptions } from './layerSource';
import { useMapInstance } from './mapContext';
import { buildingZIndex } from './zIndex';

function selectBuildingFootprint(layers: MapLayer[]): MapLayer | undefined {
  return layers.find((layer) => layer.slug === 'building_footprint');
}

const buildingStyle = new Style({
  stroke: new Stroke({ color: '#1e293b', width: 1 }),
  fill: new Fill({ color: 'rgba(0, 0, 0, 0.01)' }),
});

export default function BuildingLayer() {
  const map = useMapInstance();
  const { data: layerDef } = useLayersQuery(selectBuildingFootprint);
  const zoom = useMapViewStore((state) => state.zoom);

  useEffect(() => {
    if (!map || !layerDef) return;

    const options = toTileLayerOptions(layerDef);
    const layer = new VectorTileLayer({
      source: new VectorTileSource({
        format: new MVT(),
        url: options.url,
        attributions: options.attributions ?? undefined,
        tileSize: 256, // OL 기본값(512)이면 백엔드 256px 타일 스킴과 어긋나 한 단계 낮은 z를 요청한다
      }),
      style: buildingStyle,
      zIndex: buildingZIndex,
      minZoom: options.minZoom,
    });
    map.addLayer(layer);

    return () => {
      map.removeLayer(layer);
    };
  }, [map, layerDef]);

  const visible = layerDef ? isAboveMinZoom(zoom, layerDef.min_zoom) : false;

  if (!layerDef || visible) return null;

  return (
    <div className="pointer-events-none absolute top-4 left-1/2 z-10 -translate-x-1/2 rounded-md bg-slate-900/80 px-3 py-1.5 text-sm text-white">
      확대하면 건물이 보입니다
    </div>
  );
}
