from django.db import migrations, models


class Migration(migrations.Migration):
    """SatelliteScene.region_code 추가 + 유일 제약을 (scene_id, region_code)로 교체
    (다지역 지원 6단계). 기존 행은 전부 대전(30)이므로 "30"으로 채우지만
    (preserve_default=False), 모델 자체에는 기본값을 두지 않는다."""

    dependencies = [
        ("satellite", "0005_rasterproduct_region_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="satellitescene",
            name="region_code",
            field=models.CharField(default="30", max_length=2),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="satellitescene",
            name="scene_id",
            field=models.CharField(max_length=80),
        ),
        migrations.AddConstraint(
            model_name="satellitescene",
            constraint=models.UniqueConstraint(
                fields=["scene_id", "region_code"], name="satellite_scene_id_region_uniq"
            ),
        ),
    ]
