"""Prepare stage: raw downloads -> network inputs for R5 and the dbt staging tables."""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer

from . import boundaries, census, download, grid, gtfs, osm, service_dates, staging
from .config import Config, Paths

log = logging.getLogger(__name__)
CRS_WGS84 = "EPSG:4326"
OSM_EXTRACT = "region.osm.pbf"
GTFS_EXTRACT = "gtfs_region.zip"
METADATA = "run_metadata.json"


def run(config: Config, paths: Paths) -> dict:
    raw = paths.raw
    manifest = download.load_manifest(raw)

    boundaries_zip = raw / config.boundaries.filename
    municipalities = boundaries.load_municipalities(boundaries_zip, config.ags_prefix)
    region = shapely.union_all(municipalities.to_crs(grid.CRS_LAEA).geometry.to_numpy())
    country = to_laea(boundaries.load_country(boundaries_zip), boundaries.CRS_UTM32)
    study_area = region.buffer(config.buffer_km * 1000).intersection(country)
    shapely.prepare(study_area)
    network_area = region.buffer((config.buffer_km + config.network_margin_km) * 1000)
    bounds = gpd.GeoSeries([network_area], crs=grid.CRS_LAEA).to_crs(CRS_WGS84).total_bounds
    bbox = tuple(float(value) for value in bounds)
    log.info("%d municipalities; network bbox %s", len(municipalities), bbox)

    osm_sources = [raw / source.filename for source in config.osm]
    osm_pbf = osm.build_extract(osm_sources, bbox, paths.interim / OSM_EXTRACT)
    feed = gtfs.clip_feed(raw / config.gtfs.filename, paths.interim / GTFS_EXTRACT, bbox)
    trips = gtfs.trips_per_date(feed)
    feed_start, feed_end = trips["service_date"].min(), trips["service_date"].max()
    dates = service_dates.pick_service_dates(
        feed_start, feed_end, config.calendar, service_ok=typical_service(trips)
    )
    log.info("Feed %s..%s; analysis days %s and %s", feed_start, feed_end, dates.weekday,
             dates.sunday)
    windows = windows_frame(config, dates)

    stations, departures = gtfs.rail_station_service(feed, windows)
    osm_pois, poi_stats = osm.extract_pois(osm_pbf)
    pois = pd.concat([osm_pois, stations_as_pois(stations)], ignore_index=True)
    pois = pois[inside(study_area, pois["lon"], pois["lat"])].reset_index(drop=True)
    station_service = departures.assign(poi_id="gtfs:" + departures["station_id"].astype(str))
    station_service = station_service[station_service["poi_id"].isin(pois["poi_id"])]

    points = census.read_population_points(raw / config.census.filename, study_area.bounds)
    keep = shapely.contains_xy(
        study_area, points["x"].to_numpy(float), points["y"].to_numpy(float)
    )
    points = points[keep].reset_index(drop=True)
    points["ags"] = assign_municipality(points, municipalities)
    cells, cell_municipality = build_cells(points, config.cell_size_m)

    snapshot_id = snapshot_name(config.region_id, manifest)
    previous_id, previous_metrics, previous_fingerprint = previous_snapshot(
        paths, config.region_id, snapshot_id
    )

    out = paths.staging
    staging.write_table(cells, "cells", out)
    staging.write_table(cell_municipality, "cell_municipality", out)
    staging.write_table(municipalities_table(municipalities), "municipalities", out)
    staging.write_table(pois, "pois", out)
    staging.write_table(station_service, "station_service", out)
    staging.write_table(windows, "windows", out)
    thresholds = pd.DataFrame({"threshold_min": list(config.routing.population_thresholds)})
    staging.write_table(thresholds, "thresholds", out)
    staging.write_table(previous_metrics, "previous_municipality_metrics", out)

    per_day = dict(zip(trips["service_date"], trips["trips"], strict=True))
    metadata = {
        "snapshot_id": snapshot_id,
        "region": {
            "id": config.region_id,
            "name": config.region_name,
            "ags_prefix": config.ags_prefix,
        },
        "config": config.path.name,
        "config_fingerprint": config.fingerprint,
        "prepared_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "feed": {
            "source": "gtfs.de (DELFI e.V.)",
            "last_modified": manifest["gtfs"].get("last_modified"),
            "valid_from": feed_start.isoformat(),
            "valid_to": feed_end.isoformat(),
            "median_trips_per_day": int(trips["trips"].median()),
            "trips_on_weekday": int(per_day.get(dates.weekday, 0)),
            "trips_on_sunday": int(per_day.get(dates.sunday, 0)),
        },
        "service_dates": {"weekday": dates.weekday.isoformat(), "sunday": dates.sunday.isoformat()},
        "service_date_notes": list(dates.notes),
        "network_bbox": bbox,
        "counts": {
            "municipalities": len(municipalities),
            "cells": len(cells),
            "origin_cells": int(cells["is_origin"].sum()),
            "population_region": int(cell_municipality["population"].sum()),
            "population_study_area": int(cells["population"].sum()),
            "pois": {
                str(category): int(count)
                for category, count in pois.groupby("category")["poi_id"].nunique().items()
            },
            "gp_strict": int(pois.loc[pois["category"].eq("gp") & pois["is_strict"], "poi_id"]
                             .nunique()),
        },
        "osm_poi_stats": poi_stats,
        "previous_snapshot": {"id": previous_id, "config_fingerprint": previous_fingerprint},
        "sources": manifest,
    }
    (out / METADATA).write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    log.info("Prepared snapshot %s: %s", snapshot_id, metadata["counts"])
    return metadata


