"""Helpers for the INSPIRE grid in ETRS89-LAEA (EPSG:3035) used by the Zensus 2022."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

CRS_LAEA = "EPSG:3035"
_CELL_ID = re.compile(r"^CRS3035RES(?P<size>\d+)(?P<unit>m|km)N(?P<north>\d+)E(?P<east>\d+)$")


def resolution_label(size_m: int) -> str:
    """INSPIRE resolution label, e.g. ``100m``, ``500m`` or ``1km``."""
    return f"{size_m // 1000}km" if size_m % 1000 == 0 else f"{size_m}m"


def cell_id(x_ll: int, y_ll: int, size_m: int) -> str:
    """INSPIRE cell code from the lower-left corner, e.g. ``CRS3035RES500mN2750000E4150000``."""
    return f"CRS3035RES{resolution_label(size_m)}N{int(y_ll)}E{int(x_ll)}"


def cell_ids(x_ll, y_ll, size_m: int) -> pd.Series:
    """Vectorised :func:`cell_id`."""
    x = pd.Series(np.asarray(x_ll, dtype=np.int64)).astype(str)
    y = pd.Series(np.asarray(y_ll, dtype=np.int64)).astype(str)
    return f"CRS3035RES{resolution_label(size_m)}N" + y + "E" + x


def parse_cell_id(value: str) -> tuple[int, int, int]:
    """Return ``(size_m, x_ll, y_ll)`` for an INSPIRE cell code."""
    match = _CELL_ID.match(value)
    if match is None:
        raise ValueError(f"Not an INSPIRE cell id: {value!r}")
    factor = 1000 if match["unit"] == "km" else 1
    return int(match["size"]) * factor, int(match["east"]), int(match["north"])


def snap_down(values, size_m: int) -> np.ndarray:
    """Lower-left corner of the ``size_m`` cell that contains each coordinate."""
    return np.floor_divide(np.asarray(values, dtype=np.int64), size_m) * size_m


def aggregate_cells(points: pd.DataFrame, size_m: int) -> pd.DataFrame:
    """Aggregate 100 m census cells (midpoints ``x``, ``y``; ``population``) to ``size_m``.

    Besides the population sum, the result holds the population-weighted centroid
    (``cx``, ``cy``), which serves as routing origin: it lies where people actually live,
    not in the forest that may cover half of a cell.
    """
    if size_m % 100:
        raise ValueError("size_m must be a multiple of the 100 m source grid")
    x = points["x"].to_numpy(np.int64)
    y = points["y"].to_numpy(np.int64)
    population = points["population"].to_numpy(np.int64)
    frame = pd.DataFrame(
        {
            "x_ll": snap_down(x, size_m),
            "y_ll": snap_down(y, size_m),
            "population": population,
            "wx": x.astype(np.float64) * population,
            "wy": y.astype(np.float64) * population,
        }
    )
    cells = frame.groupby(["x_ll", "y_ll"], as_index=False).agg(
        population=("population", "sum"),
        wx=("wx", "sum"),
        wy=("wy", "sum"),
        n_subcells=("population", "size"),
    )
    half = size_m / 2
    has_people = cells["population"] > 0
    divisor = cells["population"].where(has_people, 1)
    cells["cx"] = np.where(has_people, cells["wx"] / divisor, cells["x_ll"] + half)
    cells["cy"] = np.where(has_people, cells["wy"] / divisor, cells["y_ll"] + half)
    cells["cell_id"] = cell_ids(cells["x_ll"], cells["y_ll"], size_m)
    return cells.drop(columns=["wx", "wy"])
