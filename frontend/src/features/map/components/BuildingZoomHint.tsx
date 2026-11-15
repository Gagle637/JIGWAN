import { isAboveMinZoom } from '@/features/map/layers/minZoom';
import { layerSlugs } from '@/features/map/layerSlugs';
import { useLayersQuery } from '@/features/map/queries';
import { useMapViewStore } from '@/features/map/store';
import type { MapLayer } from '@/features/map/types';

function selectBuildingFootprint(layers: MapLayer[]) {
  return layers.find((layer) => layer.slug === layerSlugs.buildingFootprint);
}

export function BuildingZoomHint() {
  const { data: layerDef } = useLayersQuery(selectBuildingFootprint);
  const zoom = useMapViewStore((state) => state.zoom);

  if (!layerDef || isAboveMinZoom(zoom, layerDef.min_zoom)) return null;

  return (
    <div className="pointer-events-none absolute top-4 left-1/2 z-10 -translate-x-1/2 rounded-md bg-primary/80 px-3 py-1.5 text-sm text-primary-foreground">
      확대하면 건물이 보입니다
    </div>
  );
}
