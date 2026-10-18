"""LLM 생성 + 검증 + 재시도 루프(spec 7-4): 실패하면 사유를 붙여 최대 2회 재생성(총 3회
시도), 그래도 실패하면 ReportGenerationFailed."""
import json
import logging

from django.conf import settings

from .llm_client import chat_completion
from .prompts import build_messages
from .validator import validate_report

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # 최초 1회 + 최대 2회 재생성


class ReportGenerationFailed(Exception):
    """재생성까지 전부 실패했다. report.status=failed로 저장되고 한도에서 차감되지 않는다."""


def run_generation(report) -> tuple[dict, str]:
    base_messages = build_messages(report.report_type, report.input_snapshot, report.user_prompt)
    last_reasons: list[str] = []

    for attempt in range(MAX_ATTEMPTS):
        messages = base_messages
        if last_reasons:
            feedback = "; ".join(last_reasons)
            messages = base_messages + [
                {
                    "role": "user",
                    "content": (
                        f"[이전 시도 실패 사유] {feedback}\n"
                        "위 사유를 고쳐서 같은 스키마로 다시 생성해줘."
                    ),
                }
            ]

        raw = chat_completion(messages)
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            last_reasons = [f"JSON 파싱 실패: {exc}"]
            logger.warning(
                "report#%s 생성 시도 %s 실패: %s", report.id, attempt + 1, last_reasons[0]
            )
            continue

        errors = validate_report(payload, report.input_snapshot, report.report_type)
        if not errors:
            return payload, settings.LLM_MODEL

        last_reasons = errors
        logger.warning(
            "report#%s 생성 시도 %s 검증 실패: %s", report.id, attempt + 1, "; ".join(errors)
        )

    raise ReportGenerationFailed("; ".join(last_reasons) if last_reasons else "알 수 없는 오류")
