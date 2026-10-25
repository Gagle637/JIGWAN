import zipfile

import pytest

from buildings.models import Building, Region
from buildings.region_loading import (
    count_bjd_code_mismatches,
    derive_parent_code,
    load_regions,
    load_sido_from_sigungu_union,
    pad_code,
    resolve_vsi_path,
)
from core.models import ServiceArea


def test_pad_code_pads_short_codes():
    assert pad_code("12345678", 10) == "1234567800"


def test_pad_code_leaves_long_enough_codes_untouched():
    assert pad_code("1234567890", 10) == "1234567890"


def test_pad_code_noop_without_pad_to():
    assert pad_code("12345678", None) == "12345678"


def test_derive_parent_code_by_level():
    assert derive_parent_code("30", "sido") is None
    assert derive_parent_code("30110", "sigungu") == "30"
    assert derive_parent_code("3011010300", "bjd") == "30110"


@pytest.mark.django_db
def test_count_bjd_code_mismatches():
    Region.objects.create(
        region_code="3011010300",
        level="bjd",
        name="효동",
        geom="MULTIPOLYGON(((0 0, 1 0, 1 1, 0 1, 0 0)))",
    )
    Building.objects.create(
        building_key="B1",
        gis_bldg_id="B1",
        pnu="p1",
        bjd_code="3011010300",
        source_date="2026-01-01",
        geom="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
    )
    Building.objects.create(
        building_key="B2",
        gis_bldg_id="B2",
        pnu="p2",
        bjd_code="9999999999",
        source_date="2026-01-01",
        geom="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
    )

    assert count_bjd_code_mismatches() == 1


# ---- resolve_vsi_path: 단일 zip / 중첩 zip(바깥 zip 안에 SIG·EMD zip) ----


