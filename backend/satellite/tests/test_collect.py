from datetime import date

import pytest
from django.contrib.gis.geos import Polygon

from core.models import ServiceArea
from satellite import collect as collect_module
from satellite.models import RasterProduct, SatelliteScene

pytestmark = pytest.mark.django_db

_GRID = {
    "crs": "EPSG:32652",
    "resolution_m": 10,
    "minx": 341700,
    "miny": 4004820,
    "maxx": 371040,
    "maxy": 4040880,
    "width": 2934,
    "height": 3606,
}


@pytest.fixture(autouse=True)
def _service_area(db):
    ServiceArea.objects.filter(sido_code="30").update(
        bbox_minx=127.24, bbox_miny=36.18, bbox_maxx=127.56, bbox_maxy=36.50, grid=_GRID
    )


class FakeItem:
    def __init__(self, item_id: str, dt_iso: str):
        self.id = item_id
        self.properties = {"datetime": dt_iso, "eo:cloud_cover": 5.0}


def test_listed_scene_is_not_treated_as_already_collected(monkeypatch):
    """백필 dry run이 status=listed로 미리 적어둔 장면은 아직 안 받은 것이니 건너뛰면 안 된다
    (일반 ready/excluded/failed 장면만 '이미 처리됨'으로 친다)."""
    listed_item = FakeItem(
        "S2B_MSIL2A_20260601T085559_N0512_R007_T52SCF_20260601T111845", "2026-06-01T08:55:59Z"
    )
    done_item = FakeItem(
        "S2B_MSIL2A_20260602T085559_N0512_R007_T52SCF_20260602T111845", "2026-06-02T08:55:59Z"
    )
    SatelliteScene.objects.create(
        scene_id=listed_item.id,
        region_code="30",
        sensed_at="2026-06-01T08:55:59+00:00",
        mgrs_tile="T52SCF",
        cloud_pct=5.0,
        processing_baseline="N0512",
        status=SatelliteScene.Status.LISTED,
    )
    SatelliteScene.objects.create(
        scene_id=done_item.id,
        region_code="30",
        sensed_at="2026-06-02T08:55:59+00:00",
        mgrs_tile="T52SCF",
        cloud_pct=5.0,
        processing_baseline="N0512",
        band_offsets={},
        boa_quantification_value=10000,
        status=SatelliteScene.Status.READY,
        cog_path="/tmp/x.tif",
    )

    monkeypatch.setattr(
        collect_module,
        "search_scenes",
        lambda start, end, bbox=None, max_cloud=None: [listed_item, done_item],
    )
    ingested_ids = []
    monkeypatch.setattr(
        collect_module,
        "ingest_date_group",
        lambda items, grid=None, sido_code=None: ingested_ids.extend(i.id for i in items) or [],
    )

    result = collect_module.collect_scenes(date(2026, 6, 1), date(2026, 8, 31), sido_code="30")

    assert listed_item.id in ingested_ids
    assert done_item.id not in ingested_ids
    assert result["skipped_existing"] == 1


def test_scene_already_done_in_another_region_is_still_new_for_this_region(monkeypatch):
    """다른 지역(36)이 이미 처리(ready)한 scene_id라도, 이 지역(30)은 아직 안 처리했으니
    "새 장면"으로 처리해야 한다(다지역 지원 6단계) — region_code로 안 좁히면 다른 지역의
    처리 완료를 보고 이 지역에서 건너뛰게 된다."""
    item = FakeItem(
        "S2B_MSIL2A_20260603T085559_N0512_R007_T52SCF_20260603T111845", "2026-06-03T08:55:59Z"
    )
    SatelliteScene.objects.create(
        scene_id=item.id,
        region_code="36",
        sensed_at="2026-06-03T08:55:59+00:00",
        mgrs_tile="T52SCF",
        cloud_pct=5.0,
        processing_baseline="N0512",
        band_offsets={},
        boa_quantification_value=10000,
        status=SatelliteScene.Status.READY,
        cog_path="/tmp/x.tif",
    )

    monkeypatch.setattr(
        collect_module, "search_scenes", lambda start, end, bbox=None, max_cloud=None: [item]
    )
    ingested_ids = []
    monkeypatch.setattr(
        collect_module,
        "ingest_date_group",
        lambda items, grid=None, sido_code=None: ingested_ids.extend(i.id for i in items) or [],
    )

    result = collect_module.collect_scenes(date(2026, 6, 1), date(2026, 8, 31), sido_code="30")

    assert item.id in ingested_ids
    assert result["skipped_existing"] == 0


