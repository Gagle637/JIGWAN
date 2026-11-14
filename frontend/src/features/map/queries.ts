import { queryOptions, useQuery, type UseQueryResult } from '@tanstack/react-query';

import { apiFetch } from '@/api/fetch';

import type { MapLayer } from './types';

export function layersQueryOptions() {
  return queryOptions({
    queryKey: ['layers'],
    queryFn: ({ signal }) => apiFetch<MapLayer[]>('/api/layers', { signal }),
    staleTime: 30 * 60 * 1000,
  });
}

export function useLayersQuery<T = MapLayer[]>(
  select?: (layers: MapLayer[]) => T,
): UseQueryResult<T> {
  return useQuery({ ...layersQueryOptions(), select });
}
