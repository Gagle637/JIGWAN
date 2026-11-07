from django.db import migrations

# spec 10-1 MVP 9개 행의 기존 표시 이름 -> 고정 slug. seed_map_layers.py가 이름을 바꿔도
# (예: "(10m 해상도)" 접미사 추가) 같은 행을 찾아 갱신하려면 이름이 아닌 이 slug로
# upsert해야 한다 — 그 전환의 첫 데이터 이관.
NAME_TO_SLUG = {
    "배경지도": "osm_basemap",
    "건물 풋프린트": "building_footprint",
    "내 표시 건물": "my_buildings",
    "분석 반경": "analysis_radius",
    "녹지 마스크": "green_mask",
    "개발 변화 구역": "change_area",
    "Before/After 위성 영상": "before_after",
    "실거래 위치": "trade_location",
    "범죄주의구간(전체)": "crime_hotspot",
}


def backfill_slug(apps, schema_editor):
    MapLayer = apps.get_model("layers", "MapLayer")
    unmapped = []
    for layer in MapLayer.objects.all():
        slug = NAME_TO_SLUG.get(layer.name)
        if slug is None:
            unmapped.append(layer.name)
            continue
        layer.slug = slug
        layer.save(update_fields=["slug"])
    if unmapped:
        # 매핑에 없는 이름이 있으면 조용히 건너뛰지 않고 마이그레이션 자체를 실패시킨다 —
        # slug 없는 행이 남으면 다음 마이그레이션(0004, NOT NULL+unique)이 깨지므로, 그
        # 전에 사람이 NAME_TO_SLUG를 고치고 다시 돌리게 한다.
        raise RuntimeError(
            f"NAME_TO_SLUG에 없는 map_layer.name이 있습니다: {unmapped}. "
            "이 마이그레이션의 NAME_TO_SLUG에 매핑을 추가한 뒤 다시 실행하세요."
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("layers", "0002_maplayer_slug_nullable_and_kind"),
    ]

    operations = [
        migrations.RunPython(backfill_slug, noop_reverse),
    ]
