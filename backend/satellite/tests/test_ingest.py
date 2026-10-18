import numpy as np
import pytest
import rasterio
from django.conf import settings

from satellite import ingest as ingest_module
from satellite.cog import grid_transform
from satellite.models import SatelliteScene

pytestmark = pytest.mark.django_db

BAND_FILES = ["B02_10m", "B03_10m", "B04_10m", "B08_10m", "B11_20m"]


class FakeItem:
    def __init__(self, item_id: str, dt_iso: str, cloud: float = 10.0):
        self.id = item_id
        self.properties = {"datetime": dt_iso, "eo:cloud_cover": cloud}


def _write_band(path, array):
    grid = settings.DAEJEON_GRID
    profile = {
        "driver": "GTiff",
        "dtype": array.dtype,
        "count": 1,
        "width": grid["width"],
        "height": grid["height"],
        "crs": grid["crs"],
        "transform": grid_transform(),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array, 1)


def _make_tile_files(tmp_path, name: str, dn_value: int, scl_value: int) -> dict:
    """DAEJEON_GRID와 똑같은 크기·transform의 가짜 밴드 파일(전체가 같은 값)을 만든다 —
    실제 밴드 파일 포맷(JP2)이 아니라 rasterio가 읽을 수 있는 GTiff지만, ingest.py의
    _read_band는 포맷을 가리지 않는다."""
    grid = settings.DAEJEON_GRID
    shape = (grid["height"], grid["width"])
    dn_array = np.full(shape, dn_value, dtype=np.uint16)
    scl_array = np.full(shape, scl_value, dtype=np.uint8)

    tile_dir = tmp_path / name
    tile_dir.mkdir()
    paths = {}
    for band in BAND_FILES:
        path = tile_dir / f"{band}.tif"
        _write_band(path, dn_array)
        paths[band] = path
    scl_path = tile_dir / "SCL_20m.tif"
    _write_band(scl_path, scl_array)
    paths["SCL_20m"] = scl_path
    return paths


def _patch_download_and_mtd(monkeypatch, files_by_key: dict, mtd_by_key: dict, tmp_path):
    def fake_download(item, dest_dir):
        key = item.id  # 테스트에서는 item.id를 바로 key로 쓴다
        paths = dict(files_by_key[key])
        paths["MTD"] = tmp_path / f"{key}_MTD.xml"
        return paths

    def fake_parse_mtd(path):
        for key, mtd in mtd_by_key.items():
            if str(path).endswith(f"{key}_MTD.xml"):
                return mtd
        raise AssertionError(f"알 수 없는 MTD 경로: {path}")

    monkeypatch.setattr(ingest_module, "download_scene_files", fake_download)
    monkeypatch.setattr(ingest_module, "parse_mtd", fake_parse_mtd)


def test_two_tiles_same_date_share_cog_path_and_use_own_offsets(tmp_path, monkeypatch):
    # tile_code()/processing_baseline()은 item.id.split("_") 규칙을 쓰므로 실제 명명 규칙을 따른다.
    tile_a = FakeItem(
        "S2B_MSIL2A_20260809T085559_N0512_R007_T52SCF_20260809T111845", "2026-08-09T08:55:59Z"
    )
    tile_b = FakeItem(
        "S2B_MSIL2A_20260809T090102_N0512_R007_T52SDF_20260809T112000", "2026-08-09T09:01:02Z"
    )

    files_by_key = {
        tile_a.id: _make_tile_files(tmp_path, "tile_a", dn_value=2000, scl_value=4),
        tile_b.id: _make_tile_files(tmp_path, "tile_b", dn_value=3000, scl_value=4),
    }
    mtd_by_key = {
        tile_a.id: {
            "band_offsets": {b: -1000 for b in ["B02", "B03", "B04", "B08", "B11"]},
            "boa_quantification_value": 10000,
        },
        tile_b.id: {
            "band_offsets": {b: -2000 for b in ["B02", "B03", "B04", "B08", "B11"]},
            "boa_quantification_value": 10000,
        },
    }
    _patch_download_and_mtd(monkeypatch, files_by_key, mtd_by_key, tmp_path)

    scenes = ingest_module.ingest_date_group([tile_a, tile_b])

    assert len(scenes) == 2
    assert scenes[0].cog_path == scenes[1].cog_path
    assert scenes[0].scl_cog_path == scenes[1].scl_cog_path
    assert scenes[0].mgrs_tile == "T52SCF"
    assert scenes[1].mgrs_tile == "T52SDF"
    # 타일별로 자기 MTD 오프셋을 그대로 기록해야 한다(결정 사항 11)
    assert scenes[0].band_offsets["B02"] == -1000
    assert scenes[1].band_offsets["B02"] == -2000
    # SCL=4(식생, 사용 가능)가 전체를 덮으므로 valid_ratio=1.0 -> ready
    assert scenes[0].status == SatelliteScene.Status.READY
    assert scenes[0].valid_ratio == 1.0


def test_upgrades_existing_listed_row_instead_of_duplicating(tmp_path, monkeypatch):
    """백필 dry run이 미리 status=listed로 적어둔 행을 다시 받으면, 새 행을 만들지 않고
    그 행을 ready/excluded로 올려 써야 한다(create가 아니라 update_or_create, spec 4장)."""
    item = FakeItem(
        "S2B_MSIL2A_20260811T085559_N0512_R007_T52SCF_20260811T111845", "2026-08-11T08:55:59Z"
    )
    SatelliteScene.objects.create(
        scene_id=item.id,
        sensed_at="2026-08-11T08:55:59+00:00",
        mgrs_tile="T52SCF",
        cloud_pct=10.0,
        processing_baseline="N0512",
        status=SatelliteScene.Status.LISTED,
    )
    files_by_key = {item.id: _make_tile_files(tmp_path, "upgrade", dn_value=2000, scl_value=4)}
    mtd_by_key = {
        item.id: {
            "band_offsets": {b: -1000 for b in ["B02", "B03", "B04", "B08", "B11"]},
            "boa_quantification_value": 10000,
        }
    }
    _patch_download_and_mtd(monkeypatch, files_by_key, mtd_by_key, tmp_path)

    scenes = ingest_module.ingest_date_group([item])

    assert SatelliteScene.objects.filter(scene_id=item.id).count() == 1
    assert scenes[0].status == SatelliteScene.Status.READY
    assert scenes[0].band_offsets["B02"] == -1000


def test_low_valid_ratio_marks_excluded(tmp_path, monkeypatch):
    item = FakeItem(
        "S2B_MSIL2A_20260810T085559_N0512_R007_T52SCF_20260810T111845", "2026-08-10T08:55:59Z"
    )
    files_by_key = {item.id: _make_tile_files(tmp_path, "cloudy", dn_value=2000, scl_value=9)}
    mtd_by_key = {
        item.id: {
            "band_offsets": {b: -1000 for b in ["B02", "B03", "B04", "B08", "B11"]},
            "boa_quantification_value": 10000,
        }
    }
    _patch_download_and_mtd(monkeypatch, files_by_key, mtd_by_key, tmp_path)

    scenes = ingest_module.ingest_date_group([item])

    assert scenes[0].valid_ratio == 0.0
    assert scenes[0].status == SatelliteScene.Status.EXCLUDED
