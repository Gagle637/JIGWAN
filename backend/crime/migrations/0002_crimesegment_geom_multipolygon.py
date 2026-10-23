import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):
    """실측 확인: 범죄주의구간(전체) 응답이 도로 LineString이 아니라 MultiPolygon 밀도분석
    구역이다(spec 8-3). crime_segment에 아직 적재된 데이터가 없어 데이터 이관 없이 타입만
    바꾼다."""

    dependencies = [
        ("crime", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="crimesegment",
            name="geom",
            field=django.contrib.gis.db.models.fields.MultiPolygonField(srid=4326),
        ),
    ]
