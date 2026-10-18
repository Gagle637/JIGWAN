# 지관(地官) 기술 명세

Oct 16, 2026 · @준호

이 탭은 기획서의 ‘무엇을 왜’를 백엔드가 바로 구현할 수 있는 ‘어떻게’로 풀어 쓴다. 수치와 규칙은 제안 기본값이며, 1장의 결정 항목이 확정되면 이에 맞춰 고친다.

## 1. 착수 전 확정할 결정

아래 8개는 개발자가 임의로 정하면 안 되는 항목이다. 제안 기본값으로 착수하되, P0 종료 전까지 확정한다.

| 결정 항목 | 제안 기본값 | 영향받는 작업 |
| --- | --- | --- |
| 시범 지역 | 대전광역시 5개 구(확정) | 위성 타일 수, 백필 용량, 변화 감지 검증 현장 선정 |
| 위성 데이터 접근 방식 | STAC(pystac-client) 검색 + CDSE S3 다운로드(확정) | 수집 잡 구현, 저장 형식 |
| 좌표계 | 저장 EPSG:4326, 표출 EPSG:3857(확정). 미터 계산은 geography 형변환(3-0) | 모든 벡터 적재와 공간 쿼리, 반경 계산 |
| 계절 구간 | 봄 3–5월, 여름 6–8월, 가을 9–11월, 겨울 12–2월 | 합성 스케줄, 변화 감지 비교 쌍 |
| 리포트 생성 방식 | 요청 시 사용자별 생성(기본 템플릿 → 맞춤 프롬프트), 건물당 여러 개 보관 | GPU 상시 기동, 사용자별 일일 한도 |
| GPU 사양 | VRAM 24GB급 1장(20b 기본 + KV 캐시 여유) | 리포트 처리량, 인프라 비용 |
| 사용자 인증 | 지도·insight는 비로그인 허용, 리포트·즐겨찾기·메모는 로그인(JWT) 필요 | API 권한, 요청 제한 설계 |
| 원본 장면 보관 기간 | 계절 합성 완료 후 90일 | 디스크 용량, 재합성 가능 여부 |

## 2. 위성 데이터 접근·전처리

