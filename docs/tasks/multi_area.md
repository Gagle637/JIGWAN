# 다지역 지원(area) 작업 목록

목표: `./scripts/areas.sh`를 실행하면 현재 서비스 지역과 추가 가능한 지역을 보여주고,
고른 지역에 필요한 작업이 자동으로 순서대로 진행되는 구조. 지역은 "추가"(기존 지역은 그대로
두고 새 지역을 더하는 것)다. 시도 코드는 사람이 입력하지 않고, `data/raw/AL_D001_00_*.zip`의
SIG 레이어에서 자동으로 뽑아 보여준 목록 중에서 고른다.

## 작업 방식(매 단계 공통)

1. 이 단계를 시작하기 전에 계획(만들/고칠 파일, 마이그레이션 여부)을 먼저 보여주고 승인받는다.
2. 구현한다.
3. 다음을 전부 실행해 결과를 보고한다: `manage.py check`, `makemigrations --check --dry-run`,
   빈 DB에서 `migrate`, 전체 `pytest`.
4. 커밋한다.
5. 멈춘다 — 사용자가 "다음 단계 진행해줘"라고 할 때만 다음 단계를 시작한다.

대화가 요약되면 이 문서를 다시 읽고 어느 단계까지 끝났는지(커밋 로그 확인) 파악한 뒤 이어서 한다.

## 격자(grid) 결정 사항(중요, 2026-10-25 확정)

- `service_area`에 `bbox`와 `grid`(EPSG:32652, 10m, minx/miny/maxx/maxy/width/height)를 **저장**한다.
- 지역을 추가할 때(`areas add` 직후, 경계 적재가 끝난 뒤) 딱 한 번만 계산한다: 해당 시도
  `region`(level=sido) 경계의 bbox + 여유 500m를 EPSG:32652로 변환 후 60m 배수로 바깥쪽 스냅.
- **이미 값이 있으면 절대 다시 계산하지 않는다** — `load_regions`로 경계를 다시 적재해도 저장된
  grid는 그대로다(이미 그 격자로 써 둔 위성 COG가 있을 수 있어서, 조용히 바뀌면 안 됨).
- `get_bbox(area)`/`get_grid(area)`는 저장된 값만 읽는다. 없으면 계산하지 말고 에러를 낸다.
- 대전(30)도 같은 규칙으로 **새로 계산**한다(1단계 시점엔 아직 실제 위성 COG가 없어 안전).
  기존 `DAEJEON_GRID` 상수와 "같은 값"인지 테스트하지 않는다 — 대신 "`load_regions`로 경계를
  다시 적재해도 저장된 grid가 바뀌지 않는다"를 테스트한다.
- 격자를 의도적으로 바꿔야 할 때를 위해 `areas regrid <코드>`를 별도 명령으로 둔다. 실행 전
  "기존 위성 결과를 전부 다시 만들어야 한다"는 경고를 띄우고 확인을 받는다(2단계 이후 구현).

## 단계 목록

### 1. `service_area` 테이블 + 지역 해석 함수

**파일**: `backend/core/models.py`(`ServiceArea` 모델 추가), 새 마이그레이션(+대전 30 초기
데이터 시딩하는 데이터 마이그레이션), `backend/core/areas.py`(신설) — `get_bbox(sido_code)`,
`get_grid(sido_code)`, `get_sgg_codes(sido_code)`(Region 테이블에서 실시간 조회),
`compute_and_store_grid(sido_code)`(위 결정 사항의 1회성 계산·저장, 이미 값 있으면 멱등하게
건너뜀), `discover_available_areas(path)`(AL_D001 zip의 SIG 레이어에서 시도 코드별 이름·
시군구 수 추출).

**필드**: `sido_code`(PK, 2자리), `name`, `enabled`(bool), `added_at`(auto_now_add),
`bbox_minx/miny/maxx/maxy`(nullable float, 4326), `grid`(nullable JSONField).

**기존 코드는 이 단계에서 바꾸지 않는다** — 다음 단계들이 하드코딩을 이 함수들로 교체한다.

**완료 기준**: `ServiceArea.objects.get(sido_code="30").name == "대전광역시"`,
`compute_and_store_grid("30")`을 두 번 불러도 grid 값이 안 바뀜(멱등) 테스트,
`discover_available_areas(실제 AL_D001 zip)`이 16개 시도(30 대전 5개 구 포함)를 돌려주는지
확인(실제 파일로, 테스트는 합성 zip으로).

### 2. 위성 쪽 하드코딩 교체

**파일**: `backend/satellite/stac_search.py`(`DAEJEON_BBOX` 제거, `search_scenes`가 bbox를
`get_bbox()`로 받음), `backend/satellite/cog.py`(5곳: `grid_transform`, `reproject_band_to_grid`,
`write_cog_atomic`, `iter_grid_blocks`, `open_cog_writer` — `settings.DAEJEON_GRID` 대신 `grid`
파라미터를 받게), `backend/satellite/catalog.py`(`_grid_matches`·`_measure_valid_ratio`·
`_daejeon_aoi_32652`가 `settings.DAEJEON_GRID`·`region_code="30"` 하드코딩 대신 파라미터/
RasterProduct.region_code 사용), `backend/satellite/ingest.py`, `backend/satellite/composite.py`,
그리고 이 함수들을 부르는 `season_chain.py`·`tasks.py`·관리 명령들. `config/settings.py`의
`DAEJEON_GRID` 상수는 제거.

**완료 기준**: 기존 `satellite/tests/test_cog.py`·`test_catalog.py`·`test_ingest.py`가
`settings.DAEJEON_GRID` 대신 테스트용 grid를 직접 만들어 통과. 전체 pytest 통과.

