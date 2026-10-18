from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

# spec 6-3 공용 에러 코드. 도메인별 코드(BUILDING_NOT_FOUND 등)는 해당 기능 구현 시
# 예외 클래스에 error_code 속성을 붙여 이 매핑 없이도 그대로 쓸 수 있다.
_CODE_BY_EXCEPTION_TYPE = {
    NotAuthenticated: "UNAUTHORIZED",
    AuthenticationFailed: "UNAUTHORIZED",
    PermissionDenied: "FORBIDDEN",
    NotFound: "NOT_FOUND",
    ValidationError: "INVALID_PARAM",
    Throttled: "RATE_LIMITED",
}


def _error_code(exc):
    custom_code = getattr(exc, "error_code", None)
    if custom_code:
        return custom_code
    for exc_type, code in _CODE_BY_EXCEPTION_TYPE.items():
        if isinstance(exc, exc_type):
            return code
    return "INTERNAL"


def _error_message(data):
    if isinstance(data, dict):
        detail = data.get("detail")
        return str(detail) if detail is not None else str(data)
    if isinstance(data, list):
        return "; ".join(str(item) for item in data)
    return str(data)


def jigwan_exception_handler(exc, context):
    """모든 에러 응답을 {"error": {"code", "message"}}로 통일한다(spec 6-3)."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return Response(
            {"error": {"code": "INTERNAL", "message": "서버 오류가 발생했습니다."}},
            status=500,
        )
    response.data = {
        "error": {
            "code": _error_code(exc),
            "message": _error_message(response.data),
        }
    }
    return response
