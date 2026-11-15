import { useEffect, useRef } from 'react';

import { useInsightQuery } from '@/features/building/queries';
import { useBuildingSelection } from '@/features/building/useBuildingSelection';
import { geoJsonFormat } from '@/features/map/layers/geoJsonFormat';
import { useMapInstance } from '@/features/map/mapContext';

const panPadding = [40, 40, 40, 40];
const panMaxZoom = 17;

export function MapPanOnSelection() {
  const map = useMapInstance();
  const { buildingId, radius, wasSelectedByClick } = useBuildingSelection();
  const { data: insight } = useInsightQuery(buildingId, radius);
  const pannedBuildingIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (buildingId === null) {
      pannedBuildingIdRef.current = null;
    }
  }, [buildingId]);

  useEffect(() => {
    if (!map || !insight || buildingId === null) return;
    if (pannedBuildingIdRef.current === buildingId) return;
    pannedBuildingIdRef.current = buildingId;
    if (wasSelectedByClick) return;

    const geometry = geoJsonFormat.readGeometry(insight.radius_geometry, {
      dataProjection: 'EPSG:4326',
      featureProjection: 'EPSG:3857',
    });
    if (!geometry) return;
    map.getView().fit(geometry.getExtent(), {
      padding: panPadding,
      maxZoom: panMaxZoom,
      duration: 300,
    });
  }, [map, insight, buildingId, wasSelectedByClick]);

  return null;
}
