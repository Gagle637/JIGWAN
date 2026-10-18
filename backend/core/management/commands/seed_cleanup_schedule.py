from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask


class Command(BaseCommand):
    help = (
        "정리 잡(90일 지난 장면 COG, 1년 지난 index_run, spec 5-4)을 "
        "주 1회(월요일 03:30 KST)에 실행하도록 Beat에 등록한다."
    )

    def handle(self, *args, **options):
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="30", hour="3", day_of_week="1", day_of_month="*", month_of_year="*"
        )
        jobs = [
            ("core.cleanup_index_runs.weekly", "core.tasks.cleanup_index_runs_task"),
            ("satellite.cleanup_scene_cogs.weekly", "satellite.tasks.cleanup_scene_cogs_task"),
        ]
        for name, task in jobs:
            periodic_task, created = PeriodicTask.objects.update_or_create(
                name=name,
                defaults={
                    "task": task,
                    "crontab": schedule,
                    "kwargs": "{}",
                    "enabled": True,
                },
            )
            verb = "생성" if created else "갱신"
            self.stdout.write(self.style.SUCCESS(f"정리 잡 스케줄 {verb}: {periodic_task.name}"))
