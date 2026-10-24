import zipfile

import pytest

from buildings.models import Region
from core.areas import (
    compute_and_store_grid,
    discover_available_areas,
    get_bbox,
    get_grid,
    get_sgg_codes,
)
from core.models import ServiceArea

pytestmark = pytest.mark.django_db


def _square_wkt(minx, miny, size=0.01):
    maxx, maxy = minx + size, miny + size
    return (
        f"MULTIPOLYGON((({minx} {miny}, {maxx} {miny}, "
        f"{maxx} {maxy}, {minx} {maxy}, {minx} {miny})))"
    )


def test_get_bbox_and_get_grid_raise_for_unknown_sido():
    with pytest.raises(ValueError, match="등록된 지역"):
        get_bbox("99")
    with pytest.raises(ValueError, match="등록된 지역"):
        get_grid("99")


def test_get_bbox_and_get_grid_raise_when_not_yet_computed():
    ServiceArea.objects.create(sido_code="99", name="테스트시")

    with pytest.raises(ValueError, match="compute_and_store_grid"):
        get_bbox("99")
    with pytest.raises(ValueError, match="compute_and_store_grid"):
        get_grid("99")


def test_get_sgg_codes_raises_when_no_sigungu_loaded():
    with pytest.raises(ValueError, match="load_regions"):
        get_sgg_codes("99")


def test_get_sgg_codes_returns_sigungu_codes_from_region():
    Region.objects.create(
        region_code="99110", level="sigungu", name="테스트시 가구", geom=_square_wkt(127.0, 36.0)
    )
    Region.objects.create(
        region_code="99140", level="sigungu", name="테스트시 나구", geom=_square_wkt(127.1, 36.0)
    )
    # 다른 시도 — 섞이면 안 된다.
    Region.objects.create(
        region_code="11110", level="sigungu", name="서울특별시 다구", geom=_square_wkt(126.0, 37.0)
    )

    assert get_sgg_codes("99") == ["99110", "99140"]


def test_compute_and_store_grid_requires_sido_region():
    ServiceArea.objects.create(sido_code="99", name="테스트시")

    with pytest.raises(ValueError, match="load_regions --level sido"):
        compute_and_store_grid("99")


def test_compute_and_store_grid_fills_bbox_and_grid_covering_the_region():
    ServiceArea.objects.create(sido_code="99", name="테스트시")
    Region.objects.create(
        region_code="99", level="sido", name="테스트시", geom=_square_wkt(127.0, 36.0, size=0.02)
    )

    compute_and_store_grid("99")

    area = ServiceArea.objects.get(sido_code="99")
    grid = area.grid
    assert grid["crs"] == "EPSG:32652"
    assert grid["resolution_m"] == 10
    # 60m 배수로 바깥 스냅됐는지.
    assert grid["minx"] % 60 == 0
    assert grid["miny"] % 60 == 0
    assert grid["maxx"] % 60 == 0
    assert grid["maxy"] % 60 == 0
    assert grid["width"] == round((grid["maxx"] - grid["minx"]) / 10)
    assert grid["height"] == round((grid["maxy"] - grid["miny"]) / 10)

    # bbox(4326)가 region(4326) 원본 경계를 항상 덮어야 한다(500m 여유를 뒀으니까).
    region = Region.objects.get(region_code="99")
    rminx, rminy, rmaxx, rmaxy = region.geom.extent
    assert area.bbox_minx <= rminx
    assert area.bbox_miny <= rminy
    assert area.bbox_maxx >= rmaxx
    assert area.bbox_maxy >= rmaxy

    # 이제 get_bbox/get_grid가 정상적으로 값을 돌려준다.
    assert get_grid("99") == grid
    assert get_bbox("99") == (area.bbox_minx, area.bbox_miny, area.bbox_maxx, area.bbox_maxy)


def test_compute_and_store_grid_is_idempotent():
    ServiceArea.objects.create(sido_code="99", name="테스트시")
    Region.objects.create(
        region_code="99", level="sido", name="테스트시", geom=_square_wkt(127.0, 36.0, size=0.02)
    )

    compute_and_store_grid("99")
    first_grid = ServiceArea.objects.get(sido_code="99").grid

    # region 경계가 바뀌어도(=다시 적재해도) grid는 이미 있으면 재계산하지 않는다.
    Region.objects.filter(region_code="99").update(geom=_square_wkt(127.0, 36.0, size=0.5))
    compute_and_store_grid("99")

    assert ServiceArea.objects.get(sido_code="99").grid == first_grid


# ---- discover_available_areas: AL_D001 zip(바깥 zip 안에 SIG zip)에서 시도 목록 추출 ----


def _make_zip(path, entries: dict[str, bytes]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def test_discover_available_areas_groups_by_sido_from_sig_layer(tmp_path, monkeypatch):
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Polygon

    square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    gdf = gpd.GeoDataFrame(
        {
            "A1": ["30110", "30140", "36110"],
            "A2": ["대전광역시 동구", "대전광역시 중구", "세종특별자치시 조치원읍"],
        },
        geometry=[square, square, square],
    )

    inner_path = tmp_path / "_inner_sig.zip"
    _make_zip(inner_path, {"dummy.shp": b"x"})
    outer_path = tmp_path / "AL_D001_00_20261009.zip"
    with zipfile.ZipFile(outer_path, "w") as outer:
        outer.write(inner_path, arcname="AL_D001_00_SIG.zip")

    monkeypatch.setattr("pyogrio.read_dataframe", lambda *a, **k: gdf)

    result = discover_available_areas(outer_path)

    assert result == [
        {"sido_code": "30", "name": "대전광역시", "sigungu_count": 2},
        {"sido_code": "36", "name": "세종특별자치시", "sigungu_count": 1},
    ]
