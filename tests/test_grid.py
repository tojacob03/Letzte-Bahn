from __future__ import annotations

import pandas as pd
import pytest

from transit_atlas.grid import aggregate_cells, cell_id, cell_ids, parse_cell_id


def test_cell_id_round_trip():
    code = cell_id(4150000, 2750000, 500)
    assert code == "CRS3035RES500mN2750000E4150000"
    assert parse_cell_id(code) == (500, 4150000, 2750000)
    assert parse_cell_id("CRS3035RES1kmN2689000E4337000") == (1000, 4337000, 2689000)
    assert cell_ids([4150000], [2750000], 1000).tolist() == ["CRS3035RES1kmN2750000E4150000"]


def test_parse_rejects_other_strings():
    with pytest.raises(ValueError):
        parse_cell_id("not a cell")


def test_aggregation_keeps_population_weighted_centroid():
    points = pd.DataFrame(
        {
            "x": [4150050, 4150450, 4150550],
            "y": [2750050, 2750050, 2750050],
            "population": [10, 30, 5],
        },
        index=[7, 8, 9],  # a non-default index must not break the alignment
    )
    cells = aggregate_cells(points, 500).set_index("cell_id")
    first = cells.loc["CRS3035RES500mN2750000E4150000"]
    assert first["population"] == 40
    assert first["n_subcells"] == 2
    assert first["cx"] == pytest.approx((4150050 * 10 + 4150450 * 30) / 40)
    assert cells.loc["CRS3035RES500mN2750000E4150500", "population"] == 5


def test_aggregation_requires_multiples_of_100_m():
    points = pd.DataFrame({"x": [50], "y": [50], "population": [1]})
    with pytest.raises(ValueError):
        aggregate_cells(points, 250)
