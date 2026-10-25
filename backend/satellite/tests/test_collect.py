from datetime import date

import pytest

from core.models import ServiceArea
from satellite import collect as collect_module
from satellite.models import SatelliteScene

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
        collect_module, "search_scenes", lambda start, end, bbox=None: [listed_item, done_item]
    )
    ingested_ids = []
    monkeypatch.setattr(
        collect_module,
        "ingest_date_group",
        lambda items, grid=None, sido_code=None: ingested_ids.extend(i.id for i in items) or [],
    )

    result = collect_module.collect_scenes(date(2026, 6, 1), date(2026, 8, 31))

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

    monkeypatch.setattr(collect_module, "search_scenes", lambda start, end, bbox=None: [item])
    ingested_ids = []
    monkeypatch.setattr(
        collect_module,
        "ingest_date_group",
        lambda items, grid=None, sido_code=None: ingested_ids.extend(i.id for i in items) or [],
    )

    result = collect_module.collect_scenes(date(2026, 6, 1), date(2026, 8, 31), sido_code="30")

    assert item.id in ingested_ids
    assert result["skipped_existing"] == 0
