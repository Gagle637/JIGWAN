"""OpenAI 호환 LLM 클라이언트: 요청 바디, 상태코드별 예외 분기를 httpx(respx)로 검증한다
(spec 9-5: "외부 API는 녹화한 응답으로 목 처리"). vLLM·Ollama 둘 다 같은 /chat/completions
모양을 쓴다고 가정한다(spec 7-1)."""
import json

import httpx
import pytest
import respx

from core.exceptions import ExternalCallError
from reports import llm_client

CHAT_URL = "http://vllm:8000/v1/chat/completions"


@pytest.fixture(autouse=True)
def _llm_settings(settings):
    settings.LLM_BASE_URL = "http://vllm:8000/v1"
    settings.LLM_MODEL = "openai/gpt-oss-20b"


def _success_response(content="{}"):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_requires_base_url_configured(settings):
    settings.LLM_BASE_URL = ""

    with pytest.raises(ValueError):
        llm_client.chat_completion([{"role": "user", "content": "hi"}])


def test_uses_llm_timeout_seconds_setting(monkeypatch, settings):
    settings.LLM_TIMEOUT_SECONDS = 42
    captured = {}

    def fake_post(url, json, timeout):
        captured["timeout"] = timeout
        return _success_response()

    monkeypatch.setattr(llm_client.httpx, "post", fake_post)

    llm_client.chat_completion([{"role": "user", "content": "hi"}])

    assert captured["timeout"] == 42


@respx.mock
def test_sends_model_temperature_max_tokens_and_json_object_response_format():
    route = respx.post(CHAT_URL).mock(return_value=_success_response())

    llm_client.chat_completion([{"role": "user", "content": "hi"}])

    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "openai/gpt-oss-20b"
    assert body["temperature"] == 0.3
    assert body["max_tokens"] == 4000
    assert body["response_format"] == {"type": "json_object"}


@respx.mock
def test_returns_message_content_from_first_choice():
    respx.post(CHAT_URL).mock(return_value=_success_response('{"summary_3lines": []}'))

    content = llm_client.chat_completion([{"role": "user", "content": "hi"}])

    assert content == '{"summary_3lines": []}'


@pytest.mark.parametrize("status_code", [429, 500, 502, 503])
@respx.mock
def test_retryable_status_codes_raise_external_call_error(status_code):
    respx.post(CHAT_URL).mock(return_value=httpx.Response(status_code))

    with pytest.raises(ExternalCallError):
        llm_client.chat_completion([{"role": "user", "content": "hi"}])


@pytest.mark.parametrize("status_code", [400, 404])
@respx.mock
def test_non_retryable_status_codes_raise_value_error(status_code):
    respx.post(CHAT_URL).mock(return_value=httpx.Response(status_code, text="bad request"))

    with pytest.raises(ValueError):
        llm_client.chat_completion([{"role": "user", "content": "hi"}])


@respx.mock
def test_timeout_raises_external_call_error():
    respx.post(CHAT_URL).mock(side_effect=httpx.TimeoutException("timed out"))

    with pytest.raises(ExternalCallError):
        llm_client.chat_completion([{"role": "user", "content": "hi"}])


@respx.mock
def test_connection_error_raises_external_call_error():
    respx.post(CHAT_URL).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(ExternalCallError):
        llm_client.chat_completion([{"role": "user", "content": "hi"}])
