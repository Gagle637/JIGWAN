from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("layers", "0003_maplayer_backfill_slug"),
    ]

    operations = [
        migrations.AlterField(
            model_name="maplayer",
            name="slug",
            field=models.SlugField(max_length=50, unique=True),
        ),
    ]
