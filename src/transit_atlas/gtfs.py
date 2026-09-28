"""GTFS: spatial clip of the national feed, service statistics and rail stations.

All tables are read as strings with pyarrow and processed with DuckDB, which keeps the
memory footprint small and the SQL readable.
"""

from __future__ import annotations

import csv
import logging
import tempfile
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

log = logging.getLogger(__name__)

# Heavy rail (incl. S-Bahn, regional and long-distance trains); no trams or light rail.
RAIL_ROUTE_TYPES = (2, *range(100, 118))
OPTIONAL_TABLES = ("agency", "calendar", "calendar_dates", "frequencies", "feed_info",
                   "attributions", "routes", "trips")
CALENDAR_COLUMNS = ("service_id", "monday", "tuesday", "wednesday", "thursday", "friday",
                    "saturday", "sunday", "start_date", "end_date")
CALENDAR_DATES_COLUMNS = ("service_id", "date", "exception_type")
BLOCK_SIZE = 32 << 20

ACTIVE_SERVICES_SQL = """
create or replace temp table active_services as
with regular as (
    select
        service_id,
        unnest(generate_series(
            strptime(start_date, '%Y%m%d'),
            strptime(end_date, '%Y%m%d'),
            interval 1 day
        ))::date as service_date,
        [monday, tuesday, wednesday, thursday, friday, saturday, sunday] as weekdays
    from calendar
),
scheduled as (
    select service_id, service_date
    from regular
    where weekdays[isodow(service_date)] = '1'
),
added as (
    select service_id, strptime("date", '%Y%m%d')::date as service_date
    from calendar_dates
    where exception_type = '1'
),
removed as (
    select service_id, strptime("date", '%Y%m%d')::date as service_date
    from calendar_dates
    where exception_type = '2'
)
select * from (select * from scheduled union select * from added)
except
select * from removed
"""


def _members(archive: zipfile.ZipFile) -> dict[str, str]:
    """Map table names (``stops``) to archive members, tolerating sub-folders."""
    members = {}
    for name in archive.namelist():
        stem = Path(name).name
        if stem.endswith(".txt"):
            members[stem[:-4]] = name
    return members


def _header(archive: zipfile.ZipFile, member: str) -> list[str]:
    with archive.open(member) as handle:
        first = handle.readline().decode("utf-8-sig")
    return [column.strip() for column in next(csv.reader([first]))]


def _options(
    columns: Sequence[str], include: Sequence[str] | None
) -> tuple[pacsv.ReadOptions, pacsv.ConvertOptions]:
    read = pacsv.ReadOptions(block_size=BLOCK_SIZE, column_names=list(columns), skip_rows=1)
    convert = pacsv.ConvertOptions(
        column_types={column: pa.string() for column in columns},
        include_columns=list(include) if include else [],
        strings_can_be_null=False,
    )
    return read, convert


def read_table(
    archive: zipfile.ZipFile,
    members: dict[str, str],
    name: str,
    include: Sequence[str] | None = None,
) -> pa.Table | None:
    """Read a GTFS table with all columns as strings (``None`` if the file is missing)."""
    member = members.get(name)
    if member is None:
        return None
    read, convert = _options(_header(archive, member), include)
    with archive.open(member) as handle:
        return pacsv.read_csv(handle, read_options=read, convert_options=convert)


def iter_batches(
    archive: zipfile.ZipFile,
    members: dict[str, str],
    name: str,
    include: Sequence[str] | None = None,
) -> Iterator[pa.RecordBatch]:
    """Stream a (large) GTFS table from the archive in record batches."""
    member = members[name]
    read, convert = _options(_header(archive, member), include)
    with archive.open(member) as handle:
        yield from pacsv.open_csv(handle, read_options=read, convert_options=convert)


def _empty(columns: Sequence[str]) -> pa.Table:
    return pa.table({column: pa.array([], pa.string()) for column in columns})


def _register_calendar(
    con: duckdb.DuckDBPyConnection, archive: zipfile.ZipFile, members: dict[str, str]
) -> None:
    calendar = read_table(archive, members, "calendar")
    calendar_dates = read_table(archive, members, "calendar_dates")
    con.register("calendar", calendar if calendar is not None else _empty(CALENDAR_COLUMNS))
    con.register(
        "calendar_dates",
        calendar_dates if calendar_dates is not None else _empty(CALENDAR_DATES_COLUMNS),
    )
    con.execute(ACTIVE_SERVICES_SQL)


