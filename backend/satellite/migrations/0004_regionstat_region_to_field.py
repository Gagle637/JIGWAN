import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """RegionStat.region FK 정리(감사 결과) — buildings.0003_region_parent_to_field와 같은
    이유: to_field="region_code"가 buildings.Region의 기본키 이름과 같아서 Django가
    deconstruct() 시 to_field를 생략한다. DB 컬럼·참조 대상은 그대로다."""

    dependencies = [
        ("satellite", "0003_scene_listed_status"),
        ("buildings", "0003_region_parent_to_field"),
    ]

    operations = [
        migrations.AlterField(
            model_name="regionstat",
            name="region",
            field=models.ForeignKey(
                db_column="region_code",
                on_delete=django.db.models.deletion.CASCADE,
                to="buildings.region",
            ),
        ),
    ]
