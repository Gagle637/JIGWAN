import pytest

from buildings.models import Region
from core.exceptions import ExternalCallError
from crime import collect, grid
from crime.models import CrimeFetchProgress, CrimeSegment

pytestmark = pytest.mark.django_db


def _feature(objt_id, grad, coords):
    """coords는 사각형의 두 대각 모서리 [[x1,y1],[x2,y2]] — 실측 확인된 응답 형태인
    MultiPolygon으로 감싼다(spec 8-3)."""
    (x1, y1), (x2, y2) = coords
    return {
        "properties": {"OBJT_ID": objt_id, "TY_CD": "10201000", "GRAD": grad},
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [[[[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]]],
        },
    }


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """1-2초 요청 간격·1·5·25분 재시도 대기를 테스트에서 실제로 기다리지 않게 한다."""
    monkeypatch.setattr(collect.time, "sleep", lambda seconds: None)


def test_run_safety_sync_requires_feature_cap_configured(settings):
    settings.CRIME_FEATURE_CAP = None

    with pytest.raises(collect.FeatureCapNotConfigured):
        collect.run_safety_sync("2023-07/2024-06", sido_code="30")


def test_run_safety_sync_saves_features_for_a_single_small_grid(monkeypatch, settings):
    settings.CRIME_FEATURE_CAP = 100
    monkeypatch.setattr(grid, "base_cells", lambda sido_code="30": [(0.0, 0.0, 2000.0)])
    monkeypatch.setattr(
        collect,
        "fetch_feature_info",
        lambda client, bbox, count: [
            _feature("OBJ1", 5, [[0, 0], [10, 10]]),
            _feature("OBJ2", 9, [[20, 20], [30, 30]]),
        ],
    )

    result = collect.run_safety_sync("2023-07/2024-06", sido_code="30")

    assert result["cells_done"] == 1
    assert result["cells_failed"] == 0
    assert result["fully_done"] is True
    assert CrimeSegment.objects.count() == 2
    seg = CrimeSegment.objects.get(objt_id="OBJ1")
    assert seg.grad == 5
    assert seg.data_period == "2023-07/2024-06"


def test_run_safety_sync_splits_cell_at_feature_cap_and_processes_children(monkeypatch, settings):
    settings.CRIME_FEATURE_CAP = 2
    monkeypatch.setattr(grid, "base_cells", lambda sido_code="30": [(0.0, 0.0, 2000.0)])

    calls = []

    def fake_fetch(client, bbox, count):
        calls.append(bbox)
        size_m = bbox[2] - bbox[0]
        if size_m > grid.MIN_CELL_SIZE_M and len(calls) == 1:
            # 큰 셀(첫 호출)은 상한과 같은 개수를 돌려줘 분할을 유도한다.
            return [_feature(f"BIG{i}", 5, [[0, 0], [1, 1]]) for i in range(2)]
        return [_feature(f"CHILD{len(calls)}", 3, [[0, 0], [1, 1]])]

    monkeypatch.setattr(collect, "fetch_feature_info", fake_fetch)

    result = collect.run_safety_sync("2023-07/2024-06", sido_code="30")

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
        grid, "base_cells", lambda sido_code="30": [(0.0, 0.0, 2000.0), (2000.0, 0.0, 2000.0)]
    )

    # 이지역(대전, 30)의 시도 경계 — 완료 후 지난 기간 정리 범위를 여기로 좁힌다.
    Region.objects.create(
        region_code="30", level="sido", name="테스트",
        geom="SRID=4326;MULTIPOLYGON(((-1 -1, 1 -1, 1 1, -1 1, -1 -1)))",
    )

    # 이전 실행에서 하나는 이미 done, 하나는 pending으로 중단된 상태를 흉내낸다.
    CrimeFetchProgress.objects.create(
        cell_id=grid.cell_id(0.0, 0.0, 2000.0),
        region_code="30",
        status=CrimeFetchProgress.Status.DONE,
        feature_count=0,
    )
    CrimeFetchProgress.objects.create(
        cell_id=grid.cell_id(2000.0, 0.0, 2000.0),
        region_code="30",
        status=CrimeFetchProgress.Status.PENDING,
    )
    CrimeSegment.objects.create(
        objt_id="OLD1",
        grad=4,
        data_period="2022-07/2023-06",
        geom="SRID=4326;MULTIPOLYGON(((0 0, 0.001 0, 0.001 0.001, 0 0.001, 0 0)))",
    )

    calls = []

    def fake_fetch(client, bbox, count):
        calls.append(bbox)
        return [_feature("NEW1", 6, [[0, 0], [1, 1]])]

    monkeypatch.setattr(collect, "fetch_feature_info", fake_fetch)

    result = collect.run_safety_sync("2023-07/2024-06", sido_code="30")

    assert len(calls) == 1  # 이미 done인 셀은 다시 호출하지 않는다(재개)
    assert result["fully_done"] is True
    # 전부 끝났으니 지난 기간(OLD1)은 정리되고 새 기간(NEW1)만 남아야 한다.
    assert not CrimeSegment.objects.filter(objt_id="OLD1").exists()
    assert CrimeSegment.objects.filter(objt_id="NEW1").exists()


