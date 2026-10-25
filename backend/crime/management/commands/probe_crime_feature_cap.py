import random
import time

import httpx
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from rasterio.warp import transform

from core.areas import enabled_sido_codes, get_bbox
from crime import grid
from crime.safemap_client import REQUESTED_FEATURE_COUNT, fetch_feature_info

REQUEST_DELAY_RANGE_SECONDS = (1.0, 2.0)

# 대전 중구 원도심(은행동·중앙로 일대) — 도로·주의구간이 촘촘해 상한에 걸릴 가능성이 큰 지점의
# 예시 좌표. 다른 지점을 보고 싶으면 --lon/--lat로 바꿀 수 있다. 대전 외 지역은 --lon/--lat를
# 안 주면 건물이 가장 많은 시군구의 건물 중심점(실제로 밀집된 곳)을 쓴다(다지역 지원 7단계).
DEFAULT_LON = 127.4258
DEFAULT_LAT = 36.3262


def _building_density_centroid(sido_code: str) -> tuple[float, float] | None:
    """건물이 가장 많은 시군구(bjd_code 앞 5자리)의 건물들 중심점. 아직 건물이 없으면 None."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT LEFT(bjd_code, 5) AS sigungu, COUNT(*) AS cnt FROM building "
            "WHERE bjd_code LIKE %s AND is_active GROUP BY sigungu ORDER BY cnt DESC LIMIT 1",
            [f"{sido_code}%"],
        )
        row = cur.fetchone()
        if row is None:
            return None
        sigungu_code = row[0]

        cur.execute(
            "SELECT ST_X(c), ST_Y(c) FROM ("
            "  SELECT ST_Centroid(ST_Collect(geom)) AS c FROM building "
            "  WHERE bjd_code LIKE %s AND is_active"
            ") t WHERE c IS NOT NULL",
            [f"{sigungu_code}%"],
        )
        point = cur.fetchone()
    return (point[0], point[1]) if point and point[0] is not None else None


class Command(BaseCommand):
    help = (
        "GetFeatureInfo의 FEATURE_COUNT 숨은 서버 상한을 추정한다. 도심 밀집 2km 구역을 한 번, "
        "같은 구역을 4등분(1km×4)해서 각각 호출해 고유 OBJT_ID 수를 비교한다. "
        "--sido를 생략하면 활성화된 지역(service_area) 전체를 돈다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--sido",
            default=None,
            help="좌표를 안 주면 이 지역을 기준으로 중심점을 고른다(생략하면 활성화된 지역 전체).",
        )
        parser.add_argument("--lon", type=float, default=None)
        parser.add_argument("--lat", type=float, default=None)

    def handle(self, *args, **options):
        if options["sido"]:
            sido_codes = [options["sido"]]
        else:
            if options["lon"] is not None or options["lat"] is not None:
                raise CommandError("--lon/--lat를 주려면 --sido도 같이 지정해야 합니다.")
            sido_codes = enabled_sido_codes()
            if not sido_codes:
                raise CommandError("활성화된 지역(service_area, enabled=True)이 없습니다.")

        for sido_code in sido_codes:
            self.stdout.write(f"=== 지역: {sido_code} ===")
            self._probe_one(sido_code, options["lon"], options["lat"])

    def _probe_one(self, sido_code, lon, lat):
        if lon is None or lat is None:
            if sido_code == "30":
                lon = lon if lon is not None else DEFAULT_LON
                lat = lat if lat is not None else DEFAULT_LAT
            else:
                centroid = _building_density_centroid(sido_code)
                if centroid is not None:
                    lon = lon if lon is not None else centroid[0]
                    lat = lat if lat is not None else centroid[1]
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            "  건물이 아직 없어 지역 bbox 중심을 씁니다"
                            "(load_buildings를 먼저 실행하면 더 밀집된 지점을 씁니다)."
                        )
                    )
                    minx, miny, maxx, maxy = get_bbox(sido_code)
                    lon = lon if lon is not None else (minx + maxx) / 2
                    lat = lat if lat is not None else (miny + maxy) / 2

        (cx,), (cy,) = transform("EPSG:4326", "EPSG:3857", [lon], [lat])
        half = grid.CELL_SIZE_M / 2
        minx, miny = cx - half, cy - half

        with httpx.Client() as client:
            self.stdout.write("  큰 구역(2km) 호출 중...")
            big_bbox = grid.cell_bbox(minx, miny, grid.CELL_SIZE_M)
            big_features = fetch_feature_info(client, big_bbox, REQUESTED_FEATURE_COUNT)
            big_ids = {f["properties"]["OBJT_ID"] for f in big_features}
            time.sleep(random.uniform(*REQUEST_DELAY_RANGE_SECONDS))

            self.stdout.write("  4등분(1km×4) 호출 중...")
            quad_ids = set()
            for qminx, qminy, qsize in grid.split_cell(minx, miny, grid.CELL_SIZE_M):
                qbbox = grid.cell_bbox(qminx, qminy, qsize)
                features = fetch_feature_info(client, qbbox, REQUESTED_FEATURE_COUNT)
                quad_ids.update(f["properties"]["OBJT_ID"] for f in features)
                time.sleep(random.uniform(*REQUEST_DELAY_RANGE_SECONDS))

        self.stdout.write(f"  큰 구역 응답 고유 OBJT_ID 수: {len(big_ids)}")
        self.stdout.write(f"  4등분 합친 고유 OBJT_ID 수: {len(quad_ids)}")

        if len(quad_ids) > len(big_ids):
            self.stdout.write(
                self.style.WARNING(
                    f"  4등분 쪽이 더 많습니다 — 서버에 숨은 상한이 있는 것으로 보입니다.\n"
                    f'  .env에 CRIME_FEATURE_CAP={len(big_ids)} 를 넣으세요(큰 구역이 실제로 받은 개수).'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "  이 구역에서는 숨은 상한이 감지되지 않았습니다. 그래도 안전하게 "
                    f".env에 CRIME_FEATURE_CAP={len(big_ids)} 를 넣어 기준값으로 쓰세요."
                )
            )
