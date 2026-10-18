from datetime import date

import pytest
from django.contrib.gis.geos import Polygon

from satellite import backfill as backfill_module
from satellite.composite import ALGO_VERSION
from satellite.models import RasterProduct, SatelliteScene
from satellite.stac_search import DAEJEON_BBOX

pytestmark = pytest.mark.django_db


class FakeItem:
    def __init__(self, item_id: str, dt_iso: str, cloud: float = 10.0):
        self.id = item_id
        self.properties = {"datetime": dt_iso, "eo:cloud_cover": cloud}


def test_target_seasons_matches_spec_example():
    """spec 4장: "2026년 10월 기준이면 2023년 여름부터 2026년 여름까지"(13개 계절 슬롯)."""
    seasons = backfill_module.target_seasons(date(2026, 10, 16))

    assert len(seasons) == 13
    assert seasons[0] == (2023, "summer")
    assert seasons[-1] == (2026, "summer")


def test_target_seasons_handles_january_as_previous_years_winter():
    seasons = backfill_module.target_seasons(date(2026, 1, 15))

    # 1월은 작년 12월에 시작한 겨울에 속하므로(spec 3-3), 그 전 계절은 (작년-1)년 가을이다.
    assert seasons[-1] == (2025, "winter")


def test_dry_run_list_scenes_creates_listed_rows_and_skips_existing(monkeypatch):
    existing = SatelliteScene.objects.create(
        scene_id="S2B_MSIL2A_20230615T085559_N0512_R007_T52SCF_20230615T111845",
        sensed_at="2023-06-15T08:55:59+00:00",
        mgrs_tile="T52SCF",
        cloud_pct=5.0,
        processing_baseline="N0512",
        band_offsets={},
        boa_quantification_value=10000,
        status=SatelliteScene.Status.READY,
        cog_path="/tmp/x.tif",
    )
    new_item = FakeItem(
        "S2B_MSIL2A_20230620T085559_N0512_R007_T52SCF_20230620T111845", "2023-06-20T08:55:59Z"
    )

    def fake_search_scenes(start, end):
        if start.year == 2023 and start.month in (6, 7, 8):
            return [
                FakeItem(existing.scene_id, "2023-06-15T08:55:59Z"),
                new_item,
            ]
        return []

    monkeypatch.setattr(backfill_module, "search_scenes", fake_search_scenes)

    summary = backfill_module.dry_run_list_scenes([(2023, "summer")])

    assert summary["total_new_scenes"] == 1
    assert summary["estimated_download_mb"] == backfill_module.ESTIMATED_MB_PER_SCENE
    assert SatelliteScene.objects.filter(scene_id=existing.scene_id).count() == 1
    listed = SatelliteScene.objects.get(scene_id=new_item.id)
    assert listed.status == SatelliteScene.Status.LISTED
    assert listed.band_offsets is None


def _publish_all_product_types(year, season):
    bbox = Polygon.from_bbox(DAEJEON_BBOX)
    for product_type in ("ndvi", "ndbi", "green_mask", "truecolor"):
        RasterProduct.objects.create(
            product_type=product_type,
            year=year,
            season=season,
            period_start=f"{year}-06-01",
            period_end=f"{year}-08-31",
            bbox=bbox,
            cog_path=f"/tmp/{product_type}.tif",
            algo_version=ALGO_VERSION,
            scene_ids=[],
            is_published=True,
        )


def test_run_backfill_skips_season_already_fully_published(monkeypatch):
    _publish_all_product_types(2023, "summer")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("이미 게시된 계절은 다시 수집하면 안 된다")

    monkeypatch.setattr(backfill_module, "collect_scenes", fail_if_called)
    monkeypatch.setattr(backfill_module, "run_season_chain_sync", fail_if_called)

    results = backfill_module.run_backfill([(2023, "summer")])

    assert results == [{"season": "2023-summer", "skipped": True}]


def test_run_backfill_processes_unfinished_season(monkeypatch):
    calls = []
    monkeypatch.setattr(
        backfill_module, "collect_scenes", lambda start, end: {"ready": 1, "excluded": 0}
    )
    monkeypatch.setattr(
        backfill_module,
        "run_season_chain_sync",
        lambda year, season: calls.append((year, season)) or {"catalog_publish": "ok"},
    )

    results = backfill_module.run_backfill([(2023, "summer")])

    assert calls == [(2023, "summer")]
    assert results[0]["season"] == "2023-summer"
    assert results[0]["chain"] == {"catalog_publish": "ok"}
