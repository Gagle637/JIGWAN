from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from buildings.building_loading import load_buildings, resolve_building_zip_path
from buildings.models import Building, Region
from buildings.region_loading import load_regions
from core.areas import discover_available_areas, list_available_areas, resolve_al_d001_zip_path
from core.jobs import JobSkipped, tracked_run
from core.models import IndexRun, ServiceArea
from crime.collect import FeatureCapNotConfigured
from crime.collect import run_safety_sync as run_crime_sync
from crime.models import CrimeFetchProgress, CrimeSegment
from publicdata.models import Trade
from publicdata.sync import months_back, sync_trades_for_months
from satellite.backfill import _season_already_published, run_backfill, target_seasons
from satellite.models import RasterProduct, SatelliteScene

STAGE_BOUNDARY = "areas_sync_boundary"
STAGE_BUILDINGS = "areas_sync_buildings"
STAGE_TRADES = "areas_sync_trades"
STAGE_SATELLITE = "areas_sync_satellite"
STAGE_CRIME = "areas_sync_crime"


class Command(BaseCommand):
    help = "서비스 지역(service_area) 관리: list/status/available/add/enable/disable/sync."

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

        p_sync = sub.add_parser("sync", help="지역 전체 백필 파이프라인(경계~범죄)을 실행한다.")
        p_sync.add_argument("--area", required=True, help="대상 시도 코드")
        p_sync.add_argument(
            "--dry-run", action="store_true", help="아무것도 하지 않고 할 일/이미 끝난 일만 출력"
        )

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
        elif action == "sync":
            self._sync(options["area"], options["dry_run"])

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

    # ---- sync: 완료 판단은 전부 실제 데이터 기준(IndexRun은 실행 기록용) ----

    @staticmethod
    def _boundary_done(sido_code: str) -> bool:
        area = ServiceArea.objects.filter(sido_code=sido_code).first()
        has_sido_region = Region.objects.filter(level="sido", region_code=sido_code).exists()
        return bool(area and area.grid is not None and has_sido_region)

    @staticmethod
    def _building_done(sido_code: str) -> bool:
        return Building.objects.filter(bjd_code__startswith=sido_code, is_active=True).exists()

    @staticmethod
    def _missing_trade_months(sido_code: str) -> list[str]:
        """최근 24개월(YYYYMM) 중, 그 지역 Trade가 하나도 없는 달만 돌려준다."""
        missing = []
        for month in months_back(24):
            deal_ym = f"{month[:4]}-{month[4:]}"
            if not Trade.objects.filter(sgg_code__startswith=sido_code, deal_ym=deal_ym).exists():
                missing.append(month)
        return missing

    @staticmethod
    def _missing_seasons(sido_code: str) -> list[tuple[int, str]]:
        """target_seasons() 중, 그 지역에 4종(ndvi·ndbi·green_mask·truecolor)이 전부
        게시되지 않은 계절만 돌려준다(계절 단위로 이어하기)."""
        return [
            (year, season)
            for year, season in target_seasons()
            if not _season_already_published(year, season, sido_code)
        ]

    @staticmethod
    def _crime_done(sido_code: str) -> bool:
        progress_qs = CrimeFetchProgress.objects.filter(region_code=sido_code)
        if not progress_qs.exists():
            return False
        if progress_qs.exclude(
            status__in=[CrimeFetchProgress.Status.DONE, CrimeFetchProgress.Status.SPLIT]
        ).exists():
            return False
        period = settings.CRIME_DATA_PERIOD
        region = Region.objects.filter(level="sido", region_code=sido_code).first()
        if region is None or not period:
            return False
        return CrimeSegment.objects.filter(
            geom__intersects=region.geom, data_period=period
        ).exists()

    @staticmethod
    def _record_skipped(job: str, sido_code: str, reason: str) -> None:
        """잠금 충돌이 아닌 건너뜀(파일 없음·설정 없음)도 SUCCEEDED가 아니라 skipped로
        기록한다 — IndexRun은 실행 기록용일 뿐, 다음 실행의 완료 판단은 실제 데이터로 한다."""
        IndexRun.objects.create(
            job=job, region_code=sido_code, status=IndexRun.Status.SKIPPED, error=reason
        )

    def _sync(self, sido_code, dry_run):
        area = ServiceArea.objects.filter(sido_code=sido_code).first()
        if area is None:
            raise CommandError(f"'{sido_code}'는 등록된 지역이 아닙니다 — 먼저 areas add를 실행하세요.")

        # 1/5 경계
        if self._boundary_done(sido_code):
            self.stdout.write("[1/5] 경계: 이미 끝남, 건너뜀")
        elif dry_run:
            self.stdout.write("[1/5] 경계: 할 일")
        else:
            try:
                al_d001_path = resolve_al_d001_zip_path(None)
            except FileNotFoundError as exc:
                reason = str(exc)
                self._record_skipped(STAGE_BOUNDARY, sido_code, reason)
                self.stdout.write(
                    self.style.ERROR(
                        f"[1/5] 경계 중단: {reason}\n"
                        "  국가공간정보포털/브이월드에서 \"법정구역정보\"(전국)를 내려받아 "
                        "data/raw/AL_D001_00_YYYYMMDD.zip 형식으로 넣고 다시 실행하세요."
                    )
                )
                return
            try:
                with tracked_run(STAGE_BOUNDARY, sido_code, lock_ttl_seconds=1800):
                    load_regions(al_d001_path, level="sigungu", sido_prefix=sido_code)
                    load_regions(al_d001_path, level="bjd", sido_prefix=sido_code)
                    load_regions(None, level="sido", sido_prefix=sido_code)
                self.stdout.write(self.style.SUCCESS("[1/5] 경계 완료"))
            except JobSkipped:
                self.stdout.write(
                    self.style.WARNING("[1/5] 경계: 다른 실행 중이라 건너뜀 — 동기화를 중단합니다.")
                )
                return

        # 2/5 건물
        if self._building_done(sido_code):
            self.stdout.write("[2/5] 건물: 이미 끝남, 건너뜀")
        elif dry_run:
            self.stdout.write("[2/5] 건물: 할 일")
        else:
            try:
                al_d010_path = resolve_building_zip_path(None, sido_code=sido_code)
            except FileNotFoundError as exc:
                reason = str(exc)
                self._record_skipped(STAGE_BUILDINGS, sido_code, reason)
                self.stdout.write(
                    self.style.WARNING(
                        f"[2/5] 건물 건너뜀: {reason}\n"
                        "  브이월드에서 \"GIS건물통합정보\"를 내려받아 "
                        f"data/raw/AL_D010_{sido_code}_YYYYMMDD.zip 형식으로 넣으세요. "
                        "건물 파일을 넣고 다시 실행하면 실거래부터 이어서 진행됩니다."
                    )
                )
            else:
                try:
                    with tracked_run(STAGE_BUILDINGS, sido_code, lock_ttl_seconds=3600):
                        load_buildings(al_d010_path, sido_code=sido_code)
                    self.stdout.write(self.style.SUCCESS("[2/5] 건물 완료"))
                except JobSkipped:
                    self.stdout.write(self.style.WARNING("[2/5] 건물: 다른 실행 중이라 건너뜀"))

        # 경계+건물이 (이번 실행이든 이전이든) 끝나 있으면 자동 활성화
        if not dry_run and self._boundary_done(sido_code) and self._building_done(sido_code):
            if not area.enabled:
                area.enabled = True
                area.save(update_fields=["enabled"])
                self.stdout.write(
                    self.style.SUCCESS(f"'{sido_code}' 자동 활성화됨(경계·건물 적재 완료)")
                )

        # 3/5 실거래 — 건물이 안 끝났으면 건너뜀(거래 위치가 건물 중심점이라 비어서 쌓임)
        if not self._building_done(sido_code):
            if not dry_run:
                self._record_skipped(
                    STAGE_TRADES, sido_code, "건물 적재가 안 끝나서 건너뜀"
                )
            self.stdout.write(
                self.style.WARNING(
                    "[3/5] 실거래 건너뜀: 건물 적재가 안 끝났습니다(거래 위치가 건물 중심점이라 "
                    "비어서 쌓입니다). 건물 파일을 넣고 다시 실행하면 실거래부터 이어서 진행됩니다."
                )
            )
        else:
            missing_months = self._missing_trade_months(sido_code)
            if not missing_months:
                self.stdout.write("[3/5] 실거래: 이미 끝남, 건너뜀")
            elif dry_run:
                self.stdout.write(f"[3/5] 실거래: 할 일({len(missing_months)}개월)")
            else:
                try:
                    with tracked_run(STAGE_TRADES, sido_code, lock_ttl_seconds=3600 * 6):
                        sync_trades_for_months(missing_months, sido_code=sido_code)
                    self.stdout.write(
                        self.style.SUCCESS(f"[3/5] 실거래 완료({len(missing_months)}개월 수집)")
                    )
                except JobSkipped:
                    self.stdout.write(self.style.WARNING("[3/5] 실거래: 다른 실행 중이라 건너뜀"))

        # 4/5 위성 — 계절마다 진행 상황 출력, 빠진 계절만 처리
        missing_seasons = self._missing_seasons(sido_code)
        if not missing_seasons:
            self.stdout.write("[4/5] 위성: 모든 계절 이미 게시됨, 건너뜀")
        elif dry_run:
            self.stdout.write(
                f"[4/5] 위성: 할 일({len(missing_seasons)}개 계절: "
                + ", ".join(f"{y}-{s}" for y, s in missing_seasons)
                + ")"
            )
        else:
            self.stdout.write(f"[4/5] 위성: {len(missing_seasons)}개 계절 처리 시작")
            for year, season in missing_seasons:
                self.stdout.write(f"  - {year}-{season}: 처리 중...")
                try:
                    with tracked_run(
                        STAGE_SATELLITE, sido_code, lock_ttl_seconds=3600 * 12
                    ):
                        run_backfill([(year, season)], sido_code=sido_code)
                    self.stdout.write(self.style.SUCCESS(f"  - {year}-{season}: 완료"))
                except JobSkipped:
                    self.stdout.write(
                        self.style.WARNING(f"  - {year}-{season}: 다른 실행 중이라 건너뜀")
                    )
            self.stdout.write(self.style.SUCCESS("[4/5] 위성 처리 끝"))

        # 5/5 범죄
        if self._crime_done(sido_code):
            self.stdout.write("[5/5] 범죄: 이미 끝남, 건너뜀")
        elif dry_run:
            self.stdout.write("[5/5] 범죄: 할 일")
        else:
            if not settings.CRIME_FEATURE_CAP or not settings.CRIME_DATA_PERIOD:
                reason = "CRIME_FEATURE_CAP·CRIME_DATA_PERIOD가 설정되지 않음"
                self._record_skipped(STAGE_CRIME, sido_code, reason)
                self.stdout.write(
                    self.style.WARNING(
                        f"[5/5] 범죄 건너뜀: {reason} — probe_crime_feature_cap --sido "
                        f"{sido_code}를 먼저 실행해 .env를 채우세요."
                    )
                )
            else:
                try:
                    with tracked_run(STAGE_CRIME, sido_code, lock_ttl_seconds=3600 * 8):
                        run_crime_sync(settings.CRIME_DATA_PERIOD, sido_code=sido_code)
                    self.stdout.write(self.style.SUCCESS("[5/5] 범죄 완료"))
                except JobSkipped:
                    self.stdout.write(self.style.WARNING("[5/5] 범죄: 다른 실행 중이라 건너뜀"))
                except FeatureCapNotConfigured as exc:
                    self._record_skipped(STAGE_CRIME, sido_code, str(exc))
                    self.stdout.write(self.style.WARNING(f"[5/5] 범죄 건너뜀: {exc}"))
