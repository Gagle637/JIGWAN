from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("buildings", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS pg_trgm;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="CREATE INDEX building_name_trgm_idx ON building USING GIN (name gin_trgm_ops);",
            reverse_sql="DROP INDEX IF EXISTS building_name_trgm_idx;",
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX building_dong_name_trgm_idx "
                "ON building USING GIN (dong_name gin_trgm_ops);"
            ),
            reverse_sql="DROP INDEX IF EXISTS building_dong_name_trgm_idx;",
        ),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX building_bjd_jibun_trgm_idx ON building USING GIN "
                "((coalesce(bjd_name, '') || ' ' || coalesce(jibun, '')) gin_trgm_ops);"
            ),
            reverse_sql="DROP INDEX IF EXISTS building_bjd_jibun_trgm_idx;",
        ),
    ]
