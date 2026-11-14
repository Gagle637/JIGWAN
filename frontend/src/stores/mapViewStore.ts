import type { Coordinate } from 'ol/coordinate';
import { fromLonLat } from 'ol/proj';
import { create } from 'zustand';

const daejeonCenter: Coordinate = [127.385, 36.35];
const defaultZoom = 12;

interface MapViewState {
  center: Coordinate;
  zoom: number;
  setView: (center: Coordinate, zoom: number) => void;
}

export const useMapViewStore = create<MapViewState>((set) => ({
  center: fromLonLat(daejeonCenter),
  zoom: defaultZoom,
  setView: (center, zoom) => set({ center, zoom }),
}));
