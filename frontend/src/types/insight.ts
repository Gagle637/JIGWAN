import type { Polygon } from 'geojson';

export type InsightStatus = 'ready' | 'partial' | 'pending';

export interface InsightMissingEntry {
  field: string;
  reason: string;
}

export interface InsightBuilding {
  id: number;
  pnu: string;
  name: string | null;
  address: string | null;
  use_type: string | null;
  geometry: Polygon;
}

export interface InsightAsOf {
  satellite_period: string | null;
  trade_synced_at: string | null;
  register_synced_at: string | null;
  crime_data_period: string | null;
}

export interface InsightSpec {
  use: string | null;
  land_area_m2: number | null;
  total_floor_area_m2: number | null;
  bcr_pct: number | null;
  far_pct: number | null;
  approval_date: string | null;
  age_years: number | null;
}

export interface InsightGreenSeriesItem {
  year: number;
  season: 'spring' | 'summer' | 'fall' | 'winter';
  ratio_pct: number | null;
  coverage_pct: number;
}

export interface InsightGreen {
  ratio_pct: number | null;
  region_avg_pct: number | null;
  diff_pp: number | null;
  coverage_pct: number;
  series: InsightGreenSeriesItem[];
}

export interface InsightChangeArea {
  id: number;
  area_m2: number;
  distance_m: number;
  period: '1y' | '2y' | '3y';
  geometry: Polygon;
}

export interface InsightChangeTiles {
  after: string | null;
  before: Partial<Record<'1y' | '2y' | '3y', string>>;
  default_compare: '1y' | '2y' | '3y' | null;
}

export interface InsightChange {
  total_area_m2: number;
  areas: InsightChangeArea[];
  tiles: InsightChangeTiles;
}

export interface InsightTradesMonthly {
  ym: string;
  deal_type: 'sale';
  median_price_per_m2: number | null;
  count: number;
}

export interface InsightTrades {
  months: number;
  count: number;
  monthly: InsightTradesMonthly[];
}

export interface InsightCrime {
  max_grad: number;
  near_grad: number | null;
  flagged_area_m2: number;
  high_share_pct: number;
}

export interface InsightMy {
  is_favorite: boolean;
  color: string | null;
  label: string | null;
  memo: string | null;
  folder_id: number | null;
  report_count: number;
}

export interface Insight {
  status: InsightStatus;
  building: InsightBuilding;
  radius_m: 500 | 1000;
  radius_geometry: Polygon;
  as_of: InsightAsOf;
  green: InsightGreen | null;
  change: InsightChange | null;
  spec: InsightSpec | null;
  trades: InsightTrades | null;
  crime: InsightCrime | null;
  my: InsightMy | null;
  missing: InsightMissingEntry[];
}
