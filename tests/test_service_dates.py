from __future__ import annotations

import datetime as dt

import pytest

from transit_atlas.config import CalendarSettings
from transit_atlas.service_dates import easter_sunday, pick_service_dates, public_holidays

D = dt.date


def settings(**overrides) -> CalendarSettings:
    values = {
        "holiday_state": "SL",
        "school_holidays": ((D(2026, 10, 5), D(2026, 10, 16)),),
        "weekday": 1,
        "min_days_after_feed_start": 2,
        "timetable_changes": (D(2026, 12, 13),),
    }
    values.update(overrides)
    return CalendarSettings(**values)


@pytest.mark.parametrize(
    ("year", "expected"),
    [(2024, D(2024, 3, 31)), (2025, D(2025, 4, 20)), (2026, D(2026, 4, 5)), (2027, D(2027, 3, 28))],
)
def test_easter_sunday(year, expected):
    assert easter_sunday(year) == expected


def test_state_specific_holidays():
    saarland = public_holidays(2026, "SL")
    assert D(2026, 8, 15) in saarland  # Maria Himmelfahrt
    assert D(2026, 6, 4) in saarland  # Fronleichnam = Easter + 60 days
    assert D(2026, 10, 31) not in saarland
    assert D(2026, 10, 31) in public_holidays(2026, "SN")
    assert D(2026, 11, 18) in public_holidays(2026, "SN")  # Buss- und Bettag


def test_first_school_tuesday_and_following_sunday():
    dates = pick_service_dates(D(2026, 9, 26), D(2026, 10, 26), settings())
    assert (dates.weekday, dates.sunday) == (D(2026, 9, 29), D(2026, 10, 4))


def test_school_holidays_are_skipped():
    dates = pick_service_dates(D(2026, 10, 3), D(2026, 11, 2), settings())
    assert dates.weekday == D(2026, 10, 20)
    assert dates.sunday == D(2026, 10, 25)


def test_new_timetable_is_preferred_once_the_feed_covers_it():
    dates = pick_service_dates(D(2026, 11, 16), D(2026, 12, 16), settings())
    assert dates.weekday == D(2026, 12, 15)
    assert dates.sunday == D(2026, 12, 13)
    assert dates.notes


def test_days_with_unusual_service_are_rejected():
    dates = pick_service_dates(
        D(2026, 9, 26), D(2026, 10, 26), settings(), service_ok=lambda day: day != D(2026, 9, 29)
    )
    assert dates.weekday == D(2026, 10, 20)


def test_fixed_dates_must_lie_in_the_feed():
    with pytest.raises(ValueError, match="outside the feed period"):
        pick_service_dates(
            D(2026, 9, 26), D(2026, 10, 26), settings(weekday_date=D(2026, 11, 3))
        )
