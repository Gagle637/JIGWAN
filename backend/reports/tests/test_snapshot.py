from reports import snapshot


def test_build_report_input_strips_geometry_tiles_my(monkeypatch):
    fake_response = {
        "status": "ready",
        "building": {"id": 1, "geometry": {"type": "Polygon", "coordinates": []}, "name": "x"},
        "change": {
            "total_area_m2": 10.0,
            "tiles": {"after": "...", "before": {}, "default_compare": None},
        },
        "my": {"is_favorite": True},
        "green": {"ratio_pct": 1.0},
    }
    monkeypatch.setattr(snapshot, "get_insight_cached", lambda building, radius_m: fake_response)

    result = snapshot.build_report_input(object(), 500)

    assert "my" not in result
    assert "geometry" not in result["building"]
    assert "tiles" not in result["change"]
    assert result["green"] == {"ratio_pct": 1.0}
    # 원본은 변형되지 않아야 한다(deepcopy)
    assert "geometry" in fake_response["building"]
    assert "tiles" in fake_response["change"]


def test_build_report_input_handles_pending_status_without_change_section(monkeypatch):
    fake_response = {
        "status": "pending",
        "building": {"id": 1, "geometry": {"type": "Polygon", "coordinates": []}},
        "change": None,
        "green": None,
        "my": None,
    }
    monkeypatch.setattr(snapshot, "get_insight_cached", lambda building, radius_m: fake_response)

    result = snapshot.build_report_input(object(), 500)

    assert result["change"] is None
    assert "geometry" not in result["building"]
    assert "my" not in result