CDSE의 Sentinel-2 L2A 원본은 COG가 아니라 SAFE 패키지 안의 JPEG 2000 파일이다. 따라서 원본을 직접 읽지 않고, 수집 잡이 필요한 밴드만 받아 대상 지역 COG로 변환해 두는 방식을 쓴다([STAC 항목 예시](https://browser.stac.dataspace.copernicus.eu/collections/sentinel-2-l2a/items/S2B_MSIL2A_20260809T085559_N0512_R007_T35SMB_20260809T111845)).

### 2-1. 검색과 다운로드

| 단계 | 규칙 |
| --- | --- |
| 검색 | STAC `https://stac.dataspace.copernicus.eu/v1/`, 컬렉션 `sentinel-2-l2a`, 지역 bbox + 기간 + `eo:cloud_cover <= 30` ([STAC 문서](https://documentation.dataspace.copernicus.eu/APIs/STAC.html)) |
| 중복 제거 | 같은 타일·촬영일에 여러 processing baseline이 있으면 최신 baseline 하나만 사용 |
| 다운로드 | CDSE S3(`eodata`) 접근 키로 필요한 파일만 받음: B02·B03·B04·B08(10m, B02·B03은 Before/After 트루컬러용), B11·SCL(20m), `MTD_MSIL2A.xml` |
| 변환 | 대상 지역으로 자른 뒤 원본 좌표계(UTM 52N, EPSG:32652) 그대로 10m COG 저장. B11은 bilinear, SCL은 nearest로 10m 리샘플링 |
| 정리 | 변환이 끝난 JP2 원본은 즉시 삭제, 변환 COG는 1장의 보관 기간을 따름 |

CDSE는 계정별 다운로드 한도가 있으므로, 백필 전에 [Quotas & Limitations](https://documentation.dataspace.copernicus.eu/Quotas.html)을 확인해 동시 다운로드 수를 정한다. 대안으로 CDSE의 Sentinel Hub API는 NDVI 같은 계산 결과를 바로 돌려주지만, 처리 단위 사용량이 차감되고 파이프라인 통제가 줄어 MVP에서는 쓰지 않는다.

검색은 pystac-client로 한다. pystac-client는 조건에 맞는 장면의 메타데이터만 돌려주고, 실제 파일(JP2)을 받으려면 CDSE 계정에서 발급한 S3 키가 따로 필요하다. 대전을 덮는 타일은 검색 결과의 장면 ID에 들어 있는 타일 코드(예: `T52S...`)로 확인하고, 대전이 두 타일에 걸치면 같은 날짜 장면을 합쳐 쓴다.

```python
from pystac_client import Client

cat = Client.open("https://stac.dataspace.copernicus.eu/v1/")
search = cat.search(
    collections=["sentinel-2-l2a"],
    bbox=[127.24, 36.18, 127.56, 36.50],   # 대전 대략 범위(경계 폴리곤으로 교체)
    datetime="2026-06-01/2026-08-31",
    filter="eo:cloud_cover <= 30",
    filter_lang="cql2-text",
)
items = list(search.items())
tiles = {item.id.split("_")[5] for item in items}   # 예: {"T52SCF", ...}
```

### 2-2. 반사율 변환

아카이브에는 여러 processing baseline이 섞여 있다([L2A baseline 현황](https://documentation.dataspace.copernicus.eu/Data/Others/Sentinel2_L2A_baseline.html)). baseline 04.00 이후 제품은 화소값에 오프셋이 더해져 있으므로, 오프셋을 하드코딩하지 않고 장면마다 메타데이터에서 읽는다.

```latex
\rho = \frac{DN + \mathrm{BOA\_ADD\_OFFSET}_{band}}{\mathrm{BOA\_QUANTIFICATION\_VALUE}}
```

- `BOA_ADD_OFFSET`(밴드별)과 `BOA_QUANTIFICATION_VALUE`는 `MTD_MSIL2A.xml`에서 읽고, 값이 없는 구형 제품은 오프셋 0으로 처리한다.
- DN 0은 nodata로 두고, 변환 후 음수 반사율은 0으로 자른다.
- `satellite_scene`에 `processing_baseline`, 밴드별 오프셋을 함께 저장해 나중에 검증할 수 있게 한다.
- Sentinel-2A·B·C 장면은 구분 없이 같은 것으로 취급한다.

### 2-3. 구름 마스킹(SCL)

| SCL 값 | 의미 | 처리 |
| --- | --- | --- |
| 0, 1 | nodata, 포화·결함 | 제외 |
| 3 | 구름 그림자 | 제외 |
| 8, 9 | 구름(중간·높은 확률) | 제외 |
| 10 | 얇은 권운 | 제외 |
| 11 | 눈·얼음 | 제외(겨울 NDVI 왜곡 방지) |
| 2, 4, 5, 6, 7 | 어두운 화소, 식생, 비식생, 물, 미분류 | 사용 |

장면의 지역 내 유효 화소 비율이 20% 미만이면 합성에서 뺀다. 전체 장면의 `eo:cloud_cover`가 낮아도 대상 지역만 구름에 덮일 수 있기 때문이다.

## 3. 좌표계·결과 카탈로그·계절·임계값 정의

위성 분석 결과는 계절 단위 COG로 만들어 결과 카탈로그에 날짜·범위와 함께 등록하고, 건물 지표는 조회 시 반경으로 잘라 계산한다. 건물별 결과는 미리 만들지 않는다.

### 3-0. 좌표계 규칙

벡터는 모두 EPSG:4326 geometry로 저장하고, 버퍼·거리·면적처럼 미터 단위가 필요한 계산은 `::geography`로 형변환해 처리한다. 4326 좌표 그대로 `ST_Buffer(geom, 500)`을 하면 단위가 ‘도(°)’가 되므로 금지한다.

| 용도 | 좌표계·타입 | 방식 |
| --- | --- | --- |
| DB 저장(건물, 카탈로그 bbox, 변화 폴리곤, 실거래 위치, 범죄주의 도로 구간) | EPSG:4326 geometry | 유일한 원본. GIST 인덱스 + 거리 검색용 `CREATE INDEX ... USING GIST ((geom::geography))` |
| 버퍼·거리·면적 | geography | `ST_Buffer(geom::geography, 500)::geometry`, `ST_DWithin(a::geography, b::geography, 500)`, `ST_Area(geom::geography)` |
| 위성 결과 래스터(COG) | EPSG:32652 | DB 밖 파일, 원본 좌표계 유지 |
| 조회 시 반경으로 COG 읽기 | EPSG:32652 | 반경 폴리곤만 COG 좌표계로 변환해 마스크(래스터는 재투영하지 않음) |
| API 입출력 | EPSG:4326 | GeoJSON 표준 |
| 화면 표출 | EPSG:3857 | OpenLayers가 4326 GeoJSON을 변환, TiTiler·외부 WMS 타일은 3857로 요청 |

### 3-1. 결과 카탈로그(`raster_product`)

배치가 만드는 모든 결과 래스터는 이 테이블에 한 행씩 등록하고, 조회는 종류·기간·범위로 검색한다.

| 컬럼 | 내용 |
| --- | --- |
| `product_type` | `ndvi` · `ndbi` · `green_mask` · `truecolor` · `change_mask` |
| `year`, `season`, `period_start`, `period_end` | 합성 기간(계절) |
| `compare_period` | 변화 결과의 비교 기준 기간(1·2·3년 전 같은 계절), 나머지는 null |
| `bbox` | 결과 범위(Polygon, 4326), GIST 인덱스 |
| `crs`, `resolution_m` | EPSG:32652, 10 |
| `cog_path` | COG 아카이브 안의 경로 |
| `algo_version` | 알고리즘·임계값 버전(예: `green_v1`). 바뀌면 새 행으로 등록하고 이전 행은 남긴다 |
| `scene_ids`, `valid_ratio` | 합성에 쓴 장면, 범위 안 유효 픽셀 비율 |
| `is_published` | 검증 통과 후 true. 조회는 true인 행만 검색 |

```sql
SELECT id, year, season, cog_path
FROM raster_product
WHERE product_type = 'green_mask'
  AND is_published
  AND algo_version = :current_version
  AND ST_Intersects(bbox, :buffer_4326)
ORDER BY period_start DESC
LIMIT 13;
```

MVP는 대전 전역을 결과 하나로 저장하므로 기간당 보통 한 행이 검색된다. 지역을 늘리거나 타일 단위로 나눠 저장하면 한 반경에 여러 행이 걸릴 수 있으므로, 조회 로직은 처음부터 여러 COG의 픽셀 수를 합산하도록 만든다.

### 3-2. 조회 시 반경 통계

1. 반경: `ST_Buffer(geom::geography, r)::geometry`(r = 500 또는 1000).
2. 반경을 COG 좌표계(EPSG:32652)로 변환하고 `rasterio.mask.mask(crop=True, all_touched=False)`로 반경 창만 읽는다(픽셀 중심이 반경 안에 있는 픽셀만 포함).
3. 녹지율 = 녹지 픽셀 수 ÷ 유효 픽셀 수(nodata 제외). 유효 비율(유효 픽셀 ÷ 반경 내 전체 픽셀)이 50% 미만이면 `insufficient_data`.
4. 시계열은 13개 계절의 `green_mask`에 같은 계산을 반복한다. 시·구 기준선은 `region_stat`에서 읽는다.
5. 변화는 `change_area`를 반경과 `ST_Intersects`로 검색하고, 반경 안 면적은 `ST_Area(ST_Intersection(geom, 반경)::geography)`, 거리는 `ST_Distance(::geography)`로 구한다.
6. 결과는 (건물, 반경, 사용한 `raster_product` id 목록)을 키로 Redis에 캐시한다.

### 3-3. 계절과 합성

| 항목 | 규칙 |
| --- | --- |
| 계절 구간 | 봄 3–5월, 여름 6–8월, 가을 9–11월, 겨울 = Y년 12월\~Y+1년 2월(연도 Y로 기록) |
| 합성 시점 | 계절 종료 15일 후(늦게 등록되는 장면 반영) |
| 합성 방식 | 장면별로 NDVI·NDBI를 먼저 계산한 뒤 화소별 중앙값 |
| 최소 관측 수 | 화소당 유효 관측 3회 미만이면 nodata |
| 재합성 | 합성 후 같은 계절 장면이 추가되면 수동 재실행으로만 갱신 |

### 3-4. 임계값(초기값, P2에서 조정)

| 항목 | 초기값 | 조정 방법 |
| --- | --- | --- |
| 녹지 화소 | NDVI ≥ 0.4 | 시범 지역 공원·도로 샘플 화소로 확인 |
| 개발 후보 화소 | ΔNDBI > +0.1 그리고 ΔNDVI < −0.15 | 검증 현장 30곳의 정밀도 80% 달성 시까지 |
| 변화 폴리곤 최소 크기 | 8방향 연결 10화소(0.1ha) | 노이즈 비율 확인 후 조정 |

## 4. 초기 적재(백필) 계획

서비스를 열려면 최신 계절과 그 이전 3년치, 총 13개 계절의 합성이 먼저 있어야 한다. 2026년 10월 기준이면 2023년 여름부터 2026년 여름까지다. 백필은 별도 코드가 아니라 정기 잡을 `mode=backfill`과 계절 파라미터로 돌린다.

1. **기반 적재**: 건물, 행정경계를 적재한다.
2. **장면 목록 작성(dry run)**: 13개 계절 전체를 STAC로 검색해 `satellite_scene`에 `status=listed`로 기록한다. 이 단계에서 총 장면 수·예상 다운로드 용량을 집계해 CDSE 한도 안에서 일정을 잡는다.
3. **계절 단위 처리**: 오래된 계절부터 다운로드 → COG 변환 → 합성(NDVI·NDBI·녹지 마스크·트루컬러) → 카탈로그 등록 순으로 한 계절을 끝내고 JP2 원본을 지운 뒤 다음 계절로 넘어간다. 디스크 최대 사용량이 한 계절분으로 제한된다.
4. **변화 분석**: 13개 계절 합성이 끝난 뒤 최신 계절을 1·2·3년 전 같은 계절과 비교해 변화 마스크·`change_area`를 만들고 카탈로그에 등록한다.
5. **지역 기준선**: 계절별 구·시 평균 녹지율을 `region_stat`에 저장한다.
6. **공공데이터 백필**: 실거래 24개월(API), 건물·건축물대장(GIS건물통합정보 파일), 범죄주의 도로 구간을 적재한다. 3–5단계와 병렬로 돌려도 된다.
7. **검증 후 게시**: 유효 비율·값 범위·대전 경계 커버리지를 확인하고 카탈로그 행을 `is_published = true`로 바꾼다.

| 완료 기준 | 확인 방법 |
| --- | --- |
| 13개 계절 결과 존재 | `raster_product`에 계절별 ndvi·ndbi·green\_mask·truecolor 행이 모두 게시됨 |
| 계절별 유효 비율 | `valid_ratio`를 계절별로 기록(여름은 낮을 수 있음) |
| 변화 결과 | 1·2·3년 비교 `change_mask` 3행 + `change_area` |
| 조회 동작 | 샘플 건물 20곳에서 `insight`가 2초 안에 모든 항목을 반환 |

백필 중에는 정기 스케줄을 멈추고, 각 계절은 독립적으로 재시작할 수 있게 한다(5장 멱등성 규칙).

## 5. 배치 운영 규칙

모든 잡은 같은 입력으로 다시 돌려도 같은 결과를 내고(멱등), 실패하면 사용자는 직전 성공 결과를 계속 본다.

### 5-1. 스케줄(KST)

| 잡 | 실행 | 큐 | 비고 |
| --- | --- | --- | --- |
| `satellite_collect` | 5일마다 02:00 | io | 직전 실행 이후 등록된 장면만 다운로드·변환 |
| `season_composite` | 3/15, 6/15, 9/15, 12/15 03:00 | cpu | 계절 종료 15일 후, 아래 체인의 시작점 |
| `change_analysis`, `region_stat` | 합성 직후 병렬 | cpu | 체인 |
| `catalog_publish` | 두 잡 완료 후 | cpu | 검증 통과 시 카탈로그 게시(5-3) |
| `trade_sync` | 매일 04:00 | io | 당월·전월 재수집 |
| `register_sync` | 매월 1일 05:00 | io | MVP 제외(건축물대장 속성은 building\_load로 함께 적재, 8-6) |
| `safety_sync` | 매년 1월 첫째 주 + 수동 | io | 범죄주의 도로 구간 수집, 레이어 범례 갱신 |
| `building_load` | 수동(새 파일을 받았을 때) | cpu | GIS건물통합정보 파일 적재 |

리포트는 스케줄 잡이 아니다. 사용자가 리포트를 요청하면 API가 gpu 큐에 생성 작업을 넣는다.

큐는 io(다운로드·외부 API), cpu(래스터·공간 연산), gpu(사용자가 요청한 리포트) 세 개로 나눠 무거운 연산이 수집을 막지 않게 한다.

### 5-2. 실행 규칙

| 항목 | 규칙 |
| --- | --- |
| 체이닝 | Celery canvas: `season_composite → group(change_analysis, region_stat) → catalog_publish`. 앞 단계가 실패하면 뒤 단계는 실행하지 않음 |
| 멱등성 키 | `(job, region_code, year, season)`. 같은 키의 기존 행을 한 트랜잭션 안에서 지우고 다시 쓴다 |
| 파일 쓰기 | 임시 경로에 쓴 뒤 완료 시 rename. 중간에 죽어도 반쯤 쓴 COG가 남지 않음 |
| 동시 실행 방지 | Redis 잠금 `lock:{job}:{region_code}`(TTL = 잡 최대 시간 × 2). 잠금이 있으면 `skipped`로 기록 |
| 재시도 | 외부 호출 오류(네트워크, 5xx, 429)만 3회, 1·5·25분 간격. 데이터 오류는 재시도하지 않고 즉시 `failed` |
| 실행 기록 | `index_run.status`: queued → running → succeeded / failed / skipped, `error`에 예외 요약 |
| 알림 | `failed` 발생 또는 잡이 예상 시간의 2배를 넘기면 관리자 알림(채널은 9장) |

### 5-3. 결과 게시

새 계절 결과는 검증(유효 비율, 값 범위, 대전 경계 커버리지)을 통과한 뒤에만 `raster_product.is_published`를 true로 바꾼다. 조회는 게시된 행만 검색하므로, 배치 도중에도 사용자는 일부만 만들어진 결과를 보지 않는다.

### 5-4. 보관

| 대상 | 보관 기간 |
| --- | --- |
| JP2 원본 | 변환 직후 삭제 |
| 장면별 COG | 해당 계절 합성 후 90일 |
| 결과 COG, 변화 폴리곤, 카탈로그 | 영구(시계열 원천) |
| `index_run` | 1년 |

## 6. 조회 API 응답 스키마

프론트와의 계약은 두 갈래다. `GET /api/buildings/{id}/insight`는 조회 시 반경을 계산해 바로 돌려주고, 리포트·즐겨찾기·메모는 6-4의 사용자별 API로 다룬다. 화면 설계 전이므로 필드는 지표 단위로만 고정한다.

### 6-1. 공통 규약

| 항목 | 규칙 |
| --- | --- |
| 좌표 | 입출력은 WGS84(EPSG:4326), 폴리곤은 GeoJSON |
| 날짜 | ISO 8601, KST(`+09:00`) |
| 단위 | 면적 ㎡, 거리 m, 비율 %, 금액 만원(실거래 API 원본 단위) |
| 빈 값 | 항목이 없으면 `null`로 두고, 이유를 `missing[]`에 `{field, reason}`으로 기록 |
| 반경 | `radius`는 500 또는 1000만 허용 |

### 6-2. `insight` 응답 예시

값은 형식을 보여주기 위한 예시이다.

```json
{
  "status": "ready",
  "building": {"id": 18273, "pnu": "0000000000000000000", "name": "예시아파트 101동", "address": "○○시 ○○구 ○○동 123", "use_type": "공동주택", "geometry": {"type": "Polygon", "coordinates": []}},
  "radius_m": 500,
  "as_of": {"satellite_period": "2026-06-01/2026-08-31", "trade_synced_at": "2026-10-16T04:12:00+09:00", "register_synced_at": "2026-10-01T05:40:00+09:00", "crime_data_period": "2023-07/2024-06"},
  "green": {
    "ratio_pct": 23.4, "region_avg_pct": 18.1, "diff_pp": 5.3, "coverage_pct": 92,
    "series": [{"year": 2023, "season": "summer", "ratio_pct": 22.0, "coverage_pct": 71}]
  },
  "change": {
    "total_area_m2": 41200,
    "areas": [{"id": 551, "area_m2": 18300, "distance_m": 320, "period": "1y", "geometry": {"type": "Polygon", "coordinates": []}}],
    "tiles": {"before": "/tiles/{z}/{x}/{y}?url=...", "after": "/tiles/{z}/{x}/{y}?url=..."}
  },
  "spec": {"use": "공동주택", "land_area_m2": 15230.5, "total_floor_area_m2": 48211.2, "bcr_pct": 18.2, "far_pct": 249.8, "approval_date": "2009-11-20", "age_years": 16},
  "trades": {"months": 24, "count": 87, "monthly": [{"ym": "2026-09", "deal_type": "sale", "median_price_per_m2": 812.3, "count": 5}]},
  "crime": {"max_grad": 7, "near_grad": 5, "flagged_length_m": 640, "high_share_pct": 4.2},
  "my": {"is_favorite": true, "color": "#e8590c", "label": "후보 1순위", "folder_id": 4, "report_count": 2},
  "missing": []
}
```

| `status` | 의미 | HTTP |
| --- | --- | --- |
| `ready` | 모든 섹션 있음 | 200 |
| `partial` | 일부 섹션 `null`, 사유는 `missing[]` | 200 |
| `pending` | 해당 범위의 위성 결과가 카탈로그에 없음, 위성 섹션만 `null` | 200 |

로그인한 경우 `my`에 내 표시(즐겨찾기·색상·라벨)와 이 건물의 내 리포트 수가 들어가고, 비로그인이면 `my`는 `null`이다. 리포트 본문은 insight에 넣지 않는다.

### 6-3. 에러 규약

에러 본문은 `{"error": {"code": "...", "message": "..."}}` 형식으로 통일한다.

| HTTP | `code` | 상황 |
| --- | --- | --- |
| 400 | `INVALID_PARAM` | 반경·좌표·기간 파라미터 오류 |
| 404 | `BUILDING_NOT_FOUND` | 건물 ID 없음 |
| 404 | `NO_BUILDING_AT_POINT` | 클릭 좌표에 건물 없음 |
| 404 | `OUT_OF_COVERAGE` | 인덱싱 대상 지역 밖 |
| 429 | `RATE_LIMITED` | 요청 제한 초과(9장) |
| 500 | `INTERNAL` | 서버 오류, 요청 ID를 함께 반환 |
| 401 | UNAUTHORIZED | 로그인이 필요한 API를 비로그인으로 호출, 토큰 만료 |
| 403 | FORBIDDEN | 다른 사용자의 리포트·표시에 접근 |
| 429 | REPORT\_QUOTA\_EXCEEDED | 사용자별 하루 리포트 생성 한도 초과 또는 이미 생성 중인 리포트 있음 |

### 6-4. 리포트·사용자 데이터 API

리포트는 건물 조회와 분리된 사용자별 리소스다. 생성 요청은 즉시 `report_id`를 돌려주고, 생성이 끝날 때까지 `status`는 `generating`이다. 프론트는 `GET /api/reports/{id}`를 2초 간격으로 최대 60초까지 폴링한다.

```json
POST /api/buildings/18273/reports
{"radius_m": 500, "report_type": "custom", "prompt": "아이 둘 키우는 4인 가족 실거주 관점에서 녹지와 주변 공사 위주로 봐줘"}
→ 202 {"report_id": 9912, "status": "generating"}

GET /api/reports/9912
→ 200 {
  "report_id": 9912, "building_id": 18273, "radius_m": 500,
  "report_type": "custom", "prompt": "아이 둘 키우는 ...",
  "status": "ready", "model": "gpt-oss-20b", "created_at": "2026-10-16T14:02:11+09:00",
  "data_as_of": {"satellite_period": "2026-06-01/2026-08-31", "trade_synced_at": "2026-10-16T04:12:00+09:00"},
  "result": {"title": "...", "answer": "...", "evidence": [{"index": 0, "keys": ["green.ratio_pct"]}], "limitations": ["통학 거리는 제공 데이터에 없음"]}
}
```

| 항목 | 규칙 |
| --- | --- |
| 소유 | 리포트·표시는 만든 사용자만 조회·삭제(모든 API에 소유자 검사) |
| 개수 | 건물·사용자당 리포트 수 제한 없음, 목록은 최신순 |
| 생성 한도 | 사용자별 하루 20건(초기값), 동시 생성 1건. 초과 시 429 `REPORT_QUOTA_EXCEEDED` |
| 재생성 | 기존 리포트는 고치지 않고 새 리포트로 만든다(생성 당시 입력 보존) |
| 프롬프트 | 500자 이내, `template`이면 비워둔다 |

```json
PUT /api/buildings/18273/mark
{"is_favorite": true, "color": "#e8590c", "label": "후보 1순위", "memo": "주말 현장 방문 예정, 주차 확인"}
```

| 필드 | 규칙 |
| --- | --- |
| `is_favorite` | 즐겨찾기 여부 |
| `color` | 정해둔 팔레트 8색 중 하나 또는 `null`(자유 색상은 받지 않음) |
| `label` | 20자 이내, 지도에 띄우는 텍스트 |
| `memo` | 2,000자 이내, 지도에는 표시하지 않고 건물 상세에서만 보임 |
| `folder_id` | 넣을 즐겨찾기 폴더. null이면 ‘미분류’(6-5) |

`is_favorite`가 false이고 `color`·`label`·`memo`가 모두 비면 행을 삭제한다(`folder_id`는 즐겨찾기일 때만 의미가 있다). `GET /api/me/buildings?bbox=`는 현재 지도 범위 안의 내 표시 건물을 GeoJSON으로 돌려준다(10-4).

### 6-5. 즐겨찾기 폴더(트리)

즐겨찾기는 폴더 트리로 묶는다. 폴더 안에 폴더를 둘 수 있고, 건물은 한 폴더에만 속하며 폴더가 없으면 ‘미분류’다.

| 항목 | 규칙 |
| --- | --- |
| 구조 | `favorite_folder(id, user_id, parent_id, name, color, is_hidden, sort_order)`, `parent_id`는 자기 참조, 최대 깊이 5 |
| 건물 소속 | `user_building.folder_id`, 건물당 폴더 하나 |
| 이동 | 폴더를 자기 하위 폴더 아래로 옮기는 요청은 400 `INVALID_PARAM`(순환 방지) |
| 정렬 | 같은 부모 안에서 `sort_order` 순 |
| 삭제 | 하위 폴더와 건물을 상위 폴더로 옮긴 뒤 삭제(즐겨찾기는 해제하지 않음) |
| 조회 | 사용자의 폴더 전체를 한 번에 읽어 서버에서 트리로 조립(폴더 수가 적어 재귀 쿼리 불필요) |
| 지도 필터 | `/api/me/buildings?folder_id=`는 하위 폴더의 건물까지 포함 |

```json
GET /api/me/favorites
→ 200 [
  {"id": 1, "name": "대전 후보", "color": "#e8590c", "is_hidden": false, "building_count": 3,
   "children": [
     {"id": 4, "name": "유성구", "color": null, "is_hidden": false, "building_count": 2, "children": []}
   ]},
  {"id": null, "name": "미분류", "building_count": 5, "children": []}
]
```

`building_count`는 그 폴더에 직접 속한 건물 수다.

## 7. gpt-oss 리포트 명세

리포트는 반경 계산 결과 JSON(맞춤 리포트는 사용자 프롬프트 추가)만 입력으로 받고, JSON 스키마로 고정된 출력을 내며, 기계 검증을 통과한 것만 저장한다. 사용자가 요청할 때 만들기 때문에 수치 응답과 분리해 비동기로 처리한다.

### 7-1. 서빙 설정

| 항목 | 값 |
| --- | --- |
| 서버 | vLLM 컨테이너, 모델 `openai/gpt-oss-20b`, OpenAI 호환 `/v1/chat/completions` ([서빙 가이드](https://developers.openai.com/cookbook/articles/gpt-oss/run-vllm)) |
| 추론 수준 | low(시스템 프롬프트에 지정). 품질이 부족하면 medium과 비교 |
| 샘플링 | temperature 0.3, max\_tokens 1,200 |
| 출력 강제 | 요청에 7-3(기본 템플릿) 또는 7-6(맞춤)의 JSON 스키마를 `response_format`으로 전달(vLLM 구조화 출력) |
| 동시성 | API가 gpu 큐에 넣고 워커가 vLLM에 보냄. 동시 생성 수와 대기열 상한은 P3 벤치마크로 결정 |

### 7-2. 프롬프트 구성

```text
[system]
역할: 한국 부동산 입지 분석 리포트 작성자
규칙:
- 입력 JSON에 있는 값만 사용한다. 없는 항목은 '정보 없음'으로 쓴다.
- 수치는 입력값을 그대로(소수점 한 자리까지) 쓴다.
- 매수·매도 권유, 수익 예측, 단정 표현을 쓰지 않는다.
- 개발 변화는 '개발 징후'로만 표현한다.
- 범죄 등급은 '최근 1년 범죄 발생 밀도'로만 표현하고 '위험하다'고 쓰지 않는다.
- 모든 주장에 근거 키를 evidence에 남긴다.
문체: 한국어 평서문, 용어 사전(녹지율, 용적률 등) 표기 준수
Reasoning: low

[few-shot 예시 2건: 입력 JSON → 모범 출력 JSON]

[user]
입력: { insight 응답에서 geometry·tiles·my를 뺀 JSON }
```

프롬프트는 코드가 아닌 파일(`prompts/report_template_v1.txt`, `prompts/report_custom_v1.txt`)로 관리하고, 버전을 `report.template_version` 또는 `report.prompt_version`에 저장해 어느 프롬프트로 만든 리포트인지 추적한다.

### 7-3. 출력 스키마

| 필드 | 타입 | 제약 |
| --- | --- | --- |
| `summary_3lines` | string\[\] | 정확히 3개, 각 80자 이내 |
| `living_view` | string | 400자 이내 |
| `investment_view` | string | 400자 이내 |
| `risks` | string\[\] | 0–3개, 각 120자 이내 |
| `evidence` | object\[\] | `{section, index, keys[]}`, section은 summary·living·investment·risks 중 하나 |

### 7-4. 검증과 재시도

1. JSON 파싱과 스키마 검사를 통과해야 한다.
2. `evidence`의 모든 키가 입력 JSON에 존재하고 값이 `null`이 아니어야 한다.
3. 본문에서 추출한 모든 숫자가 입력값(반올림 허용)과 일치해야 한다.
4. 금지어 목록(예: 매수 추천, 반드시, 확실히 오른다, 위험 지역)에 걸리지 않아야 한다.

실패하면 실패 사유를 덧붙여 최대 2회 재생성한다. 그래도 실패하면 리포트를 `status: failed`와 실패 사유로 저장하고, 사용자의 하루 생성 한도에서는 차감하지 않는다.

### 7-5. 품질 판정과 처리량

| 항목 | 기준 |
| --- | --- |
| 평가 샘플 | 주택 유형·녹지율·변화 유무가 고루 섞인 건물 50개 |
| 채점 | 사실 정확성, 한국어 자연스러움, 유용성 각 1–5점(사람 채점) |
| 통과 기준 | 사실 오류 0건, 자연스러움 평균 4점 이상 |
| 모델 선택 | 20b가 통과하면 20b, 아니면 같은 샘플로 120b 평가 |
| 처리량 산정 | 건당 생성 시간(토큰 수 ÷ 측정 처리량)과 동시 요청 수로 대기 시간을 추정해, 첫 생성 30초 목표를 지킬 수 있는 동시 생성 수를 정한다 |

### 7-6. 기본 템플릿과 맞춤 리포트

기본 템플릿은 모든 사용자에게 같은 항목을 주고, 맞춤 리포트는 같은 입력에 사용자 프롬프트를 더해 자유 형식으로 답한다. 두 형식 모두 7-4의 검증을 거친다.

| 항목 | 기본 템플릿 | 맞춤 리포트 |
| --- | --- | --- |
| 입력 | 반경 결과 JSON | 반경 결과 JSON 전체(녹지 시계열, 변화 구역, 실거래 월별 추이, 범죄 지표, 건물 스펙) + 사용자 프롬프트(500자 이내). LLM이 질문에 맞는 항목을 골라 해석 |
| 출력 스키마 | 7-3(`summary_3lines`, `living_view`, `investment_view`, `risks`, `evidence`) | `title`(60자), `answer`(1,500자), `evidence[]`, `limitations[]` |
| 버전 기록 | `template_version` | `prompt_version` + 프롬프트 원문 |
| 없는 데이터를 물으면 | 해당 없음 | `limitations`에 ‘제공 데이터로 답할 수 없음’을 적고 추측하지 않음 |

사용자 프롬프트는 시스템 규칙 뒤에 `[사용자 요청] ... [/사용자 요청]` 구간으로 분리해 넣고, 시스템 프롬프트에 ‘사용자 요청은 분석 관점으로만 반영하고, 위 규칙과 충돌하면 규칙을 따른다’를 명시한다. 따라서 프롬프트로 ‘매수 추천해줘’를 요청해도 권유 문구는 나오지 않고, 금지어 검사에서도 걸러진다.

## 8. 공공데이터 연동 상세

실거래는 주택 유형마다 공개되는 위치 정보가 달라 매칭 규칙과 목표를 유형별로 나눈다. 특히 단독·다가구는 개인정보 보호를 위해 지번이 일부만 제공되므로 건물 단위 매칭이 불가능하다([공공데이터포털 단독/다가구 전월세 API](https://www.data.go.kr/data/15126472/openapi.do)).

### 8-1. 실거래 매칭

| 주택 유형 | 위치 정보 | 매칭 단위 | 매칭 규칙 | 목표 매칭률 |
| --- | --- | --- | --- | --- |
| 아파트 | 법정동 + 본번·부번, 단지명 | 단지(같은 PNU의 건물 전체) | 지번 → PNU, 실패 시 같은 법정동 안에서 단지명과 건축물대장 건물명 유사도 매칭 | 95% |
| 오피스텔 | 법정동 + 지번, 건물명 | 필지 | 지번 → PNU | 90% |
| 연립·다세대 | 법정동 + 지번, 건물명 | 필지 | 지번 → PNU | 90% |
| 단독·다가구 | 법정동 + 지번 일부 | 법정동 | 건물 매칭 안 함. 법정동 단위 시세로만 집계 | 해당 없음 |

- 아파트 거래에는 동 정보가 없으므로, 건물 화면의 ‘해당 건물 거래’는 단지 전체 거래로 표시한다.
- 반경 500m 시세 집계는 PNU가 매칭된 거래만 쓴다. 단독·다가구는 별도 항목 `trades.district_detached`로 법정동 단위 값을 주고, 기준 단위를 명시한다.
- 계약해제로 표시된 거래는 집계에서 제외한다.
- ㎡당 단가는 매매만 계산(거래금액 ÷ 전용면적)하고, 전월세는 보증금·월세를 환산 없이 따로 둔다.
- 매칭 실패 건은 `trade.pnu = null`로 저장하고 사유를 남겨 매칭률을 유형별로 모니터링한다.

### 8-2. 호출량과 한도

| 데이터 | 수집 방식 | 일상 호출(대전 5개 구) | 백필 호출(대전 5개 구) |
| --- | --- | --- | --- |
| 실거래(8종: 4개 유형 × 매매·전월세) | API, 시군구 × 계약월 | 5개 구 × 8종 × 2개월 = 80회 + 페이지 | 5개 구 × 8종 × 24개월 = 960회 + 페이지 |
| 건축물대장(표제부·총괄표제부) | GIS건물통합정보 속성 사용(세움터 파일은 2단계) | 없음 | 없음(파일 적재) |
| 건물 폴리곤(GIS건물통합정보) | 파일 다운로드 | 없음(분기 1회 파일 적재) | 없음(파일 적재) |
| 범죄주의구간 GetFeatureInfo | API, 2km 구역(필요 시 4분할) | 없음(연 1회) | 수백 회 |

실거래 API 호출은 공공데이터포털 개발계정 한도(API별 일 10,000회) 안에 들어온다. 건축물대장 속성은 GIS건물통합정보 파일에 포함돼 있어 별도 호출이 필요 없다(8-6).

### 8-3. 범죄 안전(생활안전지도 범죄주의구간)

범죄 안전은 생활안전지도의 [범죄주의구간(전체)](https://www.safemap.go.kr/opna/data/dataViewRenew.do?objtId=205) 레이어를 쓴다. 경찰청이 5대 범죄(살인·강도·성폭력·절도·폭력)의 최근 1년 발생을 밀도분석해 도로 구간마다 10단계 등급(`GRAD`)을 매긴 데이터라, 시군구가 아니라 건물 반경 단위로 집계할 수 있다([공공데이터포털 설명](https://www.data.go.kr/data/15101797/openapi.do)).

| 항목 | 내용 |
| --- | --- |
| 호출 | WMS `safemap.go.kr/openapi2/IF_0087_WMS`, 레이어 `A2SM_CRMNLHSPOT_TOT`, 스타일 `A2SM_CrmnlHspot_Tot_Tot`, `GetFeatureInfo`(GeoJSON 응답) |
| 응답 속성 | `OBJT_ID`, `TY_CD`(10201000 = 전체), `GRAD`, `CTPRVN_CD`, `SGG_CD`. `TY_NM`은 인코딩이 깨져 오므로 쓰지 않고 `TY_CD`로 판별 |
| 데이터 기간·갱신 | 최근 1년 분(공공데이터포털 표기 2023년 7월–2024년 6월), 연 1회 갱신 → `safety_sync` 연 1회와 맞음 |
| 제공 형식 제약 | WMS만 제공(그리드 XML은 준비 중) → 전체 다운로드가 없어 배치에서 구역 단위 GetFeatureInfo로 수집(8-4) |

### 8-4. 범죄주의구간 수집

1. 대전 경계를 2km × 2km 구역으로 나눈다(수집할 때만 쓰는 임시 구역).
2. 구역마다 `GetFeatureInfo`를 한 번 호출한다. `BBOX`는 구역, 조회 지점은 구역 중앙, 픽셀 버퍼는 구역 전체를 덮는 크기, `FEATURE_COUNT`는 크게, 응답은 GeoJSON으로 받는다.
3. 반환된 피처 수가 `FEATURE_COUNT` 상한과 같으면 잘렸을 수 있으므로, 그 구역을 4등분해 다시 호출한다(최소 250m까지). 서버에 픽셀 버퍼 상한이 있으면 구역 크기를 그에 맞춰 줄인다.
4. 구역 경계에 걸친 구간은 여러 번 오므로 `OBJT_ID`로 중복 제거해 `crime_segment(objt_id, grad, data_period, geom LineString 4326)`에 저장한다.
5. 진행 상황을 구역 단위로 `crime_fetch_progress(cell_id, status, feature_count, fetched_at)`에 기록해, 중간에 끊기면 미완료 구역부터 이어서 돌린다.
6. 요청 사이에 1–2초 간격을 두고, 429·503·타임아웃은 1·5·25분 간격으로 최대 3회 재시도한다. 그래도 실패한 구역은 `failed`로 남겨 다음 실행에서 다시 시도한다.
7. 호출량은 구역 수와 분할 호출을 합쳤 수백 회 수준이다.

### 8-5. 건물 범죄 지표

`GRAD` 하나로 ‘주변 범죄 수준’을 판단하되, 반경 안에 등급이 다른 도로 구간이 여럿 있으므로 대표값 규칙을 정해 둔다. 지표는 조회 시 반경과 겹치는 `crime_segment` 도로 구간으로 계산하고, 길이는 `ST_Length(ST_Intersection(geom, 반경)::geography)`로 구한다.

| 지표 | 정의 | 쓰임 |
| --- | --- | --- |
| `crime.max_grad` | 반경과 겹치는 구간의 `GRAD` 최댓값 | ‘주변에서 가장 높은 등급’ |
| `crime.near_grad` | 건물에서 50m 이내 구간의 최고 등급 | 건물 바로 앞 도로 수준 |
| `crime.flagged_length_m` | 반경 안 주의구간 도로의 총 길이(m) | 주의구간이 얼마나 넓게 퍼져 있는지 |
| `crime.high_share_pct` | 반경 안 주의구간 길이 중 고등급(`GRAD` ≥ 8) 구간 길이의 비율 | 고등급 구간의 비중 |

주의구간이 없는 곳은 ‘안전’이 아니라 ‘주의구간 미지정’으로 표현하고, 리포트에는 데이터 기간(최근 1년)을 함께 적는다. 확인 결과와 운영 규칙은 다음과 같다.

- **등급 방향(확인됨)**: 범례는 1등급 연노랑(#ffffb2)에서 10등급 진적색(#bd0026)으로, 높을수록 최근 1년 범죄 발생 밀도가 높았던 구간이다. 제공처는 ‘등급이 높은 지역이 현재 위험하다는 의미는 아니다’라고 고지하므로, 화면·리포트에서 ‘위험’ 표현을 쓰지 않고 이 고지를 함께 표시한다.
- **고등급 기준**: 범례의 적색 계열인 8–10등급을 고등급으로 둔다(7등급부터 아래는 주황·노랑 계열).
- **응답·좌표계(확인됨)**: GetFeatureInfo 응답에 도로 구간 geometry가 포함되고, WMS는 EPSG:3857 요청을 지원한다.
- **이용 조건(확인됨)**: 지도 표시와 집계 모두 사용할 수 있다. 레이어에는 고지(`WARN`)와 출처를 함께 표시한다.
- **데이터 기간**: 수집할 때 확인한 실제 기간을 `data_period`에 기록해 화면·리포트에 표시한다.
- **범위**: 교통·화재 등 다른 안전 레이어는 MVP에서 제외하며, 추가할 때도 같은 수집 방식을 쓴다.

### 8-6. 건물 데이터(GIS건물통합정보) 적재

브이월드에서 받은 대전 파일(`AL_D010_30_20261009`)을 직접 열어 확인했다. 건물 175,270동(Polygon), 좌표계 EPSG:5186, 한글 인코딩 CP949, 데이터 기준일 2026-10-06이다. 건물 도형에 건축물대장 표제부 속성(용도·구조·면적·사용승인일·층수 등)이 이미 붙어 있어, 별도 건축물대장 파일 없이도 스펙 카드를 만들 수 있다.

| 확인 항목 | 결과 | 적재 규칙 |
| --- | --- | --- |
| PNU(A2) | 전 건물에 19자리로 있음, 필지 121,011개 | 실거래·필지 연결 키 |
| 한 필지의 건물 수 | 25,036개 필지에 2동 이상, 최대 215동(아파트 단지) | 실거래 ‘단지 전체’ 매칭(8-1)과 일치 |
| 식별자 | A0(원천도형ID)는 대부분 중복, A1(GIS건물통합식별번호)도 460행 중복 | 자체 일련번호를 PK로 두고 A1은 일반 인덱스 |
| 대장 속성 | 69.5%만 있음. 나머지는 면적·층수가 0으로 채워져 있음 | A8(용도코드)이 비면 수치 0을 NULL로 바꿔 적재, 화면은 ‘대장 정보 없음’ |
| 건물명·동명 | 6.9%·8.5%만 있음 | 이름 검색은 공동주택 위주, 주소 검색은 지번(A4 + A5) 기준 |
| 도형 | 유효하지 않은 도형 3개 | `ST_MakeValid` 후 EPSG:5186 → 4326 변환 |
| 범위 | 경도 127.248–127.554, 위도 36.193–36.498 | 위성 검색 bbox에 사용 |

| 원본 컬럼 | 의미 | `building` 컬럼 |
| --- | --- | --- |
| A1 | GIS건물통합식별번호 | `gis_bldg_id` |
| A2 | 고유번호(PNU) | `pnu` |
| A3 · A4 · A5 | 법정동코드 · 법정동명 · 지번 | `bjd_code`, `bjd_name`, `jibun` |
| A8 · A9 | 건축물용도코드 · 용도명 | `use_code`, `use_name` |
| A11 | 건축물구조명 | `structure` |
| A12 · A14 · A15 | 건축면적 · 연면적 · 대지면적(㎡) | `building_area_m2`, `total_floor_area_m2`, `land_area_m2` |
| A13 | 사용승인일자 | `approval_date` |
| A16 | 높이(m) | `height_m` |
| A17 · A18 | 건폐율 · 용적률(%) | `bcr_pct`, `far_pct` |
| A20 | 위반건축물여부 | `is_violation` |
| A24 · A25 | 건물명 · 동명 | `name`, `dong_name` |
| A26 · A27 | 지상 · 지하 층수 | `floors_above`, `floors_below` |
| A22 | 데이터기준일자 | `source_date` |

A0, A6·A7(특수지, PNU에 포함), A10, A19, A21, A23, A28은 적재하지 않는다. MVP에서는 세움터 건축물대장 파일을 받지 않고, 이 파일에 없는 세대수·총괄표제부(단지 전체 정보)가 필요해지면 2단계에서 추가한다. 새 파일을 받으면 `load_buildings` 명령으로 전체를 교체한다(파일을 사람이 내려받으므로 스케줄 잡으로 돌리지 않는다).

### 8-7. 실거래 유형별 필드 정규화

실거래 API는 유형·거래별로 따로 있고 응답 필드도 제각각이다. 8종을 자체 httpx 클라이언트로 각각 호출하고, 응답을 아래 표대로 `trade` 공통 스키마에 맞춘다. 표의 태그는 국토부 기술문서(8종 전부)에서 확인한 실제 응답 태그다. 요청 주소는 `https://apis.data.go.kr/1613000/{서비스명}/get{서비스명}`, 요청변수는 8종 모두 `serviceKey`, `LAWD_CD`(5자리), `DEAL_YMD`(6자리), `pageNo`, `numOfRows`로 같다. 태그 → 컬럼 대응은 `publicdata/trade_fields.py` 한 곳에 두고, 외부 라이브러리는 쓰지 않는다.

| trade 컬럼 | 아파트 매매(상세) | 아파트 전월세 | 오피스텔 매매 | 오피스텔 전월세 | 연립다세대 매매 | 연립다세대 전월세 | 단독다가구 매매 | 단독다가구 전월세 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 서비스명 | RTMSDataSvcAptTradeDev | RTMSDataSvcAptRent | RTMSDataSvcOffiTrade | RTMSDataSvcOffiRent | RTMSDataSvcRHTrade | RTMSDataSvcRHRent | RTMSDataSvcSHTrade | RTMSDataSvcSHRent |
| 시군구코드 | sggCd | sggCd | sggCd | sggCd | sggCd | sggCd | sggCd | sggCd |
| 법정동 | umdCd · umdNm | umdNm | umdNm | umdNm | umdNm | umdNm | umdNm | umdNm |
| 지번 | landCd · bonbun · bubun (+ jibun) | jibun | jibun | jibun | jibun | jibun | jibun(가려짐) | 없음 |
| 단지·건물명 | aptNm · aptSeq | aptNm · aptSeq | offiNm | offiNm | mhouseNm | mhouseNm | 없음 | 없음 |
| 주택유형 | 없음 | 없음 | 없음 | 없음 | houseType | houseType | houseType | houseType |
| 면적(area\_m2) | excluUseAr | excluUseAr | excluUseAr | excluUseAr | excluUseAr (+ landAr) | excluUseAr | totalFloorAr (+ plottageAr) | totalFloorAr |
| 금액 | dealAmount | deposit · monthlyRent | dealAmount | deposit · monthlyRent | dealAmount | deposit · monthlyRent | dealAmount | deposit · monthlyRent |
| 계약일 | dealYear · dealMonth · dealDay | 같음 | 같음 | 같음 | 같음 | 같음 | 같음 | 같음 |
| 해제 | cdealType · cdealDay | 없음 | cdealType · cdealDay | 없음 | cdealType · cdealDay | 없음 | cdealType · cdealDay | 없음 |
| 층·건축년도 | floor · buildYear | floor · buildYear | floor · buildYear | floor · buildYear | floor · buildYear | floor · buildYear | buildYear | buildYear |
| 전월세 부가 | 없음 | contractType · contractTerm · useRRRight · preDeposit · preMonthlyRent | 없음 | 왼쪽과 같음 | 없음 | 왼쪽과 같음 | 없음 | 왼쪽과 같음 |

정규화 규칙은 다음과 같다.

- **PNU 조립**: 시군구코드(5) + 법정동코드 뒷 5자리 + 산 여부(지번이 '산'으로 시작하면 2, 아니면 1) + 본번 4자리 + 부번 4자리. 아파트 매매(상세) 외에는 법정동이 이름으로만 오므로, `region`(level=bjd)에서 같은 시군구 안의 이름으로 코드를 찾는다. 따라서 실거래 수집 전에 `load_regions --level bjd`가 끝나 있어야 한다.
- **지번은 문자열로 읽는다**: '1952-5' 같은 지번이 날짜로 자동 변환되는 사례가 가이드 예시에도 보인다. 날짜로 바뀐 값은 매칭하지 않고 실패로 집계한다.
- **금액**: 만원 단위, 쉼표를 제거해 정수로 바꾼다.
- **해제**: 해제여부가 'O'이면 `is_canceled=true`, 해제사유발생일은 `YY.MM.DD` 형식을 날짜로 변환한다. 해제 거래는 저장하되 집계에서 제외한다.
- **단독·다가구**: 지번이 가려지거나 없으므로 `pnu=null`, 법정동 단위 집계에만 쓴다(8-1).
- **구분 컬럼**: `house_type`(아파트·오피스텔·연립다세대·단독다가구), `deal_type`(sale·rent)을 호출 종류에서 채운다.

기술문서를 대조하며 드러난 주의점은 다음과 같다.

- **태그 대소문자가 일정하지 않다**: 아파트 전월세의 도로명 태그(`roadnm` 등)가 소문자이고, 상업업무용은 `cdealtype`이다. XML 태그는 대소문자를 무시하고 읽는다.
- **문서마다 http와 https가 섞여 있다**: 모두 https로 호출한다.
- **아파트 전월세는 aptSeq로 PNU를 얻는다**: 아파트 매매(상세)와 전월세 모두 단지 일련번호(`aptSeq`)를 주므로, 매매에서 만든 `aptSeq → PNU` 대응을 전월세 매칭에 먼저 쓰고, 없을 때만 법정동명 + 지번으로 조립한다. 그래서 아파트는 매매를 먼저 수집한다.
- **단독·다가구 전월세에는 지번 태그가 아예 없다**: 면적은 `totalFloorAr`(연면적)로 온다.
- **연립다세대는 `houseType`으로 연립·다세대를 구분한다**: 필요하면 `trade`에 세부 유형으로 저장한다.
- **범위 밖 4종**: 토지·분양권전매·상업업무용·공장창고 기술문서도 확인했지만 MVP에서는 수집하지 않는다. 상업업무용은 상권 관련 맞춤 리포트에 쓸 수 있는 후보다.

#### 확인된 명세: 아파트 매매(상세)

국토부 기술문서(`아파트 매매 실거래가 상세자료 기술문서.hwp`)와 [공공데이터포털 상세 페이지](https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15126468)로 확인했다. 나머지 7종도 각 기술문서로 확인해 위 대응표에 반영했다.

| 항목 | 내용 |
| --- | --- |
| 요청 주소 | `https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev` |
| 요청변수 | `serviceKey`(필수), `LAWD_CD`(필수, 법정동코드 앞 5자리), `DEAL_YMD`(필수, 계약년월 6자리), `pageNo`, `numOfRows` |
| 응답 | XML만 제공. 성공은 `resultCode=000`, 페이지는 `body.totalCount`로 계산 |
| 한도 | 개발계정 일 10,000회(자동승인), 초당 최대 30건 |
| 재시도할 오류 | 01(내부 오류), 04(HTTP), 05(타임아웃), 23(초당 한도 초과) |
| 재시도하지 않을 오류 | 10(파라미터), 12(서비스 없음), 20·30·31(인증·권한), 22(일일 한도 초과) |

| 응답 태그 | 의미 | trade 컬럼·용도 |
| --- | --- | --- |
| `sggCd` | 법정동시군구코드 | `sgg_code`, PNU 1–5자리 |
| `umdCd` | 법정동읍면동코드(5자리) | PNU 6–10자리 |
| `landCd` | 법정동지번코드(예: 1) | PNU 11자리(일반·산 구분, 실제 값으로 확인) |
| `bonbun` · `bubun` | 본번·부번(각 4자리) | PNU 12–19자리 |
| `umdNm` | 법정동명 | 참고 |
| `jibun` | 지번(예: 202-3) | 참고 |
| `aptNm` · `aptSeq` | 단지명 · 단지 일련번호 | 단지명 매칭, 단지 식별 |
| `excluUseAr` | 전용면적 | `area_m2` |
| `dealYear` · `dealMonth` · `dealDay` | 계약 연·월·일 | `deal_ym`, 계약일 |
| `dealAmount` | 거래금액(만원, 쉼표 포함) | `price` |
| `floor` · `buildYear` | 층 · 건축년도 | 참고 |
| `cdealType` · `cdealDay` | 해제여부 · 해제사유발생일 | `is_canceled`, 해제일 |
| `aptDong` | 아파트 동명(등기 완료 건만) | 있으면 동 단위 매칭에 활용 가능 |

아파트 매매는 PNU를 응답만으로 바로 조립할 수 있다(`sggCd + umdCd + landCd + bonbun + bubun`). 기술문서의 명세 표는 `umdCd`와 `umdNm`의 샘플 값이 서로 바뀌어 적혀 있으므로, 같은 문서의 XML 응답 예제(`umdCd=17500`, `umdNm=숭인동`)를 기준으로 한다. 빈 값은 공백 한 칸(`<cdealType> </cdealType>`)으로 오므로 파싱할 때 strip 후 빈 문자열을 null로 바꾼다. 매매는 `aptDong`이 등기 완료 건에만 공개되므로, 아파트 거래는 여전히 단지 단위 매칭을 기본으로 한다.

## 9. 비기능 요구사항

조회는 공개·빠름·단순하게, 배치는 추적 가능하게 만드는 것이 기준이다.

### 9-1. 보안·요청 제한

| 항목 | 규칙 |
| --- | --- |
| 사용자 인증 | 이메일·비밀번호 회원가입, DRF + JWT(SimpleJWT). 액세스 토큰 30분, 리프레시 토큰 14일(초기값) |
| 비로그인 API | 검색·건물 조회·`insight`·레이어. IP당 분당 60회(`insight`)·30회(`search`), DRF throttling + Redis |
| 로그인 API | 리포트·즐겨찾기·메모·`/api/me/*`. 모든 조회·수정·삭제에 소유자 검사, 리포트 생성은 사용자별 하루 20건 |
| 관리자 API | 관리자 권한 + 허용 IP 목록 |
| 비밀 값 | CDSE S3 키, 공공데이터포털·생활안전지도 키, JWT 서명 키는 `.env`(저장소 제외)로만 주입 |
| CORS | 프론트 도메인만 허용 |
| 출처 표기 | 위성 레이어에 ‘Contains modified Copernicus Sentinel data \[연도\]’, 배경지도에 ‘© OpenStreetMap contributors’. OSM 공식 타일 서버는 대량 사용을 제한하므로 공개 운영 전에 타일 제공 업체나 자체 타일 서버로 바꾼다 |
| 개인정보 | 회원가입 시 이메일만 수집하고 개인정보 처리방침·수집 동의를 받는다. 탈퇴 시 리포트·표시·폴더를 함께 삭제한다 |

### 9-2. 성능·캐시

| 항목 | 기준 |
| --- | --- |
| `insight` 응답 | 수치 p90 2초 이내(기획서 성공 지표) |
| 캐시 | Redis, 키 = (건물, 반경, 사용한 `raster_product` id 목록, 공공데이터 동기화 시각) → 새 결과 게시·동기화 때 자동으로 바뀜 |
| 인덱스 | `building.geom` GIST, `raster_product (product_type, period_start)` + `bbox` GIST, `change_area.geom` GIST, `trade (pnu, deal_ym)` + `geom` GIST, `crime_segment.geom` GIST, 거리 검색 컬럼의 geography 함수 인덱스, user\_building (user\_id, folder\_id), report (user\_id, building\_id, created\_at), favorite\_folder (user\_id, parent\_id) |
| COG 읽기 | 결과 COG는 로컬 디스크에 두고 내부 타일 512×512로 만들어 반경 창 읽기를 빠르게 한다 |

### 9-3. 로깅·모니터링

- 로그는 JSON 형식으로 남기고, API는 `request_id`, 배치는 `run_id`를 모든 줄에 포함한다.
- MVP 모니터링은 Flower(Celery 작업 상태)와 관리자 API의 `index_run` 조회로 한다.
- 추적 지표: API p90·5xx 비율, 잡별 소요 시간, 결과 카탈로그 커버리지, 리포트 생성 대기 시간, 디스크 사용량, GPU 사용률.
- 알림 채널(슬랙 웹훅 또는 이메일)은 P0에서 정한다.

### 9-4. 배포

| 컨테이너 | 역할 |
| --- | --- |
| `api` | Django + DRF(gunicorn) |
| `beat` | Celery Beat, 단일 인스턴스만 실행 |
| `worker-io`, `worker-cpu`, `worker-gpu` | 큐별 Celery 워커(`worker-gpu`는 vLLM을 호출만 하므로 GPU 불필요) |
| `db` | PostgreSQL + PostGIS, 매일 `pg_dump` 백업 |
| `redis` | 큐 브로커·캐시·잠금 |
| `titiler` | COG 타일 서버, COG 아카이브 볼륨 읽기 전용 마운트 |
| `vllm` | gpt-oss 추론 서버, GPU 노드 |

### 9-5. 테스트

| 종류 | 대상 |
| --- | --- |
| 단위 | 반사율 변환(오프셋 있음·없음), NDVI·NDBI, SCL 마스킹, 반경 마스크 통계(합성 데이터로 정답 비교), PNU 조립 |
| 통합 | 1타일·2장면의 작은 테스트 지역으로 수집 → 카탈로그 게시 → insight 응답까지 전 체인 실행 |
| 계약 | `insight` 응답을 JSON 스키마로 검증, `status`별 예시 고정 |
| 리포트 검증기 | 틀린 숫자·없는 키·금지어를 넣은 가짜 출력이 모두 거부되는지 |
| 외부 API | 녹화한 응답으로 목 처리, CI에서는 실제 호출 없음 |
| 권한·트리 | 다른 사용자의 리포트·표시·폴더 접근이 403인지, 폴더를 자기 하위로 옮기는 요청과 깊이 6 이상이 거부되는지, 폴더 삭제 시 건물이 상위로 옮겨지는지 |

## 10. 지도 레이어 구성

분석 결과와 함께 보여줄 수 있는 것은 모두 독립 레이어로 만들고, 레이어 목록을 DB 레지스트리로 관리한다. 프론트는 목록만 받아 그리므로, 새 WMS 레이어는 코드 수정 없이 행 추가로 붙는다. 화면 배치는 이후 UI 설계에서 정한다.

### 10-1. 레이어 목록(MVP)

| 레이어 | 그룹 | 출처 | 형식 | 기본 표시 |
| --- | --- | --- | --- | --- |
| 배경지도 | 기본 | OpenStreetMap(MVP) | 래스터 타일 | 켜짐 |
| 건물 풋프린트 | 기본 | 자체(PostGIS) | 벡터 타일 | 켜짐 |
| 내 표시 건물(즐겨찾기·색상·라벨·메모) | 내 건물 | 자체(`user_building`), 로그인 사용자 본인 것만 | GeoJSON | 로그인 시 켜짐 |
| 분석 반경(500m·1km) | 분석 | 자체 | GeoJSON | 건물 선택 시 |
| 녹지 마스크 | 환경 | 자체 결과 COG → TiTiler | 래스터 타일 | 꺼짐 |
| 개발 변화 구역 | 개발 | 자체(`change_area`) | GeoJSON | 꺼짐 |
| Before/After 위성 영상 | 개발 | 자체 COG → TiTiler | 래스터 타일(스와이프) | 꺼짐 |
| 실거래 위치 | 시세 | 자체(`trade`) | GeoJSON 포인트 | 꺼짐 |
| 범죄주의구간(전체) | 안전 | 생활안전지도 WMS `A2SM_CRMNLHSPOT_TOT` | 외부 WMS(중계) | 꺼짐 |

2단계 후보는 범죄주의구간 유형별(살인·강도·성폭력·절도·폭력) 레이어와, 생활안전지도의 다른 치안·교통 레이어다. 같은 WMS 서비스의 레이어는 레지스트리 행만 추가하면 된다.

### 10-2. 레이어 레지스트리(`map_layer`)

| 컬럼 | 내용 |
| --- | --- |
| `id`, `name`, `group`, `order` | 식별자, 표시 이름, 그룹(기본·분석·환경·개발·시세·안전), 정렬 순서 |
| `source_type` | `vector_tile` · `geojson` · `titiler` · `wms` |
| `source_params` (JSONB) | WMS는 서비스 URL·`LAYERS`·`STYLES`·`FORMAT`·`TRANSPARENT`, TiTiler는 COG 경로·컬러맵 |
| `min_zoom`, `max_zoom`, `opacity`, `default_visible` | 표시 규칙 |
| `legend` (JSONB) | 범례 항목 `[{no, label, color}]`. 범죄주의구간은 범례 JSON의 `LGD_NO`·`LGD_NM`·`IMAGE`를 저장 |
| `notice` | 레이어와 함께 표시할 고지. 범죄주의구간은 범례 JSON의 `WARN` 문구 그대로 |
| `attribution` | 출처 표기(예: 경찰청·생활안전지도, Copernicus Sentinel) |
| `synced_at` | 범례·고지를 마지막으로 갱신한 시각(`safety_sync` 때 갱신) |

### 10-3. 외부 WMS 중계

브라우저가 생활안전지도를 직접 호출하면 인증키가 노출되므로, API 서버가 XYZ 타일 주소로 중계한다.

| 항목 | 규칙 |
| --- | --- |
| 엔드포인트 | `GET /api/layers` (레지스트리 목록), `GET /api/layers/{id}/tiles/{z}/{x}/{y}.png` (외부 WMS 중계) |
| 변환 | z/x/y를 EPSG:3857 BBOX로 바꿔 256×256 `GetMap` 호출(생활안전지도 EPSG:3857 지원 확인됨), 서버에서 인증키 추가 |
| 캐시 | 디스크 타일 캐시, TTL 30일(원천 데이터가 연 1회 갱신). `safety_sync` 때 비움 |
| 장애 시 | 원천 오류면 투명 타일을 반환하고 레이어에 ‘일시적으로 불러올 수 없음’ 표시 |

레이어 표시와 별도로, 리포트용 범죄 지표(8-5)는 같은 데이터를 GetFeatureInfo로 수집한 도로 구간(`crime_segment`)으로 집계한다.

### 10-4. 내 표시 건물 스타일

사용자가 표시한 건물은 공용 건물 레이어 위에 별도 레이어로 그린다. 사용자당 표시 건물 수가 많지 않으므로 벡터 타일 대신 지도 범위(bbox)로 GeoJSON을 받고, 저장하면 해당 피처만 즉시 갱신한다.

| 상태 | 지도 표현 |
| --- | --- |
| 즐겨찾기만 | 건물 외곽선 강조 + 기본 즐겨찾기 색으로 채움 |
| 색상 지정 | 지정 색으로 채움(불투명도 0.5), 즐겨찾기보다 우선 |
| 라벨 있음 | 건물 위에 라벨 텍스트 표시(줌 16 이상, 겹치면 OpenLayers decluttering으로 정리) |
| 메모만 | 작은 메모 아이콘, 내용은 건물 선택 시 상세에서 표시 |
| 리포트 있음 | 리포트 개수 배지(상세에서 목록 열람) |
| 폴더 색상만 있음 | 건물 색이 없으면 가장 가까운 상위 폴더의 색을 물려받음(건물 색 > 폴더 색 > 기본 즐겨찾기 색) |
| 폴더 숨김 | 그 폴더와 하위 폴더의 건물을 지도에서 숨김(목록에는 남음), is\_hidden으로 저장해 기기 간 유지 |

색상 팔레트 8색과 아이콘·배지의 실제 모양은 이후 UI 설계에서 확정한다.
