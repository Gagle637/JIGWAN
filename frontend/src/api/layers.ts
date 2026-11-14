import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { apiFetch } from '@/api/fetch';
import type { MapLayer } from '@/api/types';

export const layersQueryKey = ['layers'] as const;

export function fetchLayers(): Promise<MapLayer[]> {
  return apiFetch<MapLayer[]>('/api/layers');
}

export function useLayersQuery<T = MapLayer[]>(
  select?: (layers: MapLayer[]) => T,
): UseQueryResult<T> {
  return useQuery({
    queryKey: layersQueryKey,
    queryFn: fetchLayers,
    staleTime: 30 * 60 * 1000,
    select,
  });
}
