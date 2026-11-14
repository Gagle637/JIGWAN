import { useLayersQuery } from '@/api/layers'
import MapProvider from './MapProvider'
import BackgroundLayer from './BackgroundLayer'
import BuildingLayer from './BuildingLayer'

export default function MapCanvas() {
  const { isError, refetch } = useLayersQuery()

  if (isError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-slate-500">
        <p>지도 레이어를 불러올 수 없습니다.</p>
        <button
          type="button"
          onClick={() => refetch()}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white"
        >
          다시 시도
        </button>
      </div>
    )
  }

  return (
    <MapProvider>
      <BackgroundLayer />
      <BuildingLayer />
    </MapProvider>
  )
}
