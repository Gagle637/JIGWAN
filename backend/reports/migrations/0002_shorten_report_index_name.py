from django.db import migrations


class Migration(migrations.Migration):
    """report_user_building_created_idx(32자)가 Django Index.max_name_length(30자,
    models.E034)를 넘어 manage.py check가 전체 관리 명령을 막았다(감사 결과) — 30자 이하인
    이름으로 바꾼다. DB 영향은 인덱스 이름뿐이다."""

    dependencies = [
        ("reports", "0001_initial"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="report",
            old_name="report_user_building_created_idx",
            new_name="report_user_bldg_created_idx",
        ),
    ]
