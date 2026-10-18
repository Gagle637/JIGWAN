"""즐겨찾기 색상 팔레트(spec 6-4·10-4). spec 10-4가 "색상 팔레트 8색은 이후 UI 설계에서
확정"이라고 명시한 TBD라, 지금은 임시 값(docs/frontend_todo.md에 기록)이다 — 실제 팔레트가
정해지면 이 상수만 바꾸면 된다."""

PALETTE_COLORS = [
    "#e8590c",  # 주황(spec 6-4 예시)
    "#2f9e44",  # 초록
    "#1971c2",  # 파랑
    "#e03131",  # 빨강
    "#ae3ec9",  # 보라
    "#f08c00",  # 노랑
    "#0c8599",  # 청록
    "#495057",  # 회색
]

DEFAULT_FAVORITE_COLOR = PALETTE_COLORS[0]
