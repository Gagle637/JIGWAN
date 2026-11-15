import Fill from 'ol/style/Fill';
import Stroke from 'ol/style/Stroke';
import Style from 'ol/style/Style';

export const buildingStyle = new Style({
  stroke: new Stroke({ color: '#1e293b', width: 1 }),
  fill: new Fill({ color: 'rgba(0, 0, 0, 0.01)' }),
});

export const buildingHighlightStyle = new Style({
  stroke: new Stroke({ color: '#0f172a', width: 3 }),
  fill: new Fill({ color: 'rgba(15, 23, 42, 0.15)' }),
});

export const radiusStyle = new Style({
  stroke: new Stroke({ color: '#0f172a', width: 1.5, lineDash: [6, 4] }),
});

export const changeAreaStyle = new Style({
  stroke: new Stroke({ color: '#b45309', width: 1 }),
  fill: new Fill({ color: 'rgba(217, 119, 6, 0.25)' }),
});
