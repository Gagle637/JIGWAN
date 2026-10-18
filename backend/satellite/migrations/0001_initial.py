from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SatelliteScene",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("scene_id", models.CharField(max_length=80, unique=True)),
                ("sensed_at", models.DateTimeField()),
                ("mgrs_tile", models.CharField(max_length=10)),
                ("cloud_pct", models.FloatField()),
                ("processing_baseline", models.CharField(max_length=10)),
                ("band_offsets", models.JSONField()),
                ("boa_quantification_value", models.IntegerField()),
                ("valid_ratio", models.FloatField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ready", "ready"),
                            ("excluded", "excluded"),
                            ("failed", "failed"),
                        ],
                        max_length=10,
                    ),
                ),
                ("cog_path", models.CharField(blank=True, max_length=255, null=True)),
                ("scl_cog_path", models.CharField(blank=True, max_length=255, null=True)),
                ("error", models.TextField(blank=True, null=True)),
            ],
            options={
                "db_table": "satellite_scene",
            },
        ),
        migrations.AddIndex(
            model_name="satellitescene",
            index=models.Index(
                fields=["mgrs_tile", "sensed_at"], name="satellite_tile_sensed_idx"
            ),
        ),
    ]
