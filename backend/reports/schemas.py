"""리포트 출력 JSON 스키마(spec 7-3 기본 템플릿, 7-6 맞춤)."""

_TEMPLATE_EVIDENCE_ITEM = {
    "type": "object",
    "required": ["section", "index", "keys"],
    "properties": {
        "section": {"enum": ["summary", "living", "investment", "risks"]},
        "index": {"type": "integer"},
        "keys": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}

TEMPLATE_RESULT_SCHEMA = {
    "type": "object",
    "required": ["summary_3lines", "living_view", "investment_view", "risks", "evidence"],
    "properties": {
        "summary_3lines": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {"type": "string", "maxLength": 80},
        },
        "living_view": {"type": "string", "maxLength": 400},
        "investment_view": {"type": "string", "maxLength": 400},
        "risks": {
            "type": "array",
            "minItems": 0,
            "maxItems": 3,
            "items": {"type": "string", "maxLength": 120},
        },
        "evidence": {"type": "array", "items": _TEMPLATE_EVIDENCE_ITEM},
    },
    "additionalProperties": False,
}

# 맞춤 리포트는 고정된 4개 섹션이 없어, evidence.section을 자유 문자열로 둔다(7-6엔 enum이
# 없음 — 플랜 리뷰에서 결정).
_CUSTOM_EVIDENCE_ITEM = {
    "type": "object",
    "required": ["index", "keys"],
    "properties": {
        "section": {"type": "string"},
        "index": {"type": "integer"},
        "keys": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}

CUSTOM_RESULT_SCHEMA = {
    "type": "object",
    "required": ["title", "answer", "evidence", "limitations"],
    "properties": {
        "title": {"type": "string", "maxLength": 60},
        "answer": {"type": "string", "maxLength": 1500},
        "evidence": {"type": "array", "items": _CUSTOM_EVIDENCE_ITEM},
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}


def schema_for(report_type: str) -> dict:
    return TEMPLATE_RESULT_SCHEMA if report_type == "template" else CUSTOM_RESULT_SCHEMA
