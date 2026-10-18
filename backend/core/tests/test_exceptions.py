import pytest
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)

from config.exceptions import jigwan_exception_handler
from core.exceptions import ServiceUnavailable


@pytest.mark.parametrize(
    "exc,expected_status,expected_code",
    [
        (NotAuthenticated(), 401, "UNAUTHORIZED"),
        (AuthenticationFailed(), 401, "UNAUTHORIZED"),
        (PermissionDenied(), 403, "FORBIDDEN"),
        (NotFound(), 404, "NOT_FOUND"),
        (ValidationError("bad param"), 400, "INVALID_PARAM"),
        (Throttled(wait=5), 429, "RATE_LIMITED"),
        (ServiceUnavailable(), 503, "SERVICE_UNAVAILABLE"),
    ],
)
def test_known_exceptions_map_to_common_envelope(exc, expected_status, expected_code):
    response = jigwan_exception_handler(exc, {})

    assert response.status_code == expected_status
    assert response.data["error"]["code"] == expected_code
    assert isinstance(response.data["error"]["message"], str)
    assert response.data["error"]["message"]


def test_unhandled_exception_maps_to_internal_500():
    response = jigwan_exception_handler(ValueError("boom"), {})

    assert response.status_code == 500
    assert response.data == {
        "error": {"code": "INTERNAL", "message": "서버 오류가 발생했습니다."}
    }
