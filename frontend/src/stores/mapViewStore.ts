import { create } from 'zustand'
import { fromLonLat } from 'ol/proj'

const DAEJEON_CENTER_4326: [number, number] = [127.385, 36.35]
const DEFAULT_ZOOM = 12

interface MapViewState {
  /** EPSG:3857 */
  center: [number, number]
  zoom: number
  setView: (center: [number, number], zoom: number) => void
}

export const useMapViewStore = create<MapViewState>((set) => ({
  center: fromLonLat(DAEJEON_CENTER_4326) as [number, number],
  zoom: DEFAULT_ZOOM,
  setView: (center, zoom) => set({ center, zoom }),
}))