def clip_feed(source: Path, target: Path, bbox: tuple[float, float, float, float]) -> Path:
    """Write a feed with every trip that stops at least once inside ``bbox`` (lon/lat).

    Trips are kept with all of their stops, so trains that leave the area keep correct
    timings. The national stop_times table (~2 GB uncompressed) is streamed twice from the
    archive instead of being extracted to disk.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    con = duckdb.connect()
    with zipfile.ZipFile(source) as archive:
        members = _members(archive)
        stops = read_table(archive, members, "stops")
        con.register("src_stops", stops)
        inside = con.execute(
            """
            select stop_id from src_stops
            where try_cast(stop_lat as double) between ? and ?
              and try_cast(stop_lon as double) between ? and ?
            """,
            [min_lat, max_lat, min_lon, max_lon],
        ).fetch_arrow_table()
        inside_ids = inside.column("stop_id").combine_chunks()
        log.info("%d of %d stops lie inside the network area", len(inside_ids), stops.num_rows)

        touched = []
        for batch in iter_batches(archive, members, "stop_times", include=("trip_id", "stop_id")):
            mask = pc.is_in(batch.column("stop_id"), value_set=inside_ids)
            touched.append(pc.unique(pc.filter(batch.column("trip_id"), mask)))
        trip_ids = pc.unique(pa.concat_arrays(touched)) if touched else pa.array([], pa.string())
        log.info("%d trips stop inside the network area", len(trip_ids))

        kept = []
        schema = None
        for batch in iter_batches(archive, members, "stop_times"):
            schema = batch.schema
            part = batch.filter(pc.is_in(batch.column("trip_id"), value_set=trip_ids))
            if part.num_rows:
                kept.append(part)
        stop_times = pa.Table.from_batches(kept, schema=schema)
        tables = {name: read_table(archive, members, name) for name in OPTIONAL_TABLES}

    con.register("keep_trips", pa.table({"trip_id": trip_ids}))
    con.register("src_stop_times", stop_times)
    for name, table in tables.items():
        if table is not None:
            con.register(f"src_{name}", table)
    _write_subset(con, tables, target)
    return target


def _write_subset(
    con: duckdb.DuckDBPyConnection, tables: dict[str, pa.Table | None], target: Path
) -> None:
    routes_have_agency = "agency_id" in tables["routes"].column_names
    statements = {
        "trips": "select * from src_trips where trip_id in (select trip_id from keep_trips)",
        "stop_times": "select * from src_stop_times",
        "routes": "select * from src_routes where route_id in (select route_id from out_trips)",
        "agency": (
            "select * from src_agency where agency_id in (select agency_id from out_routes)"
            if routes_have_agency
            else "select * from src_agency"
        ),
        "stops": """
            select * from src_stops
            where stop_id in (select stop_id from out_stop_times)
               or stop_id in (
                   select parent_station from src_stops
                   where stop_id in (select stop_id from out_stop_times)
               )
        """,
        "calendar": "select * from src_calendar where service_id in "
                    "(select service_id from out_trips)",
        "calendar_dates": "select * from src_calendar_dates where service_id in "
                          "(select service_id from out_trips)",
        "frequencies": "select * from src_frequencies where trip_id in "
                       "(select trip_id from out_trips)",
        "feed_info": "select * from src_feed_info",
        "attributions": "select * from src_attributions",
    }
    required = {"trips", "stop_times", "routes", "agency", "stops"}
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        written = []
        for name, sql in statements.items():
            if name not in required and tables.get(name) is None:
                continue
            con.execute(f"create or replace temp table out_{name} as {sql}")
            path = Path(tmp) / f"{name}.txt"
            con.execute(f"copy out_{name} to '{path}' (header, delimiter ',')")
            count = con.execute(f"select count(*) from out_{name}").fetchone()[0]
            log.info("GTFS %s: %d rows", name, count)
            written.append(path)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in written:
                archive.write(path, arcname=path.name)


def trips_per_date(feed: Path) -> pd.DataFrame:
    """Number of scheduled trips for every service day of the feed."""
    con = duckdb.connect()
    with zipfile.ZipFile(feed) as archive:
        members = _members(archive)
        _register_calendar(con, archive, members)
        con.register("trips", read_table(archive, members, "trips", ("trip_id", "service_id")))
        return con.execute(
            """
            select a.service_date, count(*) as trips
            from active_services as a
            inner join trips as t on t.service_id = a.service_id
            group by a.service_date
            order by a.service_date
            """
        ).df(date_as_object=True)


def _seconds(column: str) -> str:
    """SQL expression: GTFS time (may exceed 24:00:00) to seconds after midnight."""
    parts = [f"try_cast(split_part({column}, ':', {index}) as integer)" for index in (1, 2, 3)]
    return f"({parts[0]} * 3600 + {parts[1]} * 60 + {parts[2]})"


def rail_station_service(feed: Path, windows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rail stations and the number of train departures there in every analysis window.

    ``windows`` needs ``window_id``, ``service_date``, ``start_time`` (HH:MM) and
    ``minutes``. The last stop of a trip is not a departure.
    """
    rail_types = ", ".join(str(value) for value in RAIL_ROUTE_TYPES)
    con = duckdb.connect()
    with zipfile.ZipFile(feed) as archive:
        members = _members(archive)
        _register_calendar(con, archive, members)
        for name in ("stops", "routes", "trips", "stop_times"):
            con.register(name, read_table(archive, members, name))
        columns = {row[0] for row in con.execute("describe stop_times").fetchall()}
        pickup = "st.pickup_type" if "pickup_type" in columns else "''"
        frame = windows[["window_id", "service_date", "start_time", "minutes"]].assign(
            service_date=windows["service_date"].astype(str)
        )
        con.register("analysis_windows", frame)
        con.execute(
            f"""
            create or replace temp table station_departures as
            with rail_trips as (
                select t.trip_id, t.service_id
                from trips as t
                inner join routes as r on r.route_id = t.route_id
                where try_cast(r.route_type as integer) in ({rail_types})
            ),
            calls as (
                select
                    st.trip_id,
                    st.stop_id,
                    {_seconds("st.departure_time")} as departure_s,
                    {pickup} as pickup_type,
                    row_number() over (
                        partition by st.trip_id
                        order by try_cast(st.stop_sequence as integer) desc
                    ) as calls_from_end
                from stop_times as st
                inner join rail_trips as rt on rt.trip_id = st.trip_id
            ),
            analysis as (
                select
                    window_id,
                    cast(service_date as date) as service_date,
                    try_cast(split_part(start_time, ':', 1) as integer) * 3600
                        + try_cast(split_part(start_time, ':', 2) as integer) * 60 as start_s,
                    minutes * 60 as length_s
                from analysis_windows
            ),
            stations as (
                select stop_id, coalesce(nullif(parent_station, ''), stop_id) as station_id
                from stops
            )
            select w.window_id, s.station_id, count(*) as departures
            from calls as c
            inner join rail_trips as rt on rt.trip_id = c.trip_id
            inner join active_services as a on a.service_id = rt.service_id
            inner join analysis as w on w.service_date = a.service_date
            inner join stations as s on s.stop_id = c.stop_id
            where c.calls_from_end > 1
              and c.pickup_type <> '1'
              and c.departure_s >= w.start_s
              and c.departure_s < w.start_s + w.length_s
            group by w.window_id, s.station_id
            """
        )
        departures = con.execute(
            """
            select window_id, station_id, cast(departures as integer) as departures
            from station_departures
            order by station_id, window_id
            """
        ).df()
        stations = con.execute(
            """
            select
                stop_id as station_id,
                stop_name as name,
                try_cast(stop_lon as double) as lon,
                try_cast(stop_lat as double) as lat
            from stops
            where stop_id in (select station_id from station_departures)
              and try_cast(stop_lon as double) is not null
              and try_cast(stop_lat as double) is not null
            order by stop_id
            """
        ).df()
    log.info("%d rail stations with departures in the analysis windows", len(stations))
    return stations, departures
