"""PNU 조립과 법정동 코드 조회(spec 8-1·8-7).

PNU(19자리) = 법정동코드(10) + 산여부(1, 1=일반·2=산) + 본번(4) + 부번(4).
"""
import re

from buildings.models import Region

_DATE_LIKE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_JIBUN_RE = re.compile(r"^(\d{1,4})(?:-(\d{1,4}))?$")


def parse_jibun(raw: str | None) -> tuple[bool, int, int] | None:
    """'202-3' -> (False,202,3), '산12' -> (True,12,0), '산12-3' -> (True,12,3).

    날짜로 둔갑한 값('1952-5' 같은 지번이 엑셀 등에서 날짜로 바뀌는 사례, spec 8-7)은
    매칭 실패로 보고 None을 반환한다.
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if _DATE_LIKE_RE.match(text):
        return None

    is_san = text.startswith("산")
    if is_san:
        text = text[1:].strip()

    match = _JIBUN_RE.match(text)
    if not match:
        return None

    bonbun = int(match.group(1))
    bubun = int(match.group(2)) if match.group(2) else 0
    return is_san, bonbun, bubun


def build_pnu(bjd_code_10: str, is_san: bool, bonbun: int, bubun: int) -> str:
    return f"{bjd_code_10}{2 if is_san else 1}{bonbun:04d}{bubun:04d}"


def build_pnu_from_apt_sale(sgg_cd: str, umd_cd: str, land_cd: str, bonbun: str, bubun: str) -> str:
    """아파트 매매(상세)는 sggCd+umdCd+landCd+bonbun+bubun으로 PNU를 바로 조립할 수 있다(spec 8-7)."""
    return f"{sgg_cd}{umd_cd}{land_cd}{int(bonbun):04d}{int(bubun):04d}"


def lookup_bjd_code(sgg_code: str, dong_name: str) -> str | None:
    """region(level=bjd)에서 같은 시군구(region_code가 sgg_code로 시작) 안의 이름으로 찾는다."""
    if not dong_name:
        return None
    region = Region.objects.filter(
        level="bjd", region_code__startswith=sgg_code, name=dong_name
    ).first()
    return region.region_code if region else None
