import django.contrib.gis.db.models.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Trade",
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
                ("sgg_code", models.CharField(max_length=5)),
                ("pnu", models.CharField(blank=True, db_index=True, max_length=19, null=True)),
                (
                    "house_type",
                    models.CharField(
                        choices=[
                            ("apartment", "아파트"),
                            ("officetel", "오피스텔"),
                            ("row_house", "연립다세대"),
                            ("detached", "단독다가구"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "deal_type",
                    models.CharField(
                        choices=[("sale", "매매"), ("rent", "전월세")], max_length=10
                    ),
                ),
                ("deal_ym", models.CharField(max_length=7)),
                ("deal_day", models.SmallIntegerField(blank=True, null=True)),
                ("area_m2", models.FloatField(blank=True, null=True)),
                ("price", models.IntegerField(blank=True, null=True)),
                ("deposit", models.IntegerField(blank=True, null=True)),
                ("monthly_rent", models.IntegerField(blank=True, null=True)),
                (
                    "apt_seq",
                    models.CharField(blank=True, db_index=True, max_length=20, null=True),
                ),
                ("building_name", models.CharField(blank=True, max_length=150, null=True)),
                ("floor", models.SmallIntegerField(blank=True, null=True)),
                ("build_year", models.SmallIntegerField(blank=True, null=True)),
                ("is_canceled", models.BooleanField(default=False)),
                ("canceled_at", models.DateField(blank=True, null=True)),
                (
                    "match_failure_reason",
                    models.CharField(blank=True, max_length=50, null=True),
                ),
                ("raw_bjd_name", models.CharField(blank=True, max_length=100, null=True)),
                ("raw_jibun", models.CharField(blank=True, max_length=50, null=True)),
                (
                    "geom",
                    django.contrib.gis.db.models.fields.PointField(
                        blank=True, null=True, srid=4326
                    ),
                ),
            ],
            options={
                "db_table": "trade",
            },
        ),
        migrations.AddIndex(
            model_name="trade",
            index=models.Index(fields=["pnu", "deal_ym"], name="trade_pnu_deal_ym_idx"),
        ),
        migrations.AddIndex(
            model_name="trade",
            index=models.Index(
                fields=["house_type", "deal_type", "sgg_code", "deal_ym"],
                name="trade_type_sgg_ym_idx",
            ),
        ),
    ]
