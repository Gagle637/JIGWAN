# 프론트엔드 작업 목록(미룬 것)

백엔드 작업 지시에 프론트 작업이 같이 적혀 있을 때, 지시대로 백엔드만 만들고 여기에 적어 둔다.
아래 항목은 `frontend/`를 다시 시작할 때 참고한다.

## 8단계(insight 위성 섹션 + 레이어 레지스트리)에서 미룬 것

- 녹지율 시계열 차트: `insight.green.series`(연·계절·ratio_pct·coverage_pct)를 꺾은선으로.
  `ratio_pct`가 `null`인 항목(유효 비율<50%, insufficient_data)은 끊어진 구간으로 표시.
- `/api/layers` 목록으로 레이어 토글 UI 구성. `source_type`별로 렌더 방식이 다름
  (`vector_tile`/`geojson`/`titiler`/`wms`/`raster_tile`).
- Before/After 스와이프: `insight.change.tiles.after`(현재 계절)와
  `insight.change.tiles.before`(1y/2y/3y 중 있는 것) 두 TiTiler 타일을 겹쳐 스와이프.
  **비교 기간(1y/2y/3y) 선택 UI 필요** — `before`에 어떤 키가 있는지에 따라 선택지를 동적으로
  보여주고, 기본값은 `default_compare`.

## 9단계(범죄주의구간 수집·insight.crime·레이어 WMS 중계)에서 미룬 것

- `/api/layers` 목록의 "범죄주의구간(전체)" 항목에 담긴 `legend`(10단계 색상)와 `notice`(WARN
  고지 문구)를 지도 범례 UI로 표시. 레이어를 켤 때 고지 문구가 항상 같이 보이게 해야 한다
  (CLAUDE.md: '위험' 표현 금지 — 제공처 고지를 그대로 보여주는 방식으로 대체).
  타일 자체는 `GET /api/layers/{id}/tiles/{z}/{x}/{y}.png`로 바로 쓸 수 있다.
  원천 오류 시 서버가 투명 타일을 반환하므로, 레이어에 "일시적으로 불러올 수 없음" 같은
  별도 표시는 프론트에서 판단해 보여줘야 한다(서버 응답만으론 구분이 안 됨 — 필요하면
  나중에 응답 헤더를 추가할 수 있음).
- `insight.crime`이 `null`이고 `missing`에 `{"field":"crime","reason":"no_crime_segment"}`가 있을
  때는 "주의구간 미지정"으로 표시(절대 "안전"이라고 쓰지 않기). `as_of.crime_data_period`을
  함께 보여줘 데이터가 어느 기간 기준인지 알 수 있게 한다.

## 10단계(즉겨찾기/계정)에서 미룬 것

- **팔레트 8색은 임시값**(`backend/favorites/colors.py`의 `PALETTE_COLORS`) — spec 10-4가
  "이후 UI 설계에서 확정"이라고 명시한 TBD다. 실제 디자인이 나오면 이 8개 hex 값만 바꾸면
  백엔드 검증(`color`가 팔레트 안에 있는지)도 자동으로 맞춰진다.
- 폴더 재정렬(`sort_order`) UI: 백엔드는 `PATCH /api/me/favorites/{folder_id}`에 절대값
  `sort_order`를 그대로 저장만 한다(끼워넣기용 간격 계산 없음). 드래그로 순서를 바꿀 때
  프론트에서 같은 부모의 형제 전체에 대해 새 `sort_order`를 다시 계산해 보내야 한다.
