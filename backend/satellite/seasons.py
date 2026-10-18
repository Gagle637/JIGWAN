"""'2026-summer' 같은 문자열을 (start_date, end_date)로 바꾼다(spec 3-3 계절 정의)."""
import calendar
from datetime import date

SEASON_MONTHS = {
    "spring": (3, 5),
    "summer": (6, 8),
    "fall": (9, 11),
}


def parse_season(season_str: str) -> tuple[date, date]:
    """'YYYY-spring|summer|fall|winter'.

    겨울은 'Y년 12월~Y+1년 2월'이고 기록 연도는 Y다(spec 3-3) — 'YYYY-winter'의 YYYY가 그 Y.
    """
    try:
        year_str, name = season_str.split("-", 1)
        year = int(year_str)
    except ValueError as exc:
        raise ValueError(f"잘못된 계절 문자열: {season_str}") from exc

    if name == "winter":
        start = date(year, 12, 1)
        end_year = year + 1
        last_day = calendar.monthrange(end_year, 2)[1]
        end = date(end_year, 2, last_day)
        return start, end

    if name not in SEASON_MONTHS:
        raise ValueError(f"알 수 없는 계절: {name!r} (spring/summer/fall/winter만 허용)")

    start_month, end_month = SEASON_MONTHS[name]
    start = date(year, start_month, 1)
    last_day = calendar.monthrange(year, end_month)[1]
    end = date(year, end_month, last_day)
    return start, end
