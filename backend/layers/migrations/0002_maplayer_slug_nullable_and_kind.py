from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("layers", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="maplayer",
            name="slug",
            field=models.SlugField(max_length=50, null=True, blank=True, unique=False),
        ),
        migrations.AddField(
            model_name="maplayer",
            name="kind",
            field=models.CharField(
                max_length=20,
                choices=[("background", "background"), ("analysis", "analysis")],
                default="analysis",
            ),
        ),
    ]
