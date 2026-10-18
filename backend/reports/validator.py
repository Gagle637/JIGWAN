"""리포트 출력 검증기(spec 7-4): 스키마 → evidence 키 존재·non-null → 본문 숫자 일치 →
금지어. 하나라도 걸리면 실패 사유 목록을 돌려준다(빈 리스트면 통과)."""
import re

import jsonschema

from .schemas import schema_for

NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")

# 입력 JSON 값이 아니라 spec이 고정한 상수·표현이라 본문에 자연스럽게 등장할 수 있는 숫자.
# - 50: crime.near_grad의 정의("건물에서 50m 이내")에 쓰는 고정 반경, 입력 JSON에 값으로는 없음.
# - 1: 범죄 지표는 "최근 1년 범죄 발생 밀도"로만 표현해야 하는 CLAUDE.md의 고정 문구.
# - 0: "0건"처럼 빈 값을 설명할 때 흔히 쓰고, 오탐 위험보다 놓칠 위험이 거의 없음.
_ALWAYS_ALLOWED_NUMBERS = {0, 0.0, 1, 1.0, 50, 50.0}

# spec 7-4 예시 4개 + CLAUDE.md의 포괄적 "'위험' 표현 금지"를 반영해 "위험"도 추가
# (9단계 crime 쪽에서도 같은 이유로 넓게 잡았음).
FORBIDDEN_PHRASES = ["매수 추천", "매도 추천", "반드시", "확실히 오른다", "위험"]

_MISSING = object()


def _lookup(path: str, data):
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


def _collect_numbers(data) -> set:
    """입력 JSON의 모든 숫자값과, 문자열 안에 섞인 숫자(날짜 등)까지 모두 모은다 —
    "2009-11-20"처럼 날짜가 본문에 그대로 인용돼도 숫자 불일치로 잘못 걸리지 않게 한다."""
    numbers = set()

    def walk(value):
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            numbers.add(round(float(value), 1))
            numbers.add(round(float(value)))
        elif isinstance(value, str):
            for match in NUMBER_PATTERN.finditer(value):
                try:
                    num = float(match.group())
                except ValueError:
                    continue
                numbers.add(round(num, 1))
                numbers.add(round(num))
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(data)
    return numbers


def _text_fields(payload: dict, report_type: str) -> list[str]:
    if report_type == "template":
        fields = list(payload.get("summary_3lines") or [])
        fields.append(payload.get("living_view") or "")
        fields.append(payload.get("investment_view") or "")
        fields.extend(payload.get("risks") or [])
        return fields
    return [payload.get("title") or "", payload.get("answer") or ""]


def _all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _all_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _all_strings(v)


def validate_report(payload, input_snapshot: dict, report_type: str) -> list[str]:
    errors: list[str] = []

    try:
        jsonschema.validate(payload, schema_for(report_type))
    except jsonschema.ValidationError as exc:
        return [f"스키마 위반: {exc.message}"]  # 스키마가 안 맞으면 이후 검사는 의미 없음

    for item in payload.get("evidence", []):
        for key in item.get("keys", []):
            value = _lookup(key, input_snapshot)
            if value is _MISSING:
                errors.append(f"evidence 키 '{key}'가 입력 JSON에 없습니다.")
            elif value is None:
                errors.append(f"evidence 키 '{key}'의 값이 null입니다.")

    allowed_numbers = _collect_numbers(input_snapshot) | _ALWAYS_ALLOWED_NUMBERS
    for text in _text_fields(payload, report_type):
        for match in NUMBER_PATTERN.finditer(text):
            try:
                num = float(match.group())
            except ValueError:
                continue
            if round(num, 1) not in allowed_numbers and round(num) not in allowed_numbers:
                errors.append(f"본문의 숫자 '{match.group()}'가 입력값과 일치하지 않습니다.")

    for text in _all_strings(payload):
        for phrase in FORBIDDEN_PHRASES:
            if phrase in text:
                errors.append(f"금지어 '{phrase}'가 포함돼 있습니다.")

    return errors
