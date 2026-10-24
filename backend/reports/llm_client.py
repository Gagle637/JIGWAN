"""OpenAI 호환 /v1/chat/completions 클라이언트(vLLM·Ollama 둘 다 동작, spec 7-1).

response_format은 {"type":"json_object"}만 쓴다(vLLM의 완전한 json_schema 구조화 출력 대신) —
Ollama의 OpenAI 호환 레이어가 json_schema strict 모드까지 지원하는지 확인할 수 없고, 실제
스키마 강제는 reports/validator.py가 하므로 이쪽이 둘 다에서 안전하다(플랜 리뷰에서 결정).
"""
import httpx
from django.conf import settings

from core.exceptions import ExternalCallError

# gpt-oss는 "Reasoning: low"를 지시해도 reasoning 채널만으로 수백~2000+ 토큰을 쓴다(실측
# 확인: 반경 500m 리포트 프롬프트에서 reasoning 2835자 쓰고 max_tokens=1200에 걸려 최종
# JSON(content)은 한 글자도 못 내고 finish_reason=length로 끊겼다). content는 reasoning과
# 토큰을 공유하므로 reasoning 분량까지 감안해 넉넉히 잡는다.
TEMPERATURE = 0.3
MAX_TOKENS = 4000


def chat_completion(messages: list[dict]) -> str:
    if not settings.LLM_BASE_URL:
        raise ValueError("LLM_BASE_URL이 설정되지 않았습니다.")

    url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
    body = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_object"},
    }
    try:
        response = httpx.post(url, json=body, timeout=settings.LLM_TIMEOUT_SECONDS)
    except httpx.TimeoutException as exc:
        raise ExternalCallError(f"LLM 타임아웃: {exc}") from exc
    except httpx.HTTPError as exc:
        raise ExternalCallError(f"LLM 요청 오류: {exc}") from exc

    if response.status_code in (429, 503) or response.status_code >= 500:
        raise ExternalCallError(f"LLM HTTP {response.status_code}")
    if response.status_code >= 400:
        raise ValueError(f"LLM HTTP {response.status_code}: {response.text[:300]}")

    data = response.json()
    return data["choices"][0]["message"]["content"]
