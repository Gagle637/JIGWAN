export type MapLayerKind = 'background' | 'analysis';

export interface MapLayerRegion {
  region_code: string;
  bbox: [number, number, number, number];
  tile_url: string;
  season: string;
  attribution: string | null;
}

export interface MapLayerLegendItem {
  no: number;
  label: string;
  color: string;
}

interface MapLayerBase {
  id: number;
  slug: string;
  name: string;
  group: string;
  kind: MapLayerKind;
  order: number;
  min_zoom: number | null;
  max_zoom: number | null;
  opacity: number;
  default_visible: boolean;
  legend: MapLayerLegendItem[] | null;
  notice: string | null;
  attribution: string | null;
  synced_at: string | null;
}

interface RasterTileLayer extends MapLayerBase {
  source_type: 'raster_tile';
  source_params: { url: string; regions: MapLayerRegion[] };
}

interface VectorTileLayer extends MapLayerBase {
  source_type: 'vector_tile';
  source_params: { url: string; regions: MapLayerRegion[] };
}

interface GeoJsonLayer extends MapLayerBase {
  source_type: 'geojson';
  source_params: { url?: string; regions: MapLayerRegion[] };
}

interface TitilerLayer extends MapLayerBase {
  source_type: 'titiler';
  source_params: { regions: MapLayerRegion[] };
}

interface WmsLayer extends MapLayerBase {
  source_type: 'wms';
  source_params: {
    service_url: string;
    layers: string;
    styles: string;
    version: string;
    srs: string;
    format: string;
    transparent: boolean;
    regions: MapLayerRegion[];
  };
}

export type MapLayer = RasterTileLayer | VectorTileLayer | GeoJsonLayer | TitilerLayer | WmsLayer;
