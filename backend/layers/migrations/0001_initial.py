from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MapLayer",
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
                ("name", models.CharField(max_length=100, unique=True)),
                ("group", models.CharField(max_length=50)),
                ("order", models.IntegerField(default=0)),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("vector_tile", "vector_tile"),
                            ("geojson", "geojson"),
                            ("titiler", "titiler"),
                            ("wms", "wms"),
                            ("raster_tile", "raster_tile"),
                        ],
                        max_length=20,
                    ),
                ),
                ("source_params", models.JSONField(blank=True, default=dict)),
                ("min_zoom", models.IntegerField(blank=True, null=True)),
                ("max_zoom", models.IntegerField(blank=True, null=True)),
                ("opacity", models.FloatField(default=1.0)),
                ("default_visible", models.BooleanField(default=False)),
                ("legend", models.JSONField(blank=True, null=True)),
                ("notice", models.TextField(blank=True, null=True)),
                ("attribution", models.CharField(blank=True, max_length=255, null=True)),
                ("synced_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "map_layer",
                "ordering": ["order"],
            },
        ),
    ]
