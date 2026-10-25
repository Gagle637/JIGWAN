from django.core.management.base import BaseCommand, CommandError

from core.areas import enabled_sido_codes
from satellite.season_chain import run_season_chain_sync


class Command(BaseCommand):
    help = (
        "season_composite -> group(change_analysis, region_stat) -> catalog_publish를 "
        "동기로 실행한다(수동/백필용). --season을 여러 번 줘서 여러 계절을 차례로 돌릴 수 있다. "
        "--sido를 생략하면 활성화된 지역(service_area) 전체를 돈다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            action="append",
            required=True,
            help="예: --season 2026-summer (여러 번 줄 수 있음)",
        )
        parser.add_argument(
            "--sido", default=None, help="시도 코드(생략하면 활성화된 지역 전체)"
        )

    def handle(self, *args, **options):
        if options["sido"]:
            sido_codes = [options["sido"]]
        else:
            sido_codes = enabled_sido_codes()
            if not sido_codes:
                raise CommandError("활성화된 지역(service_area, enabled=True)이 없습니다.")

        for season_str in options["season"]:
            try:
                year_str, season_name = season_str.split("-", 1)
                year = int(year_str)
            except ValueError as exc:
                raise CommandError(f"잘못된 계절 문자열: {season_str}") from exc

            for sido_code in sido_codes:
                self.stdout.write(f"=== {season_str} 체인 실행(지역: {sido_code}) ===")
                result = run_season_chain_sync(year, season_name, sido_code)
                for step, outcome in result.items():
                    if outcome == "ok":
                        self.stdout.write(self.style.SUCCESS(f"  {step}: ok"))
                    elif outcome == "skipped":
                        self.stdout.write(self.style.WARNING(f"  {step}: skipped"))
                    elif isinstance(outcome, str) and outcome.startswith("failed"):
                        self.stdout.write(self.style.ERROR(f"  {step}: {outcome}"))
