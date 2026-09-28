"""Shared fixtures: a tiny synthetic data set on which the dbt project is built.

The numbers are chosen so that every expected value in test_dbt_models.py can be
checked by hand; the reasoning is noted next to each assertion.
"""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import duckdb
import pandas as pd
import pytest
import shapely

from transit_atlas import staging, warehouse
from transit_atlas.config import PROJECT_ROOT, Paths

# Cells c0 and c1 belong to municipality A, c2 to B; c3 lies in the buffer (no origin).
CELLS = ["c0", "c1", "c2", "c3"]
POIS = [
    ("osm:n1", "gp", True),
    ("osm:n2", "gp", False),
    ("osm:n3", "pharmacy", True),
    ("osm:n4", "supermarket", True),
    ("osm:n5", "primary_school", True),
    ("osm:n6", "secondary_school", True),
    ("osm:n7", "hospital", True),
    ("gtfs:s1", "rail_station", True),
]
# Public transport minutes per window and origin; missing pairs are not reachable.
PT_MINUTES = {
    "wd_am": {
        "c0": {"c0": 0, "c2": 20, "c3": 50, "osm:n1": 25, "osm:n2": 10, "osm:n3": 12,
               "osm:n4": 8, "osm:n5": 5, "osm:n6": 30, "osm:n7": 45, "gtfs:s1": 15},
        "c1": {"c1": 0, "c0": 25, "c2": 40, "osm:n1": 40, "osm:n3": 50, "osm:n4": 20,
               "osm:n5": 15, "osm:n6": 35, "osm:n7": 70, "gtfs:s1": 30},
        "c2": {"c2": 0, "c0": 20, "c1": 35, "c3": 55, "osm:n2": 70, "osm:n3": 18,
               "osm:n4": 22, "osm:n5": 9, "osm:n6": 28, "osm:n7": 25, "gtfs:s1": 20},
    },
    "wd_pm": {
        "c0": {"c0": 0, "c2": 40, "osm:n2": 15, "osm:n4": 12, "gtfs:s1": 20},
        "c1": {"c1": 0},
        "c2": {"c2": 0, "c0": 45, "osm:n7": 40},
    },
    "su_am": {
        "c0": {"c0": 0, "c2": 30, "osm:n2": 20, "osm:n4": 15, "gtfs:s1": 25},
        "c1": {"c1": 0},
        "c2": {"c2": 0, "c0": 30, "osm:n7": 30},
    },
}
CAR_MINUTES = {
    "c0": {"c0": 0, "c2": 5, "c3": 15, "osm:n1": 5, "osm:n2": 3, "osm:n3": 4, "osm:n4": 3,
           "osm:n5": 2, "osm:n6": 8, "osm:n7": 12, "gtfs:s1": 6},
    "c1": {"c1": 0, "c0": 6, "c2": 7, "c3": 18, "osm:n1": 8, "osm:n3": 9, "osm:n4": 5,
           "osm:n5": 4, "osm:n6": 10, "osm:n7": 15, "gtfs:s1": 8},
    "c2": {"c2": 0, "c0": 5, "c1": 7, "c3": 20, "osm:n2": 12, "osm:n3": 5, "osm:n4": 6,
           "osm:n5": 3, "osm:n6": 7, "osm:n7": 6, "gtfs:s1": 5},
}


def _travel_times(
    minutes: dict, dest_idx: dict[str, int], window_id: str | None = None
) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {"origin_idx": CELLS.index(origin), "dest_idx": dest_idx[dest], "minutes": value}
            for origin, targets in minutes.items()
            for dest, value in targets.items()
        ]
    )
    if window_id is not None:
        frame.insert(0, "window_id", window_id)
    return frame


