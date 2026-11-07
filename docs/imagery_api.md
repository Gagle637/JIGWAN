# 지도 레이어·영상 타일 API

프론트 작업 때 참고하는 기술 문서. 레이어 목록·필드 의미·타일 주소 조립 규칙·
`insight.change.tiles`(Before/After 스와이프) 사용법을 정리한다. 출처 문구 자체는
`docs/data_sources.md`를 본다.

## 1. `GET /api/layers`

인증 불필요(spec 9-1). `order` 순으로 정렬된 배열을 돌려준다. 모든 레이어가 같은
모양(`source_params.regions`는 해당 없는 레이어도 항상 `[]`)이라 프론트는 레이어 종류를
분기하지 않고 공통 렌더러로 돌릴 수 있다.

```json
[
  {
    "id": 1,
    "slug": "osm_basemap",
    "name": "배경지도",
    "group": "기본",
    "kind": "background",
    "order": 1,
    "source_type": "raster_tile",
    "source_params": {
      "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      "regions": []
    },
    "min_zoom": 0,
    "max_zoom": 19,
    "opacity": 1.0,
    "default_visible": true,
    "legend": null,
    "notice": null,
    "attribution": "© OpenStreetMap contributors",
    "synced_at": null
  },
  {
    "id": 5,
    "slug": "green_mask",
    "name": "녹지 마스크 (10m 해상도)",
    "group": "환경",
    "kind": "analysis",
    "order": 5,
    "source_type": "titiler",
    "source_params": {
      "regions": [
        {
          "region_code": "30",
          "bbox": [127.24, 36.18, 127.56, 36.50],
          "tile_url": "http://localhost:8001/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=%2Fdata%2Fcog%2F30_2026_summer_green_v1_green_mask.tif&nodata=255&colormap=...",
          "season": "2026-summer",
          "attribution": "Contains modified Copernicus Sentinel data 2026"
        },
        {
          "region_code": "36",
          "bbox": [127.0, 36.0, 127.3, 36.3],
          "tile_url": "http://localhost:8001/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=%2Fdata%2Fcog%2F36_2025_summer_green_v1_green_mask.tif&...",
          "season": "2025-summer",
          "attribution": "Contains modified Copernicus Sentinel data 2025"
        }
      ]
    },
    "min_zoom": null,
    "max_zoom": 15,
    "opacity": 0.6,
    "default_visible": false,
    "legend": [{"no": 1, "label": "녹지", "color": "#228B22"}],
    "notice": "catalog_publish가 게시할 때마다 활성 지역별로 최신 계절로 자동 갱신된다.",
    "attribution": "Contains modified Copernicus Sentinel data 2025–2026",
    "synced_at": "2026-11-07T10:00:00+09:00"
  }
]
```

### 1-1. 필드

| 필드 | 의미 |
| --- | --- |
| `slug` | 변하지 않는 식별자(upsert 키). 프론트도 레이어를 코드로 참조할 땐 `name`이 아니라 `slug`를 써야 한다 — `name`은 "(10m 해상도)"처럼 바뀔 수 있다 |
| `kind` | `background`(배경지도·건물 풋프린트, 끄는 일이 거의 없는 기준 레이어) 또는 `analysis`(나머지 7개, 분석용 오버레이) — 레이어 패널을 2단으로 나눌 때 씀 |
| `group` | spec 10-1의 세부 그룹(기본/내 건물/분석/환경/개발/시세/안전) |
| `source_type` | `raster_tile`(배경지도 전용) / `vector_tile`(MVT) / `geojson` / `titiler`(Sentinel COG) / `wms`(외부 WMS 중계) |
| `source_params.regions` | **모든 레이어에 항상 존재**(해당 없으면 `[]`). `titiler` 타입(녹지 마스크·Before/After)만 실제로 채워진다 — 활성 지역마다 가장 최근 게시된 계절의 타일 주소 1개씩 |
| `attribution` | 레이어 전체 출처 문구. `regions`가 있는 레이어는 그 안의 연도들로 자동 계산된 범위(`2025–2026`)가 들어간다(동일 연도면 그냥 `2026`) — `regions[].attribution`은 그 지역·계절 하나만의 연도를 담은 값이라 레이어 전체 값과 다를 수 있다 |
| `min_zoom`/`max_zoom` | 표시 줌 범위. 녹지 마스크·Before/After는 `max_zoom=15`(spec 10-5 — Sentinel 10m은 줌 16 이상에서 건물 확인용으로 못 씀, 그 이상은 항공사진 배경을 쓴다. 항공사진 레이어는 아직 없음) |
| `legend`/`notice` | 범례·고지. 범죄주의구간은 `notice`에 경찰청 요청 문구("등급이 높다고 현재 위험하다는 뜻은 아님")가 들어간다 |