def test_run_safety_sync_dedupes_segment_seen_in_multiple_cells(monkeypatch, settings):
    settings.CRIME_FEATURE_CAP = 100
    monkeypatch.setattr(
        grid, "base_cells", lambda sido_code="30": [(0.0, 0.0, 2000.0), (2000.0, 0.0, 2000.0)]
    )
    monkeypatch.setattr(
        collect,
        "fetch_feature_info",
        lambda client, bbox, count: [_feature("SHARED", 7, [[0, 0], [1, 1]])],
    )

    collect.run_safety_sync("2023-07/2024-06", sido_code="30")

    assert CrimeSegment.objects.filter(objt_id="SHARED").count() == 1


def test_run_safety_sync_marks_cell_failed_after_retries_but_continues_other_cells(
    monkeypatch, settings
):
    settings.CRIME_FEATURE_CAP = 100
    monkeypatch.setattr(
        grid, "base_cells", lambda sido_code="30": [(0.0, 0.0, 2000.0), (2000.0, 0.0, 2000.0)]
    )

    def fake_fetch(client, bbox, count):
        if bbox[0] == 0.0:
            raise ExternalCallError("일시 오류")
        return [_feature("OK1", 2, [[0, 0], [1, 1]])]

    monkeypatch.setattr(collect, "fetch_feature_info", fake_fetch)

    result = collect.run_safety_sync("2023-07/2024-06", sido_code="30")

    assert result["cells_failed"] == 1
    assert result["cells_done"] == 1
    assert result["fully_done"] is False  # failed 셀이 남아 있어 전부 끝난 게 아니다
    assert CrimeSegment.objects.filter(objt_id="OK1").exists()


def test_run_safety_sync_does_not_delete_border_or_neighboring_regions_segments(
    monkeypatch, settings
):
    """경계에 걸친 구간(이 지역 셀 쿼리가 실제로 다시 받아옴)과 이웃 지역 안쪽 구간(이 지역
    경계와 안 겹침) 둘 다, 이 지역(91)만 새 기간으로 동기화해도 지워지면 안 된다(다지역
    지원 6단계) — bbox(격자 여유로 이웃 땅까지 포함)가 아니라 실제 시도 경계 폴리곤으로
    정리 범위를 좁혔기 때문이다."""
    settings.CRIME_FEATURE_CAP = 100

    Region.objects.create(
        region_code="91", level="sido", name="A",
        geom="SRID=4326;MULTIPOLYGON(((0 0, 100 0, 100 100, 0 100, 0 0)))",
    )
    Region.objects.create(
        region_code="92", level="sido", name="B",
        geom="SRID=4326;MULTIPOLYGON(((100 0, 200 0, 200 100, 100 100, 100 0)))",
    )

    monkeypatch.setattr(grid, "base_cells", lambda sido_code="91": [(0.0, 0.0, 2000.0)])
    monkeypatch.setattr(
        collect,
        "fetch_feature_info",
        # A의 셀 쿼리가 경계 너머까지 걸친 BORDER1을 실제로 다시 받아온다(현실적인 상황).
        lambda client, bbox, count: [_feature("BORDER1", 5, [[0, 0], [1, 1]])],
    )

    CrimeSegment.objects.create(
        objt_id="BORDER1", grad=4, data_period="2022-07/2023-06",
        geom="SRID=4326;MULTIPOLYGON(((95 40, 105 40, 105 60, 95 60, 95 40)))",
    )
    CrimeSegment.objects.create(
        objt_id="INSIDE_B", grad=4, data_period="2022-07/2023-06",
        geom="SRID=4326;MULTIPOLYGON(((150 40, 160 40, 160 60, 150 60, 150 40)))",
    )

    result = collect.run_safety_sync("2023-07/2024-06", sido_code="91")

    assert result["fully_done"] is True
    border = CrimeSegment.objects.get(objt_id="BORDER1")
    assert border.data_period == "2023-07/2024-06"  # 이번 실행에서 다시 받아 갱신됨
    inside_b = CrimeSegment.objects.get(objt_id="INSIDE_B")
    assert inside_b.data_period == "2022-07/2023-06"  # 이 지역과 안 겹쳐 안 건드려짐
