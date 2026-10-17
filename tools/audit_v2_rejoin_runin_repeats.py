#!/usr/bin/env python3
"""Audit archived three-seed native-PVS route run-in cases without rerunning ROS."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "AUV-Master-Mag/results/v2/inspection_rejoin_runin_20260926"
OUT = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data"


def audit_case(seed: int, offset: int, current: str) -> dict:
    sign = "minus" if offset < 0 else "plus"
    name = f"{sign}{abs(offset)}_{current}"
    folder = SOURCE / (f"adaptive_{name}" if seed == 101 else f"rep_seed{seed}_{name}")
    summary_path = folder / f"wire_seed_{seed}_summary.json"
    csv_path = folder / f"wire_seed_{seed}.csv"
    summary = json.loads(summary_path.read_text())
    with csv_path.open(newline="") as stream:
        track = [row for row in csv.DictReader(stream)
                 if row["mode"] == "track" and float(row["x_m"]) >= 0.]
    errors = [abs(float(row["y_m"]) - offset) for row in track]
    expected_runin = 20. if ((offset > 0 and current == "north") or
                              (offset < 0 and current == "south")) else 5.
    result = {
        "seed": seed,
        "offset_m": offset,
        "current_direction": current,
        "current_speed_mps": .05,
        "completed": bool(summary["completed"]),
        "first_hold_reason": summary["first_hold_reason"],
        "depth_published": bool(summary["depth_published"]),
        "selected_runin_m": summary["rejoin_runin_selected_m"],
        "track_samples": len(errors),
        "track_true_lateral_mae_m": sum(errors) / len(errors) if errors else None,
        "track_true_lateral_max_m": max(errors) if errors else None,
        "summary_source": str(summary_path.relative_to(ROOT)),
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    }
    assert result["completed"] and result["first_hold_reason"] is None
    assert not result["depth_published"] and result["selected_runin_m"] == expected_runin
    assert result["track_samples"] > 0
    assert result["track_true_lateral_mae_m"] < 1.
    assert result["track_true_lateral_max_m"] < 2.
    return result


def main() -> None:
    cases = [audit_case(seed, offset, current)
             for seed in (101, 102, 103)
             for offset in (-8, -2, 2, 8)
             for current in ("south", "north")]
    payload = {
        "scope": "24 discrete ROS2/PID/guard/UDP/native PVS synthetic single-wire cases; three noise seeds, not a field-success probability",
        "quality_reference": {"mean_route_offset_m": 1., "max_route_offset_m": 2.},
        "all_24_complete": all(item["completed"] for item in cases),
        "all_24_within_example_lateral_gates": all(
            item["track_true_lateral_mae_m"] < 1. and item["track_true_lateral_max_m"] < 2.
            for item in cases),
        "all_24_depth_unpublished": all(not item["depth_published"] for item in cases),
        "mae_range_m": [min(item["track_true_lateral_mae_m"] for item in cases),
                        max(item["track_true_lateral_mae_m"] for item in cases)],
        "max_error_range_m": [min(item["track_true_lateral_max_m"] for item in cases),
                              max(item["track_true_lateral_max_m"] for item in cases)],
        "cases": cases,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "26_current_conditioned_rejoin_three_seed_audit.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(cases)} cases; MAE {payload['mae_range_m']}; max {payload['max_error_range_m']}")


if __name__ == "__main__":
    main()
