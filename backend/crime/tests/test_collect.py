import pytest

from core.exceptions import ExternalCallError
from crime import collect, grid
from crime.models import CrimeFetchProgress, CrimeSegment

pytestmark = pytest.mark.django_db


def _feature(objt_id, grad, coords):
    return {
        "properties": {"OBJT_ID": objt_id, "TY_CD": "10201000", "GRAD": grad},
        "geometry": {"type": "LineString", "coordinates": coords},
    }


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """1-2초 요청 간격·1·5·25분 재시도 대기를 테스트에서 실제로 기다리지 않게 한다."""
    monkeypatch.setattr(collect.time, "sleep", lambda seconds: None)


def test_run_safety_sync_requires_feature_cap_configured(settings):
    settings.CRIME_FEATURE_CAP = None

    with pytest.raises(collect.FeatureCapNotConfigured):
        collect.run_safety_sync("2023-07/2024-06")


def test_run_safety_sync_saves_features_for_a_single_small_grid(monkeypatch, settings):
    settings.CRIME_FEATURE_CAP = 100
    monkeypatch.setattr(grid, "base_cells", lambda: [(0.0, 0.0, 2000.0)])
    monkeypatch.setattr(
        collect,
        "fetch_feature_info",
        lambda client, bbox, count: [
            _feature("OBJ1", 5, [[0, 0], [10, 10]]),
            _feature("OBJ2", 9, [[20, 20], [30, 30]]),
        ],
    )

    result = collect.run_safety_sync("2023-07/2024-06")

    assert result["cells_done"] == 1
    assert result["cells_failed"] == 0
    assert result["fully_done"] is True
    assert CrimeSegment.objects.count() == 2
    seg = CrimeSegment.objects.get(objt_id="OBJ1")
    assert seg.grad == 5
    assert seg.data_period == "2023-07/2024-06"


def test_run_safety_sync_splits_cell_at_feature_cap_and_processes_children(monkeypatch, settings):
    settings.CRIME_FEATURE_CAP = 2
    monkeypatch.setattr(grid, "base_cells", lambda: [(0.0, 0.0, 2000.0)])

    calls = []

    def fake_fetch(client, bbox, count):
        calls.append(bbox)
        size_m = bbox[2] - bbox[0]
        if size_m > grid.MIN_CELL_SIZE_M and len(calls) == 1:
            # 큰 셀(첫 호출)은 상한과 같은 개수를 돌려줘 분할을 유도한다.
            return [_feature(f"BIG{i}", 5, [[0, 0], [1, 1]]) for i in range(2)]
        return [_feature(f"CHILD{len(calls)}", 3, [[0, 0], [1, 1]])]

    monkeypatch.setattr(collect, "fetch_feature_info", fake_fetch)

    result = collect.run_safety_sync("2023-07/2024-06")

    assert result["cells_done"] == 4  # 부모는 split, 자식 4개가 done
    assert (
        CrimeFetchProgress.objects.filter(status=CrimeFetchProgress.Status.SPLIT).count() == 1
    )
    assert (
        CrimeFetchProgress.objects.filter(status=CrimeFetchProgress.Status.DONE).count() == 4
    )
    # 큰 셀 응답(BIG*)은 잘렸을 수 있어 버려야 하고, 자식 응답만 저장돼야 한다.
    assert not CrimeSegment.objects.filter(objt_id__startswith="BIG").exists()
    assert CrimeSegment.objects.filter(objt_id__startswith="CHILD").count() == 4


def test_run_safety_sync_resumes_only_unfinished_cells_and_cleans_stale_segments_when_done(
    monkeypatch, settings
):
    settings.CRIME_FEATURE_CAP = 100
    monkeypatch.setattr(
        grid, "base_cells", lambda: [(0.0, 0.0, 2000.0), (2000.0, 0.0, 2000.0)]
    )

    # 이전 실행에서 하나는 이미 done, 하나는 pending으로 중단된 상태를 흉내낸다.
    CrimeFetchProgress.objects.create(
        cell_id=grid.cell_id(0.0, 0.0, 2000.0),
        status=CrimeFetchProgress.Status.DONE,
        feature_count=0,
    )
    CrimeFetchProgress.objects.create(
        cell_id=grid.cell_id(2000.0, 0.0, 2000.0),
        status=CrimeFetchProgress.Status.PENDING,
    )
    CrimeSegment.objects.create(
        objt_id="OLD1",
        grad=4,
        data_period="2022-07/2023-06",
        geom="SRID=4326;LINESTRING(0 0, 0.001 0.001)",
    )

    calls = []

    def fake_fetch(client, bbox, count):
        calls.append(bbox)
        return [_feature("NEW1", 6, [[0, 0], [1, 1]])]

    monkeypatch.setattr(collect, "fetch_feature_info", fake_fetch)

    result = collect.run_safety_sync("2023-07/2024-06")

    assert len(calls) == 1  # 이미 done인 셀은 다시 호출하지 않는다(재개)
    assert result["fully_done"] is True
    # 전부 끝났으니 지난 기간(OLD1)은 정리되고 새 기간(NEW1)만 남아야 한다.
    assert not CrimeSegment.objects.filter(objt_id="OLD1").exists()
    assert CrimeSegment.objects.filter(objt_id="NEW1").exists()


def test_run_safety_sync_dedupes_segment_seen_in_multiple_cells(monkeypatch, settings):
    settings.CRIME_FEATURE_CAP = 100
    monkeypatch.setattr(
        grid, "base_cells", lambda: [(0.0, 0.0, 2000.0), (2000.0, 0.0, 2000.0)]
    )
    monkeypatch.setattr(
        collect,
        "fetch_feature_info",
        lambda client, bbox, count: [_feature("SHARED", 7, [[0, 0], [1, 1]])],
    )

    collect.run_safety_sync("2023-07/2024-06")

    assert CrimeSegment.objects.filter(objt_id="SHARED").count() == 1


def test_run_safety_sync_marks_cell_failed_after_retries_but_continues_other_cells(
    monkeypatch, settings
):
    settings.CRIME_FEATURE_CAP = 100
    monkeypatch.setattr(
        grid, "base_cells", lambda: [(0.0, 0.0, 2000.0), (2000.0, 0.0, 2000.0)]
    )

    def fake_fetch(client, bbox, count):
        if bbox[0] == 0.0:
            raise ExternalCallError("일시 오류")
        return [_feature("OK1", 2, [[0, 0], [1, 1]])]

    monkeypatch.setattr(collect, "fetch_feature_info", fake_fetch)

    result = collect.run_safety_sync("2023-07/2024-06")

    assert result["cells_failed"] == 1
    assert result["cells_done"] == 1
    assert result["fully_done"] is False  # failed 셀이 남아 있어 전부 끝난 게 아니다
    assert CrimeSegment.objects.filter(objt_id="OK1").exists()
