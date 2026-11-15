import Feature from 'ol/Feature';
import type { GeoJSONGeometry } from 'ol/format/GeoJSON';
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import type Style from 'ol/style/Style';

import { geoJsonFormat } from './geoJsonFormat';

interface GeoJsonLayerOptions {
  zIndex?: number;
  style?: Style | Style[];
}

export class GeoJsonLayer extends VectorLayer {
  constructor(options: GeoJsonLayerOptions = {}) {
    super({
      source: new VectorSource(),
      zIndex: options.zIndex,
      style: options.style,
    });
  }

  setGeoJson(geometries: GeoJSONGeometry[]): void {
    const source = this.getSource();
    source?.clear();
    const features = geometries.flatMap((geometry) => {
      const readGeometry = geoJsonFormat.readGeometry(geometry, {
        dataProjection: 'EPSG:4326',
        featureProjection: 'EPSG:3857',
      });
      return readGeometry ? [new Feature({ geometry: readGeometry })] : [];
    });
    source?.addFeatures(features);
  }
}
