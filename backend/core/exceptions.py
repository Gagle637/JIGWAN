from rest_framework.exceptions import APIException


class ExternalCallError(Exception):
    """외부 호출 실패(네트워크, 5xx, 429)를 알리는 예외.

    tracked_job 래퍼는 이 예외만 재시도 대상으로 다룬다(spec 5-2).
    데이터·로직 오류는 일반 예외를 그대로 raise하면 즉시 failed 처리된다.
    """


class ServiceUnavailable(APIException):
    status_code = 503
    default_detail = "서비스를 일시적으로 사용할 수 없습니다."
    default_code = "service_unavailable"
    error_code = "SERVICE_UNAVAILABLE"
