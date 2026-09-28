"""Run configuration: loading, inheritance via ``extends`` and validation."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DAY_TYPES = ("weekday", "sunday")
# The analysis (findings, web app) relies on these three windows.
REQUIRED_WINDOWS = ("wd_am", "wd_pm", "su_am")


class ConfigError(ValueError):
    """Raised when a configuration file is incomplete or inconsistent."""


@dataclass(frozen=True)
class Source:
    url: str
    filename: str


@dataclass(frozen=True)
class TimeWindow:
    id: str
    label: str
    day: str
    start: dt.time
    minutes: int


@dataclass(frozen=True)
class CalendarSettings:
    holiday_state: str
    school_holidays: tuple[tuple[dt.date, dt.date], ...]
    weekday: int
    min_days_after_feed_start: int
    timetable_changes: tuple[dt.date, ...] = ()
    weekday_date: dt.date | None = None
    sunday_date: dt.date | None = None


@dataclass(frozen=True)
class RoutingSettings:
    walk_speed_kmh: float
    max_walk_minutes: int
    max_trip_minutes: int
    max_rides: int
    population_thresholds: tuple[int, ...]
    threads: int
    origin_chunk_size: int
    car: bool = True


@dataclass(frozen=True)
class Config:
    path: Path
    region_id: str
    region_name: str
    ags_prefix: str
    buffer_km: float
    network_margin_km: float
    cell_size_m: int
    gtfs: Source
    osm: tuple[Source, ...]
    census: Source
    boundaries: Source
    calendar: CalendarSettings
    windows: tuple[TimeWindow, ...]
    routing: RoutingSettings
    raw: dict[str, Any]

    @property
    def fingerprint(self) -> str:
        """Short hash of the effective configuration, stored with every snapshot."""
        blob = json.dumps(self.raw, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()[:12]

    def window(self, window_id: str) -> TimeWindow:
        for window in self.windows:
            if window.id == window_id:
                return window
        raise KeyError(window_id)


@dataclass(frozen=True)
class Paths:
    """Directory layout of a pipeline run."""

    root: Path = PROJECT_ROOT

    @property
    def raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def interim(self) -> Path:
        return self.root / "data" / "interim"

    @property
    def staging(self) -> Path:
        return self.root / "data" / "staging"

    @property
    def warehouse(self) -> Path:
        return self.root / "data" / "warehouse"

    @property
    def published(self) -> Path:
        return self.root / "data" / "published"

    @property
    def web_data(self) -> Path:
        return self.root / "web" / "data"

    def ensure(self) -> Paths:
        directories = (
            self.raw,
            self.interim,
            self.staging,
            self.warehouse,
            self.published,
            self.web_data,
        )
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        return self


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge ``override`` into ``base``; nested mappings merge, everything else replaces."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parent = data.pop("extends", None)
    if parent is None:
        return data
    return deep_merge(_read_yaml(path.parent / parent), data)


def parse_time(value: Any) -> dt.time:
    """Parse ``"07:00"``; YAML 1.1 reads an unquoted 07:00 as the integer 420."""
    if isinstance(value, int):
        return dt.time(value // 60, value % 60)
    return dt.time.fromisoformat(str(value))


def parse_date(value: Any) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def _optional_date(value: Any) -> dt.date | None:
    return None if value is None else parse_date(value)


def _source(item: dict[str, Any]) -> Source:
    return Source(url=str(item["url"]), filename=str(item["filename"]))


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    raw = _read_yaml(path)
    try:
        config = _parse(raw, path)
    except (KeyError, TypeError, ValueError) as error:
        raise ConfigError(f"{path}: missing or invalid setting: {error}") from error
    _validate(config)
    return config


def _parse(raw: dict[str, Any], path: Path) -> Config:
    region = raw["region"]
    sources = raw["sources"]
    calendar = raw["calendar"]
    routing = raw["routing"]
    return Config(
        path=path,
        region_id=str(region["id"]),
        region_name=str(region["name"]),
        ags_prefix=str(region["ags_prefix"]),
        buffer_km=float(region.get("buffer_km", 20)),
        network_margin_km=float(region.get("network_margin_km", 5)),
        cell_size_m=int(raw["grid"]["cell_size_m"]),
        gtfs=_source(sources["gtfs"]),
        osm=tuple(_source(item) for item in sources["osm"]),
        census=_source(sources["census"]),
        boundaries=_source(sources["boundaries"]),
        calendar=CalendarSettings(
            holiday_state=str(calendar["holiday_state"]),
            school_holidays=tuple(
                (parse_date(start), parse_date(end))
                for start, end in calendar.get("school_holidays", [])
            ),
            weekday=int(calendar.get("weekday", 1)),
            min_days_after_feed_start=int(calendar.get("min_days_after_feed_start", 2)),
            timetable_changes=tuple(
                parse_date(day) for day in calendar.get("timetable_changes", [])
            ),
            weekday_date=_optional_date(calendar.get("weekday_date")),
            sunday_date=_optional_date(calendar.get("sunday_date")),
        ),
        windows=tuple(
            TimeWindow(
                id=str(window["id"]),
                label=str(window["label"]),
                day=str(window["day"]),
                start=parse_time(window["start"]),
                minutes=int(window["minutes"]),
            )
            for window in raw["windows"]
        ),
        routing=RoutingSettings(
            walk_speed_kmh=float(routing["walk_speed_kmh"]),
            max_walk_minutes=int(routing["max_walk_minutes"]),
            max_trip_minutes=int(routing["max_trip_minutes"]),
            max_rides=int(routing.get("max_rides", 8)),
            population_thresholds=tuple(int(value) for value in routing["population_thresholds"]),
            threads=int(routing.get("threads", 4)),
            origin_chunk_size=int(routing.get("origin_chunk_size", 400)),
            car=bool(routing.get("car", True)),
        ),
        raw=raw,
    )


def _validate(config: Config) -> None:
    problems: list[str] = []
    if not config.ags_prefix.isdigit() or not 2 <= len(config.ags_prefix) <= 8:
        problems.append("region.ags_prefix must consist of 2 to 8 digits")
    if config.cell_size_m < 100 or config.cell_size_m % 100:
        problems.append("grid.cell_size_m must be a multiple of the 100 m census grid")
    ids = [window.id for window in config.windows]
    if len(set(ids)) != len(ids):
        problems.append("window ids must be unique")
    missing = [window_id for window_id in REQUIRED_WINDOWS if window_id not in ids]
    if missing:
        problems.append(f"missing time windows: {', '.join(missing)}")
    for window in config.windows:
        if window.day not in DAY_TYPES:
            problems.append(f"window {window.id}: day must be one of {DAY_TYPES}")
        if window.minutes < 5:
            problems.append(f"window {window.id}: needs at least 5 minutes")
    thresholds = list(config.routing.population_thresholds)
    if not thresholds or thresholds != sorted(set(thresholds)):
        problems.append("routing.population_thresholds must be ascending and unique")
    elif thresholds[-1] > config.routing.max_trip_minutes:
        problems.append("population thresholds cannot exceed routing.max_trip_minutes")
    if not 0 <= config.calendar.weekday <= 4:
        problems.append("calendar.weekday must be between 0 (Monday) and 4 (Friday)")
    for start, end in config.calendar.school_holidays:
        if end < start:
            problems.append(f"school holiday {start}..{end} ends before it starts")
    if config.routing.threads < 1 or config.routing.origin_chunk_size < 1:
        problems.append("routing.threads and routing.origin_chunk_size must be positive")
    if problems:
        raise ConfigError(f"{config.path}: " + "; ".join(problems))
