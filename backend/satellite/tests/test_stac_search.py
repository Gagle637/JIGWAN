from datetime import date

from satellite.stac_search import (
    baseline_number,
    dedupe_latest_baseline,
    group_by_date,
    processing_baseline,
    sensed_at,
    tile_code,
)


class FakeItem:
    def __init__(self, item_id: str, dt_iso: str, cloud_cover: float = 10.0):
        self.id = item_id
        self.properties = {"datetime": dt_iso, "eo:cloud_cover": cloud_cover}


def _compact(dt_iso: str) -> str:
    """'2026-08-09T08:55:59Z' -> '20260809T085559' (item.id에 쓰는 압축 형식)."""
    date_part, time_part = dt_iso.rstrip("Z").split("T")
    return date_part.replace("-", "") + "T" + time_part.replace(":", "")


def _item(tile: str, dt_iso: str, baseline: str, cloud: float = 10.0) -> FakeItem:
    compact = _compact(dt_iso)
    item_id = f"S2B_MSIL2A_{compact}_{baseline}_R007_{tile}_{compact}"
    return FakeItem(item_id, dt_iso, cloud)


def test_tile_code_and_baseline_from_item_id():
    item = _item("T52SCF", "2026-08-09T08:55:59Z", "N0512")
    assert tile_code(item) == "T52SCF"
    assert processing_baseline(item) == "N0512"
    assert baseline_number(item) == 512


def test_sensed_at_parses_datetime_property():
    item = _item("T52SCF", "2026-08-09T08:55:59Z", "N0512")
    assert sensed_at(item).date() == date(2026, 8, 9)


def test_dedupe_latest_baseline_keeps_highest():
    old = _item("T52SCF", "2026-08-09T08:55:59Z", "N0400")
    new = _item("T52SCF", "2026-08-09T08:55:59Z", "N0512")

    result = dedupe_latest_baseline([old, new])

    assert len(result) == 1
    assert result[0] is new


def test_dedupe_latest_baseline_keeps_different_tiles_and_dates_separate():
    tile_a = _item("T52SCF", "2026-08-09T08:55:59Z", "N0512")
    tile_b = _item("T52SDF", "2026-08-09T08:55:59Z", "N0512")
    other_date = _item("T52SCF", "2026-08-14T08:55:59Z", "N0512")

    result = dedupe_latest_baseline([tile_a, tile_b, other_date])

    assert len(result) == 3


def test_group_by_date_groups_two_tiles_same_day():
    tile_a = _item("T52SCF", "2026-08-09T08:55:59Z", "N0512")
    tile_b = _item("T52SDF", "2026-08-09T09:01:02Z", "N0512")
    other_day = _item("T52SCF", "2026-08-14T08:55:59Z", "N0512")

    groups = group_by_date([tile_a, tile_b, other_day])

    assert len(groups) == 2
    assert len(groups[date(2026, 8, 9)]) == 2
    assert len(groups[date(2026, 8, 14)]) == 1
