from __future__ import annotations

import csv
from pathlib import Path

from tools.aggregate_uncertainty_metrics import read_nis_event_metrics
from tools.uncertainty_metrics import _chi2_two_sided_95


def test_chi_square_bands_are_dimension_specific() -> None:
    lower_1, upper_1 = _chi2_two_sided_95(1)
    lower_3, upper_3 = _chi2_two_sided_95(3)

    assert lower_1 < lower_3
    assert upper_1 < upper_3
    assert abs(upper_1 - 5.02388619) < 1e-8
    assert abs(upper_3 - 9.34840360) < 1e-8


def test_nis_events_are_aggregated_by_source_and_dimension(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nis_events.csv"
    fields = [
        "source",
        "dimension",
        "nis",
        "nis_per_dof",
        "in_two_sided_95",
        "above_upper_95",
        "r_scale_after_update",
    ]
    rows = [
        {
            "source": "dvl_world",
            "dimension": 3,
            "nis": 3.0,
            "nis_per_dof": 1.0,
            "in_two_sided_95": True,
            "above_upper_95": False,
            "r_scale_after_update": 1.0,
        },
        {
            "source": "dvl_world",
            "dimension": 3,
            "nis": 12.0,
            "nis_per_dof": 4.0,
            "in_two_sided_95": False,
            "above_upper_95": True,
            "r_scale_after_update": 1.5,
        },
        {
            "source": "depth",
            "dimension": 1,
            "nis": 1.0,
            "nis_per_dof": 1.0,
            "in_two_sided_95": True,
            "above_upper_95": False,
            "r_scale_after_update": 1.0,
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summaries = read_nis_event_metrics(path)
    keyed = {
        (str(row["source"]), int(row["dimension"])): row for row in summaries
    }

    assert set(keyed) == {("dvl_world", 3), ("depth", 1)}
    assert keyed[("dvl_world", 3)]["event_count"] == 2
    assert keyed[("dvl_world", 3)]["coverage_95"] == 0.5
    assert keyed[("dvl_world", 3)]["upper_exceed_ratio"] == 0.5
    assert keyed[("depth", 1)]["nis_per_dof_mean"] == 1.0
