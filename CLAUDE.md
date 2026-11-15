# 지관(地官, JIGWAN)

대전 건물 단위 입지 분석 웹 서비스(사이드 프로젝트). 설계는 docs/plan.md(기획서)와
docs/spec.md(기술 명세)가 기준이다. 설계와 다르게 구현해야 하면 먼저 물어볼 것.

## 스택
- Backend: Python 3.11, Django + DRF, Celery + Redis(+ django-celery-beat), PostgreSQL 16 + PostGIS
- Raster: rasterio, numpy, geopandas, shapely, pystac-client
- Tiles: TiTiler(Docker)
- LLM: gpt-oss-20b, OpenAI 호환 API. 기본은 로컬 Ollama, vLLM은 선택(GPU 있을 때). base_url은 환경 변수
- Frontend: Vite + React + TypeScript, Tailwind CSS(v4, `@tailwindcss/vite`), Zustand(화면 상태),
  TanStack Query(서버 데이터), React Router, OpenLayers, Chart.js(react-chartjs-2). 패키지 매니저 npm
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

## 프론트엔드 규칙
- 폴더: `src/app`(App·router·RootLayout 등 앱 구성), `src/pages`(기능을 조립해 화면을 만듦),
  `src/features/<기능>`(그 기능의 컴포넌트·훅·스토어·`queries.ts`·순수 함수 — `types.ts`는 두지
  않음), `src/types/<백엔드 리소스>.ts`(여러 곳이 쓰는 타입·API 응답·도메인 데이터 타입),
  `src/components/ui`(기능과 무관한 공용 UI), `src/lib`(공용 유틸), `src/api/fetch.ts`(API 호출
  한 곳).
- 의존 방향: `pages → features → components/ui·lib·api`. 기능끼리는 서로 import하지 않는다
  (지도 기반인 `features/map`만 예외 — 다른 기능이 지도 인스턴스·레이어 훅을 가져다 쓸 수 있다.
  반대 방향은 금지).
- 라우팅은 React Router. 공통 레이아웃 라우트 아래에 페이지를 두는 구조(페이지를 늘릴 수 있게).
  없는 경로는 `/`로 보낸다. 로그인·회원가입·마이페이지 같은 경로는 그 기능을 만드는 단계에서
  라우트·헤더 링크를 같이 추가한다(미리 자리만 만들지 않음).
- 서버 데이터는 TanStack Query로만 다룬다. Zustand에는 화면 상태(선택한 건물, 반경, 레이어
  켜짐, 패널 열림 등)만 둔다.
- export는 named만 쓴다(`vite.config.ts`, `eslint.config.js` 같은 설정 파일은 예외).
  `as` 타입 단언은 `src/api/fetch.ts` 밖에서 쓰지 않는다. `eslint-disable` 주석을 쓰지 않는다.
- API 응답 형태는 추측하지 않는다. backend의 해당 뷰 코드와 docs/spec.md 6장으로 확인해서
  전역 `src/types/`에 백엔드 리소스 단위 파일로 적는다(`layer.ts`, 이후 `insight.ts`·`report.ts`·
  `favorite.ts`·`auth.ts`). 인터페이스 하나당 파일 하나로 쪼개지 않고, `index.ts`로 묶어 내보내지
  않는다(`@/types/layer`처럼 바로 import). `src/types/`의 파일에는 타입만 둔다(실행 코드 없음,
  `features`·`components`·`lib`·`api`를 import하지 않음). 한 파일만 쓰는 타입(props, 옵션)은 그
  파일 위쪽에 두고, 30줄을 넘으면 같은 폴더의 `<파일이름>.types.ts`로 뺀다. 아무도 import하지
  않는 타입은 `export`를 떼어 내부 전용으로 둔다. 필드 이름은 백엔드의 snake_case 그대로 쓴다
  (변환 계층 없음). `source_type`처럼 값에 따라 모양이 갈리는 타입은 구분 유니온으로 정의한다.
  객체 모양은 `interface`, 유니온·별칭은 `type`. props 타입 이름은 `<컴포넌트>Props`, `I` 접두사·
  `Type` 접미사는 쓰지 않는다.
- 반경 도형은 직접 그리지 않는다. `insight.radius_geometry`를 그대로 그린다.
- 좌표: API 입출력은 EPSG:4326, 지도 표출은 EPSG:3857.
- 문구: '위험', '안전'이라고 쓰지 않는다. 범죄는 '최근 1년 범죄 발생 밀도 등급'(데이터 없으면
  '주의구간 미지정'), 개발 변화는 '개발 징후'. 값이 없는 항목은 숨기지 말고 '데이터 없음'과
  사유를 보여준다.
- 지표·리포트 옆에는 데이터 기준일(`as_of`)과 '투자 자문이 아닌 참고 정보' 고지를 둔다.
- 레이어를 켜면 그 레이어의 출처(attribution)와 고지(notice)가 함께 보여야 한다.
- 디자인은 Tailwind 기본으로 절제해서 만든다. UI 라이브러리·디자인 시스템은 먼저 묻지 않고
  추가하지 않는다. 색은 `index.css`의 `@theme` 토큰 클래스(`bg-primary`, `text-foreground-muted`
  등)만 쓴다 — `slate-900` 같은 원색 클래스 금지. 토큰을 새로 추가할 때는 계획에 적는다.
- `backend/`, `docs/`는 프론트엔드 작업에서 수정하지 않는다. API가 부족하거나 문서와 다르면
  고치지 말고 보고한다.
