import Fill from 'ol/style/Fill';
import Stroke from 'ol/style/Stroke';
import Style from 'ol/style/Style';

export const buildingStyle = new Style({
  stroke: new Stroke({ color: '#1e293b', width: 1 }),
  fill: new Fill({ color: 'rgba(0, 0, 0, 0.01)' }),
});