def to_laea(geometry: shapely.Geometry, crs: str) -> shapely.Geometry:
    return gpd.GeoSeries([geometry], crs=crs).to_crs(grid.CRS_LAEA).iloc[0]


def inside(area: shapely.Geometry, lon: pd.Series, lat: pd.Series) -> np.ndarray:
    """Which lon/lat points lie inside ``area`` (an EPSG:3035 geometry)."""
    to_laea_xy = Transformer.from_crs(CRS_WGS84, grid.CRS_LAEA, always_xy=True)
    x, y = to_laea_xy.transform(lon.to_numpy(float), lat.to_numpy(float))
    return shapely.contains_xy(area, np.asarray(x), np.asarray(y))


def typical_service(trips: pd.DataFrame, share: float = 0.8) -> Callable[[dt.date], bool]:
    """Reject days with far fewer trips than usual for that weekday (data gaps, specials)."""
    counts = dict(zip(trips["service_date"], trips["trips"], strict=True))
    series = pd.Series(counts)
    medians = series.groupby([day.weekday() for day in series.index]).median()

    def ok(day: dt.date) -> bool:
        usual = medians.get(day.weekday())
        return usual is not None and counts.get(day, 0) >= share * usual

    return ok


def windows_frame(config: Config, dates: service_dates.ServiceDates) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "window_id": window.id,
                "label": window.label,
                "day_type": window.day,
                "service_date": dates.for_day(window.day),
                "start_time": window.start.strftime("%H:%M"),
                "minutes": window.minutes,
                "sort_order": order,
            }
            for order, window in enumerate(config.windows)
        ]
    )


def stations_as_pois(stations: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "poi_id": "gtfs:" + stations["station_id"].astype(str),
            "category": "rail_station",
            "is_strict": True,
            "name": stations["name"],
            "lon": stations["lon"],
            "lat": stations["lat"],
            "source": "gtfs",
        }
    )