def test_collect_scenes_passes_settings_max_cloud_pct_to_search(monkeypatch, settings):
    """eo:cloud_cover 상한은 .env의 SATELLITE_MAX_CLOUD_PCT를 그대로 쓴다(장마철 여름 계절이
    타일 전체 구름양 때문에 장면 0~2개로 잘려 나가던 문제의 해결책) — 기본값 30이 아니라
    settings 값이 search_scenes로 전달되는지 확인한다."""
    settings.SATELLITE_MAX_CLOUD_PCT = 70
    captured = {}
    monkeypatch.setattr(
        collect_module,
        "search_scenes",
        lambda start, end, bbox=None, max_cloud=None: captured.update(max_cloud=max_cloud) or [],
    )
    monkeypatch.setattr(
        collect_module, "ingest_date_group", lambda items, grid=None, sido_code=None: []
    )

    collect_module.collect_scenes(date(2026, 6, 1), date(2026, 8, 31), sido_code="30")

    assert captured["max_cloud"] == 70


# ---- 버그2: baseline 재처리(다른 실행에서 더 높은 baseline으로 재공개) ----


def test_baseline_upgrade_supersedes_old_scene_and_reingests_it(monkeypatch):
    old_item_id = "S2B_MSIL2A_20260601T085559_N0511_R007_T52SCF_20260601T111845"
    new_item = FakeItem(
        "S2B_MSIL2A_20260601T085559_N0512_R007_T52SCF_20260601T111845", "2026-06-01T08:55:59Z"
    )
    old_scene = SatelliteScene.objects.create(
        scene_id=old_item_id, region_code="30", sensed_at="2026-06-01T08:55:59+00:00",
        mgrs_tile="T52SCF", cloud_pct=5.0, processing_baseline="N0511",
        band_offsets={}, boa_quantification_value=10000, status=SatelliteScene.Status.READY,
        cog_path="/tmp/old.tif", scl_cog_path="/tmp/old_scl.tif",
    )

    monkeypatch.setattr(
        collect_module, "search_scenes", lambda start, end, bbox=None, max_cloud=None: [new_item]
    )
    ingested_ids = []
    monkeypatch.setattr(
        collect_module, "ingest_date_group",
        lambda items, grid=None, sido_code=None: ingested_ids.extend(i.id for i in items) or [],
    )

    result = collect_module.collect_scenes(date(2026, 6, 1), date(2026, 8, 31), sido_code="30")

    assert new_item.id in ingested_ids
    old_scene.refresh_from_db()
    assert old_scene.status == SatelliteScene.Status.SUPERSEDED
    assert result["superseded_affecting_published_seasons"] == []


def test_baseline_upgrade_on_shared_cog_path_resupersedes_whole_group_and_reingests_both_tiles(
    monkeypatch,
):
    """2타일 병합(같은 cog_path 공유)에서 한쪽 타일만 재처리돼도, 공유 파일 전체가
    superseded가 되고 날짜 그룹 전체(변경 안 된 타일 포함)가 다시 ingest돼야 한다 —
    안 그러면 한쪽만 새 COG로 바뀌어 겹치는 영역이 두 번 세어진다."""
    shared_cog = "/tmp/shared.tif"
    old_tile_a_id = "S2B_MSIL2A_20260601T085559_N0511_R007_T52SCF_20260601T111845"
    old_tile_b_id = "S2B_MSIL2A_20260601T090102_N0511_R007_T52SDF_20260601T112000"
    new_tile_a = FakeItem(
        "S2B_MSIL2A_20260601T085559_N0512_R007_T52SCF_20260601T111845", "2026-06-01T08:55:59Z"
    )
    unchanged_tile_b = FakeItem(old_tile_b_id, "2026-06-01T09:01:02Z")

    old_a = SatelliteScene.objects.create(
        scene_id=old_tile_a_id, region_code="30", sensed_at="2026-06-01T08:55:59+00:00",
        mgrs_tile="T52SCF", cloud_pct=5.0, processing_baseline="N0511",
        band_offsets={}, boa_quantification_value=10000, status=SatelliteScene.Status.READY,
        cog_path=shared_cog, scl_cog_path="/tmp/shared_scl.tif",
    )
    old_b = SatelliteScene.objects.create(
        scene_id=old_tile_b_id, region_code="30", sensed_at="2026-06-01T09:01:02+00:00",
        mgrs_tile="T52SDF", cloud_pct=5.0, processing_baseline="N0511",
        band_offsets={}, boa_quantification_value=10000, status=SatelliteScene.Status.READY,
        cog_path=shared_cog, scl_cog_path="/tmp/shared_scl.tif",
    )

    monkeypatch.setattr(
        collect_module, "search_scenes",
        lambda start, end, bbox=None, max_cloud=None: [new_tile_a, unchanged_tile_b],
    )
    ingested_ids = []
    monkeypatch.setattr(
        collect_module, "ingest_date_group",
        lambda items, grid=None, sido_code=None: ingested_ids.extend(i.id for i in items) or [],
    )

    collect_module.collect_scenes(date(2026, 6, 1), date(2026, 8, 31), sido_code="30")

    assert set(ingested_ids) == {new_tile_a.id, unchanged_tile_b.id}
    old_a.refresh_from_db()
    old_b.refresh_from_db()
    assert old_a.status == SatelliteScene.Status.SUPERSEDED
    assert old_b.status == SatelliteScene.Status.SUPERSEDED


