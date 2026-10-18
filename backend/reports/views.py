from django.conf import settings
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from buildings.exceptions import BuildingNotFound
from buildings.insight import ALLOWED_RADIUS_M
from buildings.models import Building
from demo.snapshots import apply_demo_overlay, get_demo_snapshot

from .models import Report
from .prompts import version_for
from .quota import check_quota
from .snapshot import build_demo_report_input, build_report_input
from .tasks import generate_report


def _get_building(building_id) -> Building:
    building = Building.objects.filter(is_active=True, pk=building_id).first()
    if building is None:
        raise BuildingNotFound()
    return building


def _get_owned_report(report_id, user) -> Report:
    report = Report.objects.filter(pk=report_id).first()
    if report is None:
        raise NotFound("리포트를 찾을 수 없습니다.")
    if report.user_id != user.id:
        raise PermissionDenied("다른 사용자의 리포트입니다.")
    return report


def _serialize_list_item(report: Report) -> dict:
    return {
        "id": report.id,
        "report_type": report.report_type,
        "user_prompt": report.user_prompt,
        "status": report.status,
        "created_at": report.created_at.isoformat(),
    }


def _serialize_detail(report: Report) -> dict:
    body = {
        "report_id": report.id,
        "building_id": report.building_id,
        "radius_m": report.radius_m,
        "report_type": report.report_type,
        "status": report.status,
        "created_at": report.created_at.isoformat(),
    }
    if report.status == Report.Status.READY:
        as_of = report.input_snapshot.get("as_of") or {}
        body["model"] = report.model
        body["template_version"] = report.template_version
        body["prompt_version"] = report.prompt_version
        body["data_as_of"] = {
            "satellite_period": as_of.get("satellite_period"),
            "trade_synced_at": as_of.get("trade_synced_at"),
        }
        body["result"] = report.payload
    elif report.status == Report.Status.FAILED:
        body["error"] = (report.payload or {}).get("error")
    return body


class BuildingReportsView(APIView):
    """GET·POST /api/buildings/{id}/reports (spec 6-4)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, building_id):
        building = _get_building(building_id)
        reports = Report.objects.filter(user=request.user, building=building).order_by(
            "-created_at"
        )
        return Response([_serialize_list_item(r) for r in reports])

    def post(self, request, building_id):
        building = _get_building(building_id)

        radius_m = request.data.get("radius_m")
        if radius_m not in ALLOWED_RADIUS_M:
            raise ValidationError("radius_m은 500 또는 1000만 허용합니다.")

        report_type = request.data.get("report_type")
        if report_type not in (Report.ReportType.TEMPLATE, Report.ReportType.CUSTOM):
            raise ValidationError("report_type은 template 또는 custom이어야 합니다.")

        prompt = request.data.get("prompt")
        if report_type == Report.ReportType.CUSTOM:
            if not prompt or not prompt.strip():
                raise ValidationError("custom 리포트는 prompt가 필요합니다.")
            if len(prompt) > 500:
                raise ValidationError("prompt는 500자 이내여야 합니다.")
        else:
            prompt = None

        check_quota(request.user)

        # 13단계: DEMO_MODE고 이 건물이 데모 스냅샷에 있으면, GPU·외부 API 없이 고정
        # 리포트를 즉시 ready로 저장한다("서버가 꺼져 있어도 시연할 수 있게").
        demo = get_demo_snapshot(building.pnu) if settings.DEMO_MODE else None
        if demo is not None:
            demo_report = demo["reports"].get(report_type)
            if demo_report is None:
                raise ValidationError(f"이 데모 건물에는 {report_type} 리포트 예시가 없습니다.")
            demo_insight = apply_demo_overlay(demo["insight"], building)
            report = Report.objects.create(
                user=request.user,
                building=building,
                radius_m=radius_m,
                report_type=report_type,
                template_version="demo" if report_type == Report.ReportType.TEMPLATE else None,
                prompt_version="demo" if report_type == Report.ReportType.CUSTOM else None,
                user_prompt=prompt,
                input_snapshot=build_demo_report_input(demo_insight),
                model="demo",
                payload=demo_report,
                status=Report.Status.READY,
            )
            return Response({"report_id": report.id, "status": report.status}, status=202)

        input_snapshot = build_report_input(building, radius_m)
        version = version_for(report_type)
        report = Report.objects.create(
            user=request.user,
            building=building,
            radius_m=radius_m,
            report_type=report_type,
            template_version=version if report_type == Report.ReportType.TEMPLATE else None,
            prompt_version=version if report_type == Report.ReportType.CUSTOM else None,
            user_prompt=prompt,
            input_snapshot=input_snapshot,
            status=Report.Status.GENERATING,
        )
        generate_report.delay(report.id)

        return Response({"report_id": report.id, "status": report.status}, status=202)


class ReportDetailView(APIView):
    """GET·DELETE /api/reports/{report_id} (spec 6-4)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, report_id):
        report = _get_owned_report(report_id, request.user)
        return Response(_serialize_detail(report))

    def delete(self, request, report_id):
        report = _get_owned_report(report_id, request.user)
        report.delete()
        return Response(status=204)
