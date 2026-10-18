"""프롬프트 파일 로드 + 메시지 조립(spec 7-2, 7-6). 프롬프트는 코드가 아닌 파일로 관리하고
버전을 report.template_version/prompt_version에 남긴다."""
import json
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

TEMPLATE_VERSION = "v1"
PROMPT_VERSION = "v1"

_TEMPLATE_FILE = PROMPTS_DIR / f"report_template_{TEMPLATE_VERSION}.txt"
_CUSTOM_FILE = PROMPTS_DIR / f"report_custom_{PROMPT_VERSION}.txt"


def build_messages(report_type: str, input_snapshot: dict, user_prompt: str | None) -> list[dict]:
    input_json = json.dumps(input_snapshot, ensure_ascii=False)

    if report_type == "template":
        system_content = _TEMPLATE_FILE.read_text(encoding="utf-8")
        user_content = f"입력: {input_json}"
    else:
        system_content = _CUSTOM_FILE.read_text(encoding="utf-8")
        user_content = (
            f"입력: {input_json}\n[사용자 요청] {user_prompt} [/사용자 요청]"
        )

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def version_for(report_type: str) -> str:
    return TEMPLATE_VERSION if report_type == "template" else PROMPT_VERSION
