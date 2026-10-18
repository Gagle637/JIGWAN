from datetime import date

import pytest

from satellite import collect as collect_module
from satellite.models import SatelliteScene

pytestmark = pytest.mark.django_db


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
        sensed_at="2026-06-01T08:55:59+00:00",
        mgrs_tile="T52SCF",
        cloud_pct=5.0,
        processing_baseline="N0512",
        status=SatelliteScene.Status.LISTED,
    )
    SatelliteScene.objects.create(
        scene_id=done_item.id,
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
        collect_module, "search_scenes", lambda start, end: [listed_item, done_item]
    )
    ingested_ids = []
    monkeypatch.setattr(
        collect_module,
        "ingest_date_group",
        lambda items: ingested_ids.extend(i.id for i in items) or [],
    )

    result = collect_module.collect_scenes(date(2026, 6, 1), date(2026, 8, 31))

    assert listed_item.id in ingested_ids
    assert done_item.id not in ingested_ids
    assert result["skipped_existing"] == 1
