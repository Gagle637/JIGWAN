from django.core.management.base import BaseCommand, CommandError

from buildings.models import Building, Region
from core.areas import discover_available_areas, list_available_areas, resolve_al_d001_zip_path
from core.models import ServiceArea
from crime.models import CrimeFetchProgress, CrimeSegment
from publicdata.models import Trade
from satellite.models import RasterProduct, SatelliteScene


class Command(BaseCommand):
    help = "서비스 지역(service_area) 관리: list/status/available/add/enable/disable."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)

        sub.add_parser("list", help="등록된 지역 전체를 보여준다.")

        p_status = sub.add_parser("status", help="지역별 단계 진행 상황을 보여준다.")
        p_status.add_argument("sido", nargs="?", default=None)

        p_available = sub.add_parser(
            "available", help="AL_D001_00 zip에서 추가 가능한 지역 목록을 보여준다."
        )
        p_available.add_argument(
            "--path", default=None, help="AL_D001_00_*.zip 경로(생략하면 data/raw에서 최신 파일)"
        )

        p_add = sub.add_parser("add", help="새 지역을 비활성 상태로 등록한다.")
        p_add.add_argument("sido")
        p_add.add_argument(
            "--path", default=None, help="AL_D001_00_*.zip 경로(생략하면 data/raw에서 최신 파일)"
        )

        p_enable = sub.add_parser("enable", help="지역을 활성화한다(경계·격자가 있어야 함).")
        p_enable.add_argument("sido")

        p_disable = sub.add_parser("disable", help="지역을 비활성화한다.")
        p_disable.add_argument("sido")

    def handle(self, *args, **options):
        action = options["action"]
        if action == "list":
            self._list()
        elif action == "status":
            self._status(options["sido"])
        elif action == "available":
            self._available(options["path"])
        elif action == "add":
            self._add(options["sido"], options["path"])
        elif action == "enable":
            self._set_enabled(options["sido"], True)
        elif action == "disable":
            self._set_enabled(options["sido"], False)

    # ---- list ----

    def _list(self):
        areas = ServiceArea.objects.order_by("sido_code")
        if not areas:
            self.stdout.write("등록된 지역이 없습니다.")
            return
        for area in areas:
            state = "활성" if area.enabled else "비활성"
            grid_state = "grid 있음" if area.grid else "grid 없음"
            self.stdout.write(f"{area.sido_code}  {area.name}  [{state}, {grid_state}]")

    # ---- available ----

    def _available(self, explicit_path):
        try:
            entries = list_available_areas(explicit_path)
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc

        if not entries:
            self.stdout.write("추가 가능한 지역을 찾지 못했습니다.")
            return
        for entry in entries:
            self.stdout.write(
                f"{entry['sido_code']}  {entry['name']}  "
                f"(시군구 {entry['sigungu_count']}개)  [{entry['status']}]"
            )

    # ---- add ----

    def _add(self, sido_code, explicit_path):
        if ServiceArea.objects.filter(sido_code=sido_code).exists():
            raise CommandError(f"'{sido_code}'는 이미 등록돼 있습니다.")

        try:
            path = resolve_al_d001_zip_path(explicit_path)
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc

        entry = next(
            (e for e in discover_available_areas(path) if e["sido_code"] == sido_code), None
        )
        if entry is None:
            raise CommandError(f"'{sido_code}'를 {path}에서 찾지 못했습니다.")

        ServiceArea.objects.create(sido_code=sido_code, name=entry["name"], enabled=False)
        self.stdout.write(
            self.style.SUCCESS(
                f"'{sido_code}' {entry['name']}을 비활성 상태로 추가했습니다. "
                "경계·건물 적재 등은 따로 실행하세요(areas sync 또는 load_regions/load_buildings)."
            )
        )

    # ---- enable / disable ----

    def _set_enabled(self, sido_code, enabled):
        area = ServiceArea.objects.filter(sido_code=sido_code).first()
        if area is None:
            raise CommandError(f"'{sido_code}'는 등록된 지역이 아닙니다.")

        if enabled:
            has_region = Region.objects.filter(level="sido", region_code=sido_code).exists()
            if not has_region or area.grid is None:
                raise CommandError(
                    f"'{sido_code}' 지역의 경계·격자가 아직 없습니다 — 먼저 경계를 적재하세요"
                    f"(areas sync 또는 load_regions --sido {sido_code})."
                )

        area.enabled = enabled
        area.save(update_fields=["enabled"])
        verb = "활성화" if enabled else "비활성화"
        self.stdout.write(self.style.SUCCESS(f"'{sido_code}' {area.name}을 {verb}했습니다."))

    # ---- status ----

    def _status(self, sido_code):
        if sido_code:
            area = ServiceArea.objects.filter(sido_code=sido_code).first()
            if area is None:
                raise CommandError(f"'{sido_code}'는 등록된 지역이 아닙니다.")
            areas = [area]
        else:
            areas = list(ServiceArea.objects.order_by("sido_code"))
            if not areas:
                self.stdout.write("등록된 지역이 없습니다.")
                return

        for area in areas:
            self._print_status(area)

    def _print_status(self, area: ServiceArea):
        code = area.sido_code
        self.stdout.write(self.style.SUCCESS(f"== {code} {area.name} =="))
        self.stdout.write(f"  활성화: {'예' if area.enabled else '아니오'}")
        self.stdout.write(f"  grid/bbox: {'있음' if area.grid else '없음'}")

        region_counts = {
            level: Region.objects.filter(level=level, region_code__startswith=code).count()
            for level in ("sido", "sigungu", "bjd")
        }
        self.stdout.write(
            f"  행정경계: 시도 {region_counts['sido']}, 시군구 {region_counts['sigungu']}, "
            f"법정동 {region_counts['bjd']}"
        )

        building_count = Building.objects.filter(
            bjd_code__startswith=code, is_active=True
        ).count()
        self.stdout.write(f"  건물: {building_count}개(활성)")

        scene_ready = SatelliteScene.objects.filter(
            region_code=code, status=SatelliteScene.Status.READY
        ).count()
        product_published = RasterProduct.objects.filter(
            region_code=code, is_published=True
        ).count()
        self.stdout.write(
            f"  위성: 장면(ready) {scene_ready}개, raster_product(게시) {product_published}개"
        )

        trade_count = Trade.objects.filter(sgg_code__startswith=code).count()
        self.stdout.write(f"  실거래: {trade_count}건")

        progress_counts = {
            status: CrimeFetchProgress.objects.filter(region_code=code, status=status).count()
            for status in (
                CrimeFetchProgress.Status.DONE,
                CrimeFetchProgress.Status.PENDING,
                CrimeFetchProgress.Status.FAILED,
                CrimeFetchProgress.Status.SPLIT,
            )
        }
        total_cells = sum(progress_counts.values())
        region_sido = Region.objects.filter(level="sido", region_code=code).first()
        if region_sido is not None:
            segment_count = CrimeSegment.objects.filter(geom__intersects=region_sido.geom).count()
            segment_note = f"{segment_count}개"
        else:
            segment_note = "경계 없음, 측정 불가"
        self.stdout.write(
            f"  범죄: 셀 done {progress_counts[CrimeFetchProgress.Status.DONE]}/{total_cells}"
            f"(failed {progress_counts[CrimeFetchProgress.Status.FAILED]}), 구간 {segment_note}"
        )
