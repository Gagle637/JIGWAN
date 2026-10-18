# 지관(地官, JIGWAN)

대전 건물 단위 입지 분석 웹 서비스(사이드 프로젝트). 설계는 docs/plan.md(기획서)와
docs/spec.md(기술 명세)가 기준이다. 설계와 다르게 구현해야 하면 먼저 물어볼 것.

## 스택
- Backend: Python 3.11, Django + DRF, Celery + Redis(+ django-celery-beat), PostgreSQL 16 + PostGIS
- Raster: rasterio, numpy, geopandas, shapely, pystac-client
- Tiles: TiTiler(Docker)
- LLM: gpt-oss-20b, OpenAI 호환 API(vLLM 또는 로컬 Ollama). base_url은 환경 변수
- Frontend: Vue 3(Composition API) + Pinia + Tailwind, OpenLayers, Chart.js
- 실행: docker compose

## 반드시 지킬 규칙
- 벡터는 전부 EPSG:4326 geometry로 저장한다. 미터 계산은 ::geography
  (ST_Buffer, ST_DWithin, ST_Area, ST_Length). 4326에 바로 ST_Buffer(geom, 500) 금지.
- 위성 COG는 EPSG:32652를 유지한다. 래스터를 재투영하지 말고, 반경 폴리곤을 COG 좌표계로 바꿔 마스크한다.
- 화면 표출은 EPSG:3857.
- 건물별 결과를 미리 계산·저장하지 않는다. 배치는 raster_product(결과 카탈로그)에 결과를 쌓고,
  조회 시 반경만 읽어 계산한다.
- Sentinel-2 반사율은 장면마다 MTD_MSIL2A.xml의 BOA_ADD_OFFSET, BOA_QUANTIFICATION_VALUE로
  변환한다. 하드코딩 금지.
- 모든 배치 잡은 멱등(같은 키 재실행 시 같은 결과)이고 index_run에 기록한다.
- 범죄 등급은 '최근 1년 범죄 발생 밀도'로만 표현한다. '위험' 표현 금지.
- 리포트: 입력에 없는 수치 금지, 매수·매도 권유 금지, 검증기를 통과한 것만 저장.
- API 키, CDSE S3 키, JWT 서명 키는 .env로만 넣고 커밋하지 않는다.
- 테이블·컬럼·API 경로 이름은 docs/spec.md, docs/plan.md의 이름을 그대로 쓴다.

## 작업 방식
- 단계마다 계획(만들 파일, 마이그레이션, 테스트)을 먼저 보여주고 승인 후 구현한다.
- 외부 API(CDSE, 실거래, 생활안전지도, LLM)는 테스트에서 녹화한 응답으로 목 처리한다.
- 끝나면 실행 방법과 확인 방법(명령어)을 요약한다.

## 디렉터리
backend/   Django 프로젝트(config/) + 앱: buildings, satellite, publicdata, crime,
           reports, accounts, favorites, layers
frontend/  Vue 앱
docker/    compose·이미지 설정
data/raw/  원본 파일(git 제외)
docs/      plan.md, spec.md