import { useEffect, useRef, useState } from 'react'
import Map from 'ol/Map'
import View from 'ol/View'
import TileLayer from 'ol/layer/Tile'
import VectorTileLayer from 'ol/layer/VectorTile'
import XYZ from 'ol/source/XYZ'
import VectorTileSource from 'ol/source/VectorTile'
import MVT from 'ol/format/MVT'
import Style from 'ol/style/Style'
import Stroke from 'ol/style/Stroke'
import Fill from 'ol/style/Fill'
import { defaults as defaultControls } from 'ol/control/defaults'
import Attribution from 'ol/control/Attribution'
import 'ol/ol.css'

import { useLayersQuery } from '../../api/layers'
import { useMapViewStore } from '../../stores/mapViewStore'
import { isAboveMinZoom, toTileLayerOptions } from './layerSource'
import type { MapLayer } from '../../api/types'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

// 다음 단계(건물 클릭)에서 건물 안쪽도 클릭이 잡히도록 채움을 거의 투명하게 넣는다
// (채움이 전혀 없으면 OpenLayers가 외곽선 밖은 클릭으로 안 잡는다).
const BUILDING_STYLE = new Style({
  stroke: new Stroke({ color: '#1e293b', width: 1 }),
  fill: new Fill({ color: 'rgba(0, 0, 0, 0.01)' }),
})

function selectBackgroundLayers(layers: MapLayer[]): MapLayer[] {
  return layers.filter((layer) => layer.kind === 'background').sort((a, b) => a.order - b.order)
}

function buildOlLayer(layer: MapLayer) {
  const options = toTileLayerOptions(layer, API_BASE)
  const attributions = options.attributions ?? undefined

  if (layer.source_type === 'vector_tile') {
    return new VectorTileLayer({
      source: new VectorTileSource({
        format: new MVT(),
        url: options.url,
        attributions,
        // VectorTileSource 기본 tileSize는 512인데, 우리 백엔드(render_building_tile)는
        // 표준 256px 기준 XYZ z/x/y를 쓴다. 맞춰주지 않으면 OpenLayers가 뷰 해상도에
        // 맞는 z보다 한 단계 낮은 z를 요청해(실측 확인됨 — 줌 14에서도 계속 z13 타일만
        // 요청) 건물이 기준 지도보다 한 단계 거칠게·어긋나게 그려진다.
        tileSize: 256,
      }),
      style: BUILDING_STYLE,
    })
  }
  return new TileLayer({ source: new XYZ({ url: options.url, attributions }) })
}

export default function MapCanvas() {
  const targetRef = useRef<HTMLDivElement | null>(null)
  const { center, zoom, setView } = useMapViewStore()
  const [currentZoom, setCurrentZoom] = useState(zoom)
  const { data: layers, isPending, isError, refetch } = useLayersQuery(selectBackgroundLayers)

  useEffect(() => {
    if (!targetRef.current || !layers) return

    const olLayers = layers.map(buildOlLayer)
    const buildingIndex = layers.findIndex((layer) => layer.slug === 'building_footprint')
    const buildingOlLayer = buildingIndex >= 0 ? olLayers[buildingIndex] : undefined
    const buildingMinZoom = buildingIndex >= 0 ? layers[buildingIndex].min_zoom : null

    const applyZoomGate = (z: number) => {
      buildingOlLayer?.setVisible(isAboveMinZoom(z, buildingMinZoom))
    }
    applyZoomGate(zoom)

    const map = new Map({
      target: targetRef.current,
      layers: olLayers,
      view: new View({ center, zoom }),
      // 출처 표시는 접히지 않고 항상 보이게 한다.
      controls: defaultControls({ attribution: false }).extend([
        new Attribution({ collapsible: false }),
      ]),
    })

    map.on('moveend', () => {
      const view = map.getView()
      const newCenter = view.getCenter() as [number, number] | undefined
      const newZoom = view.getZoom()
      if (newCenter && newZoom !== undefined) {
        setView(newCenter, newZoom)
        setCurrentZoom(newZoom)
        applyZoomGate(newZoom)
      }
    })

    // React StrictMode는 개발 모드에서 effect를 두 번 실행한다. target을 비워 지도를
    // 완전히 떼어내야 같은 DOM에 지도가 두 개 겹쳐 남는 걸 막을 수 있다.
    return () => {
      map.setTarget(undefined)
    }
    // center·zoom은 최초 생성에만 쓴다 — moveend가 스토어를 갱신할 때마다 지도를
    // 다시 만들면 매번 지도가 깜빡이고 moveend가 또 발생해 끝없이 재생성된다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layers])

  const buildingLayer = layers?.find((layer) => layer.slug === 'building_footprint')
  const showZoomHint = buildingLayer
    ? !isAboveMinZoom(currentZoom, buildingLayer.min_zoom)
    : false

  if (isError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-slate-500">
        <p>지도 레이어를 불러올 수 없습니다.</p>
        <button
          type="button"
          onClick={() => refetch()}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white"
        >
          다시 시도
        </button>
      </div>
    )
  }

  return (
    <div className="relative h-full w-full">
      <div ref={targetRef} className="h-full w-full" />
      {!isPending && showZoomHint && (
        <div className="pointer-events-none absolute top-4 left-1/2 z-10 -translate-x-1/2 rounded-md bg-slate-900/80 px-3 py-1.5 text-sm text-white">
          확대하면 건물이 보입니다
        </div>
      )}
    </div>
  )
}
