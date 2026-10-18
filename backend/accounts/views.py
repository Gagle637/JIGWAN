from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from favorites.models import FavoriteFolder, UserBuilding

from .models import User


class LoginView(TokenObtainPairView):
    """POST /api/auth/login — SimpleJWT 뷰 그대로, DEFAULT_PERMISSION_CLASSES가
    IsAuthenticated로 바뀌었어도 로그인 전에 막히지 않게 AllowAny로 명시한다."""

    permission_classes = [AllowAny]
    authentication_classes = []


class RefreshView(TokenRefreshView):
    """POST /api/auth/refresh — 위와 같은 이유로 AllowAny."""

    permission_classes = [AllowAny]
    authentication_classes = []


class RegisterView(APIView):
    """POST /api/auth/register — spec 9-1: 이메일만 수집, 수집 동의를 받는다.

    가입만 하고 토큰은 주지 않는다 — 가입 후 /api/auth/login을 따로 호출한다.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        password = request.data.get("password") or ""
        privacy_consent = request.data.get("privacy_consent")

        if not email:
            raise ValidationError("email은 필수입니다.")
        if privacy_consent is not True:
            raise ValidationError("개인정보 수집 동의가 필요합니다.")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("이미 가입된 이메일입니다.")

        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise ValidationError(list(exc.messages))

        user = User.objects.create_user(
            email=email, password=password, privacy_consent_at=timezone.now()
        )
        return Response({"id": user.id, "email": user.email}, status=201)


class MeDeleteView(APIView):
    """DELETE /api/auth/me — 본인 탈퇴(spec 9-1: 탈퇴 시 표시·폴더를 함께 삭제).

    UserBuilding.folder·FavoriteFolder.parent가 PROTECT라 user.delete()의 기본 CASCADE에
    맡기면 Django의 삭제 수집기가 "이 폴더를 참조하는 UserBuilding/하위 폴더가 같은
    트랜잭션에서 같이 지워진다"는 걸 못 보고 ProtectedError(500)를 낸다(감사 중 실제
    Postgres로 재현됨). PROTECT로 막히는 참조를 먼저 직접 끊고 지운다.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        with transaction.atomic():
            UserBuilding.objects.filter(user=user).delete()
            FavoriteFolder.objects.filter(user=user).update(parent=None)
            FavoriteFolder.objects.filter(user=user).delete()
            user.delete()
        return Response(status=204)
