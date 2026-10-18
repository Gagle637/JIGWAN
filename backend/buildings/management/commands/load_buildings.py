from django.core.management.base import BaseCommand

from buildings.building_loading import load_buildings, resolve_building_zip_path
from core.jobs import JobSkipped, SkipJob, tracked_run


class Command(BaseCommand):
    help = (
        "GIS건물통합정보(대전) 파일을 building 테이블에 upsert로 적재한다. "
        "zip_path를 생략하면 data/raw/AL_D010_30_*.zip 중 파일명 날짜가 가장 최신인 파일을 쓴다."
    )

    def add_arguments(self, parser):
        parser.add_argument("zip_path", nargs="?", default=None)

    def handle(self, *args, **options):
        zip_path = resolve_building_zip_path(options["zip_path"])
        self.stdout.write(f"대상 파일: {zip_path}")

        try:
            with tracked_run("building_load", "daejeon") as run:
                summary = load_buildings(zip_path)
        except JobSkipped:
            self.stdout.write(self.style.WARNING("다른 적재가 실행 중이라 건너뜀"))
            return

        if run.status == run.Status.SKIPPED:
            self.stdout.write(self.style.WARNING(f"건너뜀: {run.error}"))
            return

        self.stdout.write(self.style.SUCCESS("적재 완료"))
        self.stdout.write(f"  총 건수: {summary['total_rows']}")
        self.stdout.write(f"  source_date: {summary['source_date']}")
        self.stdout.write(f"  영향 받은 행(신규/갱신): {summary['affected_rows']}")
        self.stdout.write(f"  PNU 결측: {summary['missing_pnu']}")
        self.stdout.write(
            f"  대장 속성 없음: {summary['missing_registry']} "
            f"({summary['missing_registry_pct']}%)"
        )
        self.stdout.write(f"  고친 도형 수: {summary['invalid_geometry_fixed']}")
        self.stdout.write(
            f"  approval_date 파싱 실패: {summary['approval_date_parse_failed']}"
        )
