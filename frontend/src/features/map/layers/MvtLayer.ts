import MVT from 'ol/format/MVT';
import VectorTileLayer from 'ol/layer/VectorTile';
import VectorTileSource from 'ol/source/VectorTile';
import type Style from 'ol/style/Style';

import { toOlMinZoom } from './minZoom';

interface MvtLayerOptions {
  url: string;
  attributions?: string;
  zIndex?: number;
  visibleFromZoom?: number | null;
  style?: Style;
}

export class MvtLayer extends VectorTileLayer {
  constructor({ url, attributions, zIndex, visibleFromZoom = null, style }: MvtLayerOptions) {
    super({
      source: new VectorTileSource({
        format: new MVT(),
        url,
        attributions,
        tileSize: 256, // OL 기본값(512)이면 백엔드 256px 타일 스킴과 어긋난다
      }),
      style,
      zIndex,
      minZoom: toOlMinZoom(visibleFromZoom),
    });
  }
}
