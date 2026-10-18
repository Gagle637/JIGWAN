import django.contrib.gis.db.models.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CrimeSegment",
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
                ("objt_id", models.CharField(max_length=40, unique=True)),
                ("grad", models.SmallIntegerField()),
                ("data_period", models.CharField(max_length=20)),
                ("geom", django.contrib.gis.db.models.fields.LineStringField(srid=4326)),
            ],
            options={
                "db_table": "crime_segment",
            },
        ),
        migrations.CreateModel(
            name="CrimeFetchProgress",
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
                ("cell_id", models.CharField(max_length=60, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "pending"),
                            ("done", "done"),
                            ("split", "split"),
                            ("failed", "failed"),
                        ],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("feature_count", models.IntegerField(blank=True, null=True)),
                ("fetched_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "crime_fetch_progress",
            },
        ),
        migrations.AddIndex(
            model_name="crimesegment",
            index=models.Index(fields=["grad"], name="crime_segment_grad_idx"),
        ),
    ]
