import json

from django.core.management.base import BaseCommand
from django_celery_beat.models import IntervalSchedule, PeriodicTask


class Command(BaseCommand):
    help = "Beat 데모 스케줄 1건을 등록한다: healthcheck_ping을 5분마다 실행(core.jobs 래퍼 동작 확인용)."

    def handle(self, *args, **options):
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=5, period=IntervalSchedule.MINUTES
        )
        task, created = PeriodicTask.objects.update_or_create(
            name="core.healthcheck_ping.demo",
            defaults={
                "task": "core.tasks.healthcheck_ping",
                "interval": schedule,
                "kwargs": json.dumps({"region_code": "global"}),
                "enabled": True,
            },
        )
        verb = "생성" if created else "갱신"
        self.stdout.write(self.style.SUCCESS(f"데모 스케줄 {verb}: {task.name}"))
