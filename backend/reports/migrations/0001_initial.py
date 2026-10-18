import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("buildings", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Report",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("radius_m", models.IntegerField()),
                (
                    "report_type",
                    models.CharField(
                        choices=[("template", "template"), ("custom", "custom")], max_length=10
                    ),
                ),
                ("template_version", models.CharField(blank=True, max_length=20, null=True)),
                ("prompt_version", models.CharField(blank=True, max_length=20, null=True)),
                ("user_prompt", models.TextField(blank=True, max_length=500, null=True)),
                ("input_snapshot", models.JSONField()),
                ("model", models.CharField(blank=True, max_length=100, null=True)),
                ("payload", models.JSONField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("generating", "generating"),
                            ("ready", "ready"),
                            ("failed", "failed"),
                        ],
                        default="generating",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "building",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="buildings.building"
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
            options={
                "db_table": "report",
            },
        ),
        migrations.AddIndex(
            model_name="report",
            index=models.Index(
                fields=["user", "building", "created_at"], name="report_user_building_created_idx"
            ),
        ),
    ]
