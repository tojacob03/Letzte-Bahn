from __future__ import annotations

import zipfile

import pandas as pd
import pytest

from transit_atlas.census import MEMBER, parse_population, read_population_points

CSV = (
    "GITTER_ID_100m;x_mp_100m;y_mp_100m;Einwohner\n"
    "CRS3035RES100mN2689100E4337000;4337050;2689150;4\n"
    "CRS3035RES100mN2689100E4341100;4341150;2689150;–\n"
    "CRS3035RES100mN3000000E5000000;5000050;3000050;9\n"
)


def test_secrecy_marker_counts_as_zero():
    assert parse_population(pd.Series(["4", "–", " 12 "])).tolist() == [4, 0, 12]


def test_unknown_values_are_rejected():
    with pytest.raises(ValueError, match="Unexpected"):
        parse_population(pd.Series(["4", "x"]))


def test_reads_only_cells_inside_the_bounds(tmp_path):
    archive = tmp_path / "zensus.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(MEMBER, CSV)
    points = read_population_points(archive, (4330000, 2680000, 4350000, 2700000))
    assert points["x"].tolist() == [4337050, 4341150]
    assert points["population"].tolist() == [4, 0]
