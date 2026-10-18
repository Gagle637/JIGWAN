from django.db import migrations


class Migration(migrations.Migration):
    """index_run의 (job, region_code) 인덱스 이름을 사람이 읽을 수 있는 이름으로 바꾼다.

    0001_initial.py가 Django 자동 해시 이름 형식을 손으로 베껴 적어 뒀는데(이 프로젝트는
    실제 makemigrations를 돌리지 않고 마이그레이션을 직접 작성해 왔음), 실제 Django가
    계산하는 해시값과 달라 모델과 항상 어긋났다(감사 결과) — 다른 앱들처럼 명시적인
    이름으로 통일한다.
    """

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="indexrun",
            old_name="core_indexr_job_f36c3e_idx",
            new_name="index_run_job_region_code_idx",
        ),
    ]
