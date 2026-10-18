import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Building",
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
                ("building_key", models.CharField(max_length=40, unique=True)),
                ("gis_bldg_id", models.CharField(db_index=True, max_length=28)),
                ("pnu", models.CharField(db_index=True, max_length=19)),
                ("bjd_code", models.CharField(max_length=10)),
                ("bjd_name", models.CharField(blank=True, max_length=100, null=True)),
                ("jibun", models.CharField(blank=True, max_length=20, null=True)),
                ("use_code", models.CharField(blank=True, max_length=5, null=True)),
                ("use_name", models.CharField(blank=True, max_length=100, null=True)),
                ("structure", models.CharField(blank=True, max_length=100, null=True)),
                ("building_area_m2", models.FloatField(blank=True, null=True)),
                ("approval_date", models.DateField(blank=True, null=True)),
                ("total_floor_area_m2", models.FloatField(blank=True, null=True)),
                ("land_area_m2", models.FloatField(blank=True, null=True)),
                ("height_m", models.FloatField(blank=True, null=True)),
                ("bcr_pct", models.FloatField(blank=True, null=True)),
                ("far_pct", models.FloatField(blank=True, null=True)),
                ("is_violation", models.BooleanField(blank=True, null=True)),
                ("name", models.CharField(blank=True, max_length=150, null=True)),
                ("dong_name", models.CharField(blank=True, max_length=100, null=True)),
                ("floors_above", models.SmallIntegerField(blank=True, null=True)),
                ("floors_below", models.SmallIntegerField(blank=True, null=True)),
                ("source_date", models.DateField()),
                ("is_active", models.BooleanField(default=True)),
                (
                    "geom",
                    django.contrib.gis.db.models.fields.PolygonField(srid=4326),
                ),
            ],
            options={
                "db_table": "building",
                "indexes": [
                    models.Index(fields=["bjd_code"], name="building_bjd_code_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Region",
            fields=[
                (
                    "region_code",
                    models.CharField(max_length=10, primary_key=True, serialize=False),
                ),
                (
                    "level",
                    models.CharField(
                        choices=[
                            ("sido", "시도"),
                            ("sigungu", "시군구"),
                            ("bjd", "법정동"),
                        ],
                        max_length=10,
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("source_date", models.DateField(blank=True, null=True)),
                (
                    "geom",
                    django.contrib.gis.db.models.fields.MultiPolygonField(srid=4326),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        db_column="parent_code",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="children",
                        to="buildings.region",
                        to_field="region_code",
                    ),
                ),
            ],
            options={
                "db_table": "region",
                "indexes": [
                    models.Index(fields=["level"], name="region_level_idx"),
                ],
            },
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX building_geom_geography_gist "
                "ON building USING GIST ((geom::geography));"
            ),
            reverse_sql="DROP INDEX IF EXISTS building_geom_geography_gist;",
        ),
    ]
