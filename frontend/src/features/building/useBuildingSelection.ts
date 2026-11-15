import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { create } from 'zustand';

interface SelectionOriginState {
  wasSelectedByClick: boolean;
  setWasSelectedByClick: (value: boolean) => void;
}

const useSelectionOriginStore = create<SelectionOriginState>((set) => ({
  wasSelectedByClick: false,
  setWasSelectedByClick: (value) => set({ wasSelectedByClick: value }),
}));

export type Radius = 500 | 1000;

function parseRadius(value: string | null): Radius {
  return value === '1000' ? 1000 : 500;
}

export function useBuildingSelection() {
  const [searchParams, setSearchParams] = useSearchParams();
  const wasSelectedByClick = useSelectionOriginStore((state) => state.wasSelectedByClick);
  const setWasSelectedByClick = useSelectionOriginStore((state) => state.setWasSelectedByClick);

  const rawBuildingId = searchParams.get('b');
  const buildingId = rawBuildingId ? Number(rawBuildingId) : null;
  const radius = parseRadius(searchParams.get('r'));

  const selectFromMapClick = useCallback(
    (id: number) => {
      setWasSelectedByClick(true);
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set('b', String(id));
        return next;
      });
    },
    [setSearchParams, setWasSelectedByClick],
  );

  const select = useCallback(
    (id: number) => {
      setWasSelectedByClick(false);
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set('b', String(id));
        return next;
      });
    },
    [setSearchParams, setWasSelectedByClick],
  );

  const setRadius = useCallback(
    (nextRadius: Radius) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set('r', String(nextRadius));
        return next;
      });
    },
    [setSearchParams],
  );

  const clear = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete('b');
      return next;
    });
  }, [setSearchParams]);

  return { buildingId, radius, wasSelectedByClick, selectFromMapClick, select, setRadius, clear };
}
