from datetime import date

from django.core.management.base import BaseCommand, CommandError

from core.jobs import JobSkipped, tracked_run
from satellite.collect import collect_scenes
from satellite.seasons import parse_season


class Command(BaseCommand):
    help = (
        "Sentinel-2 L2A 장면을 수집한다. --season 2026-summer 또는 "
        "--start YYYY-MM-DD --end YYYY-MM-DD 중 하나를 지정해야 한다."
    )

    def add_arguments(self, parser):
        parser.add_argument("--season", default=None, help="예: 2026-summer")
        parser.add_argument("--start", default=None, help="YYYY-MM-DD")
        parser.add_argument("--end", default=None, help="YYYY-MM-DD")

    def handle(self, *args, **options):
        if options["season"]:
            start, end = parse_season(options["season"])
        elif options["start"] and options["end"]:
            start = date.fromisoformat(options["start"])
            end = date.fromisoformat(options["end"])
        else:
            raise CommandError("--season 또는 --start/--end를 지정해야 합니다.")

        self.stdout.write(f"수집 기간: {start} ~ {end}")

        try:
            with tracked_run("satellite_backfill", "daejeon", lock_ttl_seconds=3600 * 12):
                summary = collect_scenes(start, end)
        except JobSkipped:
            self.stdout.write(self.style.WARNING("다른 수집이 실행 중이라 건너뜀"))
            return

        self.stdout.write(self.style.SUCCESS("수집 완료"))
        self.stdout.write(
            f"  ready: {summary['ready']}, excluded: {summary['excluded']}, "
            f"기존 건 제외: {summary['skipped_existing']}"
        )
        self.stdout.write(f"  대전을 덮는 타일: {', '.join(summary['tiles']) or '없음'}")