def assign_municipality(points: pd.DataFrame, municipalities: gpd.GeoDataFrame) -> pd.Series:
    """AGS of the municipality each 100 m cell midpoint lies in (NaN outside the region)."""
    geo = gpd.GeoDataFrame(
        index=points.index,
        geometry=gpd.points_from_xy(points["x"], points["y"]),
        crs=grid.CRS_LAEA,
    )
    areas = municipalities[["ags", "geometry"]].to_crs(grid.CRS_LAEA)
    joined = gpd.sjoin(geo, areas, how="left", predicate="intersects")
    joined = joined[~joined.index.duplicated(keep="first")]
    return joined["ags"].reindex(points.index)


def build_cells(points: pd.DataFrame, size_m: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Grid cells of the study area and the population of each cell per municipality."""
    cells = grid.aggregate_cells(points, size_m)
    in_region = points.dropna(subset=["ags"])
    weights = (
        in_region.assign(
            x_ll=grid.snap_down(in_region["x"], size_m),
            y_ll=grid.snap_down(in_region["y"], size_m),
        )
        .groupby(["x_ll", "y_ll", "ags"], as_index=False)["population"]
        .sum()
    )
    weights["cell_id"] = grid.cell_ids(weights["x_ll"], weights["y_ll"], size_m)
    weights = weights[weights["population"] > 0]
    cells["is_origin"] = cells["cell_id"].isin(weights["cell_id"])
    to_wgs84 = Transformer.from_crs(grid.CRS_LAEA, CRS_WGS84, always_xy=True)
    lon, lat = to_wgs84.transform(cells["cx"].to_numpy(), cells["cy"].to_numpy())
    cells["lon"] = np.asarray(lon)
    cells["lat"] = np.asarray(lat)
    cells = cells.sort_values("cell_id").reset_index(drop=True)
    cells["cell_idx"] = np.arange(len(cells), dtype=np.int32)
    return cells, weights[["cell_id", "ags", "population"]].reset_index(drop=True)


def municipalities_table(municipalities: gpd.GeoDataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ags": municipalities["ags"].to_numpy(),
            "name": municipalities["name"].to_numpy(),
            "bez": municipalities["bez"].to_numpy(),
            "kreis_ags": municipalities["kreis_ags"].to_numpy(),
            "kreis_name": municipalities["kreis_name"].to_numpy(),
            "area_km2": municipalities["area_km2"].to_numpy(),
            "geometry_wkb": shapely.to_wkb(municipalities.geometry.to_numpy()),
        }
    )


def snapshot_name(region_id: str, manifest: dict) -> str:
    """Snapshot id: region plus the publication day of the timetable feed (Fahrplanstand)."""
    entry = manifest["gtfs"]
    if entry.get("last_modified"):
        stamp = parsedate_to_datetime(entry["last_modified"])
        day = stamp.astimezone(ZoneInfo("Europe/Berlin")).date()
    else:
        day = dt.datetime.fromisoformat(entry["retrieved_at"]).date()
    return f"{region_id}_{day.isoformat()}"


def previous_snapshot(
    paths: Paths, region_id: str, current: str
) -> tuple[str | None, pd.DataFrame, str | None]:
    """Metrics of the latest published snapshot before ``current`` (empty if none)."""
    root = paths.published / "snapshots"
    earlier = sorted(
        directory
        for directory in root.glob(f"{region_id}_*")
        if directory.name < current and (directory / "municipality_metrics.csv").exists()
    )
    if not earlier:
        return None, staging.empty_frame("previous_municipality_metrics"), None
    chosen = earlier[-1]
    metrics = pd.read_csv(
        chosen / "municipality_metrics.csv",
        dtype={"ags": str, "window_id": str, "dimension": str, "metric": str},
    )
    metrics["snapshot_id"] = chosen.name
    meta_path = chosen / "metadata.json"
    fingerprint = None
    if meta_path.exists():
        fingerprint = json.loads(meta_path.read_text(encoding="utf-8")).get("config_fingerprint")
    log.info("Previous snapshot for comparison: %s", chosen.name)
    return chosen.name, metrics, fingerprint
