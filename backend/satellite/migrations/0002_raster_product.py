import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("satellite", "0001_initial"),
        ("buildings", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RasterProduct",
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
                (
                    "product_type",
                    models.CharField(
                        choices=[
                            ("ndvi", "ndvi"),
                            ("ndbi", "ndbi"),
                            ("green_mask", "green_mask"),
                            ("truecolor", "truecolor"),
                            ("change_mask", "change_mask"),
                        ],
                        max_length=20,
                    ),
                ),
                ("year", models.IntegerField()),
                (
                    "season",
                    models.CharField(
                        choices=[
                            ("spring", "spring"),
                            ("summer", "summer"),
                            ("fall", "fall"),
                            ("winter", "winter"),
                        ],
                        max_length=10,
                    ),
                ),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                ("compare_period", models.CharField(blank=True, max_length=5, null=True)),
                (
                    "bbox",
                    django.contrib.gis.db.models.fields.PolygonField(srid=4326),
                ),
                ("crs", models.CharField(default="EPSG:32652", max_length=20)),
                ("resolution_m", models.IntegerField(default=10)),
                ("cog_path", models.CharField(max_length=255)),
                ("algo_version", models.CharField(max_length=20)),
                ("scene_ids", models.JSONField()),
                ("valid_ratio", models.FloatField(blank=True, null=True)),
                ("is_published", models.BooleanField(default=False)),
            ],
            options={
                "db_table": "raster_product",
            },
        ),
        migrations.AddIndex(
            model_name="rasterproduct",
            index=models.Index(
                fields=["product_type", "period_start"], name="raster_product_type_period_idx"
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX raster_product_bbox_gist "
                "ON raster_product USING GIST (bbox);"
            ),
            reverse_sql="DROP INDEX IF EXISTS raster_product_bbox_gist;",
        ),
        migrations.CreateModel(
            name="ChangeArea",
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
                ("period", models.CharField(max_length=5)),
                ("area_m2", models.FloatField()),
                ("delta_ndbi", models.FloatField()),
                ("delta_ndvi", models.FloatField()),
                (
                    "geom",
                    django.contrib.gis.db.models.fields.PolygonField(srid=4326),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="change_areas",
                        to="satellite.rasterproduct",
                    ),
                ),
            ],
            options={
                "db_table": "change_area",
            },
        ),
        migrations.CreateModel(
            name="RegionStat",
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
                ("green_ratio", models.FloatField()),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="satellite.rasterproduct"
                    ),
                ),
                (
                    "region",
                    models.ForeignKey(
                        db_column="region_code",
                        on_delete=django.db.models.deletion.CASCADE,
                        to="buildings.region",
                        to_field="region_code",
                    ),
                ),
            ],
            options={
                "db_table": "region_stat",
            },
        ),
        migrations.AddConstraint(
            model_name="regionstat",
            constraint=models.UniqueConstraint(
                fields=("region", "product"), name="uq_region_stat_region_product"
            ),
        ),
    ]
