import json

import pytest

from reports import generation
from reports.generation import ReportGenerationFailed, run_generation


class FakeReport:
    def __init__(self, report_type="template", input_snapshot=None, user_prompt=None):
        self.id = 1
        self.report_type = report_type
        self.input_snapshot = input_snapshot or {"green": {"ratio_pct": 23.4}}
        self.user_prompt = user_prompt


def _valid_payload_json():
    return json.dumps(
        {
            "summary_3lines": ["a", "b", "c"],
            "living_view": "녹지율은 23.4%입니다.",
            "investment_view": "정보 없음",
            "risks": [],
            "evidence": [{"section": "summary", "index": 0, "keys": ["green.ratio_pct"]}],
        }
    )


def test_run_generation_succeeds_on_first_try(monkeypatch):
    calls = []

    def fake_chat(messages):
        calls.append(messages)
        return _valid_payload_json()

    monkeypatch.setattr(generation, "chat_completion", fake_chat)

    payload, _model = run_generation(FakeReport())

    assert len(calls) == 1
    assert payload["living_view"].startswith("녹지율")


def test_run_generation_retries_once_then_succeeds(monkeypatch):
    responses = ['{"invalid": true}', _valid_payload_json()]
    calls = []

    def fake_chat(messages):
        calls.append(messages)
        return responses[len(calls) - 1]

    monkeypatch.setattr(generation, "chat_completion", fake_chat)

    payload, _model = run_generation(FakeReport())

    assert len(calls) == 2
    assert "이전 시도 실패 사유" in calls[1][-1]["content"]
    assert payload["living_view"].startswith("녹지율")


def test_run_generation_raises_after_max_attempts(monkeypatch):
    monkeypatch.setattr(generation, "chat_completion", lambda messages: '{"invalid": true}')

    with pytest.raises(ReportGenerationFailed):
        run_generation(FakeReport())


def test_run_generation_handles_unparseable_json(monkeypatch):
    calls = []

    def fake_chat(messages):
        calls.append(messages)
        if len(calls) == 1:
            return "이건 JSON이 아닙니다"
        return _valid_payload_json()

    monkeypatch.setattr(generation, "chat_completion", fake_chat)

    payload, _model = run_generation(FakeReport())

    assert len(calls) == 2
    assert "JSON 파싱 실패" in calls[1][-1]["content"]
