import { fromLonLat } from 'ol/proj';
import { create } from 'zustand';

const daejeonCenter: [number, number] = [127.385, 36.35];
const defaultZoom = 12;

interface MapViewState {
  center: [number, number]
  zoom: number
  setView: (center: [number, number], zoom: number) => void
}

export const useMapViewStore = create<MapViewState>((set) => ({
  center: fromLonLat(daejeonCenter) as [number, number],
  zoom: defaultZoom,
  setView: (center, zoom) => set({ center, zoom }),
}));
