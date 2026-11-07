import numpy as np
import pytest
import rasterio
from django.contrib.gis.geos import MultiPolygon
from django.contrib.gis.geos import Polygon as GEOSPolygon
from django.utils import timezone

from buildings.models import Region
from satellite.cog import grid_transform
from satellite.composite import (
    GREEN_NDVI_THRESHOLD,
    _check_scene_files_or_flag_for_recollection,
    _dedupe_scenes_by_cog_path,
    build_season_composite,
    compute_ndbi,
    compute_ndvi,
    mask_scene_reflectance,
    median_with_min_observations,
)
from satellite.index_scaling import MASK_NODATA
from satellite.ingest import REFLECTANCE_BANDS
from satellite.models import SatelliteScene


def test_compute_ndvi_known_values():
    b08 = np.array([0.5, 0.2])
    b04 = np.array([0.1, 0.2])
    ndvi = compute_ndvi(b08, b04)
    # (0.5-0.1)/(0.5+0.1)=0.6667, (0.2-0.2)/(0.2+0.2)=0
    assert np.allclose(ndvi, [0.6666667, 0.0], atol=1e-5)


def test_compute_ndbi_known_values():
    b11 = np.array([0.4])
    b08 = np.array([0.1])
    ndbi = compute_ndbi(b11, b08)
    assert np.allclose(ndbi, [0.6])  # (0.4-0.1)/(0.4+0.1)


def test_mask_scene_reflectance_sets_unusable_scl_to_nan():
    bands = {
        "B04": np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32),
        "B08": np.array([[0.5, 0.6], [0.7, 0.8]], dtype=np.float32),
    }
    scl = np.array([[4, 9], [8, 2]])  # 4·2=사용가능, 9·8=구름(제외)
    masked = mask_scene_reflectance(bands, scl)

    # float32라 0.1/0.4의 float64 리터럴과 정확히는 안 맞는다(감사에서 발견) -> approx로 비교.
    assert masked["B04"][0, 0] == pytest.approx(0.1)  # SCL=4, 유지
    assert np.isnan(masked["B04"][0, 1])  # SCL=9, 제외
    assert np.isnan(masked["B04"][1, 0])  # SCL=8, 제외
    assert masked["B04"][1, 1] == pytest.approx(0.4)  # SCL=2, 유지


def test_median_with_min_observations_requires_three():
    # 화소 0: 2개 관측 -> nodata. 화소 1: 3개 관측 -> 중앙값.
    stack = np.array(
        [
            [1.0, 1.0],
            [2.0, 2.0],
            [np.nan, 3.0],
        ]
    )
    result = median_with_min_observations(stack, min_obs=3)
    assert np.isnan(result[0])
    assert result[1] == 2.0


def test_median_with_min_observations_all_nan_block():
    stack = np.full((5, 2, 2), np.nan)
    result = median_with_min_observations(stack)
    assert np.all(np.isnan(result))


def test_green_mask_threshold_constant():
    assert GREEN_NDVI_THRESHOLD == 0.4


# ---- build_season_composite: 맞닿은 두 지역의 겹치는 버퍼 띠에서 이중 계산 방지(5단계) ----


def _sido_region(region_code: str, minx, miny, maxx, maxy) -> Region:
    poly_32652 = GEOSPolygon.from_bbox((minx, miny, maxx, maxy))
    poly_32652.srid = 32652
    geom_4326 = MultiPolygon(poly_32652.transform(4326, clone=True))
    return Region.objects.create(
        region_code=region_code, level="sido", name=f"테스트{region_code}", geom=geom_4326
    )


def _write_reflectance_and_scl(tmp_path, name, grid, value=3000, scl_value=4):
    transform = grid_transform(grid)
    shape = (grid["height"], grid["width"])
    refl_path = tmp_path / f"{name}_refl.tif"
    scl_path = tmp_path / f"{name}_scl.tif"

    with rasterio.open(
        refl_path, "w", driver="GTiff", dtype="uint16", count=len(REFLECTANCE_BANDS),
        width=grid["width"], height=grid["height"], crs=grid["crs"], transform=transform,
    ) as dst:
        for i in range(len(REFLECTANCE_BANDS)):
            dst.write(np.full(shape, value, dtype=np.uint16), i + 1)

    with rasterio.open(
        scl_path, "w", driver="GTiff", dtype="uint8", count=1,
        width=grid["width"], height=grid["height"], crs=grid["crs"], transform=transform,
    ) as dst:
        dst.write(np.full(shape, scl_value, dtype=np.uint8), 1)

    return str(refl_path), str(scl_path)


