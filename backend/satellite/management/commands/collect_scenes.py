from datetime import date

from django.core.management.base import BaseCommand, CommandError

from core.areas import enabled_sido_codes
from core.jobs import JobSkipped, tracked_run
from satellite.collect import collect_scenes
from satellite.seasons import parse_season


class Command(BaseCommand):
    help = (
        "Sentinel-2 L2A 장면을 수집한다. --season 2026-summer 또는 "
        "--start YYYY-MM-DD --end YYYY-MM-DD 중 하나를 지정해야 한다. "
        "--sido를 생략하면 활성화된 지역(service_area) 전체를 돈다."
    )

    def add_arguments(self, parser):
        parser.add_argument("--season", default=None, help="예: 2026-summer")
        parser.add_argument("--start", default=None, help="YYYY-MM-DD")
        parser.add_argument("--end", default=None, help="YYYY-MM-DD")
        parser.add_argument(
            "--sido", default=None, help="시도 코드(생략하면 활성화된 지역 전체)"
        )

    def handle(self, *args, **options):
        if options["season"]:
            start, end = parse_season(options["season"])
        elif options["start"] and options["end"]:
            start = date.fromisoformat(options["start"])
            end = date.fromisoformat(options["end"])
        else:
            raise CommandError("--season 또는 --start/--end를 지정해야 합니다.")

        if options["sido"]:
            sido_codes = [options["sido"]]
        else:
            sido_codes = enabled_sido_codes()
            if not sido_codes:
                raise CommandError("활성화된 지역(service_area, enabled=True)이 없습니다.")

        for sido_code in sido_codes:
            self.stdout.write(f"수집 기간: {start} ~ {end} (지역: {sido_code})")
            try:
                with tracked_run(
                    "satellite_backfill", sido_code, lock_ttl_seconds=3600 * 12
                ):
                    summary = collect_scenes(start, end, sido_code=sido_code)
            except JobSkipped:
                self.stdout.write(self.style.WARNING("  다른 수집이 실행 중이라 건너뜀"))
                continue

            self.stdout.write(self.style.SUCCESS("  수집 완료"))
            self.stdout.write(
                f"    ready: {summary['ready']}, excluded: {summary['excluded']}, "
                f"기존 건 제외: {summary['skipped_existing']}"
            )
            self.stdout.write(f"    덮는 타일: {', '.join(summary['tiles']) or '없음'}")
