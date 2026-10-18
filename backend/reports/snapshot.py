"""리포트 입력 스냅샷(spec 7-2: "insight 응답에서 geometry·tiles·my를 뺀 JSON")."""
import copy

from buildings.insight import get_insight_cached


def _strip_sensitive_sections(snapshot: dict) -> dict:
    snapshot.pop("my", None)
    if snapshot.get("building"):
        snapshot["building"].pop("geometry", None)
    if snapshot.get("change"):
        snapshot["change"].pop("tiles", None)
    return snapshot


def build_report_input(building, radius_m: int) -> dict:
    snapshot = copy.deepcopy(get_insight_cached(building, radius_m))
    return _strip_sensitive_sections(snapshot)


def build_demo_report_input(insight_response: dict) -> dict:
    """DEMO_MODE(13단계)용 — 이미 만들어진(데모) insight 응답에서 같은 섹션을 뺀다."""
    return _strip_sensitive_sections(copy.deepcopy(insight_response))
