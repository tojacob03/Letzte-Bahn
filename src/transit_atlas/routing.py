"""Route stage: travel-time matrices with R5 (through r5py), parallelised over origins."""

from __future__ import annotations

import copy
import datetime as dt
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import staging
from .config import Config, Paths
from .prepare import GTFS_EXTRACT, METADATA, OSM_EXTRACT

log = logging.getLogger(__name__)


class OriginRouter:
    """Travel times from single origins to one fixed set of destinations.

    ``r5py.TravelTimeMatrix`` routes origin after origin. R5 itself is thread-safe and
    JPype releases the GIL while Java code runs, so a thread pool can route several
    origins at once on one shared transport network and one prepared request.
    """

    def __init__(self, network, destinations: gpd.GeoDataFrame, **task_options) -> None:
        import r5py
        from com.conveyal.r5.analyst import TravelTimeComputer

        self._computer = TravelTimeComputer
        self._network = network
        self._request = r5py.RegionalTask(network, origin=None, destinations=None, **task_options)
        self._request.destinations = destinations

    def travel_times(self, origin) -> np.ndarray:
        """Minutes to every destination; unreachable destinations are MAX_INT32."""
        request = copy.copy(self._request)
        request.origin = origin
        result = self._computer(request, self._network).computeTravelTimes()
        return np.asarray(result.travelTimes.getValues()[0], dtype=np.int64)


def route_to_file(
    router: OriginRouter,
    origins: pd.DataFrame,
    cutoff: np.ndarray,
    kinds: np.ndarray,
    writer: pq.ParquetWriter,
    *,
    window_id: str | None,
    threads: int,
    chunk_size: int,
) -> dict:
    """Route all ``origins`` and append travel times within ``cutoff`` to ``writer``."""
    label = window_id or "car"
    points = list(gpd.points_from_xy(origins["lon"], origins["lat"]))
    origin_idx = origins["cell_idx"].to_numpy(np.int64)
    reached = np.zeros(len(cutoff), dtype=bool)
    isolated = 0
    rows_written = 0
    started = time.monotonic()
    router.travel_times(points[0])  # warm-up: links the destinations to the street network
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for start in range(0, len(points), chunk_size):
            stop = min(start + chunk_size, len(points))
            matrix = np.vstack(list(pool.map(router.travel_times, points[start:stop])))
            own = origin_idx[start:stop]
            matrix[np.arange(stop - start), own] = 0  # a cell reaches itself, as in r5py
            keep = matrix <= cutoff
            reached |= keep.any(axis=0)
            isolated += int((keep.sum(axis=1) <= 1).sum())
            rows, cols = np.nonzero(keep)
            columns = {
                "origin_idx": own[rows].astype(np.int32),
                "dest_idx": cols.astype(np.int32),
                "minutes": matrix[rows, cols].astype(np.int16),
            }
            if window_id is not None:
                columns = {"window_id": np.full(len(rows), window_id), **columns}
            writer.write_table(pa.table(columns, schema=writer.schema))
            rows_written += len(rows)
            rate = stop / (time.monotonic() - started)
            log.info(
                "%s: %d/%d origins, %.1f origins/s, about %.0f min left",
                label, stop, len(points), rate, (len(points) - stop) / rate / 60,
            )
    return {
        "origins": len(points),
        "minutes": round((time.monotonic() - started) / 60, 1),
        "rows": rows_written,
        "isolated_origins": isolated,
        "unreached_destinations": {
            str(kind): int((~reached[kinds == kind]).sum()) for kind in np.unique(kinds)
        },
    }


def run(config: Config, paths: Paths) -> dict:
    import r5py

    metadata_path = paths.staging / METADATA
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    settings = config.routing

    cells = pd.read_parquet(paths.staging / "cells.parquet").sort_values("cell_idx")
    cells = cells.reset_index(drop=True)
    pois = pd.read_parquet(paths.staging / "pois.parquet").drop_duplicates("poi_id")
    destinations = pd.concat(
        [
            pd.DataFrame(
                {"dest_kind": "cell", "dest_key": cells["cell_id"], "lon": cells["lon"],
                 "lat": cells["lat"]}
            ),
            pd.DataFrame(
                {"dest_kind": "poi", "dest_key": pois["poi_id"], "lon": pois["lon"],
                 "lat": pois["lat"]}
            ),
        ],
        ignore_index=True,
    )
    destinations["dest_idx"] = np.arange(len(destinations), dtype=np.int32)
    staging.write_table(destinations, "destinations", paths.staging)

    points = gpd.GeoDataFrame(
        {"id": destinations["dest_idx"].astype(str)},
        geometry=gpd.points_from_xy(destinations["lon"], destinations["lat"]),
        crs="EPSG:4326",
    )
    kinds = destinations["dest_kind"].to_numpy()
    # Keep cells within the largest population threshold and POIs within the trip limit.
    cutoff = np.where(
        kinds == "cell", max(settings.population_thresholds), settings.max_trip_minutes
    ).astype(np.int64)
    origins = cells[cells["is_origin"]]
    log.info("Routing %d origins to %d destinations", len(origins), len(destinations))

    network = r5py.TransportNetwork(paths.interim / OSM_EXTRACT, [paths.interim / GTFS_EXTRACT])
    common = {"threads": settings.threads, "chunk_size": settings.origin_chunk_size}
    stats: dict[str, dict] = {}
    pt_file = paths.staging / "travel_times_pt.parquet"
    with pq.ParquetWriter(pt_file, staging.SCHEMAS["travel_times_pt"]) as writer:
        for window in config.windows:
            day = dt.date.fromisoformat(metadata["service_dates"][window.day])
            router = OriginRouter(
                network,
                points,
                departure=dt.datetime.combine(day, window.start),
                departure_time_window=dt.timedelta(minutes=window.minutes),
                percentiles=[50],
                transport_modes=[r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
                access_modes=[r5py.TransportMode.WALK],
                max_time=dt.timedelta(minutes=settings.max_trip_minutes),
                max_time_walking=dt.timedelta(minutes=settings.max_walk_minutes),
                speed_walking=settings.walk_speed_kmh,
                max_public_transport_rides=settings.max_rides,
            )
            stats[window.id] = route_to_file(
                router, origins, cutoff, kinds, writer, window_id=window.id, **common
            )

    car_file = paths.staging / "travel_times_car.parquet"
    with pq.ParquetWriter(car_file, staging.SCHEMAS["travel_times_car"]) as writer:
        if settings.car:
            weekday = dt.date.fromisoformat(metadata["service_dates"]["weekday"])
            router = OriginRouter(
                network,
                points,
                departure=dt.datetime.combine(weekday, dt.time(10, 0)),
                departure_time_window=dt.timedelta(minutes=10),
                percentiles=[50],
                transport_modes=[r5py.TransportMode.CAR],
                max_time=dt.timedelta(minutes=settings.max_trip_minutes),
            )
            stats["car"] = route_to_file(
                router, origins, cutoff, kinds, writer, window_id=None, **common
            )

    metadata["routing"] = {"r5py": r5py.__version__, "stats": stats}
    metadata_path.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    log.info("Routing finished: %s", stats)
    return stats