def _make_scenes(tmp_path, name_prefix, grid, count=3):
    """median_with_min_observations가 최소 3개 관측을 요구하므로(MIN_OBSERVATIONS) 똑같은
    장면을 3개 만든다 — 값 자체는 중요하지 않고, 격자 전체(버퍼 포함)가 유효해야 한다."""
    scenes = []
    for i in range(count):
        refl_path, scl_path = _write_reflectance_and_scl(tmp_path, f"{name_prefix}_{i}", grid)
        scenes.append(
            SatelliteScene(scene_id=f"{name_prefix}_{i}", cog_path=refl_path, scl_cog_path=scl_path)
        )
    return scenes


def _pixel_value(path, grid, x, y, resolution_m):
    row = int((grid["maxy"] - y) / resolution_m)
    col = int((x - grid["minx"]) / resolution_m)
    with rasterio.open(path) as ds:
        return ds.read(1)[row, col]


@pytest.mark.django_db
def test_build_season_composite_clips_to_sido_boundary_to_avoid_double_counting_at_shared_border(
    tmp_path,
):
    """격자에는 버퍼(여유)가 있어 맞닿은 두 지역의 격자가 겹친다(대전·세종처럼 실제로 맞닿은
    경우) — 각 지역의 합성 결과는 자기 시도 경계 밖을 nodata로 잘라야, 반경 통계가 같은 기간의
    여러 COG 픽셀을 합산할 때 겹치는 띠에서 두 번 세지 않는다."""
    resolution_m = 10
    buffer_m = 40
    # 시도 A: x[341700,341900], 시도 B: x[341900,342100] — y는 공통, 서로 맞닿아 있다.
    _sido_region("91", 341700, 4004820, 341900, 4004920)
    _sido_region("92", 341900, 4004820, 342100, 4004920)

    def _grid(minx, miny, maxx, maxy):
        g = {
            "crs": "EPSG:32652", "resolution_m": resolution_m,
            "minx": minx - buffer_m, "miny": miny - buffer_m,
            "maxx": maxx + buffer_m, "maxy": maxy + buffer_m,
        }
        g["width"] = round((g["maxx"] - g["minx"]) / resolution_m)
        g["height"] = round((g["maxy"] - g["miny"]) / resolution_m)
        return g

    grid_a = _grid(341700, 4004820, 341900, 4004920)
    grid_b = _grid(341900, 4004820, 342100, 4004920)

    result_a = build_season_composite(
        _make_scenes(tmp_path, "a", grid_a), 2026, "summer", grid_a, sido_code="91"
    )
    result_b = build_season_composite(
        _make_scenes(tmp_path, "b", grid_b), 2026, "summer", grid_b, sido_code="92"
    )

    # 겹치는 버퍼 띠 안, B 쪽 진짜 영역(x=341920) — A의 결과는 자기 경계 밖이라 nodata여야
    # 하고, B의 결과만 유효해야 한다(둘 다 유효하면 반경 통계가 이중 계산됨).
    a_at_b_side = _pixel_value(result_a["paths"]["green_mask"], grid_a, 341920, 4004870, resolution_m)
    b_at_b_side = _pixel_value(result_b["paths"]["green_mask"], grid_b, 341920, 4004870, resolution_m)
    assert a_at_b_side == MASK_NODATA
    assert b_at_b_side != MASK_NODATA

    # 대칭: A 쪽 진짜 영역(x=341880) — B의 결과는 nodata, A의 결과만 유효해야 한다.
    a_at_a_side = _pixel_value(result_a["paths"]["green_mask"], grid_a, 341880, 4004870, resolution_m)
    b_at_a_side = _pixel_value(result_b["paths"]["green_mask"], grid_b, 341880, 4004870, resolution_m)
    assert a_at_a_side != MASK_NODATA
    assert b_at_a_side == MASK_NODATA


# ---- 버그1: 2타일 병합이 공유하는 cog_path를 관측 수 집계에서 중복으로 세면 안 된다 ----


def test_dedupe_scenes_by_cog_path_keeps_one_representative_per_file():
    scenes = [
        SatelliteScene(scene_id="A", cog_path="/x.tif", scl_cog_path="/x_scl.tif"),
        SatelliteScene(scene_id="B", cog_path="/x.tif", scl_cog_path="/x_scl.tif"),  # A와 공유
        SatelliteScene(scene_id="C", cog_path="/y.tif", scl_cog_path="/y_scl.tif"),
    ]

    deduped = _dedupe_scenes_by_cog_path(scenes)

    assert [s.scene_id for s in deduped] == ["A", "C"]


