from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="IndexRun",
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
                ("job", models.CharField(max_length=100)),
                ("region_code", models.CharField(max_length=50)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "queued"),
                            ("running", "running"),
                            ("succeeded", "succeeded"),
                            ("failed", "failed"),
                            ("skipped", "skipped"),
                        ],
                        default="queued",
                        max_length=20,
                    ),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("error", models.TextField(blank=True, null=True)),
            ],
            options={
                "db_table": "index_run",
            },
        ),
        migrations.AddIndex(
            model_name="indexrun",
            index=models.Index(
                fields=["job", "region_code"], name="core_indexr_job_f36c3e_idx"
            ),
        ),
    ]
