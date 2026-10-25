from django.db import migrations, models


class Migration(migrations.Migration):
    """RasterProduct.region_code 추가(다지역 지원 5단계). 기존 행은 전부 대전(30)이므로
    "30"으로 채우지만(preserve_default=False), 모델 자체에는 기본값을 두지 않는다 — 앞으로
    지역 코드 없이 저장하면 안 되기 때문이다."""

    dependencies = [
        ("satellite", "0004_regionstat_region_to_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="rasterproduct",
            name="region_code",
            field=models.CharField(default="30", max_length=2),
            preserve_default=False,
        ),
        migrations.RemoveIndex(
            model_name="rasterproduct",
            name="raster_product_type_period_idx",
        ),
        migrations.AddIndex(
            model_name="rasterproduct",
            index=models.Index(
                fields=["region_code", "product_type", "period_start"],
                name="raster_product_type_period_idx",
            ),
        ),
    ]
