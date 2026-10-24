from django.db import migrations


def seed_daejeon(apps, schema_editor):
    ServiceArea = apps.get_model("core", "ServiceArea")
    ServiceArea.objects.get_or_create(
        sido_code="30", defaults={"name": "대전광역시", "enabled": True}
    )


def unseed_daejeon(apps, schema_editor):
    ServiceArea = apps.get_model("core", "ServiceArea")
    ServiceArea.objects.filter(sido_code="30").delete()


class Migration(migrations.Migration):
    """초기 데이터(docs/tasks/multi_area.md 1단계). bbox/grid는 비워 둔다 — region(sido=30)이
    아직 없는 빈 DB 상태라 계산할 수 없고, load_regions가 시도 행을 만들 때 채운다."""

    dependencies = [
        ("core", "0003_servicearea"),
    ]

    operations = [
        migrations.RunPython(seed_daejeon, unseed_daejeon),
    ]
