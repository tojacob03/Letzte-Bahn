"""Zensus 2022 population counts on the 100 m INSPIRE grid, read from the zip archive."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

MEMBER = "Zensus2022_Bevoelkerungszahl_100m-Gitter.csv"
_TYPES = {
    "GITTER_ID_100m": pa.string(),
    "x_mp_100m": pa.int64(),
    "y_mp_100m": pa.int64(),
    "Einwohner": pa.string(),
}
# The dataset description uses "–" for cells that are exactly zero or were set to zero.
_ZERO_MARKERS = ("-", "–", "—")


def parse_population(values: pd.Series) -> pd.Series:
    """Convert the ``Einwohner`` column to integers (secrecy markers become 0)."""
    text = values.astype("string").str.strip()
    text = text.mask(text.isin(_ZERO_MARKERS), "0")
    numbers = pd.to_numeric(text, errors="coerce")
    invalid = numbers.isna()
    if invalid.any():
        examples = sorted(set(values[invalid].astype(str)))[:5]
        raise ValueError(f"Unexpected population values: {examples}")
    return numbers.astype("int64")


def read_population_points(
    zip_path: Path, bounds: tuple[float, float, float, float]
) -> pd.DataFrame:
    """100 m cell midpoints (``x``, ``y`` in EPSG:3035) with ``population`` inside ``bounds``.

    The national CSV (~150 MB) is streamed from the archive and filtered batch by batch.
    """
    min_x, min_y, max_x, max_y = bounds
    parts = []
    with zipfile.ZipFile(zip_path) as archive, archive.open(MEMBER) as handle:
        reader = pacsv.open_csv(
            handle,
            parse_options=pacsv.ParseOptions(delimiter=";"),
            convert_options=pacsv.ConvertOptions(column_types=_TYPES),
        )
        for batch in reader:
            x = batch.column("x_mp_100m")
            y = batch.column("y_mp_100m")
            inside = pc.and_(
                pc.and_(pc.greater_equal(x, min_x), pc.less_equal(x, max_x)),
                pc.and_(pc.greater_equal(y, min_y), pc.less_equal(y, max_y)),
            )
            selected = batch.filter(inside)
            if selected.num_rows:
                parts.append(selected.to_pandas())
    if not parts:
        return pd.DataFrame(
            {
                "x": pd.Series(dtype="int64"),
                "y": pd.Series(dtype="int64"),
                "population": pd.Series(dtype="int64"),
            }
        )
    frame = pd.concat(parts, ignore_index=True)
    return pd.DataFrame(
        {
            "x": frame["x_mp_100m"].astype("int64"),
            "y": frame["y_mp_100m"].astype("int64"),
            "population": parse_population(frame["Einwohner"]),
        }
    )
