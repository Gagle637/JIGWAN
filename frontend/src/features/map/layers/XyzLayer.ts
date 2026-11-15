import TileLayer from 'ol/layer/Tile';
import XYZ from 'ol/source/XYZ';

interface XyzLayerOptions {
  url: string;
  attributions?: string;
  zIndex?: number;
  slug: string;
}

export class XyzLayer extends TileLayer {
  constructor({ url, attributions, zIndex, slug }: XyzLayerOptions) {
    super({
      source: new XYZ({ url, attributions }),
      zIndex,
      properties: { slug },
    });
  }
}
