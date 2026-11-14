import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { apiFetch } from './client'
import type { MapLayer } from './types'

export const layersQueryKey = ['layers'] as const

export function fetchLayers(): Promise<MapLayer[]> {
  return apiFetch<MapLayer[]>('/api/layers')
}

/**
 * 전체 레이어 목록을 하나의 쿼리로 캐시한다(레이어 패널 등 다른 화면도 같은 쿼리를 쓴다).
 * 배경 레이어만 고르는 것처럼 화면별로 다른 가공이 필요하면 select로 한다.
 */
export function useLayersQuery<T = MapLayer[]>(
  select?: (layers: MapLayer[]) => T,
): UseQueryResult<T> {
  return useQuery({
    queryKey: layersQueryKey,
    queryFn: fetchLayers,
    staleTime: 30 * 60 * 1000,
    select,
  })
}
