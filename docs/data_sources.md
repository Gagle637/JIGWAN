# 데이터 출처·이용 조건

지관(JIGWAN)이 쓰는 모든 외부 데이터의 제공처·이용 조건·표시 의무를 정리한다. 레이어별
`attribution`·`notice` 문구는 `backend/layers/management/commands/seed_map_layers.py`가
이 문서와 같은 내용으로 `map_layer`에 심는다. 프론트는 `/api/layers` 응답의
`attribution`을 그대로 지도 하단 출처 표시에 쓰면 된다(docs/imagery_api.md 참고).

## 1. Sentinel-2 위성 영상(Copernicus)

| 항목 | 내용 |
| --- | --- |
| 제공처 | European Space Agency(ESA) / Copernicus Data Space Ecosystem(CDSE) |
| 데이터 | Sentinel-2 L2A, 10~20m 해상도 |
| 이용 조건 | [Copernicus Sentinel Data Terms and Conditions](https://sentinels.copernicus.eu/documents/d/sentinel/sentinel-data-legal-notice) — 무료, 재배포 가능. **공공누리가 아니라 Copernicus 자체 조항**이라 문구를 그대로 지켜야 한다 |
| 필수 표시 문구 | `Contains modified Copernicus Sentinel data [연도]` — 연도는 실제 촬영/합성 계절의 연도. 여러 연도가 섞이면 범위로(`2025–2026`) |
| 적용 레이어 | 녹지 마스크(`green_mask`), Before/After 위성 영상(`before_after`) — 지역·계절별로 `source_params.regions[].attribution`에 연도가 들어간다. 개발 변화 구역(`change_area`)도 Sentinel 파생 결과라 같은 고지가 필요하지만, 이 레이어는 아직 지역별 목록 동기화 대상이 아니라 연도 없는 정적 문구를 쓴다 |

## 2. 건물·행정경계(브이월드)

| 항목 | 내용 |
| --- | --- |
| 제공처 | 국토교통부 브이월드(V-World) |
| 데이터 | GIS건물통합정보(`AL_D010`, 건물 풋프린트), 법정구역정보(`AL_D001`, 시도/시군구 경계) |
| 이용 조건 | 공공데이터포털 공공누리 제1유형(출처표시) |
| 공공누리 정식 문구 | "본 저작물은 '공공누리 제1유형'에 따라 국토교통부의 공공저작물(브이월드 GIS건물통합정보, 법정구역정보)을 이용하였으며, 해당 저작물은 브이월드(www.vworld.kr)에서 무료로 다운받으실 수 있습니다." |
| 적용 레이어 | 건물 풋프린트(`building_footprint`) — attribution: `브이월드 GIS건물통합정보` |
| 비고 | 법정구역정보는 경계·격자 계산에만 쓰고 별도 지도 레이어로는 안 보여준다(그래서 레이어 목록엔 "경계"가 따로 없음) |

## 3. 실거래가(국토교통부)

| 항목 | 내용 |
| --- | --- |
| 제공처 | 국토교통부 실거래가 공개시스템, 공공데이터포털 API |
| 이용 조건 | 공공누리 제1유형, API 키 필요(일 10,000회 한도, `docs/spec.md` 8-2) |
| 공공누리 정식 문구 | "본 저작물은 '공공누리 제1유형'에 따라 국토교통부의 공공저작물(아파트 매매 실거래가 등)을 이용하였으며, 해당 저작물은 공공데이터포털(www.data.go.kr)에서 무료로 다운받으실 수 있습니다." |
| 적용 레이어 | 실거래 위치(`trade_location`) — attribution: `국토교통부 실거래가 공개시스템(공공데이터포털)` |

## 4. 범죄주의구간(경찰청)

| 항목 | 내용 |
| --- | --- |
| 제공처 | 경찰청 생활안전지도(안전Dream), WMS |
| 데이터 | 범죄주의구간(전체) `A2SM_CRMNLHSPOT_TOT`, 최근 1년 범죄 발생 밀도 등급(1~10등급) |
| 이용 조건 | 생활안전지도 자체 제공 약관. **경찰청 요청으로 "등급이 높다고 현재 위험하다는 뜻은 아님"** 고지를 레이어와 함께 반드시 표시(`map_layer.notice`, `layers/fixtures/crime_legend_tot.json`의 `WARN` 필드) |
| 적용 레이어 | 범죄주의구간(전체)(`crime_hotspot`) — attribution: `경찰청 생활안전지도` |
| 비고 | CLAUDE.md 규칙: "위험" 표현 금지, '최근 1년 범죄 발생 밀도'로만 표현 |

## 5. 배경지도(OpenStreetMap)

| 항목 | 내용 |
| --- | --- |
| 제공처 | OpenStreetMap contributors |
| 이용 조건 | [ODbL(Open Database License)](https://www.openstreetmap.org/copyright) |
| 필수 표시 문구 | `© OpenStreetMap contributors` |
| 적용 레이어 | 배경지도(`osm_basemap`) |
| 비고 | 지금은 OSM 공식 타일 서버(`tile.openstreetmap.org`)를 그대로 쓴다 — 공개 운영 전에는 대량 사용 제한 때문에 자체 타일 서버나 상용 타일 제공자로 교체해야 한다 |

## 6. 자체 데이터(외부 출처 없음)

내 표시 건물(`my_buildings`)·분석 반경(`analysis_radius`)은 사용자 조작·서버 계산으로만
만들어지는 데이터라 외부 출처가 없다 — `attribution`을 비워 둔다(사용자 결정).

## 7. 항공사진(보류)

docs/spec.md 10-5에 정의된 "건물 확대 배경"용 항공사진 영상지도 API(브이월드 또는
국토지리정보원 WMTS)는 아직 레이어로 추가하지 않았다. 추가할 때 이 문서에 제공처·이용
조건·촬영 시점 안내 문구를 채운다.
