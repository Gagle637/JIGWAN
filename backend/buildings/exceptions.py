from rest_framework.exceptions import APIException


class BuildingNotFound(APIException):
    status_code = 404
    default_detail = "건물을 찾을 수 없습니다."
    default_code = "building_not_found"
    error_code = "BUILDING_NOT_FOUND"


class NoBuildingAtPoint(APIException):
    status_code = 404
    default_detail = "클릭한 좌표에 건물이 없습니다."
    default_code = "no_building_at_point"
    error_code = "NO_BUILDING_AT_POINT"
