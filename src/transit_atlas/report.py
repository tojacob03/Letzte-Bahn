"""Keep the key findings in README.md and CASE_STUDY.md in sync with the latest snapshot.

The numbers come from ``fct_findings``; only the wording lives here, so documents never
contain numbers that the pipeline did not compute.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f} %"


def _count(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.0f}"


def _ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}×"


def _get(findings: dict, finding: str, key: str) -> Any:
    return findings.get(finding, {}).get(key)


def _window_span(meta: dict, window_id: str) -> str:
    for window in meta.get("windows", []):
        if window["id"] == window_id:
            hours, minutes = (int(part) for part in window["start"].split(":"))
            end = hours * 60 + minutes + int(window["minutes"])
            return f"{window['start']}–{end // 60:02d}:{end % 60:02d}"
    return window_id


def key_sentences(findings: dict, meta: dict) -> list[str]:
    """The three-sentence summary shown in the README."""
    region = meta["region"]["name"]
    below = _get(findings, "gp_evening_60", "municipalities_below_half")
    total = _get(findings, "gp_evening_60", "municipalities_total")
    morning = _get(findings, "reach_45", "median_wd_am")
    sunday = _get(findings, "reach_45", "median_su_am")
    drop = None if not morning or sunday is None else 1 - sunday / morning
    ratio = _get(findings, "pt_car_ratio_supermarket", "median_ratio_wd_am")
    over_three = _get(findings, "pt_car_ratio_supermarket", "share_over_3_wd_am")
    return [
        f"In {_count(below)} of {_count(total)} municipalities in {region}, fewer than half of "
        f"the residents can reach a family doctor's practice within 60 minutes by bus and "
        f"train on a weekday evening ({_window_span(meta, 'wd_pm')}).",
        f"Within 45 minutes, the median resident reaches {_count(morning)} people on a weekday "
        f"morning but only {_count(sunday)} on a Sunday morning ({_pct(drop)} fewer).",
        f"Getting to the nearest supermarket takes the median resident {_ratio(ratio)} as long "
        f"by public transport as by car; for {_pct(over_three)} of residents it takes more than "
        f"three times as long or is not possible within two hours.",
    ]


def detailed_results(findings: dict, meta: dict) -> list[str]:
    """All headline numbers as a bullet list (used in CASE_STUDY.md)."""

    def by_window(finding: str, prefix: str, formatter) -> str:
        parts = []
        for window in meta.get("windows", []):
            value = _get(findings, finding, f"{prefix}{window['id']}")
            parts.append(f"{window['label']}: {formatter(value)}")
        return "; ".join(parts)

    best = findings.get("municipal_gap_45", {})
    return [
        "Share of residents who cannot reach a family doctor within 60 minutes — "
        + by_window("gp_evening_60", "population_share_without_", _pct),
        "Median number of people reachable within 45 minutes — "
        + by_window("reach_45", "median_", _count)
        + f"; by car: {_count(_get(findings, 'reach_45', 'car_median'))}",
        "Median ratio of public transport to car travel time to the nearest supermarket — "
        + by_window("pt_car_ratio_supermarket", "median_ratio_", _ratio),
        "Share of residents without a hospital within 60 minutes — "
        + by_window("hospital_60", "population_share_without_", _pct),
        "Share of residents within 30 minutes of a served rail station — "
        + by_window("rail_station_30", "population_share_within_", _pct),
        f"Average reachable population within 45 minutes (weekday morning): highest in "
        f"{best.get('best_label', 'n/a')} ({_count(best.get('best'))}), lowest in "
        f"{best.get('worst_label', 'n/a')} ({_count(best.get('worst'))}).",
    ]


def render_block(findings: dict, meta: dict, *, detailed: bool) -> str:
    dates = meta["service_dates"]
    header = (
        f"_Snapshot `{meta['snapshot_id']}` · timetable days {dates['weekday']} (weekday) and "
        f"{dates['sunday']} (Sunday) · written by the pipeline, do not edit by hand._"
    )
    if detailed:
        body = "\n".join(f"- {line}" for line in detailed_results(findings, meta))
    else:
        body = " ".join(key_sentences(findings, meta))
    return f"{header}\n\n{body}"


def replace_block(text: str, name: str, content: str) -> str:
    """Replace the text between ``<!-- name:start -->`` and ``<!-- name:end -->``."""
    pattern = re.compile(rf"(<!-- {name}:start -->)(.*?)(<!-- {name}:end -->)", re.DOTALL)
    return pattern.sub(lambda match: f"{match.group(1)}\n{content}\n{match.group(3)}", text)


def update_documents(root: Path, findings: dict, meta: dict) -> None:
    targets = (("README.md", "findings", False), ("CASE_STUDY.md", "results", True))
    for filename, block, detailed in targets:
        path = root / filename
        if path.exists():
            content = render_block(findings, meta, detailed=detailed)
            path.write_text(replace_block(path.read_text(encoding="utf-8"), block, content),
                            encoding="utf-8")