def test_baseline_regression_or_duplicate_item_is_skipped_and_existing_untouched(monkeypatch):
    existing_id = "S2B_MSIL2A_20260601T085559_N0512_R007_T52SCF_20260601T111845"
    regressed_item = FakeItem(
        "S2B_MSIL2A_20260601T085559_N0400_R007_T52SCF_20260601T111845", "2026-06-01T08:55:59Z"
    )
    existing = SatelliteScene.objects.create(
        scene_id=existing_id, region_code="30", sensed_at="2026-06-01T08:55:59+00:00",
        mgrs_tile="T52SCF", cloud_pct=5.0, processing_baseline="N0512",
        band_offsets={}, boa_quantification_value=10000, status=SatelliteScene.Status.READY,
        cog_path="/tmp/good.tif", scl_cog_path="/tmp/good_scl.tif",
    )

    monkeypatch.setattr(
        collect_module, "search_scenes",
        lambda start, end, bbox=None, max_cloud=None: [regressed_item],
    )
    ingested_ids = []
    monkeypatch.setattr(
        collect_module, "ingest_date_group",
        lambda items, grid=None, sido_code=None: ingested_ids.extend(i.id for i in items) or [],
    )

    collect_module.collect_scenes(date(2026, 6, 1), date(2026, 8, 31), sido_code="30")

    assert ingested_ids == []
    existing.refresh_from_db()
    assert existing.status == SatelliteScene.Status.READY


def test_superseded_scene_used_in_published_product_is_reported_but_not_reprocessed(monkeypatch):
    old_item_id = "S2B_MSIL2A_20260601T085559_N0511_R007_T52SCF_20260601T111845"
    new_item = FakeItem(
        "S2B_MSIL2A_20260601T085559_N0512_R007_T52SCF_20260601T111845", "2026-06-01T08:55:59Z"
    )
    SatelliteScene.objects.create(
        scene_id=old_item_id, region_code="30", sensed_at="2026-06-01T08:55:59+00:00",
        mgrs_tile="T52SCF", cloud_pct=5.0, processing_baseline="N0511",
        band_offsets={}, boa_quantification_value=10000, status=SatelliteScene.Status.READY,
        cog_path="/tmp/old.tif", scl_cog_path="/tmp/old_scl.tif",
    )
    RasterProduct.objects.create(
        region_code="30", product_type="ndvi", year=2026, season="summer",
        period_start="2026-06-01", period_end="2026-08-31",
        bbox=Polygon.from_bbox((127.24, 36.18, 127.56, 36.50)),
        cog_path="/tmp/x.tif", algo_version="green_v1",
        scene_ids=[old_item_id], is_published=True,
    )

    monkeypatch.setattr(
        collect_module, "search_scenes", lambda start, end, bbox=None, max_cloud=None: [new_item]
    )
    monkeypatch.setattr(
        collect_module, "ingest_date_group", lambda items, grid=None, sido_code=None: []
    )

    result = collect_module.collect_scenes(date(2026, 6, 1), date(2026, 8, 31), sido_code="30")

    assert result["superseded_affecting_published_seasons"] == ["2026-summer"]
