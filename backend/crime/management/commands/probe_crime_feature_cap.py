import random
import time

import httpx
from django.core.management.base import BaseCommand
from rasterio.warp import transform

from crime import grid
from crime.safemap_client import REQUESTED_FEATURE_COUNT, fetch_feature_info

REQUEST_DELAY_RANGE_SECONDS = (1.0, 2.0)

# 대전 중구 원도심(은행동·중앙로 일대) — 도로·주의구간이 촘촘해 상한에 걸릴 가능성이 큰 지점의
# 예시 좌표. 다른 지점을 보고 싶으면 --lon/--lat로 바꿀 수 있다.
DEFAULT_LON = 127.4258
DEFAULT_LAT = 36.3262


class Command(BaseCommand):
    help = (
        "GetFeatureInfo의 FEATURE_COUNT 숨은 서버 상한을 추정한다. 도심 밀집 2km 구역을 한 번, "
        "같은 구역을 4등분(1km×4)해서 각각 호출해 고유 OBJT_ID 수를 비교한다."
    )

    def add_arguments(self, parser):
        parser.add_argument("--lon", type=float, default=DEFAULT_LON)
        parser.add_argument("--lat", type=float, default=DEFAULT_LAT)

    def handle(self, *args, **options):
        (cx,), (cy,) = transform("EPSG:4326", "EPSG:3857", [options["lon"]], [options["lat"]])
        half = grid.CELL_SIZE_M / 2
        minx, miny = cx - half, cy - half

        with httpx.Client() as client:
            self.stdout.write("큰 구역(2km) 호출 중...")
            big_bbox = grid.cell_bbox(minx, miny, grid.CELL_SIZE_M)
            big_features = fetch_feature_info(client, big_bbox, REQUESTED_FEATURE_COUNT)
            big_ids = {f["properties"]["OBJT_ID"] for f in big_features}
            time.sleep(random.uniform(*REQUEST_DELAY_RANGE_SECONDS))

            self.stdout.write("4등분(1km×4) 호출 중...")
            quad_ids = set()
            for qminx, qminy, qsize in grid.split_cell(minx, miny, grid.CELL_SIZE_M):
                qbbox = grid.cell_bbox(qminx, qminy, qsize)
                features = fetch_feature_info(client, qbbox, REQUESTED_FEATURE_COUNT)
                quad_ids.update(f["properties"]["OBJT_ID"] for f in features)
                time.sleep(random.uniform(*REQUEST_DELAY_RANGE_SECONDS))

        self.stdout.write(f"큰 구역 응답 고유 OBJT_ID 수: {len(big_ids)}")
        self.stdout.write(f"4등분 합친 고유 OBJT_ID 수: {len(quad_ids)}")

        if len(quad_ids) > len(big_ids):
            self.stdout.write(
                self.style.WARNING(
                    f"4등분 쪽이 더 많습니다 — 서버에 숨은 상한이 있는 것으로 보입니다.\n"
                    f'.env에 CRIME_FEATURE_CAP={len(big_ids)} 를 넣으세요(큰 구역이 실제로 받은 개수).'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "이 구역에서는 숨은 상한이 감지되지 않았습니다. 그래도 안전하게 "
                    f".env에 CRIME_FEATURE_CAP={len(big_ids)} 를 넣어 기준값으로 쓰세요."
                )
            )
