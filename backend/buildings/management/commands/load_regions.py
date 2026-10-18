from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from buildings.region_loading import load_regions
from core.jobs import JobSkipped, tracked_run


class Command(BaseCommand):
    help = (
        "법정구역 경계(브이월드·국가공간정보포털)를 region 테이블에 upsert로 적재한다. "
        "sido -> sigungu -> bjd 순으로 각각 한 번씩 실행해야 한다(부모 코드가 먼저 있어야 함)."
    )

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--level", required=True, choices=["sido", "sigungu", "bjd"])
        parser.add_argument("--source-srid", type=int, required=True)
        parser.add_argument("--code-field", default=None)
        parser.add_argument("--name-field", default=None)
        parser.add_argument("--pad-to", type=int, default=None)
        parser.add_argument("--source-date", default=None, help="YYYY-MM-DD")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"파일을 찾을 수 없습니다: {path}")

        source_date = (
            date.fromisoformat(options["source_date"]) if options["source_date"] else None
        )

        try:
            with tracked_run("load_regions", f"daejeon:{options['level']}") as run:
                summary = load_regions(
                    path,
                    level=options["level"],
                    source_srid=options["source_srid"],
                    code_field=options["code_field"],
                    name_field=options["name_field"],
                    pad_to=options["pad_to"],
                    source_date=source_date,
                )
        except JobSkipped:
            self.stdout.write(self.style.WARNING("다른 적재가 실행 중이라 건너뜀"))
            return

        self.stdout.write(self.style.SUCCESS("적재 완료"))
        self.stdout.write(f"  level: {summary['level']}")
        self.stdout.write(f"  총 건수: {summary['total_rows']}")
        self.stdout.write(f"  영향 받은 행(신규/갱신): {summary['affected_rows']}")
        if "bjd_code_mismatch_count" in summary:
            self.stdout.write(
                f"  building.bjd_code 중 region에 없는 코드 수: "
                f"{summary['bjd_code_mismatch_count']}"
            )