def _make_zip(path, entries: dict[str, bytes]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def test_resolve_vsi_path_single_zip_finds_shp(tmp_path):
    zip_path = tmp_path / "TL_SCCO_SIG.zip"
    _make_zip(zip_path, {"TL_SCCO_SIG.shp": b"x", "TL_SCCO_SIG.dbf": b"x"})

    result = resolve_vsi_path(zip_path, "sigungu")

    assert result == f"/vsizip/{zip_path.resolve()}/TL_SCCO_SIG.shp"


def test_resolve_vsi_path_nested_zip_finds_inner_by_keyword(tmp_path):
    inner_path = tmp_path / "_inner_sig.zip"
    _make_zip(inner_path, {"TL_SCCO_SIG.shp": b"x", "TL_SCCO_SIG.dbf": b"x"})

    outer_path = tmp_path / "AL_D001_00_20261009.zip"
    with zipfile.ZipFile(outer_path, "w") as outer:
        outer.write(inner_path, arcname="AL_D001_00_SIG.zip")
        inner_emd = tmp_path / "_inner_emd.zip"
        _make_zip(inner_emd, {"TL_SCCO_EMD.shp": b"x"})
        outer.write(inner_emd, arcname="AL_D001_00_EMD.zip")

    sigungu_result = resolve_vsi_path(outer_path, "sigungu")
    bjd_result = resolve_vsi_path(outer_path, "bjd")

    assert sigungu_result == (
        f"/vsizip/{{/vsizip/{outer_path.resolve()}/AL_D001_00_SIG.zip}}/TL_SCCO_SIG.shp"
    )
    assert bjd_result == (
        f"/vsizip/{{/vsizip/{outer_path.resolve()}/AL_D001_00_EMD.zip}}/TL_SCCO_EMD.shp"
    )


def test_resolve_vsi_path_raises_when_keyword_not_found(tmp_path):
    outer_path = tmp_path / "outer.zip"
    inner_path = tmp_path / "_inner.zip"
    _make_zip(inner_path, {"a.shp": b"x"})
    with zipfile.ZipFile(outer_path, "w") as outer:
        outer.write(inner_path, arcname="only_lio.zip")  # SIG/EMD 없음, LIO만 있음

    with pytest.raises(ValueError, match="SIG"):
        resolve_vsi_path(outer_path, "sigungu")


# ---- load_regions(sigungu/bjd): 필드 기본값·좌표계 자동 인식·--sido 필터·8->10자리 패딩 ----


def _gdf(rows, crs="EPSG:5186"):
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Polygon

    square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    data = {"A1": [r[0] for r in rows], "A2": [r[1] for r in rows]}
    return gpd.GeoDataFrame(data, geometry=[square] * len(rows), crs=crs)


@pytest.mark.django_db
def test_load_regions_bjd_pads_8_digit_code_and_filters_by_sido(monkeypatch, tmp_path):
    # bjd.parent_code -> sigungu.region_code는 실제 FK라서(region.parent), 부모가 먼저 있어야 한다
    # (실제 운영 순서인 sigungu -> bjd와 동일).
    Region.objects.create(
        region_code="30110", level="sigungu", name="대전광역시 동구", geom=_square_wkt(127.40, 36.30)
    )
    monkeypatch.setattr("buildings.region_loading.resolve_vsi_path", lambda p, lvl: "dummy")
    monkeypatch.setattr(
        "pyogrio.read_dataframe",
        lambda *a, **k: _gdf([("30110250", "대전광역시 동구 효동"), ("11110250", "서울특별시 종로구 청운동")]),
    )

    summary = load_regions(tmp_path / "x.zip", level="bjd", sido_prefix="30")

    assert summary["total_rows"] == 1
    assert summary["skipped_outside_sido"] == 1
    assert summary["source_srid"] == 5186
    region = Region.objects.get(region_code="3011025000")
    assert region.name == "대전광역시 동구 효동"


@pytest.mark.django_db
def test_load_regions_raises_when_srid_cannot_be_determined(monkeypatch, tmp_path):
    monkeypatch.setattr("buildings.region_loading.resolve_vsi_path", lambda p, lvl: "dummy")
    monkeypatch.setattr(
        "pyogrio.read_dataframe",
        lambda *a, **k: _gdf([("30110", "대전광역시 동구")], crs=None),
    )

    with pytest.raises(ValueError, match="source-srid"):
        load_regions(tmp_path / "x.zip", level="sigungu", sido_prefix="30")


def test_load_regions_sido_without_path_requires_no_file(monkeypatch):
    called = {}

    def fake_union(prefix, source_date):
        called["prefix"] = prefix
        return {"ok": True}

    monkeypatch.setattr("buildings.region_loading.load_sido_from_sigungu_union", fake_union)

    result = load_regions(None, level="sido", sido_prefix="30")

    assert result == {"ok": True}
    assert called["prefix"] == "30"


def test_load_regions_non_sido_without_path_raises():
    with pytest.raises(ValueError, match="path"):
        load_regions(None, level="bjd", sido_prefix="30")


# ---- load_sido_from_sigungu_union: 이미 적재된 시군구를 union해서 시도를 만든다 ----


def _square_wkt(minx, miny, size=0.01):
    maxx, maxy = minx + size, miny + size
    return (
        f"MULTIPOLYGON((({minx} {miny}, {maxx} {miny}, "
        f"{maxx} {maxy}, {minx} {maxy}, {minx} {miny})))"
    )


@pytest.mark.django_db
def test_load_sido_from_sigungu_union_creates_sido_row_with_area_stats():
    Region.objects.create(
        region_code="30110", level="sigungu", name="대전광역시 동구", geom=_square_wkt(127.40, 36.30)
    )
    Region.objects.create(
        region_code="30140",
        level="sigungu",
        name="대전광역시 중구",
        geom=_square_wkt(127.41, 36.30),  # 바로 옆 — 겹치지 않는 인접 사각형
    )

    summary = load_sido_from_sigungu_union("30", source_date=None)

    assert summary["sigungu_count"] == 2
    assert summary["union_is_valid"] is True
    assert summary["area_diff_pct"] == pytest.approx(0.0, abs=0.01)
    region = Region.objects.get(region_code="30")
    assert region.level == "sido"
    assert region.name == "대전광역시"
    # sigungu는 시도가 없던 시점에 parent_code=NULL로 들어갔어야 하고, 시도가 생긴 뒤 채워진다.
    assert Region.objects.get(region_code="30110").parent_id == "30"
    assert Region.objects.get(region_code="30140").parent_id == "30"


@pytest.mark.django_db
def test_load_sido_from_sigungu_union_raises_when_no_sigungu():
    with pytest.raises(ValueError, match="sigungu"):
        load_sido_from_sigungu_union("30", source_date=None)


@pytest.mark.django_db
def test_load_sido_from_sigungu_union_raises_when_names_disagree():
    Region.objects.create(
        region_code="30110", level="sigungu", name="대전광역시 동구", geom=_square_wkt(127.40, 36.30)
    )
    Region.objects.create(
        region_code="30200", level="sigungu", name="세종특별자치시 조치원읍", geom=_square_wkt(127.41, 36.30)
    )

    with pytest.raises(ValueError, match="시도 이름"):
        load_sido_from_sigungu_union("30", source_date=None)


@pytest.mark.django_db
def test_load_sido_from_sigungu_union_computes_grid_when_service_area_registered():
    # "30"은 데이터 마이그레이션이 이미 시딩해 둔다(core/migrations/0004) — 중복 생성 방지.
    ServiceArea.objects.get_or_create(sido_code="30", defaults={"name": "대전광역시"})
    Region.objects.create(
        region_code="30110", level="sigungu", name="대전광역시 동구", geom=_square_wkt(127.40, 36.30)
    )

    load_sido_from_sigungu_union("30", source_date=None)

    assert ServiceArea.objects.get(sido_code="30").grid is not None


@pytest.mark.django_db
def test_load_sido_from_sigungu_union_skips_grid_when_no_service_area():
    # service_area에 없는 시도를 그냥 적재만 해 본 경우 — 에러 없이 조용히 건너뛴다.
    Region.objects.create(
        region_code="11110", level="sigungu", name="서울특별시 종로구", geom=_square_wkt(126.97, 37.57)
    )

    result = load_sido_from_sigungu_union("11", source_date=None)

    assert result["total_rows"] == 1
    assert not ServiceArea.objects.filter(sido_code="11").exists()
