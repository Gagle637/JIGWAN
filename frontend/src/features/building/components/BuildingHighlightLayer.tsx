import { useInsightQuery } from '@/features/building/queries';
import { useBuildingSelection } from '@/features/building/useBuildingSelection';
import { buildingHighlightStyle } from '@/features/map/layers/mapStyle';
import { selectionZIndexBase } from '@/features/map/layers/zIndex';
import { useGeoJsonLayer } from '@/features/map/useGeoJsonLayer';

export function BuildingHighlightLayer() {
  const { buildingId, radius } = useBuildingSelection();
  const { data: insight } = useInsightQuery(buildingId, radius);

  useGeoJsonLayer(insight ? [insight.building.geometry] : null, {
    zIndex: selectionZIndexBase,
    style: buildingHighlightStyle,
  });

  return null;
}
