import { createContext, useContext } from 'react';

import type Map from 'ol/Map';

export const mapContext = createContext<Map | null>(null);

export function useMapInstance(): Map | null {
  return useContext(mapContext);
}
