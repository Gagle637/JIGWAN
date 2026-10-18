from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask

# 계절 종료 15일 후(spec 3-3): 3/15, 6/15, 9/15, 12/15 03:00 KST(spec 5-1).
SCHEDULE_MONTHS_DAYS = [(3, 15), (6, 15), (9, 15), (12, 15)]


class Command(BaseCommand):
    help = "satellite.tasks.trigger_season_chain_for_last_season을 분기 4번(spec 5-1)에 등록한다."

    def handle(self, *args, **options):
        for month, day in SCHEDULE_MONTHS_DAYS:
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute="0",
                hour="3",
                day_of_month=str(day),
                month_of_year=str(month),
                day_of_week="*",
            )
            task, created = PeriodicTask.objects.update_or_create(
                name=f"satellite.season_chain.{month:02d}{day:02d}",
                defaults={
                    "task": "satellite.tasks.trigger_season_chain_for_last_season",
                    "crontab": schedule,
                    "kwargs": "{}",
                    "enabled": True,
                },
            )
            verb = "생성" if created else "갱신"
            self.stdout.write(self.style.SUCCESS(f"계절 합성 스케줄 {verb}: {task.name}"))
