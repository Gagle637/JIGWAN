from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import ServiceUnavailable
from .locks import get_redis_client


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        checks = {"db": self._check_db(), "redis": self._check_redis()}

        if not all(ok for ok, _ in checks.values()):
            detail = {name: reason for name, (ok, reason) in checks.items() if not ok}
            raise ServiceUnavailable(detail=f"의존 서비스 연결 실패: {detail}")

        return Response(
            {"status": "ok", "checks": {name: "ok" for name in checks}}
        )

    @staticmethod
    def _check_db():
        try:
            connection.ensure_connection()
            return True, "ok"
        except Exception as exc:  # noqa: BLE001 — 헬스체크는 모든 연결 오류를 잡아야 함
            return False, str(exc)

    @staticmethod
    def _check_redis():
        try:
            get_redis_client().ping()
            return True, "ok"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
