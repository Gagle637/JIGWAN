from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.areas import enabled_sido_codes
from core.jobs import JobSkipped, tracked_run
from crime.collect import run_safety_sync
from crime.registry import crime_layer_id
from layers.wms_proxy import clear_tile_cache


class Command(BaseCommand):
    help = (
        "범죄주의구간을 수동으로 수집한다(spec 8-4). 중단됐으면 이어서 재개한다. "
        "--sido를 생략하면 활성화된 지역(service_area) 전체를 돈다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-period",
            default=None,
            help="예: 2023-07/2024-06. 생략하면 .env의 CRIME_DATA_PERIOD를 쓴다.",
        )
        parser.add_argument(
            "--sido", default=None, help="수집 대상 시도 코드(생략하면 활성화된 지역 전체)"
        )

    def handle(self, *args, **options):
        if not settings.CRIME_FEATURE_CAP:
            raise CommandError(
                "CRIME_FEATURE_CAP이 설정되지 않았습니다. probe_crime_feature_cap을 먼저 실행하세요."
            )

        data_period = options["data_period"] or settings.CRIME_DATA_PERIOD
        if not data_period:
            raise CommandError("--data-period 또는 .env의 CRIME_DATA_PERIOD가 필요합니다.")

        if options["sido"]:
            sido_codes = [options["sido"]]
        else:
            sido_codes = enabled_sido_codes()
            if not sido_codes:
                raise CommandError("활성화된 지역(service_area, enabled=True)이 없습니다.")

        for sido_code in sido_codes:
            self.stdout.write(f"=== 지역: {sido_code} ===")
            try:
                with tracked_run("safety_sync", sido_code, lock_ttl_seconds=3600 * 8):
                    summary = run_safety_sync(data_period, sido_code=sido_code)
            except JobSkipped:
                self.stdout.write(self.style.WARNING("  다른 수집이 실행 중이라 건너뜀"))
                continue

            layer_id = crime_layer_id()
            if layer_id is not None:
                clear_tile_cache(layer_id)

            self.stdout.write(self.style.SUCCESS("  수집 실행 완료"))
            self.stdout.write(
                f"    done: {summary['cells_done']}, failed: {summary['cells_failed']}, "
                f"전체 완료: {summary['fully_done']}"
            )
            if summary["cells_failed"]:
                self.stdout.write(
                    self.style.WARNING(
                        "    일부 구역이 failed로 남았습니다. 이 명령을 다시 실행하면 그 구역부터 재시도합니다."
                    )
                )
            self.stdout.write(f"    누적 구간 수: {summary['segments_total']}")
