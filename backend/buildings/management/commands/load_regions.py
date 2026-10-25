from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from buildings.region_loading import load_regions
from core.areas import enabled_sido_codes
from core.jobs import JobSkipped, tracked_run


class Command(BaseCommand):
    help = (
        "법정구역 경계(국가공간정보포털 AL_D001_00)를 region 테이블에 upsert로 적재한다. "
        "sigungu -> bjd 순으로 각각 한 번씩 실행한 뒤(원본 파일 필요), 마지막으로 "
        "--level sido를 실행한다(파일 없이 sigungu를 union해서 만든다, path 생략). "
        "--sido를 생략하면 활성화된 지역(service_area) 전체를 돈다."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=None, help="sido는 생략한다")
        parser.add_argument("--level", required=True, choices=["sido", "sigungu", "bjd"])
        parser.add_argument(
            "--source-srid",
            type=int,
            default=None,
            help="생략하면 .prj에서 자동으로 읽는다(원본에서 못 읽으면 에러로 알려준다)",
        )
        parser.add_argument("--code-field", default=None)
        parser.add_argument("--name-field", default=None)
        parser.add_argument("--pad-to", type=int, default=None)
        parser.add_argument("--source-date", default=None, help="YYYY-MM-DD")
        parser.add_argument(
            "--sido",
            default=None,
            help="이 코드로 시작하는 행만 적재한다(생략하면 활성화된 지역 전체). sido 레벨에서는 "
            "이 코드로 시군구를 union해서 시도를 만든다.",
        )

    def handle(self, *args, **options):
        path = Path(options["path"]) if options["path"] else None
        if path is not None and not path.exists():
            raise CommandError(f"파일을 찾을 수 없습니다: {path}")
        if path is None and options["level"] != "sido":
            raise CommandError("sido가 아니면 path가 필요합니다.")

        if options["sido"]:
            sido_codes = [options["sido"]]
        else:
            sido_codes = enabled_sido_codes()
            if not sido_codes:
                raise CommandError("활성화된 지역(service_area, enabled=True)이 없습니다.")

        source_date = (
            date.fromisoformat(options["source_date"]) if options["source_date"] else None
        )

        for sido_code in sido_codes:
            self.stdout.write(f"=== 지역: {sido_code} ===")
            try:
                with tracked_run("load_regions", f"{sido_code}:{options['level']}") as run:
                    summary = load_regions(
                        path,
                        level=options["level"],
                        source_srid=options["source_srid"],
                        code_field=options["code_field"],
                        name_field=options["name_field"],
                        pad_to=options["pad_to"],
                        source_date=source_date,
                        sido_prefix=sido_code,
                    )
            except JobSkipped:
                self.stdout.write(self.style.WARNING("  다른 적재가 실행 중이라 건너뜀"))
                continue

            self.stdout.write(self.style.SUCCESS("  적재 완료"))
            self.stdout.write(f"    level: {summary['level']}")
            self.stdout.write(f"    총 건수: {summary['total_rows']}")
            self.stdout.write(f"    영향 받은 행(신규/갱신): {summary['affected_rows']}")

            if summary["level"] == "sido":
                self.stdout.write(f"    union한 시군구 수: {summary['sigungu_count']}")
                self.stdout.write(
                    f"    면적: union {summary['union_area_m2']}㎡ vs 구 면적 합 "
                    f"{summary['sum_area_m2']}㎡ (차이 {summary['area_diff_pct']}%)"
                )
                self.stdout.write(f"    union 유효성(ST_IsValid): {summary['union_is_valid']}")
            else:
                self.stdout.write(f"    읽은 좌표계(EPSG): {summary['source_srid']}")
                if summary["skipped_outside_sido"]:
                    self.stdout.write(
                        f"    --sido 범위 밖이라 건너뛴 행: {summary['skipped_outside_sido']}"
                    )
            if "bjd_code_mismatch_count" in summary:
                self.stdout.write(
                    f"    building.bjd_code 중 region에 없는 코드 수: "
                    f"{summary['bjd_code_mismatch_count']}"
                )
