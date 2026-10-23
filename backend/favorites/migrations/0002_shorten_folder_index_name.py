from django.db import migrations


class Migration(migrations.Migration):
    """favorite_folder_user_parent_idx(31자)가 Django Index.max_name_length(30자,
    models.E034)를 넘어 manage.py check가 전체 관리 명령을 막았다(감사 결과) — 30자 이하인
    이름으로 바꾼다. DB 영향은 인덱스 이름뿐이다."""

    dependencies = [
        ("favorites", "0001_initial"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="favoritefolder",
            old_name="favorite_folder_user_parent_idx",
            new_name="fav_folder_user_parent_idx",
        ),
    ]
