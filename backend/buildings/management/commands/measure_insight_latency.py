import random
import time

from django.core.management.base import BaseCommand

from buildings.insight import ALLOWED_RADIUS_M, get_insight_cached
from buildings.models import Building


class Command(BaseCommand):
    help = (
        "표본 건물 N곳의 insight 계산 시간을 재서 p50/p90/max를 출력한다"
        "(spec 9-2 완료 기준: p90 2초 이내). 캐시를 비우고 측정하므로 '처음 조회' 기준이다."
    )

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=20)
        parser.add_argument("--radius", type=int, default=500, choices=list(ALLOWED_RADIUS_M))

    def handle(self, *args, **options):
        count = options["count"]
        radius_m = options["radius"]

        building_ids = list(
            Building.objects.filter(is_active=True).values_list("id", flat=True)
        )
        if not building_ids:
            self.stdout.write(self.style.WARNING("is_active 건물이 없습니다."))
            return

        sample_ids = random.sample(building_ids, min(count, len(building_ids)))
        durations = []
        for building_id in sample_ids:
            building = Building.objects.get(pk=building_id)
            started = time.perf_counter()
            get_insight_cached(building, radius_m)
            durations.append(time.perf_counter() - started)

        durations.sort()
        n = len(durations)
        p50 = durations[int(n * 0.5)]
        p90 = durations[min(int(n * 0.9), n - 1)]
        worst = durations[-1]

        self.stdout.write(f"표본 {n}곳, radius={radius_m}m")
        self.stdout.write(f"  p50: {p50:.3f}s")
        self.stdout.write(f"  p90: {p90:.3f}s (목표: 2.0s 이내)")
        self.stdout.write(f"  max: {worst:.3f}s")

        if p90 > 2.0:
            self.stdout.write(self.style.ERROR("p90이 2초를 넘었습니다."))
        else:
            self.stdout.write(self.style.SUCCESS("p90 2초 이내."))