### 3. 실거래·범죄 하드코딩 교체

**파일**: `backend/publicdata/trade_fields.py`(`SGG_CODES` 제거), `backend/publicdata/sync.py`
(`get_sgg_codes()` 호출), `backend/publicdata/management/commands/backfill_trades.py`(`--sido`
또는 `--area` 옵션 추가), `backend/crime/grid.py`(`DAEJEON_BBOX` 대신 `get_bbox()`).

**완료 기준**: `get_sgg_codes("30")`이 실제 Region 데이터로 대전 5개 구를 돌려줌(이미 1단계
테스트에서 검증된 함수 재사용). 전체 pytest 통과.

### 4. 건물 적재 지역화

**파일**: `backend/buildings/building_loading.py`(파일명 패턴 `AL_D010_30_*.zip` →
`AL_D010_{sido}_*.zip`, sido 파라미터화), `backend/buildings/management/commands/load_buildings.py`,
`backend/core/gis_load.py`(`sync_geotable`의 소프트 삭제 UPDATE에 지역 범위 조건 추가 —
현재는 전체 테이블 기준이라 다른 지역 건물까지 soft-delete될 위험이 있음).

**완료 기준**: "세종 건물을 적재해도 기존 대전 건물이 그대로 `is_active=True`로 남는다" 테스트
추가·통과. 전체 pytest 통과.

### 5. `raster_product` 지역 컬럼

**파일**: `backend/satellite/models.py`(`RasterProduct.region_code` 추가, 마이그레이션),
재계산 키(캐시 키 등)에 포함되는 곳, COG 파일 경로 조립 로직(지역 포함하도록).

**완료 기준**: 새 마이그레이션 적용 후 `makemigrations --check` 깨끗함. 관련 테스트 갱신·통과.

### 6. `satellite_scene` 유일 키 + crime 수집 지역 구분

**파일**: `backend/satellite/models.py`(`SatelliteScene`의 unique 제약을 `(scene_id, region_code)`로,
마이그레이션), `backend/crime/models.py`(`CrimeFetchProgress`에 `region_code` 추가 여부 — 셀
좌표가 지역마다 겹칠 가능성이 낮아도 명시적으로 구분해 두는 게 안전, 마이그레이션),
`backend/crime/collect.py`.

**완료 기준**: 두 지역이 같은 `scene_id`를 가져도 DB에서 별개로 저장되는 테스트. 전체 pytest 통과.

### 7. 잠금·index_run 지역화 + 정기 배치 다지역화

**파일**: `backend/crime/collect.py`·`management/commands/run_safety_sync.py`·
`probe_crime_feature_cap.py`, `backend/satellite/tasks.py`·`season_chain.py`·
`management/commands/backfill.py`·`collect_scenes.py`, `backend/publicdata/tasks.py`·
`backfill_trades.py` — `tracked_run`/`tracked_job`에 넘기는 `region_code="daejeon"` 고정 문자열을
시도 코드 기반으로. `trade_sync`·`satellite_collect`·계절 체인·`safety_sync`의 Celery Beat
주기 작업이 `ServiceArea.objects.filter(enabled=True)`를 돌며 지역별로 실행되게.

**완료 기준**: 비활성화(`enabled=False`) 지역은 정기 배치에서 건너뛰는 테스트. 전체 pytest 통과.

### 8. `areas` 관리 명령 — list/status/add/disable

**파일**: `backend/core/management/commands/areas.py`(신설). 하위 명령: `list`(등록된 지역 +
활성화 상태), `status`(지역별 단계 진행 상황), `add <코드>`(`discover_available_areas` 목록에서
고른 코드로 `service_area` 행 생성), `disable <코드>`.

**완료 기준**: `manage.py areas list`가 대전을 보여줌, `manage.py areas add 36`이 세종을
비활성 상태로 추가(실제 수집은 안 함). 전체 pytest 통과.

### 9. `areas sync` — 지역별 전체 백필 파이프라인

**파일**: `backend/core/management/commands/areas.py`(`sync [--area 코드] [--dry-run]` 추가).
순서: (1) 경계 적재(전국 AL_D001에서 해당 시도만 sigungu→bjd→sido union) (2) 건물 적재
(3) 실거래 24개월 백필 (4) 위성 13계절 백필 (5) 범죄 상한 측정·수집. 이미 끝난 단계는
건너뛴다(각 단계를 `tracked_run`으로 기록해 판단). 원본 파일(`AL_D001_00_*`, `AL_D010_{sido}_*`)이
없으면 그 단계에서 멈추고 어디서 받는지(브이월드 "GIS건물통합정보" 등)·파일명 형식·넣을 위치를
안내한다.

**완료 기준**: `--dry-run`이 실제 수집 없이 "할 일/이미 끝난 일" 목록만 출력. 중간에 끊겼다가
다시 실행하면 끝난 단계를 건너뛰는 테스트.

### 10. 대화형 메뉴 + 셸 스크립트 + 문서

**파일**: `backend/core/management/commands/areas.py`(인자 없이 실행하면 대화형 메뉴 — 현재
지역+단계별 ✓/✗, 추가 가능 지역 번호 목록, 번호 선택 → `add` → `sync` 순서로 안내),
`scripts/areas.sh`(신설, `docker compose exec [-it] api python manage.py areas "$@"` 한 줄
래퍼 — 인자 없으면 `-it`), `README.md`("지역 추가 방법" 섹션 추가).

**완료 기준**: `./scripts/areas.sh list`, `./scripts/areas.sh sync --area 30 --dry-run` 실행
예시를 README에 반영. 전체 pytest 통과.
