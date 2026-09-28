"""Export stage: data for the static website and the published snapshot files."""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import shapely.errors
from pyproj import Transformer

from . import report
from .boundaries import CRS_UTM32
from .config import Config, Paths
from .grid import CRS_LAEA
from .prepare import METADATA
from .warehouse import DATABASE

log = logging.getLogger(__name__)
DECIMALS = 5  # about 1 m
SIMPLIFY_M = 25
# Web property names of the municipality metrics compared between snapshots.
CHANGE_KEYS = {
    "median_pt_minutes": "t_{window}_{dimension}",
    "share_within_30": "s30_{window}_{dimension}",
    "share_within_60": "s60_{window}_{dimension}",
    "mean_reachable_population_pt": "p{dimension}_{window}",
}


def clean(value: Any) -> Any:
    """JSON-friendly scalars: missing -> None, whole floats -> int, other floats rounded."""
    if value is None:
        return None
    if isinstance(value, bool | np.bool_):
        return bool(value)
    if pd.api.types.is_scalar(value) and pd.isna(value):
        return None
    if isinstance(value, int | np.integer):
        return int(value)
    if isinstance(value, float | np.floating):
        number = float(value)
        return int(number) if number.is_integer() else round(number, 3)
    return value


def write_json(path: Path, payload: Any, *, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    separators = (",", ": ") if indent else (",", ":")
    text = json.dumps(
        payload, ensure_ascii=False, indent=indent, separators=separators, allow_nan=False
    )
    path.write_text(text + "\n", encoding="utf-8")


def records(frame: pd.DataFrame) -> list[dict]:
    return [{key: clean(value) for key, value in row.items()} for row in frame.to_dict("records")]


def wide(
    frame: pd.DataFrame, index: str, columns: str | list[str], values: str, name: Callable
) -> pd.DataFrame:
    """Pivot ``values`` into one column per value of ``columns``, named by ``name``."""
    table = frame.pivot(index=index, columns=columns, values=values)
    if isinstance(columns, list):
        table.columns = [name(*key) for key in table.columns]
    else:
        table.columns = [name(key) for key in table.columns]
    return table


def cell_rings(x_ll: np.ndarray, y_ll: np.ndarray, size_m: int) -> list[list[list[float]]]:
    """Square EPSG:3035 grid cells as closed lon/lat rings (five points each)."""
    dx = np.array([0, size_m, size_m, 0, 0])
    dy = np.array([0, 0, size_m, size_m, 0])
    to_wgs84 = Transformer.from_crs(CRS_LAEA, "EPSG:4326", always_xy=True)
    lon, lat = to_wgs84.transform((x_ll[:, None] + dx).ravel(), (y_ll[:, None] + dy).ravel())
    lon = np.round(np.asarray(lon), DECIMALS).reshape(-1, 5)
    lat = np.round(np.asarray(lat), DECIMALS).reshape(-1, 5)
    return [np.stack([lo, la], axis=1).tolist() for lo, la in zip(lon, lat, strict=True)]


def cell_features(con: duckdb.DuckDBPyConnection, size_m: int, categories: list[str]) -> dict:
    cells = con.execute(
        "select cell_id, x_ll, y_ll, population, main_ags from dim_cells "
        "where is_origin order by cell_id"
    ).df()
    access = con.execute(
        "select cell_id, window_id, category, pt_minutes, car_minutes from fct_cell_accessibility"
    ).df()
    access = access[access["category"].isin(categories)]
    reach = con.execute(
        "select cell_id, window_id, threshold_min, reachable_population_pt, "
        "reachable_population_car from fct_cell_reachability"
    ).df()
    table = cells.set_index("cell_id").join(
        [
            wide(access, "cell_id", ["window_id", "category"], "pt_minutes",
                 lambda w, c: f"t_{w}_{c}"),
            wide(access.drop_duplicates(["cell_id", "category"]), "cell_id", "category",
                 "car_minutes", lambda c: f"c_{c}"),
            wide(reach, "cell_id", ["window_id", "threshold_min"], "reachable_population_pt",
                 lambda w, t: f"p{t}_{w}"),
            wide(reach.drop_duplicates(["cell_id", "threshold_min"]), "cell_id", "threshold_min",
                 "reachable_population_car", lambda t: f"pc{t}"),
        ]
    )
    rings = cell_rings(table["x_ll"].to_numpy(np.int64), table["y_ll"].to_numpy(np.int64), size_m)
    metrics = [column for column in table.columns
               if column not in ("x_ll", "y_ll", "population", "main_ags")]
    features = []
    for (cell_id, row), ring in zip(table.iterrows(), rings, strict=True):
        properties = {"id": cell_id, "pop": clean(row["population"]), "ags": clean(row["main_ags"])}
        properties.update({column: clean(row[column]) for column in metrics})
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": properties,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def municipality_geometries(staging_dir: Path) -> dict[str, shapely.Geometry]:
    """Simplified municipality outlines in lon/lat; shared borders stay shared."""
    frame = pd.read_parquet(staging_dir / "municipalities.parquet", columns=["ags", "geometry_wkb"])
    geometries = shapely.from_wkb(frame["geometry_wkb"].to_numpy())
    try:
        simplified = shapely.coverage_simplify(geometries, SIMPLIFY_M)
    except (AttributeError, shapely.errors.GEOSException):
        simplified = shapely.simplify(geometries, SIMPLIFY_M, preserve_topology=True)
    series = gpd.GeoSeries(simplified, index=frame["ags"].to_numpy(), crs=CRS_UTM32)
    series = series.to_crs("EPSG:4326")
    rounded = shapely.transform(series.to_numpy(), lambda coords: np.round(coords, DECIMALS))
    return dict(zip(series.index, rounded, strict=True))


def municipality_features(
    con: duckdb.DuckDBPyConnection, staging_dir: Path, categories: list[str]
) -> dict:
    base = con.execute(
        "select ags, name, kreis_name, population, area_km2 from dim_municipalities order by ags"
    ).df()
    access = con.execute(
        "select ags, window_id, category, median_pt_minutes, share_within_30, share_within_60, "
        "median_car_minutes, median_pt_car_ratio from fct_municipality_accessibility"
    ).df()
    access = access[access["category"].isin(categories)]
    reach = con.execute(
        "select ags, window_id, threshold_min, mean_reachable_population_pt, "
        "mean_reachable_population_car from fct_municipality_reachability"
    ).df()
    neighbors = con.execute(
        "select ags, list(neighbor_ags order by neighbor_ags) as nb "
        "from dim_municipality_neighbors group by ags"
    ).df().set_index("ags")
    by_window = ["window_id", "category"]
    parts = [
        wide(access, "ags", by_window, "median_pt_minutes", lambda w, c: f"t_{w}_{c}"),
        wide(access, "ags", by_window, "share_within_30", lambda w, c: f"s30_{w}_{c}"),
        wide(access, "ags", by_window, "share_within_60", lambda w, c: f"s60_{w}_{c}"),
        wide(access, "ags", by_window, "median_pt_car_ratio", lambda w, c: f"r_{w}_{c}"),
        wide(access.drop_duplicates(["ags", "category"]), "ags", "category",
             "median_car_minutes", lambda c: f"c_{c}"),
        wide(reach, "ags", ["window_id", "threshold_min"], "mean_reachable_population_pt",
             lambda w, t: f"p{t}_{w}"),
        wide(reach.drop_duplicates(["ags", "threshold_min"]), "ags", "threshold_min",
             "mean_reachable_population_car", lambda t: f"pc{t}"),
    ]
    table = base.set_index("ags").join([*parts, neighbors])
    geometries = municipality_geometries(staging_dir)
    fixed = {"name", "kreis_name", "population", "area_km2", "nb"}
    features = []
    for ags, row in table.iterrows():
        neighbours = row["nb"]
        properties = {
            "ags": ags,
            "name": row["name"],
            "kreis": clean(row["kreis_name"]),
            "pop": clean(row["population"]),
            "area": clean(row["area_km2"]),
            "nb": [str(value) for value in neighbours]
            if isinstance(neighbours, list | np.ndarray)
            else [],
        }
        properties.update({column: clean(row[column]) for column in table.columns
                           if column not in fixed})
        features.append(
            {
                "type": "Feature",
                "geometry": shapely.geometry.mapping(geometries[ags]),
                "properties": properties,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def findings_dict(con: duckdb.DuckDBPyConnection) -> dict[str, dict[str, Any]]:
    findings: dict[str, dict[str, Any]] = {}
    rows = con.execute(
        "select finding_id, metric_key, value_num, value_text from fct_findings order by all"
    ).fetchall()
    for finding_id, key, value_num, value_text in rows:
        entry = findings.setdefault(finding_id, {})
        entry[key] = clean(value_num)
        if value_text is not None:
            entry[f"{key}_label"] = value_text
    return findings


def change_dict(con: duckdb.DuckDBPyConnection, metadata: dict) -> dict | None:
    rows = con.execute(
        "select ags, window_id, dimension, metric, previous_snapshot_id, change "
        "from fct_municipality_change"
    ).fetchall()
    if not rows:
        return None
    by_ags: dict[str, dict[str, Any]] = {}
    for ags, window_id, dimension, metric, _previous, change in rows:
        template = CHANGE_KEYS.get(metric)
        if template is None or window_id == "car":
            continue
        key = template.format(window=window_id, dimension=dimension)
        by_ags.setdefault(ags, {})[key] = clean(change)
    previous = metadata.get("previous_snapshot") or {}
    return {
        "previous_snapshot": rows[0][4],
        "comparable": previous.get("config_fingerprint") == metadata.get("config_fingerprint"),
        "municipalities": by_ags,
    }


def region_dict(con: duckdb.DuckDBPyConnection) -> dict:
    accessibility = con.execute(
        "select * from fct_region_accessibility order by window_id, category"
    ).df()
    reachability = con.execute(
        "select * from fct_region_reachability order by window_id, threshold_min"
    ).df()
    return {"accessibility": records(accessibility), "reachability": records(reachability)}


def source_summary(manifest: dict) -> list[dict]:
    entries = []
    for role, value in manifest.items():
        for entry in value if isinstance(value, list) else [value]:
            entries.append(
                {
                    "role": role,
                    "url": entry["url"],
                    "last_modified": entry.get("last_modified"),
                    "retrieved_at": entry.get("retrieved_at"),
                }
            )
    return entries


def build_meta(
    config: Config,
    metadata: dict,
    categories: pd.DataFrame,
    windows: pd.DataFrame,
    change: dict | None,
) -> dict:
    routing = config.routing
    return {
        "snapshot_id": metadata["snapshot_id"],
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "region": metadata["region"],
        "service_dates": metadata["service_dates"],
        "service_date_notes": metadata.get("service_date_notes", []),
        "feed": metadata["feed"],
        "windows": records(windows),
        "categories": records(categories),
        "thresholds": list(routing.population_thresholds),
        "grid_cell_size_m": config.cell_size_m,
        "routing": {
            "walk_speed_kmh": routing.walk_speed_kmh,
            "max_walk_minutes": routing.max_walk_minutes,
            "max_trip_minutes": routing.max_trip_minutes,
            "max_rides": routing.max_rides,
            "statistic": "median over all departure minutes of the window",
        },
        "counts": metadata["counts"],
        "sources": source_summary(metadata["sources"]),
        "change": None
        if change is None
        else {"previous_snapshot": change["previous_snapshot"], "comparable": change["comparable"]},
    }


def run(config: Config, paths: Paths) -> None:
    metadata = json.loads((paths.staging / METADATA).read_text(encoding="utf-8"))
    with duckdb.connect(str(paths.warehouse / DATABASE), read_only=True) as con:
        categories = con.execute(
            "select category_id as id, label_de as label, label_en from categories "
            "where not is_sensitivity order by sort_order"
        ).df()
        windows = con.execute(
            "select window_id as id, label, day_type, cast(service_date as varchar) as date, "
            "start_time as start, minutes from dim_windows order by sort_order"
        ).df()
        category_ids = categories["id"].tolist()
        cells = cell_features(con, config.cell_size_m, category_ids)
        municipalities = municipality_features(con, paths.staging, category_ids)
        findings = findings_dict(con)
        region = region_dict(con)
        change = change_dict(con, metadata)
        metrics = con.execute(
            "select * from mart_municipality_metrics_long "
            "order by ags, window_id, dimension, metric"
        ).df()

    meta = build_meta(config, metadata, categories, windows, change)
    web = paths.web_data
    write_json(web / "meta.json", meta, indent=2)
    write_json(web / "cells.geojson", cells)
    write_json(web / "municipalities.geojson", municipalities)
    write_json(web / "findings.json", findings, indent=2)
    write_json(web / "region.json", region)
    change_path = web / "change.json"
    if change is None:
        change_path.unlink(missing_ok=True)
    else:
        write_json(change_path, change)

    snapshot = paths.published / "snapshots" / metadata["snapshot_id"]
    snapshot.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(snapshot / "municipality_metrics.csv", index=False, float_format="%.4f")
    write_json(snapshot / "findings.json", findings, indent=2)
    published_meta = {**meta, "config_fingerprint": metadata["config_fingerprint"]}
    write_json(snapshot / "metadata.json", published_meta, indent=2)
    report.update_documents(paths.root, findings, meta)
    log.info("Exported snapshot %s (%d cells, %d municipalities)", metadata["snapshot_id"],
             len(cells["features"]), len(municipalities["features"]))
