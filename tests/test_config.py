from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from transit_atlas.config import PROJECT_ROOT, ConfigError, load_config, parse_time


def test_pilot_config_loads():
    config = load_config(PROJECT_ROOT / "config" / "saarland.yaml")
    assert config.ags_prefix == "10"
    assert config.window("wd_pm").start == dt.time(20, 0)
    assert config.routing.population_thresholds == (30, 45, 60)
    assert (dt.date(2026, 10, 5), dt.date(2026, 10, 16)) in config.calendar.school_holidays


def test_smoke_config_extends_the_pilot():
    config = load_config(PROJECT_ROOT / "config" / "smoke.yaml")
    assert config.cell_size_m == 1000
    assert config.calendar.holiday_state == "SL"
    assert [source.filename for source in config.osm] == ["saarland-latest.osm.pbf"]
    pilot = load_config(PROJECT_ROOT / "config" / "saarland.yaml")
    assert config.fingerprint != pilot.fingerprint


def test_rejects_cell_size_that_does_not_fit_the_census_grid(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    base = PROJECT_ROOT / "config" / "saarland.yaml"
    path.write_text(f"extends: '{base}'\ngrid:\n  cell_size_m: 250\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="multiple of the 100 m"):
        load_config(path)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("07:00", dt.time(7)), (420, dt.time(7)), ("20:30", dt.time(20, 30))],
)
def test_parse_time_handles_yaml_sexagesimal_numbers(value, expected):
    assert parse_time(value) == expected
