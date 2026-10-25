from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.areas import enabled_sido_codes
from core.jobs import JobSkipped, tracked_run
from crime.collect import FeatureCapNotConfigured
from crime.collect import run_safety_sync as run_crime_backfill
from publicdata.sync import months_back, sync_trades_for_months
from satellite.backfill import dry_run_list_scenes, run_backfill, target_seasons


class Command(BaseCommand):
    help = (
        "초기 적재 백필(spec 4장): 13개 계절 위성 분석 + 공공데이터(실거래·범죄주의구간). "
        "건물·행정경계(1단계)는 load_buildings/load_regions를 먼저 따로 실행해야 한다. "
        "--sido를 생략하면 활성화된 지역(service_area) 전체를 돈다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="2단계(장면 목록·용량 추정)만 하고 끝낸다. 아무것도 다운로드하지 않는다.",
        )
        parser.add_argument("--skip-trades", action="store_true")
        parser.add_argument("--skip-crime", action="store_true")
        parser.add_argument("--trade-months", type=int, default=24)
        parser.add_argument(
            "--sido",
            default=None,
            help="위성·실거래·범죄 수집 대상 시도 코드(생략하면 활성화된 지역 전체)",
        )

    def handle(self, *args, **options):
        if options["sido"]:
            sido_codes = [options["sido"]]
        else:
            sido_codes = enabled_sido_codes()
            if not sido_codes:
                raise CommandError("활성화된 지역(service_area, enabled=True)이 없습니다.")

        for sido_code in sido_codes:
            self.stdout.write(self.style.SUCCESS(f"\n######## 지역: {sido_code} ########"))
            self._run_for_region(sido_code, options)

    def _run_for_region(self, sido_code, options):
        seasons = target_seasons()
        self.stdout.write(
            f"대상 계절({len(seasons)}개): {seasons[0][0]}-{seasons[0][1]} ~ "
            f"{seasons[-1][0]}-{seasons[-1][1]}"
        )

        self.stdout.write("\n=== 2단계: 장면 목록 작성(dry run) ===")
        summary = dry_run_list_scenes(seasons, sido_code=sido_code)
        for row in summary["seasons"]:
            self.stdout.write(f"  {row['season']}: {row['scenes']}개(신규 {row['new']})")
        self.stdout.write(
            self.style.SUCCESS(
                f"신규 장면 {summary['total_new_scenes']}개, "
                f"예상 다운로드 용량 약 {summary['estimated_download_mb']:,}MB "
                "(장면당 150MB 추정 — 실제 CDSE 자산 크기를 확인한 값이 아니라 일정 참고용)"
            )
        )

        if options["dry_run"]:
            self.stdout.write("--dry-run이라 이 지역은 여기서 끝냅니다.")
            return

        self.stdout.write("\n=== 3·4·5단계: 계절별 수집·합성·변화·기준선·게시 ===")
        results = run_backfill(seasons, sido_code=sido_code)
        for row in results:
            if row.get("skipped"):
                self.stdout.write(f"  {row['season']}: 이미 게시됨, 건너뜀")
            else:
                self.stdout.write(f"  {row['season']}: {row['chain']}")

        if not options["skip_trades"]:
            self.stdout.write("\n=== 6단계: 실거래 백필 ===")
            months = months_back(options["trade_months"])
            try:
                with tracked_run("trade_backfill", sido_code, lock_ttl_seconds=3600 * 6):
                    sync_trades_for_months(months, sido_code=sido_code)
                self.stdout.write(self.style.SUCCESS("실거래 백필 완료"))
            except JobSkipped:
                self.stdout.write(self.style.WARNING("실거래 백필: 다른 실행 중이라 건너뜀"))

        if not options["skip_crime"]:
            self.stdout.write("\n=== 6단계: 범죄주의구간 백필 ===")
            if not settings.CRIME_FEATURE_CAP or not settings.CRIME_DATA_PERIOD:
                self.stdout.write(
                    self.style.WARNING(
                        "CRIME_FEATURE_CAP·CRIME_DATA_PERIOD가 설정되지 않아 건너뜁니다"
                        "(probe_crime_feature_cap을 먼저 실행하세요)."
                    )
                )
            else:
                try:
                    with tracked_run("safety_sync", sido_code, lock_ttl_seconds=3600 * 8):
                        run_crime_backfill(settings.CRIME_DATA_PERIOD, sido_code=sido_code)
                    self.stdout.write(self.style.SUCCESS("범죄주의구간 백필 완료"))
                except JobSkipped:
                    self.stdout.write(
                        self.style.WARNING("범죄주의구간 백필: 다른 실행 중이라 건너뜀")
                    )
                except FeatureCapNotConfigured as exc:
                    self.stdout.write(self.style.WARNING(f"범죄주의구간 백필 건너뜀: {exc}"))

        self.stdout.write(self.style.SUCCESS("\n백필 완료"))
