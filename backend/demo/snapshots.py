"""DEMO_MODE 고정 스냅샷(13단계): 대표 건물 5곳의 insight·리포트를 고정해 두고, GPU·외부
API 없이 그 값을 돌려준다.

fixtures/demo_snapshots.json의 PNU("DEMO0000...")는 예시(placeholder)다 — 실제 시연
전에 운영자가 자기 환경에 실제로 적재된 건물의 PNU로 바꿔야 한다(README 참고).
"""
import json
from functools import lru_cache
from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "demo_snapshots.json"


@lru_cache(maxsize=1)
def load_demo_snapshots() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def get_demo_snapshot(pnu: str) -> dict | None:
    return load_demo_snapshots().get(pnu)


def apply_demo_overlay(demo_insight: dict, building) -> dict:
    """데모 insight 템플릿에 실제 적재된 건물의 id·geometry 등을 덮어씌운다 — 분석 섹션은
    고정값이지만, 지도에 그릴 건물 자체는 실제 DB 행의 위치여야 폴리곤이 맞게 그려진다."""
    address = f"{building.bjd_name or ''} {building.jibun or ''}".strip() or None
    overlay = dict(demo_insight)
    overlay["building"] = {
        "id": building.id,
        "pnu": building.pnu,
        "name": building.name,
        "address": address,
        "use_type": building.use_name,
        "geometry": json.loads(building.geom.geojson),
    }
    return overlay
