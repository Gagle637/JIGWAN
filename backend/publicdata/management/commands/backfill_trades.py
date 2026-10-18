from django.core.management.base import BaseCommand

from core.jobs import JobSkipped, tracked_run
from publicdata.sync import months_back, sync_trades_for_months


class Command(BaseCommand):
    help = "실거래 백필: 이번 달부터 --months 개월 전까지 재수집한다."

    def add_arguments(self, parser):
        parser.add_argument("--months", type=int, default=24)

    def handle(self, *args, **options):
        months = months_back(options["months"])
        self.stdout.write(f"대상 월: {months[-1]} ~ {months[0]} ({len(months)}개월)")

        try:
            with tracked_run("trade_backfill", "daejeon", lock_ttl_seconds=3600 * 6):
                overall = sync_trades_for_months(months)
        except JobSkipped:
            self.stdout.write(self.style.WARNING("다른 백필이 실행 중이라 건너뜀"))
            return

        for deal_ymd, month_stats in overall.items():
            self.stdout.write(f"[{deal_ymd}]")
            for house_type, stat in month_stats.items():
                if stat.get("match_rate_pct") is None and stat.get("matched") is None:
                    self.stdout.write(f"  {house_type}: 총 {stat['total']}건 (매칭 대상 아님)")
                else:
                    self.stdout.write(
                        f"  {house_type}: 총 {stat['total']}건, "
                        f"매칭 {stat['matched']}건({stat['match_rate_pct']}%), "
                        f"실패 사유 {stat['failed']}"
                    )
