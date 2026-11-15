import { useEffect, useRef, useState, type ReactNode } from 'react';

import Attribution from 'ol/control/Attribution';
import { defaults as defaultControls } from 'ol/control/defaults';
import Map from 'ol/Map';
import View from 'ol/View';

import { mapContext } from '@/features/map/mapContext';
import { useMapViewStore } from '@/features/map/store';

import 'ol/ol.css';

interface MapProviderProps {
  children: ReactNode;
}

export function MapProvider({ children }: MapProviderProps) {
  const targetRef = useRef<HTMLDivElement | null>(null);
  const [map, setMap] = useState<Map | null>(null);

  useEffect(() => {
    if (!targetRef.current) return;

    const { center, zoom, setView } = useMapViewStore.getState();
    const instance = new Map({
      target: targetRef.current,
      view: new View({ center, zoom }),
      controls: defaultControls({ attribution: false }).extend([
        new Attribution({ collapsible: false }),
      ]),
    });

    instance.on('moveend', () => {
      const view = instance.getView();
      const nextCenter = view.getCenter();
      const nextZoom = view.getZoom();
      if (nextCenter && nextZoom !== undefined) {
        setView(nextCenter, nextZoom);
      }
    });

    setMap(instance);

    return () => {
      instance.setTarget(undefined);
      setMap(null);
    };
  }, []);

  return (
    <div className="relative h-full w-full">
      <div ref={targetRef} className="h-full w-full" />
      <mapContext.Provider value={map}>{children}</mapContext.Provider>
    </div>
  );
}
