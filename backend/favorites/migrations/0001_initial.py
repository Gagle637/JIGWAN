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
            name="FavoriteFolder",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=50)),
                ("color", models.CharField(blank=True, max_length=7, null=True)),
                ("is_hidden", models.BooleanField(default=False)),
                ("sort_order", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="children",
                        to="favorites.favoritefolder",
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
                "db_table": "favorite_folder",
            },
        ),
        migrations.CreateModel(
            name="UserBuilding",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("is_favorite", models.BooleanField(default=False)),
                ("color", models.CharField(blank=True, max_length=7, null=True)),
                ("label", models.CharField(blank=True, max_length=20, null=True)),
                ("memo", models.TextField(blank=True, max_length=2000, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "building",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="buildings.building"
                    ),
                ),
                (
                    "folder",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="favorites.favoritefolder",
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
                "db_table": "user_building",
            },
        ),
        migrations.AddIndex(
            model_name="favoritefolder",
            index=models.Index(fields=["user", "parent"], name="favorite_folder_user_parent_idx"),
        ),
        migrations.AddIndex(
            model_name="userbuilding",
            index=models.Index(fields=["user", "folder"], name="user_building_user_folder_idx"),
        ),
        migrations.AddConstraint(
            model_name="userbuilding",
            constraint=models.UniqueConstraint(
                fields=["user", "building"], name="uq_user_building"
            ),
        ),
    ]
