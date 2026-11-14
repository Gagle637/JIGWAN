import { describe, expect, it } from 'vitest'
import { isAboveMinZoom, toOlMinZoom, toTileLayerOptions } from './layerSource'
import type { MapLayer } from '../../api/types'

function makeLayer(overrides: Partial<MapLayer>): MapLayer {
  return {
    id: 1,
    slug: 'test',
    name: 'test',
    group: '기본',
    kind: 'background',
    order: 1,
    source_type: 'raster_tile',
    source_params: { regions: [] },
    min_zoom: null,
    max_zoom: null,
    opacity: 1,
    default_visible: true,
    legend: null,
    notice: null,
    attribution: null,
    synced_at: null,
    ...overrides,
  }
}

describe('toOlMinZoom', () => {
  it('backend min_zoom(포함)을 OpenLayers minZoom(배타적 경계)으로 1 낮춘다', () => {
    expect(toOlMinZoom(14)).toBe(13)
  })

  it('min_zoom이 없으면 undefined(제한 없음)', () => {
    expect(toOlMinZoom(null)).toBeUndefined()
  })
})

describe('isAboveMinZoom', () => {
  it('줌이 정확히 min_zoom일 때도 true다(건물이 보여야 한다)', () => {
    expect(isAboveMinZoom(14, 14)).toBe(true)
  })

  it('min_zoom보다 한 단계 낮으면 false다', () => {
    expect(isAboveMinZoom(13, 14)).toBe(false)
  })

  it('min_zoom보다 크면 true다', () => {
    expect(isAboveMinZoom(15, 14)).toBe(true)
  })

  it('min_zoom이 없으면 항상 true다', () => {
    expect(isAboveMinZoom(0, null)).toBe(true)
  })
})

describe('toTileLayerOptions', () => {
  it('상대 경로 url은 apiBase를 붙인다(vector_tile)', () => {
    const layer = makeLayer({
      slug: 'building_footprint',
      source_type: 'vector_tile',
      source_params: { url: '/api/tiles/buildings/{z}/{x}/{y}.mvt', regions: [] },
      min_zoom: 14,
      attribution: '브이월드 GIS건물통합정보',
    })

    const options = toTileLayerOptions(layer, 'http://localhost:8000')

    expect(options.url).toBe('http://localhost:8000/api/tiles/buildings/{z}/{x}/{y}.mvt')
    expect(options.minZoom).toBe(13)
    expect(options.attributions).toBe('브이월드 GIS건물통합정보')
  })

  it('이미 절대 URL이면 apiBase를 붙이지 않는다(raster_tile)', () => {
    const layer = makeLayer({
      slug: 'osm_basemap',
      source_type: 'raster_tile',
      source_params: { url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', regions: [] },
      min_zoom: 0,
      attribution: '© OpenStreetMap contributors',
    })

    const options = toTileLayerOptions(layer, 'http://localhost:8000')

    expect(options.url).toBe('https://tile.openstreetmap.org/{z}/{x}/{y}.png')
    expect(options.attributions).toBe('© OpenStreetMap contributors')
  })

  it('source_params.url이 없으면 빈 문자열이다', () => {
    const layer = makeLayer({ source_params: { regions: [] } })

    const options = toTileLayerOptions(layer, 'http://localhost:8000')

    expect(options.url).toBe('')
  })
})
