import { useInsightQuery } from '@/features/building/queries';
import { useBuildingSelection } from '@/features/building/useBuildingSelection';
import { radiusStyle } from '@/features/map/layers/mapStyle';
import { selectionZIndexBase } from '@/features/map/layers/zIndex';
import { useGeoJsonLayer } from '@/features/map/useGeoJsonLayer';

export function RadiusLayer() {
  const { buildingId, radius } = useBuildingSelection();
  const { data: insight } = useInsightQuery(buildingId, radius);

  useGeoJsonLayer(insight ? [insight.radius_geometry] : null, {
    zIndex: selectionZIndexBase + 1,
    style: radiusStyle,
  });

  return null;
}
