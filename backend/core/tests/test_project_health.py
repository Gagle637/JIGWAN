"""프로젝트 전체 정합성 — manage.py check·makemigrations --check가 깨지면 migrate를
포함한 모든 관리 명령이 시작 전에 멈춘다. pytest는 테스트 DB를 만들 때 이 시스템 검사를
건너뛰어서(--skip-checks 상당) 그동안 못 잡혔다(감사 결과: 인덱스 이름 30자 초과로
manage.py check가 실패했었음, models.E034)."""
import pytest
from django.core.management import call_command
from django.core.management.base import SystemCheckError

pytestmark = pytest.mark.django_db


def test_manage_py_check_has_no_errors():
    try:
        call_command("check")
    except SystemCheckError as exc:
        pytest.fail(f"manage.py check 실패:\n{exc}")


def test_makemigrations_check_detects_no_pending_model_changes():
    """모델이 마이그레이션과 어긋나면(인덱스 이름, FK to_field 등) 여기서 걸린다 — 이 상태로는
    migrate를 포함한 모든 관리 명령이 시작도 안 된다."""
    try:
        call_command("makemigrations", "--check", "--dry-run", verbosity=0)
    except SystemExit as exc:
        pytest.fail(
            f"makemigrations --check가 적용 안 된 모델 변경을 찾았습니다(exit code {exc.code}). "
            "models.py와 migrations/가 어긋났다는 뜻이니 makemigrations로 새 마이그레이션을 "
            "만들어야 합니다."
        )
