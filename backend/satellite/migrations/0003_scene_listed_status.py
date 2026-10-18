from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("satellite", "0002_raster_product"),
    ]

    operations = [
        migrations.AlterField(
            model_name="satellitescene",
            name="status",
            field=models.CharField(
                choices=[
                    ("listed", "listed"),
                    ("ready", "ready"),
                    ("excluded", "excluded"),
                    ("failed", "failed"),
                ],
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="satellitescene",
            name="band_offsets",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="satellitescene",
            name="boa_quantification_value",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
