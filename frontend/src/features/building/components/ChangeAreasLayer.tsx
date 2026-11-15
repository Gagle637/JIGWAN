import { useInsightQuery } from '@/features/building/queries';
import { useBuildingSelection } from '@/features/building/useBuildingSelection';
import { changeAreaStyle } from '@/features/map/layers/mapStyle';
import { selectionZIndexBase } from '@/features/map/layers/zIndex';
import { useGeoJsonLayer } from '@/features/map/useGeoJsonLayer';

export function ChangeAreasLayer() {
  const { buildingId, radius } = useBuildingSelection();
  const { data: insight } = useInsightQuery(buildingId, radius);

  const geometries = insight?.change?.areas.map((area) => area.geometry) ?? null;

  useGeoJsonLayer(geometries, {
    zIndex: selectionZIndexBase + 2,
    style: changeAreaStyle,
  });

  return null;
}