def write_staging_fixture(directory: Path) -> None:
    write = staging.write_table
    cells = pd.DataFrame(
        {
            "cell_id": CELLS,
            "cell_idx": [0, 1, 2, 3],
            "x_ll": [0, 500, 1000, 5000],
            "y_ll": [0, 0, 0, 0],
            "lon": [7.0, 7.01, 7.02, 7.1],
            "lat": [49.3, 49.3, 49.3, 49.3],
            "population": [100, 300, 200, 1000],
            "is_origin": [True, True, True, False],
        }
    )
    write(cells, "cells", directory)
    weights = pd.DataFrame(
        {"cell_id": ["c0", "c1", "c2"], "ags": ["A", "A", "B"], "population": [100, 300, 200]}
    )
    write(weights, "cell_municipality", directory)
    municipalities = pd.DataFrame(
        {
            "ags": ["A", "B"],
            "name": ["Adorf", "Bstadt"],
            "bez": ["Gemeinde", "Stadt"],
            "kreis_ags": ["K", "K"],
            "kreis_name": ["Kreis", "Kreis"],
            "area_km2": [1.0, 1.0],
            "geometry_wkb": shapely.to_wkb(
                [shapely.box(0, 0, 1000, 1000), shapely.box(1000, 0, 2000, 1000)]
            ),
        }
    )
    write(municipalities, "municipalities", directory)
    pois = pd.DataFrame(POIS, columns=["poi_id", "category", "is_strict"]).assign(
        name="", lon=7.0, lat=49.3, source="fixture"
    )
    write(pois, "pois", directory)
    # Trains leave s1 in the morning and on Sunday, but not in the evening window.
    service = pd.DataFrame(
        {"poi_id": ["gtfs:s1", "gtfs:s1"], "window_id": ["wd_am", "su_am"], "departures": [12, 3]}
    )
    write(service, "station_service", directory)
    windows = pd.DataFrame(
        {
            "window_id": ["wd_am", "wd_pm", "su_am"],
            "label": ["Werktag 7–9 Uhr", "Werktag 20–22 Uhr", "Sonntag 10–12 Uhr"],
            "day_type": ["weekday", "weekday", "sunday"],
            "service_date": [dt.date(2026, 9, 29), dt.date(2026, 9, 29), dt.date(2026, 10, 4)],
            "start_time": ["07:00", "20:00", "10:00"],
            "minutes": [120, 120, 120],
            "sort_order": [0, 1, 2],
        }
    )
    write(windows, "windows", directory)
    write(pd.DataFrame({"threshold_min": [30, 45, 60]}), "thresholds", directory)
    keys = CELLS + [poi_id for poi_id, _, _ in POIS]
    dest_idx = {key: index for index, key in enumerate(keys)}
    destinations = pd.DataFrame(
        {
            "dest_idx": list(dest_idx.values()),
            "dest_kind": ["cell"] * len(CELLS) + ["poi"] * len(POIS),
            "dest_key": keys,
        }
    )
    write(destinations, "destinations", directory)
    pt = pd.concat(
        [_travel_times(PT_MINUTES[window], dest_idx, window) for window in PT_MINUTES],
        ignore_index=True,
    )
    write(pt, "travel_times_pt", directory)
    write(_travel_times(CAR_MINUTES, dest_idx), "travel_times_car", directory)
    previous = pd.DataFrame(
        {
            "snapshot_id": ["fixture_previous"],
            "ags": ["A"],
            "window_id": ["wd_am"],
            "dimension": ["gp"],
            "metric": ["median_pt_minutes"],
            "value": [50.0],
        }
    )
    write(previous, "previous_municipality_metrics", directory)


@pytest.fixture(scope="session")
def fixture_warehouse(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("atlas")
    shutil.copytree(
        PROJECT_ROOT / "dbt", root / "dbt", ignore=shutil.ignore_patterns("target", "logs")
    )
    paths = Paths(root).ensure()
    write_staging_fixture(paths.staging)
    warehouse.dbt(paths, "build")
    # dbt-duckdb keeps its database open in this process; DuckDB only allows further
    # connections to the same file with the same (default) configuration.
    con = duckdb.connect(str(paths.warehouse / warehouse.DATABASE))
    yield con
    con.close()
