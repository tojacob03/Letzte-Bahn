from __future__ import annotations

import numpy as np
import pandas as pd

from transit_atlas.export import cell_rings, clean
from transit_atlas.report import key_sentences, replace_block


def test_clean_makes_values_json_friendly():
    assert clean(float("nan")) is None
    assert clean(pd.NA) is None
    assert clean(np.int16(4)) == 4
    assert clean(12.0) == 12
    assert clean(0.123456) == 0.123
    assert clean(np.bool_(True)) is True
    assert clean("text") == "text"


def test_cell_rings_are_closed_squares():
    rings = cell_rings(np.array([4150000]), np.array([2750000]), 500)
    assert len(rings) == 1
    assert len(rings[0]) == 5
    assert rings[0][0] == rings[0][-1]


def test_replace_block_only_touches_the_marked_section():
    text = "intro\n<!-- findings:start -->\nold\n<!-- findings:end -->\noutro"
    expected = "intro\n<!-- findings:start -->\nnew\n<!-- findings:end -->\noutro"
    assert replace_block(text, "findings", "new") == expected


def test_key_sentences_use_pipeline_numbers():
    findings = {
        "gp_evening_60": {"municipalities_below_half": 20, "municipalities_total": 52},
        "reach_45": {"median_wd_am": 100000, "median_su_am": 50000},
        "pt_car_ratio_supermarket": {"median_ratio_wd_am": 2.5, "share_over_3_wd_am": 0.3},
    }
    meta = {
        "region": {"name": "Saarland"},
        "windows": [{"id": "wd_pm", "start": "20:00", "minutes": 120}],
    }
    text = " ".join(key_sentences(findings, meta))
    assert "20 of 52" in text
    assert "20:00–22:00" in text
    assert "50 % fewer" in text
    assert "2.5×" in text