### 1-2. 레이어 하나의 타일을 지도에 올리는 법(`titiler` 타입)

```js
const layer = layers.find(l => l.slug === 'green_mask');
const myRegion = layer.source_params.regions.find(r => r.region_code === currentSidoCode);
if (myRegion) {
  map.addLayer(new TileLayer({ source: new XYZ({ url: myRegion.tile_url }) }));
  showAttribution(myRegion.attribution);  // 또는 layer.attribution(전체 범위)
}
```

`regions`가 빈 배열이면 그 지역엔 아직 게시된 합성이 없다는 뜻(spec 6-2의 `status: "pending"`과
같은 상황) — 레이어를 숨기거나 "아직 데이터 없음"을 보여준다.

### 1-3. `wms` 타입(범죄주의구간) 타일

프론트가 WMS를 직접 부르지 않는다(인증키 노출 방지, spec 10-3) — 우리 API가 중계한다.

```
GET /api/layers/{id}/tiles/{z}/{x}/{y}.png
```

`id`는 `/api/layers` 응답의 `id` 필드(숫자). `source_type`이 `wms`가 아닌 레이어 id로
부르면 404.

## 2. `insight.change.tiles`(Before/After 스와이프)

`GET /api/buildings/{id}/insight`의 `change.tiles`는 **레이어 목록과 별개**로, 그 건물
반경 기준 Before/After 비교용 타일 주소를 직접 준다(지도 전체가 아니라 건물 하나 보는
화면용이라 `/api/layers`를 안 거친다).

```json
"tiles": {
  "after": "http://localhost:8001/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=...truecolor.tif&bidx=1&bidx=2&bidx=3&rescale=0,3000",
  "before": {
    "1y": "http://localhost:8001/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=...",
    "2y": "...",
    "3y": "..."
  },
  "default_compare": "1y"
}
```

- `after`: 가장 최근 게시된 truecolor(항상 있음, 게시된 게 있을 때만 `change` 섹션 자체가 채워짐)
- `before`: **게시된 과거 계절 truecolor가 있는 기간만** 키가 있다(1y/2y/3y 중 일부만 있을 수
  있음). `default_compare`는 1y→2y→3y 순서로 처음 존재하는 키, 하나도 없으면 `null`
- 스와이프 UI는 `after`를 고정 배경으로 깔고 `before[default_compare]`를 클리핑 마스크로
  겹쳐 좌우로 끄는 식으로 구현한다(OpenLayers는 `ol/render/Layer`의 클리핑 예제 참고)

## 3. TiTiler 타일 주소 조립 규칙

`regions[].tile_url`과 `change.tiles`는 전부 `backend/layers/tile_params.py`의
`build_titiler_url()` 하나로 만든다 — 형식:

```
{TITILER_PUBLIC_URL}/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=<COG 경로>&<표시 파라미터>
```

프론트는 이 문자열을 그대로 OpenLayers `XYZ` source의 `url`로 쓰면 된다(`{z}/{x}/{y}`
플레이스홀더 포함, 이미 완성된 템플릿).

| 레이어 | 표시 파라미터 |
| --- | --- |
| truecolor(Before/After) | `bidx=1&bidx=2&bidx=3&rescale=0,3000`(B04·B03·B02 → RGB) |
| green_mask(녹지 마스크) | `nodata=255&colormap={"0":[0,0,0,0],"1":[34,139,34,255]}`(0=투명, 1=녹지) |

## 4. 항공사진(보류)

spec 10-5의 "건물 확대 배경"(줌 16 이상, 브이월드/국토지리정보원 영상지도 API)은 아직
레이어로 없다. 추가되면 이 문서와 `docs/data_sources.md`에 같이 반영한다.
