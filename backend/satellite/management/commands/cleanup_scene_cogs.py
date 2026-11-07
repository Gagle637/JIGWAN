from django.core.management.base import BaseCommand

from satellite.retention import (
    cleanup_old_excluded_scene_cogs,
    cleanup_old_scene_cogs,
    cleanup_superseded_scene_cogs,
)

_PATH_PREVIEW_LIMIT = 20


class Command(BaseCommand):
    help = (
        "장면별 COG 정리(ready 90일·excluded 30일·superseded 즉시). 기본은 dry-run — "
        "지울 파일 목록·개수·용량만 보여주고 아무것도 지우지 않는다. 실제로 지우려면 "
        "--execute를 준다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute", action="store_true", help="실제로 파일을 지운다(기본은 dry-run)."
        )

    def handle(self, *args, **options):
        dry_run = not options["execute"]
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "[dry-run] 실제로 지우지 않습니다. 진짜로 지우려면 --execute를 주세요.\n"
                )
            )

        sections = {
            "ready(90일, 합성 completed_at 기준)": cleanup_old_scene_cogs(dry_run=dry_run),
            "excluded(30일, collected_at 기준)": cleanup_old_excluded_scene_cogs(dry_run=dry_run),
            "superseded(즉시)": cleanup_superseded_scene_cogs(dry_run=dry_run),
        }

        total_files = 0
        total_bytes = 0
        for label, result in sections.items():
            total_files += result["files"]
            total_bytes += result["bytes"]
            self.stdout.write(
                f"{label}: 장면 {result['scenes']}건, 파일 {result['files']}개, "
                f"{result['bytes'] / 1e6:.1f}MB"
            )
            paths = result["paths"]
            for path in paths[:_PATH_PREVIEW_LIMIT]:
                self.stdout.write(f"    {path}")
            if len(paths) > _PATH_PREVIEW_LIMIT:
                self.stdout.write(f"    ... 외 {len(paths) - _PATH_PREVIEW_LIMIT}개")

        verb = "지울 예정" if dry_run else "지움"
        self.stdout.write(
            self.style.SUCCESS(f"\n합계: 파일 {total_files}개 {verb}, {total_bytes / 1e6:.1f}MB")
        )
