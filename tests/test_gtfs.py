"""GTFS clipping, service calendar and rail station statistics on a hand-made feed."""

from __future__ import annotations

import datetime as dt
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from transit_atlas import gtfs

# T1: regional train from A (inside the box) to C (far away); T2: bus that never enters
# the box; T3: bus inside the box. Service S1 runs on Tuesdays (not on 29 Sep), S2 on Sundays.
FEED = {
    "agency.txt": (
        "agency_id,agency_name,agency_url,agency_timezone\n"
        "1,Rail,https://example.org,Europe/Berlin\n"
        "2,Bus,https://example.org,Europe/Berlin\n"
        "3,Far away,https://example.org,Europe/Berlin\n"
    ),
    "stops.txt": (
        "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station\n"
        "P,Hbf,49.30,7.00,1,\n"
        "A,Hbf Gleis 1,49.3001,7.0001,,P\n"
        "B,Markt,49.31,7.01,,\n"
        "C,Berlin,52.5,13.4,,\n"
        "D,Potsdam,52.4,13.06,,\n"
    ),
    "routes.txt": (
        "route_id,agency_id,route_short_name,route_type\n"
        "R1,1,RE 1,2\n"
        "R2,2,101,3\n"
        "R3,3,X,3\n"
    ),
    "trips.txt": "route_id,service_id,trip_id\nR1,S1,T1\nR3,S1,T2\nR2,S2,T3\n",
    "stop_times.txt": (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,07:30:00,07:30:00,A,1\n"
        "T1,12:00:00,12:00:00,C,2\n"
        "T2,08:00:00,08:00:00,D,1\n"
        "T2,08:30:00,08:30:00,C,2\n"
        "T3,10:00:00,10:00:00,A,1\n"
        "T3,10:10:00,10:10:00,B,2\n"
    ),
    "calendar.txt": (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
        "start_date,end_date\n"
        "S1,0,1,0,0,0,0,0,20260901,20261031\n"
        "S2,0,0,0,0,0,0,1,20260901,20261031\n"
    ),
    "calendar_dates.txt": "service_id,date,exception_type\nS1,20260929,2\n",
}
BBOX = (6.9, 49.2, 7.1, 49.4)


@pytest.fixture
def feed(tmp_path: Path) -> Path:
    path = tmp_path / "feed.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in FEED.items():
            archive.writestr(name, content)
    return path


def read(path: Path, name: str) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive, archive.open(f"{name}.txt") as handle:
        return pd.read_csv(handle, dtype=str, keep_default_na=False)


def test_clip_keeps_complete_trips_that_touch_the_area(feed, tmp_path):
    clipped = gtfs.clip_feed(feed, tmp_path / "clipped.zip", BBOX)
    assert sorted(read(clipped, "trips")["trip_id"]) == ["T1", "T3"]
    stop_times = read(clipped, "stop_times")
    assert sorted(stop_times.loc[stop_times["trip_id"] == "T1", "stop_id"]) == ["A", "C"]
    assert sorted(read(clipped, "stops")["stop_id"]) == ["A", "B", "C", "P"]
    assert sorted(read(clipped, "agency")["agency_id"]) == ["1", "2"]
    assert sorted(read(clipped, "routes")["route_id"]) == ["R1", "R2"]


def test_trips_per_date_applies_calendar_exceptions(feed):
    counts = gtfs.trips_per_date(feed).set_index("service_date")["trips"]
    assert counts[dt.date(2026, 9, 22)] == 2  # T1 and T2
    assert counts[dt.date(2026, 9, 27)] == 1  # T3 on Sunday
    assert dt.date(2026, 9, 29) not in counts.index  # removed by calendar_dates


def test_rail_departures_are_counted_at_the_parent_station(feed):
    windows = pd.DataFrame(
        {
            "window_id": ["wd_am", "wd_pm"],
            "service_date": [dt.date(2026, 9, 22), dt.date(2026, 9, 22)],
            "start_time": ["07:00", "20:00"],
            "minutes": [120, 120],
        }
    )
    stations, departures = gtfs.rail_station_service(feed, windows)
    assert stations["station_id"].tolist() == ["P"]
    # the arrival in C is the last stop of T1 and therefore no departure
    assert departures.to_dict("records") == [
        {"window_id": "wd_am", "station_id": "P", "departures": 1}
    ]
