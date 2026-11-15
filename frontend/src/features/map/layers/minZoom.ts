const minZoomEpsilon = 0.0001;

export function toOlMinZoom(visibleFromZoom: number | null): number | undefined {
  if (visibleFromZoom === null) return undefined;
  return visibleFromZoom - minZoomEpsilon;
}

export function isAboveMinZoom(currentZoom: number, visibleFromZoom: number | null): boolean {
  const olMinZoom = toOlMinZoom(visibleFromZoom);
  if (olMinZoom === undefined) return true;
  return currentZoom > olMinZoom;
}
