"""Staging tables: the typed contract between the Python stages and the dbt project.

Every table is written to ``data/staging/<name>.parquet`` with the schema below; the dbt
sources in ``dbt/models/staging/_sources.yml`` read exactly these files.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_S = pa.string()

SCHEMAS: dict[str, pa.Schema] = {
    "cells": pa.schema(
        [
            ("cell_id", _S),
            ("cell_idx", pa.int32()),
            ("x_ll", pa.int64()),
            ("y_ll", pa.int64()),
            ("lon", pa.float64()),
            ("lat", pa.float64()),
            ("population", pa.int64()),
            ("is_origin", pa.bool_()),
        ]
    ),
    "cell_municipality": pa.schema([("cell_id", _S), ("ags", _S), ("population", pa.int64())]),
    "municipalities": pa.schema(
        [
            ("ags", _S),
            ("name", _S),
            ("bez", _S),
            ("kreis_ags", _S),
            ("kreis_name", _S),
            ("area_km2", pa.float64()),
            ("geometry_wkb", pa.binary()),
        ]
    ),
    "pois": pa.schema(
        [
            ("poi_id", _S),
            ("category", _S),
            ("is_strict", pa.bool_()),
            ("name", _S),
            ("lon", pa.float64()),
            ("lat", pa.float64()),
            ("source", _S),
        ]
    ),
    "station_service": pa.schema(
        [("poi_id", _S), ("window_id", _S), ("departures", pa.int32())]
    ),
    "windows": pa.schema(
        [
            ("window_id", _S),
            ("label", _S),
            ("day_type", _S),
            ("service_date", pa.date32()),
            ("start_time", _S),
            ("minutes", pa.int32()),
            ("sort_order", pa.int32()),
        ]
    ),
    "thresholds": pa.schema([("threshold_min", pa.int32())]),
    "destinations": pa.schema([("dest_idx", pa.int32()), ("dest_kind", _S), ("dest_key", _S)]),
    "travel_times_pt": pa.schema(
        [
            ("window_id", _S),
            ("origin_idx", pa.int32()),
            ("dest_idx", pa.int32()),
            ("minutes", pa.int16()),
        ]
    ),
    "travel_times_car": pa.schema(
        [("origin_idx", pa.int32()), ("dest_idx", pa.int32()), ("minutes", pa.int16())]
    ),
    "previous_municipality_metrics": pa.schema(
        [
            ("snapshot_id", _S),
            ("ags", _S),
            ("window_id", _S),
            ("dimension", _S),
            ("metric", _S),
            ("value", pa.float64()),
        ]
    ),
}


def to_table(frame: pd.DataFrame, name: str) -> pa.Table:
    schema = SCHEMAS[name]
    missing = [column for column in schema.names if column not in frame.columns]
    if missing:
        raise KeyError(f"staging table {name!r} is missing columns {missing}")
    return pa.Table.from_pandas(frame[schema.names], schema=schema, preserve_index=False)


def write_table(frame: pd.DataFrame, name: str, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.parquet"
    pq.write_table(to_table(frame, name), path)
    return path


def empty_frame(name: str) -> pd.DataFrame:
    return SCHEMAS[name].empty_table().to_pandas()