- 테스트는 지금 쓰지 않는다(당분간).
- 서버 요청은 `apiFetch(path, { method, json, params, signal })`로만 한다. 기본 주소·헤더·
  에러 변환·인증 토큰은 `src/api/fetch.ts` 한 곳에 모은다(다른 파일에서 `import.meta.env`를
  직접 읽지 않음). 쿼리는 기능별 `queries.ts`에 TanStack의 `queryOptions`로 정의하고, `queryFn`이
  TanStack이 주는 `signal`을 `apiFetch`에 넘겨 요청이 취소되게 한다.
- 공용 컴포넌트(`src/components/ui`)는 실제로 필요해지는 단계에서 추가한다(같은 클래스 묶음이
  두 곳 이상 나오면 그때 올린다). 모양 변형은 `variant`·`size` props로 받고, 바깥에서 받은
  `className`은 `cn()`으로 병합, 네이티브 속성(`type`·`disabled`·`onClick` 등)은 그대로 전달한다.
  `features`를 import하지 않는다.
- 지도 레이어: `source_type`별 조합마다 OL 클래스를 상속한 클래스를 `features/map/layers/`에
  두고, `createOlLayer`(switch + `never` 검사로 빠뜨린 형식을 컴파일 에러로 잡음)로 만들어
  `useOlLayer`로 지도에 붙이고 뗀다. 컴포넌트에서 레이어·소스를 직접 `new`하거나
  `addLayer`·`removeLayer`를 부르지 않는다. 레이어 컴포넌트는 화면을 그리지 않는다(안내
  문구 같은 지도 위 UI는 분리된 컴포넌트에 둔다). `layers/` 안에는 React를 import하지 않는다.
  지도 색은 `mapStyle.ts`, 코드가 아는 레이어 slug는 `layerSlugs.ts`, 쌓이는 순서는 `zIndex.ts`에
  모은다.
- 아직 없는 기능의 자리(빈 페이지, 빈 링크, placeholder)는 만들지 않는다. 그 기능을 만드는
  단계에서 같이 추가한다.
- 파일 안 순서: import → 타입 → 상수 → 보조 함수 → 내보내는 함수·컴포넌트·클래스.
  단, 같은 파일의 다른 코드가 쓰는 클래스(에러 클래스 등)는 타입 바로 다음에 둔다.
- 스타일은 Tailwind 클래스로 쓴다. 컴포넌트별 CSS 파일은 만들지 않는다. CSS를 직접 써야 하면
  (외부 라이브러리 스타일 덮어쓰기, 스크롤바, 키프레임) `src/styles/`에 주제별 파일로 두고
  `index.css`에서 불러온다. 컴포넌트는 기본적으로 파일 하나(`<이름>.tsx`)로 두고, 하위
  컴포넌트가 생기면 `<이름>/` 폴더로 올린다(`index.tsx`는 쓰지 않고 폴더 안 파일에도 이름을
  붙인다).
- 상수 이름은 camelCase로 쓴다(전부 대문자 이름을 쓰지 않는다).
- 주석은 지우면 버그가 나는 우회 코드의 이유 한 줄만 남긴다. 작업 과정·단계 설명, 코드를
  풀어 쓴 설명, 좌표계 같은 공통 규칙은 주석으로 쓰지 않는다.
- import는 `@/` 별칭(src 기준)을 쓴다. 같은 폴더 안은 `./`로 두고, 그 밖은 `@/`로 쓴다.
- 세미콜론·작은따옴표(JSX 속성은 큰따옴표)·import 순서는 직접 맞추지 말고 `npm run lint:fix`로
  맞춘다. `./index.css`·`ol/ol.css`처럼 사이드이펙트용 CSS import는 이 규칙이 정렬하지 않으니
  항상 파일 맨 아래에 둔다.
- 조건부 클래스·클래스 병합은 템플릿 문자열로 잇지 말고 `src/lib/cn.ts`의 `cn()`을 쓴다.

## 작업 방식
- 단계마다 계획(만들 파일, 마이그레이션, 테스트)을 먼저 보여주고 승인 후 구현한다.
- 외부 API(CDSE, 실거래, 생활안전지도, LLM)는 테스트에서 녹화한 응답으로 목 처리한다.
- 끝나면 실행 방법과 확인 방법(명령어)을 요약한다.
- 실제 데이터(DB·data/·docker/data/)에 삭제·덮어쓰기를 일으키는 명령은 dry-run 결과를
  먼저 보여주고 사용자 승인 후 실행한다. 스모크 테스트는 테스트 DB나 복사본에서만 한다.
- 테스트는 운영 폴더(data/, docker/data/ 등)에 파일을 쓰지 않는다.
- 커밋과 푸시는 사용자가 한다. 작업이 끝나면 git add까지만 하고 커밋 메시지를 추천한다.

## 디렉터리
backend/   Django 프로젝트(config/) + 앱: buildings, satellite, publicdata, crime,
           reports, accounts, favorites, layers, core, demo
backend/prompts/  리포트 LLM 프롬프트 템플릿
frontend/  Vite+React+TS 앱. src/app(App·router·RootLayout), src/pages(기능 조립),
           src/features/<기능>(컴포넌트·훅·스토어·queries.ts, 지금은 map만 있음),
           src/types(리소스별 타입, 지금은 layer.ts만 있음),
           src/components/ui(공용 UI), src/lib, src/api/fetch.ts
docker/    compose·이미지 설정
data/raw/  원본 파일(git 제외)
docs/      plan.md, spec.md