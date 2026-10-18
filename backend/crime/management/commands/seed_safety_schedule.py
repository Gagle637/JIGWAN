from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask


class Command(BaseCommand):
    help = "safety_sync를 매년 1월 첫째 주(1/5 03:00 KST)에 실행하도록 Beat에 등록한다(spec 5-1)."

    def handle(self, *args, **options):
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0", hour="3", day_of_month="5", month_of_year="1", day_of_week="*"
        )
        task, created = PeriodicTask.objects.update_or_create(
            name="crime.safety_sync.yearly",
            defaults={
                "task": "crime.tasks.safety_sync",
                "crontab": schedule,
                "kwargs": "{}",
                "enabled": True,
            },
        )
        verb = "생성" if created else "갱신"
        self.stdout.write(self.style.SUCCESS(f"범죄주의구간 수집 스케줄 {verb}: {task.name}"))
        self.stdout.write(
            self.style.WARNING(
                "CRIME_DATA_PERIOD(.env)를 이번 해 실제 데이터 기간으로 먼저 갱신해 두세요."
            )
        )
