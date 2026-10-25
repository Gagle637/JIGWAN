from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask

# crontab에는 "N일마다"가 없어서, 한 달을 5일 단위로 고정 앵커링한다(spec 5-1: 5일마다 02:00).
DAYS_OF_MONTH = "1,6,11,16,21,26,31"


class Command(BaseCommand):
    help = (
        "활성 지역(service_area, enabled=True)마다 satellite_collect를 5일마다 02:00(KST)에 "
        "실행하도록 Beat에 등록한다(spec 5-1, 다지역 지원 7단계). 지금까지 이 작업은 "
        "Beat에 한 번도 등록된 적이 없었다."
    )

    def handle(self, *args, **options):
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="2",
            day_of_month=DAYS_OF_MONTH,
            month_of_year="*",
            day_of_week="*",
        )
        task, created = PeriodicTask.objects.update_or_create(
            name="satellite.satellite_collect.every_5_days",
            defaults={
                "task": "satellite.tasks.trigger_satellite_collect_for_enabled_regions",
                "crontab": schedule,
                "kwargs": "{}",
                "enabled": True,
            },
        )
        verb = "생성" if created else "갱신"
        self.stdout.write(self.style.SUCCESS(f"위성 수집 스케줄 {verb}: {task.name}"))
