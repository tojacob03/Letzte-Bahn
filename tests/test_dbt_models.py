"""dbt models on the synthetic fixture from conftest.py; expected values worked out by hand."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.dbt

NEAREST = (
    "select minutes from int_nearest_destination_pt "
    "where cell_id = ? and window_id = ? and category = ?"
)


def scalar(con, sql: str, *params):
    row = con.execute(sql, list(params)).fetchone()
    return None if row is None else row[0]


def test_family_doctor_default_and_strict_definition(fixture_warehouse):
    # c0 reaches the untagged doctor n2 in 10 min, the tagged doctor n1 in 25 min
    assert scalar(fixture_warehouse, NEAREST, "c0", "wd_am", "gp") == 10
    assert scalar(fixture_warehouse, NEAREST, "c0", "wd_am", "gp_strict") == 25


def test_rail_station_needs_departures_in_the_window(fixture_warehouse):
    assert scalar(fixture_warehouse, NEAREST, "c0", "wd_am", "rail_station") == 15
    # s1 can be reached in the evening, but no train leaves there between 20 and 22 h
    assert scalar(fixture_warehouse, NEAREST, "c0", "wd_pm", "rail_station") is None


def test_weighted_median_and_shares_per_municipality(fixture_warehouse):
    # A: c0 (100 people, 10 min) and c1 (300 people, 40 min) -> the median resident needs 40
    row = fixture_warehouse.execute(
        "select median_pt_minutes, share_within_30, share_within_60 "
        "from fct_municipality_accessibility "
        "where ags = 'A' and window_id = 'wd_am' and category = 'gp'"
    ).fetchone()
    assert row == (40, 0.25, 1.0)


def test_median_is_null_when_most_residents_cannot_reach(fixture_warehouse):
    # evening: c0 reaches a doctor in 15 min, c1 (75 % of A) reaches none
    row = fixture_warehouse.execute(
        "select median_pt_minutes, share_unreachable from fct_municipality_accessibility "
        "where ags = 'A' and window_id = 'wd_pm' and category = 'gp'"
    ).fetchone()
    assert row == (None, 0.75)


def test_reachable_population_per_threshold(fixture_warehouse):
    rows = dict(
        fixture_warehouse.execute(
            "select threshold_min, reachable_population_pt from fct_cell_reachability "
            "where cell_id = 'c0' and window_id = 'wd_am'"
        ).fetchall()
    )
    # own cell (100) + c2 after 20 min (200) + c3 after 50 min (1000)
    assert rows == {30: 300, 45: 300, 60: 1300}
    by_car = scalar(
        fixture_warehouse,
        "select reachable_population_car from fct_cell_reachability "
        "where cell_id = 'c0' and window_id = 'wd_am' and threshold_min = 30",
    )
    assert by_car == 1300


def test_public_transport_to_car_ratio(fixture_warehouse):
    ratio = scalar(
        fixture_warehouse,
        "select pt_car_ratio from fct_cell_accessibility "
        "where cell_id = 'c0' and window_id = 'wd_am' and category = 'supermarket'",
    )
    assert ratio == pytest.approx(8 / 3, abs=1e-3)


def test_region_weighted_median(fixture_warehouse):
    # 10 min (100 people), 40 min (300), 70 min (200): half of 600 is reached at 40 min
    median = scalar(
        fixture_warehouse,
        "select median_pt_minutes from fct_region_accessibility "
        "where window_id = 'wd_am' and category = 'gp'",
    )
    assert median == 40


def test_neighbours_are_symmetric(fixture_warehouse):
    pairs = set(
        fixture_warehouse.execute("select ags, neighbor_ags from dim_municipality_neighbors")
        .fetchall()
    )
    assert pairs == {("A", "B"), ("B", "A")}


def test_findings(fixture_warehouse):
    findings = {
        (finding, key): value
        for finding, key, value in fixture_warehouse.execute(
            "select finding_id, metric_key, value_num from fct_findings"
        ).fetchall()
    }
    # A: 25 % and B: 0 % of residents reach a doctor within 60 min in the evening
    assert findings[("gp_evening_60", "municipalities_below_half")] == 2
    assert findings[("gp_evening_60", "municipalities_total")] == 2
    # B: 600 people within 45 min for its only cell; A: (100*300 + 300*600) / 400 = 525
    assert findings[("municipal_gap_45", "best")] == 600
    assert findings[("municipal_gap_45", "worst")] == 525


def test_change_against_previous_snapshot(fixture_warehouse):
    change = scalar(
        fixture_warehouse,
        "select change from fct_municipality_change where ags = 'A' and window_id = 'wd_am' "
        "and dimension = 'gp' and metric = 'median_pt_minutes'",
    )
    assert change == -10
