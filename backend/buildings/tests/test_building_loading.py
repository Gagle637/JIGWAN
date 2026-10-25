import zipfile
from datetime import date
from pathlib import Path

import pytest

from buildings import building_loading
from buildings.models import Building
from core.jobs import SkipJob


def _make_zip(path: Path, shp_name: str | None = None) -> Path:
    """load_buildings가 실제로 zip 목록에서 .shp를 찾으므로(다지역 지원 4단계 보강), 테스트용
    zip도 진짜 zip이어야 한다 — pyogrio는 모킹하므로 .shp 안의 내용은 비워도 된다."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(shp_name or (path.stem + ".shp"), b"")
    return path


# ---- resolve_building_zip_path: 파일시스템만, DB 불필요 ----


def test_resolve_building_zip_path_picks_latest_by_filename_date(tmp_path, monkeypatch):
    monkeypatch.setattr(building_loading, "DATA_RAW_DIR", tmp_path)
    (tmp_path / "AL_D010_30_20250101.zip").touch()
    (tmp_path / "AL_D010_30_20261009.zip").touch()
    (tmp_path / "AL_D010_30_20240601.zip").touch()

    resolved = building_loading.resolve_building_zip_path(None)
    assert resolved.name == "AL_D010_30_20261009.zip"


def test_resolve_building_zip_path_uses_explicit_path(tmp_path):
    explicit = tmp_path / "custom.zip"
    explicit.touch()
    assert building_loading.resolve_building_zip_path(str(explicit)) == explicit


def test_resolve_building_zip_path_missing_explicit_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        building_loading.resolve_building_zip_path(str(tmp_path / "nope.zip"))


def test_resolve_building_zip_path_no_candidates_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(building_loading, "DATA_RAW_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        building_loading.resolve_building_zip_path(None)


# ---- resolve_vsizip_shp_path: zip 파일명이 아니라 실제 안의 .shp를 찾아야 한다 ----


def test_resolve_vsizip_shp_path_finds_shp_even_when_zip_filename_has_extra_suffix(tmp_path):
    """다운로드하며 zip 파일명에 " (1)" 같은 접미사가 붙어도(실제로 재현됨) 안의 .shp
    이름은 원래 그대로이므로, zip 파일명으로 .shp 이름을 추정하면 안 된다."""
    zip_path = tmp_path / "AL_D010_30_20261009 (1).zip"
    _make_zip(zip_path, shp_name="AL_D010_30_20261009.shp")

    vsi_path = building_loading.resolve_vsizip_shp_path(zip_path)

    assert vsi_path == f"/vsizip/{zip_path.resolve()}/AL_D010_30_20261009.shp"


def test_resolve_vsizip_shp_path_raises_when_zip_has_no_shp(tmp_path):
    zip_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("readme.txt", b"")

    with pytest.raises(ValueError, match=r"\.shp"):
        building_loading.resolve_vsizip_shp_path(zip_path)


def test_resolve_vsizip_shp_path_raises_when_zip_has_more_than_one_shp(tmp_path):
    zip_path = tmp_path / "ambiguous.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("a.shp", b"")
        zf.writestr("b.shp", b"")

    with pytest.raises(ValueError, match=r"\.shp"):
        building_loading.resolve_vsizip_shp_path(zip_path)


# ---- assign_building_keys: 순수 함수, DB 불필요 ----


def test_assign_building_keys_single_group_uses_gis_bldg_id():
    records = [{"gis_bldg_id": "A1", "building_area_m2": 10.0, "pnu": "p", "jibun": "j"}]
    building_loading.assign_building_keys(records)
    assert records[0]["building_key"] == "A1"


def test_assign_building_keys_duplicate_group_orders_by_area_desc():
    records = [
        {"gis_bldg_id": "DUP", "building_area_m2": 10.0, "pnu": "p1", "jibun": "j1"},
        {"gis_bldg_id": "DUP", "building_area_m2": 50.0, "pnu": "p2", "jibun": "j2"},
        {"gis_bldg_id": "DUP", "building_area_m2": 30.0, "pnu": "p3", "jibun": "j3"},
    ]
    building_loading.assign_building_keys(records)
    keys = {r["pnu"]: r["building_key"] for r in records}
    assert keys["p2"] == "DUP_1"  # 면적 50 (가장 큼)
    assert keys["p3"] == "DUP_2"  # 면적 30
    assert keys["p1"] == "DUP_3"  # 면적 10


def test_assign_building_keys_is_deterministic_on_area_tie():
    records = [
        {"gis_bldg_id": "DUP", "building_area_m2": 10.0, "pnu": "pB", "jibun": "j"},
        {"gis_bldg_id": "DUP", "building_area_m2": 10.0, "pnu": "pA", "jibun": "j"},
    ]
    building_loading.assign_building_keys(records)
    keys = {r["pnu"]: r["building_key"] for r in records}
    assert keys["pA"] == "DUP_1"  # 면적 동률이면 pnu 사전순
    assert keys["pB"] == "DUP_2"


# ---- 좌표 변환: EPSG:5186 투영 원점(알려진 점)이 (127.0, 38.0) 근처로 변환되는지 ----


def test_epsg_5186_projection_origin_matches_known_point():
    pyproj = pytest.importorskip("pyproj")
    transformer = pyproj.Transformer.from_crs(5186, 4326, always_xy=True)
    lon, lat = transformer.transform(200000.0, 600000.0)
    assert lon == pytest.approx(127.0, abs=1e-3)
    assert lat == pytest.approx(38.0, abs=1e-3)


# ---- load_buildings: source_date 동일 시 SkipJob (django_db, pyogrio는 모킹) ----


def _tiny_gdf(
    source_date_value,
    gis_bldg_id="GISID001",
    pnu="3011010300101530003",
    bjd_code="3011010300",
):
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Polygon

    square = Polygon([(200000, 600000), (200010, 600000), (200010, 600010), (200000, 600010)])
    data = {
        "A1": [gis_bldg_id],
        "A2": [pnu],
        "A3": [bjd_code],
        "A4": ["대전광역시 동구 효동"],
        "A5": ["153-3"],
        "A8": ["01000"],
        "A9": ["단독주택"],
        "A11": ["벽돌구조"],
        "A12": [83.37],
        "A13": ["1977-08-17"],
        "A14": [135.21],
        "A15": [187.0],
        "A16": [8.0],
        "A17": [44.58],
        "A18": [72.3],
        "A20": ["N"],
        "A24": [""],
        "A25": [""],
        "A26": [2],
        "A27": [0],
        "A22": [source_date_value],
    }
    return gpd.GeoDataFrame(data, geometry=[square])


@pytest.mark.django_db
def test_load_buildings_skips_when_source_date_unchanged(monkeypatch, tmp_path):
    existing_date = date(2026, 10, 6)
    Building.objects.create(
        building_key="EXISTING",
        gis_bldg_id="EXISTING",
        pnu="0000000000000000000",
        bjd_code="3099999999",
        source_date=existing_date,
        geom="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
    )

    monkeypatch.setattr("pyogrio.read_dataframe", lambda *a, **k: _tiny_gdf(existing_date))

    zip_path = _make_zip(tmp_path / "AL_D010_30_20261006.zip")

    with pytest.raises(SkipJob):
        building_loading.load_buildings(zip_path)


@pytest.mark.django_db
def test_load_buildings_upsert_preserves_id_and_soft_deletes_missing(monkeypatch, tmp_path):
    pytest.importorskip("geopandas")

    monkeypatch.setattr(
        "pyogrio.read_dataframe", lambda *a, **k: _tiny_gdf(date(2026, 1, 1))
    )
    zip1 = _make_zip(tmp_path / "AL_D010_30_20260101.zip")
    building_loading.load_buildings(zip1)

    building = Building.objects.get(building_key="GISID001")
    first_id = building.id
    assert building.is_active is True

    monkeypatch.setattr(
        "pyogrio.read_dataframe",
        lambda *a, **k: _tiny_gdf(
            date(2026, 4, 1), gis_bldg_id="GISID002", pnu="9999999999999999999"
        ),
    )
    zip2 = _make_zip(tmp_path / "AL_D010_30_20260401.zip")
    building_loading.load_buildings(zip2)

    building.refresh_from_db()
    assert building.id == first_id
    assert building.is_active is False  # 새 파일에 없음 -> 비활성화, 삭제 아님

    new_building = Building.objects.get(building_key="GISID002")
    assert new_building.is_active is True

    # 3차 적재: 비활성화됐던 GISID001이 다시 나타나면 is_active=true로 복구되고, id도 그대로여야 한다.
    monkeypatch.setattr(
        "pyogrio.read_dataframe", lambda *a, **k: _tiny_gdf(date(2026, 7, 1))
    )
    zip3 = _make_zip(tmp_path / "AL_D010_30_20260701.zip")
    building_loading.load_buildings(zip3)

    building.refresh_from_db()
    assert building.id == first_id
    assert building.is_active is True


# ---- 다지역 지원 4단계: 지역 범위 soft-delete + 파일/지정 지역 불일치 안전장치 ----


@pytest.mark.django_db
def test_load_buildings_for_another_sido_does_not_deactivate_existing_region(monkeypatch, tmp_path):
    """세종(36) 건물을 적재해도 기존 대전(30) 건물이 그대로 is_active=True로 남아야 한다
    (완료 기준) — sync_geotable의 soft-delete가 지역 범위로 좁혀져 있는지 확인한다."""
    pytest.importorskip("geopandas")

    daejeon_building = Building.objects.create(
        building_key="DAEJEON1",
        gis_bldg_id="DAEJEON1",
        pnu="3011010300101530003",
        bjd_code="3011010300",
        source_date=date(2026, 1, 1),
        geom="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
    )

    monkeypatch.setattr(
        "pyogrio.read_dataframe",
        lambda *a, **k: _tiny_gdf(
            date(2026, 1, 1),
            gis_bldg_id="SEJONG1",
            pnu="3611010100101530003",
            bjd_code="3611010100",
        ),
    )
    zip_path = _make_zip(tmp_path / "AL_D010_36_20260101.zip")

    building_loading.load_buildings(zip_path, sido_code="36")

    daejeon_building.refresh_from_db()
    assert daejeon_building.is_active is True
    sejong_building = Building.objects.get(building_key="SEJONG1")
    assert sejong_building.is_active is True


@pytest.mark.django_db
def test_load_buildings_rejects_file_whose_region_does_not_match_sido_code(monkeypatch, tmp_path):
    """세종(36) 파일을 --sido 30으로 잘못 넣으면, 트랜잭션을 시작하지 않고 바로 실패해야
    한다 — 대전 건물 전체가 비활성화되는 사고를 막기 위한 안전장치."""
    pytest.importorskip("geopandas")

    daejeon_building = Building.objects.create(
        building_key="DAEJEON1",
        gis_bldg_id="DAEJEON1",
        pnu="3011010300101530003",
        bjd_code="3011010300",
        source_date=date(2026, 1, 1),
        geom="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
    )

    monkeypatch.setattr(
        "pyogrio.read_dataframe",
        lambda *a, **k: _tiny_gdf(
            date(2026, 4, 1),
            gis_bldg_id="SEJONG1",
            pnu="3611010100101530003",
            bjd_code="3611010100",
        ),
    )
    zip_path = _make_zip(tmp_path / "AL_D010_30_20260401.zip")

    with pytest.raises(ValueError, match="지정한 지역"):
        building_loading.load_buildings(zip_path, sido_code="30")

    daejeon_building.refresh_from_db()
    assert daejeon_building.is_active is True  # 실패했으니 기존 건물은 전혀 안 바뀌어야 한다
    assert not Building.objects.filter(building_key="SEJONG1").exists()


@pytest.mark.django_db
def test_load_buildings_works_when_zip_filename_has_extra_suffix(monkeypatch, tmp_path):
    """zip 파일명이 "AL_D010_30_20261009 (1).zip"처럼 바뀌어도(다운로드 시 실제로
    재현됨) 적재가 되어야 한다 — resolve_vsizip_shp_path가 zip 안의 실제 .shp 이름을
    쓰는지 end-to-end로 확인한다."""
    pytest.importorskip("geopandas")

    zip_path = tmp_path / "AL_D010_30_20261009 (1).zip"
    _make_zip(zip_path, shp_name="AL_D010_30_20261009.shp")

    captured_vsi_paths = []

    def fake_read_dataframe(vsi_path, **kwargs):
        captured_vsi_paths.append(vsi_path)
        return _tiny_gdf(date(2026, 1, 1))

    monkeypatch.setattr("pyogrio.read_dataframe", fake_read_dataframe)

    building_loading.load_buildings(zip_path)

    assert captured_vsi_paths == [f"/vsizip/{zip_path.resolve()}/AL_D010_30_20261009.shp"]
    assert Building.objects.filter(building_key="GISID001").exists()
