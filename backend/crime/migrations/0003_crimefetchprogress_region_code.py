from django.db import migrations, models


class Migration(migrations.Migration):
    """CrimeFetchProgress.region_code 추가 + 유일 제약을 (cell_id, region_code)로 교체
    (다지역 지원 6단계). 기존 행은 전부 대전(30)이므로 "30"으로 채우지만
    (preserve_default=False), 모델 자체에는 기본값을 두지 않는다."""

    dependencies = [
        ("crime", "0002_crimesegment_geom_multipolygon"),
    ]

    operations = [
        migrations.AddField(
            model_name="crimefetchprogress",
            name="region_code",
            field=models.CharField(default="30", max_length=2),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="crimefetchprogress",
            name="cell_id",
            field=models.CharField(max_length=60),
        ),
        migrations.AddConstraint(
            model_name="crimefetchprogress",
            constraint=models.UniqueConstraint(
                fields=["cell_id", "region_code"], name="crime_fetch_progress_cell_region_uniq"
            ),
        ),
    ]
