from rest_framework.exceptions import APIException


class ReportQuotaExceeded(APIException):
    status_code = 429
    default_detail = "리포트 생성 한도를 초과했습니다."
    default_code = "report_quota_exceeded"
    error_code = "REPORT_QUOTA_EXCEEDED"
