"""데모 리포트(backend/demo/fixtures/demo_snapshots.json)가 실제 generate_report 경로와
같은 reports.validator.validate_report()를 통과하는지 확인한다.

실행 경로(DEMO_MODE)는 그대로 둔다 — 데모 리포트는 LLM을 안 거치니 저장 전에 검증기를
타진 않지만, 내용 자체가 검증 규칙(스키마·evidence·숫자 일치·금지어)을 어겼는지는 이 테스트로
미리 잡아낸다.

reports.snapshot.build_demo_report_input은 buildings.insight(→ GIS 앱 전체)를 끌고 와서
무거우니, 여기선 그 함수가 하는 것과 똑같은 my/tiles 제거만 직접 해서 가볍게 검증한다."""
import copy

import pytest

from demo.snapshots import load_demo_snapshots
from reports.validator import validate_report

DEMO_SNAPSHOTS = load_demo_snapshots()
DEMO_CASES = [
    (pnu, report_type)
    for pnu, entry in DEMO_SNAPSHOTS.items()
    for report_type in entry["reports"]
]


def _strip_sensitive_sections(snapshot: dict) -> dict:
    """reports.snapshot._strip_sensitive_sections와 동일한 규칙(spec 7-2)."""
    snapshot.pop("my", None)
    if snapshot.get("building"):
        snapshot["building"].pop("geometry", None)
    if snapshot.get("change"):
        snapshot["change"].pop("tiles", None)
    return snapshot


@pytest.mark.parametrize("pnu,report_type", DEMO_CASES)
def test_demo_report_passes_validator(pnu, report_type):
    entry = DEMO_SNAPSHOTS[pnu]
    input_snapshot = _strip_sensitive_sections(copy.deepcopy(entry["insight"]))
    payload = entry["reports"][report_type]

    errors = validate_report(payload, input_snapshot, report_type)

    assert errors == [], f"{pnu}/{report_type}: {errors}"
