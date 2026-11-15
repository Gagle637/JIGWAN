import { useEffect } from 'react';
import type MapBrowserEvent from 'ol/MapBrowserEvent';

import { useBuildingSelection } from '@/features/building/useBuildingSelection';
import { layerSlugs } from '@/features/map/layerSlugs';
import { useMapInstance } from '@/features/map/mapContext';

export function BuildingClickHandler() {
  const map = useMapInstance();
  const { selectFromMapClick } = useBuildingSelection();

  useEffect(() => {
    if (!map) return;

    const handleClick = (event: MapBrowserEvent) => {
      const feature = map.forEachFeatureAtPixel(event.pixel, (found) => found, {
        layerFilter: (layer) => layer.get('slug') === layerSlugs.buildingFootprint,
      });
      const id = feature?.get('id');
      if (typeof id === 'number') {
        selectFromMapClick(id);
      }
    };

    map.on('singleclick', handleClick);
    return () => {
      map.un('singleclick', handleClick);
    };
  }, [map, selectFromMapClick]);

  return null;
}
