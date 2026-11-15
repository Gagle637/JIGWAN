import { queryOptions, useQuery } from '@tanstack/react-query';

import { apiFetch } from '@/api/fetch';
import type { Insight } from '@/types/insight';

import type { Radius } from './useBuildingSelection';

export function insightQueryOptions(buildingId: number, radius: Radius) {
  return queryOptions({
    queryKey: ['insight', buildingId, radius] as const,
    queryFn: ({ signal }) =>
      apiFetch<Insight>(`/api/buildings/${buildingId}/insight`, { params: { radius }, signal }),
    staleTime: 5 * 60 * 1000,
  });
}

export function useInsightQuery(buildingId: number | null, radius: Radius) {
  return useQuery({
    ...insightQueryOptions(buildingId ?? 0, radius),
    enabled: buildingId !== null,
    placeholderData: (previousData, previousQuery) => {
      const previousBuildingId = previousQuery?.queryKey[1];
      return previousBuildingId === buildingId ? previousData : undefined;
    },
  });
}
