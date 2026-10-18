from reports.validator import validate_report

_INPUT = {
    "green": {"ratio_pct": 23.4},
    "trades": {"count": 87},
    "spec": {"approval_date": "2009-11-20"},
    "crime": None,
}


def _valid_template_payload():
    return {
        "summary_3lines": ["녹지율은 23.4%입니다.", "거래는 87건입니다.", "세 번째 문장입니다."],
        "living_view": "녹지율은 23.4%입니다.",
        "investment_view": "거래는 87건입니다.",
        "risks": [],
        "evidence": [
            {"section": "summary", "index": 0, "keys": ["green.ratio_pct"]},
            {"section": "investment", "index": 0, "keys": ["trades.count"]},
        ],
    }


def test_valid_template_payload_passes():
    errors = validate_report(_valid_template_payload(), _INPUT, "template")

    assert errors == []


def test_schema_violation_wrong_summary_count_fails():
    payload = _valid_template_payload()
    payload["summary_3lines"] = ["한 줄만"]

    errors = validate_report(payload, _INPUT, "template")

    assert errors
    assert "스키마" in errors[0]


def test_evidence_key_missing_from_input_fails():
    payload = _valid_template_payload()
    payload["evidence"].append({"section": "risks", "index": 0, "keys": ["no.such.key"]})

    errors = validate_report(payload, _INPUT, "template")

    assert any("no.such.key" in e for e in errors)


def test_evidence_key_with_null_value_fails():
    payload = _valid_template_payload()
    payload["evidence"].append({"section": "risks", "index": 0, "keys": ["crime"]})

    errors = validate_report(payload, _INPUT, "template")

    assert any("crime" in e and "null" in e for e in errors)


def test_number_not_matching_input_fails():
    payload = _valid_template_payload()
    payload["living_view"] = "녹지율은 99.9%입니다."

    errors = validate_report(payload, _INPUT, "template")

    assert any("99.9" in e for e in errors)


def test_number_embedded_in_date_string_does_not_false_positive():
    """입력 문자열("2009-11-20") 안의 숫자를 본문에 그대로 인용해도 틀렸다고 하면 안 된다."""
    payload = _valid_template_payload()
    payload["living_view"] = "이 건물은 2009년에 사용승인됐습니다."

    errors = validate_report(payload, _INPUT, "template")

    assert errors == []


def test_fixed_spec_constants_in_text_do_not_false_positive():
    """50(근접 반경 m)·1("최근 1년")은 입력 JSON 값이 아니라 spec이 고정한 상수라 허용된다."""
    payload = _valid_template_payload()
    payload["living_view"] = "최근 1년 범죄 발생 밀도는 건물 50m 이내에서도 확인됩니다."

    errors = validate_report(payload, _INPUT, "template")

    assert errors == []


def test_forbidden_word_fails():
    payload = _valid_template_payload()
    payload["living_view"] = "이 지역은 위험합니다."

    errors = validate_report(payload, _INPUT, "template")

    assert any("위험" in e for e in errors)


def test_forbidden_phrase_buy_recommendation_fails():
    payload = _valid_template_payload()
    payload["investment_view"] = "지금이 매수 추천 시점입니다."

    errors = validate_report(payload, _INPUT, "template")

    assert any("매수 추천" in e for e in errors)


def test_valid_custom_payload_passes():
    payload = {
        "title": "요약 제목",
        "answer": "녹지율은 23.4%이고 거래는 87건입니다.",
        "evidence": [
            {"section": "녹지", "index": 0, "keys": ["green.ratio_pct"]},
            {"section": "시세", "index": 0, "keys": ["trades.count"]},
        ],
        "limitations": [],
    }

    errors = validate_report(payload, _INPUT, "custom")

    assert errors == []


def test_custom_schema_rejects_unexpected_field():
    payload = {
        "title": "제목",
        "answer": "답변",
        "evidence": [],
        "limitations": [],
        "extra_field": "허용 안 됨",
    }

    errors = validate_report(payload, _INPUT, "custom")

    assert errors
