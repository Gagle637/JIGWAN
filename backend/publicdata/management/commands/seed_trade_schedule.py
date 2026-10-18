from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask


class Command(BaseCommand):
    help = "trade_sync를 매일 04:00(KST)에 실행하도록 Beat에 등록한다(spec 5-1)."

    def handle(self, *args, **options):
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0", hour="4", day_of_week="*", day_of_month="*", month_of_year="*"
        )
        task, created = PeriodicTask.objects.update_or_create(
            name="publicdata.trade_sync.daily",
            defaults={
                "task": "publicdata.tasks.trade_sync",
                "crontab": schedule,
                "kwargs": "{}",
                "enabled": True,
            },
        )
        verb = "생성" if created else "갱신"
        self.stdout.write(self.style.SUCCESS(f"실거래 수집 스케줄 {verb}: {task.name}"))
