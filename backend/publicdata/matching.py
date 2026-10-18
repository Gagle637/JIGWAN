"""거래-건물 매칭(spec 8-1·8-7)과, insight.trades에 쓸 건물의 주택 유형 판정."""
from django.db.models import Count

from .models import Trade
from .pnu import build_pnu, lookup_bjd_code, parse_jibun


def build_apt_seq_cache() -> dict[str, str]:
    """DB에 이미 있는 아파트 매매 기록에서 apt_seq -> pnu 캐시를 만든다(이전 실행 포함, spec 8-7)."""
    rows = (
        Trade.objects.filter(
            house_type=Trade.HouseType.APARTMENT,
            deal_type=Trade.DealType.SALE,
            pnu__isnull=False,
        )
        .exclude(apt_seq__isnull=True)
        .exclude(apt_seq="")
        .values_list("apt_seq", "pnu")
    )
    return dict(rows)


def match_trade(normalized: dict, apt_seq_cache: dict[str, str]) -> tuple[str | None, str | None]:
    """(pnu, failure_reason). detached는 (None, None) — 애초에 매칭 대상이 아님(실패 아님, spec 8-1)."""
    house_type = normalized["house_type"]

    if house_type == Trade.HouseType.DETACHED:
        return None, None

    if normalized.get("pnu_hint"):
        return normalized["pnu_hint"], None

    if house_type == Trade.HouseType.APARTMENT:
        apt_seq = normalized.get("apt_seq")
        if apt_seq and apt_seq in apt_seq_cache:
            return apt_seq_cache[apt_seq], None

    jibun_parsed = parse_jibun(normalized.get("jibun_raw"))
    if jibun_parsed is None:
        return None, "jibun_parse_failed"

    bjd_code = lookup_bjd_code(normalized["sgg_code"], normalized.get("bjd_name"))
    if bjd_code is None:
        return None, "region_not_found"

    is_san, bonbun, bubun = jibun_parsed
    return build_pnu(bjd_code, is_san, bonbun, bubun), None


def determine_house_types_for_building(building) -> tuple[str | None, list[str]]:
    """(대표 house_type 또는 None, 반경 집계에 쓸 house_type 목록).

    ① building.pnu로 매칭된(match_failure_reason이 없는) trade 중 다수결.
    ② 없으면 building.use_name 대분류로 추정 — 실제 건물 파일엔 '공동주택'·'단독주택'·'업무시설' 같은
       대분류만 있고 '아파트'·'연립'·'오피스텔' 글자는 없음을 확인했다.
    """
    if building.pnu:
        majority = (
            Trade.objects.filter(pnu=building.pnu, match_failure_reason__isnull=True)
            .values("house_type")
            .annotate(n=Count("id"))
            .order_by("-n")
            .first()
        )
        if majority:
            house_type = majority["house_type"]
            return house_type, [house_type]

    use_name = building.use_name or ""
    if "공동주택" in use_name:
        # 대분류 추정이라 아파트·연립다세대가 섞여 있을 수 있어 반경 집계는 둘 다 본다.
        return Trade.HouseType.APARTMENT, [Trade.HouseType.APARTMENT, Trade.HouseType.ROW_HOUSE]
    if "업무시설" in use_name:
        return Trade.HouseType.OFFICETEL, [Trade.HouseType.OFFICETEL]
    if "단독주택" in use_name:
        return Trade.HouseType.DETACHED, [Trade.HouseType.DETACHED]
    return None, []
