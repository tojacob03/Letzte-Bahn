"""Choose representative service days inside the validity period of a GTFS feed."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

from .config import CalendarSettings

ONE_DAY = dt.timedelta(days=1)

# Public holidays that exist only in some federal states (ISO 3166-2:DE codes).
STATE_HOLIDAYS: dict[str, frozenset[str]] = {
    "epiphany": frozenset({"BW", "BY", "ST"}),
    "womens_day": frozenset({"BE", "MV"}),
    "corpus_christi": frozenset({"BW", "BY", "HE", "NW", "RP", "SL"}),
    "assumption": frozenset({"SL"}),
    "childrens_day": frozenset({"TH"}),
    "reformation": frozenset({"BB", "HB", "HH", "MV", "NI", "SN", "ST", "SH", "TH"}),
    "all_saints": frozenset({"BW", "BY", "NW", "RP", "SL"}),
    "repentance": frozenset({"SN"}),
}
# Days with a special timetable although they are not public holidays.
SPECIAL_DAYS = ((12, 24), (12, 31))


@dataclass(frozen=True)
class ServiceDates:
    weekday: dt.date
    sunday: dt.date
    notes: tuple[str, ...] = ()

    def for_day(self, day_type: str) -> dt.date:
        if day_type == "weekday":
            return self.weekday
        if day_type == "sunday":
            return self.sunday
        raise ValueError(f"Unknown day type: {day_type!r}")


def easter_sunday(year: int) -> dt.date:
    """Gregorian Easter Sunday (Meeus/Jones/Butcher algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    shift = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * shift) // 451
    month, day = divmod(h + shift - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def _repentance_day(year: int) -> dt.date:
    """Buss- und Bettag: the Wednesday before 23 November."""
    day = dt.date(year, 11, 22)
    while day.weekday() != 2:
        day -= ONE_DAY
    return day


def public_holidays(year: int, state: str) -> dict[dt.date, str]:
    """Public holidays in ``state``, plus Easter and Whit Sunday (special Sunday service)."""
    easter = easter_sunday(year)
    holidays = {
        dt.date(year, 1, 1): "Neujahr",
        easter - 2 * ONE_DAY: "Karfreitag",
        easter: "Ostersonntag",
        easter + ONE_DAY: "Ostermontag",
        dt.date(year, 5, 1): "Tag der Arbeit",
        easter + 39 * ONE_DAY: "Christi Himmelfahrt",
        easter + 49 * ONE_DAY: "Pfingstsonntag",
        easter + 50 * ONE_DAY: "Pfingstmontag",
        dt.date(year, 10, 3): "Tag der Deutschen Einheit",
        dt.date(year, 12, 25): "1. Weihnachtstag",
        dt.date(year, 12, 26): "2. Weihnachtstag",
    }
    optional = {
        "epiphany": (dt.date(year, 1, 6), "Heilige Drei Könige"),
        "womens_day": (dt.date(year, 3, 8), "Internationaler Frauentag"),
        "corpus_christi": (easter + 60 * ONE_DAY, "Fronleichnam"),
        "assumption": (dt.date(year, 8, 15), "Mariä Himmelfahrt"),
        "childrens_day": (dt.date(year, 9, 20), "Weltkindertag"),
        "reformation": (dt.date(year, 10, 31), "Reformationstag"),
        "all_saints": (dt.date(year, 11, 1), "Allerheiligen"),
        "repentance": (_repentance_day(year), "Buss- und Bettag"),
    }
    for key, (day, name) in optional.items():
        if state in STATE_HOLIDAYS[key]:
            holidays[day] = name
    return holidays


def is_school_holiday(day: dt.date, ranges: tuple[tuple[dt.date, dt.date], ...]) -> bool:
    return any(start <= day <= end for start, end in ranges)


def _excluded(day: dt.date, settings: CalendarSettings, *, school: bool) -> bool:
    if day in public_holidays(day.year, settings.holiday_state):
        return True
    if (day.month, day.day) in SPECIAL_DAYS:
        return True
    return school and is_school_holiday(day, settings.school_holidays)


def _search(
    first: dt.date,
    last: dt.date,
    predicate: Callable[[dt.date], bool],
    *,
    backwards: bool = False,
) -> dt.date | None:
    span = (last - first).days
    if span < 0:
        return None
    offsets = range(span, -1, -1) if backwards else range(span + 1)
    for offset in offsets:
        day = first + offset * ONE_DAY
        if predicate(day):
            return day
    return None


def pick_service_dates(
    feed_start: dt.date,
    feed_end: dt.date,
    settings: CalendarSettings,
    service_ok: Callable[[dt.date], bool] | None = None,
) -> ServiceDates:
    """Pick a regular school weekday and a regular Sunday inside the feed period.

    Rules: skip the first days of the feed; if the feed already covers a timetable change,
    use days after it; avoid public holidays, 24 and 31 December and school holidays; and,
    via ``service_ok``, avoid days with unusually little service.
    """
    ok = service_ok or (lambda _day: True)
    notes: list[str] = []
    earliest = feed_start + settings.min_days_after_feed_start * ONE_DAY
    changes = [day for day in settings.timetable_changes if earliest < day <= feed_end]
    if changes:
        earliest = max(changes)
        notes.append(f"Feed covers the timetable change of {earliest.isoformat()}; "
                     "the new timetable is analysed.")

    def weekday_ok(day: dt.date, *, school: bool = True) -> bool:
        return (
            day.weekday() == settings.weekday
            and not _excluded(day, settings, school=school)
            and ok(day)
        )

    def sunday_ok(day: dt.date) -> bool:
        return day.weekday() == 6 and not _excluded(day, settings, school=False) and ok(day)

    weekday = settings.weekday_date or _search(earliest, feed_end, weekday_ok)
    if weekday is None:
        weekday = _search(earliest, feed_end, lambda day: weekday_ok(day, school=False))
        if weekday is not None:
            notes.append("No regular school day in the feed period; a holiday week is used.")
    if weekday is None:
        raise ValueError(f"No suitable weekday between {earliest} and {feed_end}")

    sunday = settings.sunday_date
    if sunday is None:
        sunday = _search(weekday + ONE_DAY, feed_end, sunday_ok) or _search(
            earliest, weekday, sunday_ok, backwards=True
        )
    if sunday is None:
        raise ValueError(f"No suitable Sunday between {earliest} and {feed_end}")

    for label, day in (("weekday", weekday), ("sunday", sunday)):
        if not feed_start <= day <= feed_end:
            raise ValueError(f"{label} {day} lies outside the feed period {feed_start}..{feed_end}")
    return ServiceDates(weekday=weekday, sunday=sunday, notes=tuple(notes))