@pytest.mark.django_db
def test_build_season_composite_dedupes_shared_cog_path_so_observations_are_not_double_counted(
    tmp_path,
):
    """같은 cog_path를 공유하는 두 장면(2타일 병합, scene_id만 다름)을 별도 파일의 세 번째
    장면과 합쳐도 실제 고유 관측 수는 2개뿐이어야 한다 — MIN_OBSERVATIONS=3 미달로 전부
    nodata가 나와야 정상이다. 수정 전처럼 공유 파일을 열 때마다 새로 세면 관측 수가 3으로
    둔갑해(사실은 같은 파일을 두 번 읽은 것) 미달 기준을 통과해버린다."""
    resolution_m = 10
    minx, miny, maxx, maxy = 341700, 4004820, 341900, 4004920
    _sido_region("95", minx, miny, maxx, maxy)
    grid = {
        "crs": "EPSG:32652", "resolution_m": resolution_m,
        "minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy,
        "width": round((maxx - minx) / resolution_m),
        "height": round((maxy - miny) / resolution_m),
    }

    shared_refl, shared_scl = _write_reflectance_and_scl(tmp_path, "shared", grid)
    other_refl, other_scl = _write_reflectance_and_scl(tmp_path, "other", grid)

    scenes = [
        SatelliteScene(scene_id="TILE_A", cog_path=shared_refl, scl_cog_path=shared_scl),
        SatelliteScene(scene_id="TILE_B", cog_path=shared_refl, scl_cog_path=shared_scl),
        SatelliteScene(scene_id="OTHER", cog_path=other_refl, scl_cog_path=other_scl),
    ]

    result = build_season_composite(scenes, 2026, "summer", grid, sido_code="95")

    assert result["valid_ratio"]["green_mask"] == 0.0
    # scene_ids 기록(보존 정책 추적용)은 중복 제거 전 원본 전부를 그대로 유지한다.
    assert result["scene_ids"] == ["TILE_A", "TILE_B", "OTHER"]


# ---- 버그3: 파일이 지워진 ready 장면으로 합성을 시도하면 조용히 진행하지 않는다 ----


@pytest.mark.django_db
def test_check_scene_files_flags_missing_scene_as_listed_and_raises_with_recovery_command(
    tmp_path,
):
    present_refl = tmp_path / "present_REFL.tif"
    present_scl = tmp_path / "present_SCL.tif"
    present_refl.write_bytes(b"x")
    present_scl.write_bytes(b"x")

    ok_scene = SatelliteScene.objects.create(
        scene_id="OK1", region_code="30", sensed_at=timezone.now(), mgrs_tile="T52SCF",
        cloud_pct=5.0, processing_baseline="N0512", status=SatelliteScene.Status.READY,
        cog_path=str(present_refl), scl_cog_path=str(present_scl),
    )
    missing_scene = SatelliteScene.objects.create(
        scene_id="MISSING1", region_code="30", sensed_at=timezone.now(), mgrs_tile="T52SCF",
        cloud_pct=5.0, processing_baseline="N0512", status=SatelliteScene.Status.READY,
        cog_path=str(tmp_path / "gone_REFL.tif"), scl_cog_path=str(tmp_path / "gone_SCL.tif"),
    )

    with pytest.raises(RuntimeError) as exc_info:
        _check_scene_files_or_flag_for_recollection(
            [ok_scene, missing_scene], 2026, "summer", "30"
        )

    message = str(exc_info.value)
    assert "MISSING1" in message
    assert "collect_scenes --season 2026-summer --sido 30" in message
    assert "run_season_chain --season 2026-summer --sido 30" in message

    missing_scene.refresh_from_db()
    assert missing_scene.status == SatelliteScene.Status.LISTED
    assert missing_scene.cog_path is None
    assert missing_scene.scl_cog_path is None

    ok_scene.refresh_from_db()
    assert ok_scene.status == SatelliteScene.Status.READY
    assert ok_scene.cog_path == str(present_refl)


@pytest.mark.django_db
def test_check_scene_files_does_nothing_when_all_files_present(tmp_path):
    present_refl = tmp_path / "present_REFL.tif"
    present_scl = tmp_path / "present_SCL.tif"
    present_refl.write_bytes(b"x")
    present_scl.write_bytes(b"x")
    scene = SatelliteScene.objects.create(
        scene_id="OK1", region_code="30", sensed_at=timezone.now(), mgrs_tile="T52SCF",
        cloud_pct=5.0, processing_baseline="N0512", status=SatelliteScene.Status.READY,
        cog_path=str(present_refl), scl_cog_path=str(present_scl),
    )

    _check_scene_files_or_flag_for_recollection([scene], 2026, "summer", "30")  # raise 안 함

    scene.refresh_from_db()
    assert scene.status == SatelliteScene.Status.READY
