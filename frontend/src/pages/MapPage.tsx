import { ErrorState } from '@/components/ui/ErrorState';
import { BuildingClickHandler } from '@/features/building/components/BuildingClickHandler';
import { BuildingHighlightLayer } from '@/features/building/components/BuildingHighlightLayer';
import { BuildingPanel } from '@/features/building/components/BuildingPanel/BuildingPanel';
import { ChangeAreasLayer } from '@/features/building/components/ChangeAreasLayer';
import { MapPanOnSelection } from '@/features/building/components/MapPanOnSelection';
import { RadiusLayer } from '@/features/building/components/RadiusLayer';
import { BackgroundLayer } from '@/features/map/components/BackgroundLayer';
import { BuildingLayer } from '@/features/map/components/BuildingLayer';
import { BuildingZoomHint } from '@/features/map/components/BuildingZoomHint';
import { MapProvider } from '@/features/map/components/MapProvider';
import { useLayersQuery } from '@/features/map/queries';

export function MapPage() {
  const { isError, refetch } = useLayersQuery();

  return (
    <MapProvider>
      <BackgroundLayer />
      <BuildingLayer />
      <BuildingZoomHint />
      <BuildingClickHandler />
      <BuildingHighlightLayer />
      <RadiusLayer />
      <ChangeAreasLayer />
      <MapPanOnSelection />
      <BuildingPanel />
      {isError && (
        <ErrorState
          className="absolute inset-0 z-20 bg-surface/90"
          message="지도 레이어를 불러올 수 없습니다."
          onRetry={() => refetch()}
        />
      )}
    </MapProvider>
  );
}
