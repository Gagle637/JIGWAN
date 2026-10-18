import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Region.parent FK 정리(감사 결과): Django의 ForeignKey.deconstruct()는 to_field가
    대상 모델의 기본키 이름(region_code)과 같으면 to_field를 생략한다. 모델 코드는 여전히
    명시적으로 to_field="region_code"를 쓰지만(가독성), 기본키를 가리키는 FK라 실제로는
    아무 효과가 없는 값이라 makemigrations가 "to_field 없음" 쪽을 현재 상태로 본다.
    DB에는 영향 없음(필드가 가리키는 컬럼·on_delete·db_column 전부 그대로)."""

    dependencies = [
        ("buildings", "0002_search_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="region",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                db_column="parent_code",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children",
                to="buildings.region",
            ),
        ),
    ]
