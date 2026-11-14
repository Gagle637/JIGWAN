import { ErrorState } from '@/components/ui/ErrorState';
import { useLayersQuery } from '@/features/map/queries';

import { BackgroundLayer } from './BackgroundLayer';
import { BuildingLayer } from './BuildingLayer';
import { MapProvider } from './MapProvider';

export function MapCanvas() {
  const { isError, refetch } = useLayersQuery();

  if (isError) {
    return <ErrorState message="지도 레이어를 불러올 수 없습니다." onRetry={() => refetch()} />;
  }

  return (
    <MapProvider>
      <BackgroundLayer />
      <BuildingLayer />
    </MapProvider>
  );
}
