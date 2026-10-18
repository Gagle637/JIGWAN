from datetime import date

import pytest

from satellite.seasons import parse_season


def test_spring():
    assert parse_season("2026-spring") == (date(2026, 3, 1), date(2026, 5, 31))


def test_summer():
    assert parse_season("2026-summer") == (date(2026, 6, 1), date(2026, 8, 31))


def test_fall():
    assert parse_season("2026-fall") == (date(2026, 9, 1), date(2026, 11, 30))


def test_winter_spans_into_next_year():
    # spec 3-3: 겨울 = Y년 12월~Y+1년 2월, 기록 연도는 Y
    assert parse_season("2026-winter") == (date(2026, 12, 1), date(2027, 2, 28))


def test_winter_leap_year_end():
    assert parse_season("2027-winter") == (date(2027, 12, 1), date(2028, 2, 29))  # 2028은 윤년


def test_unknown_season_raises():
    with pytest.raises(ValueError):
        parse_season("2026-monsoon")


def test_malformed_string_raises():
    with pytest.raises(ValueError):
        parse_season("not-a-season-string-at-all")
