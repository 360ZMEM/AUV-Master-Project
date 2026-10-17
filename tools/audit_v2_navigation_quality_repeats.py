#!/usr/bin/env python3
"""Audit all eight navigation-perturbed corner cases over three noise seeds."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "AUV-Master-Mag/results/v2/inspection_route_quality_gate_20260926"
OUTPUT = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data/27_navigation_quality_three_seed_audit.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    cases = []
    for seed in (101, 102, 103):
        for side in ("minus", "plus"):
            for offset in (2, 8):
                for flow in ("south", "north"):
                    stem = f"final_seed{seed}_{side}{offset}_{flow}"
                    # The first +2 m/north acceptance replay was archived
                    # before the other seven seed-101 corners were launched.
                    directory = INPUT / ("expected_accept_speed_bias_001"
                                         if stem == "final_seed101_plus2_north" else stem)
                    summary_path = directory / f"wire_seed_{seed}_summary.json"
                    csv_path = directory / f"wire_seed_{seed}.csv"
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                    expected_offset = offset if side == "plus" else -offset
                    expected_flow = 90.0 if flow == "north" else 270.0
                    expected_heading = 1.0 if side == "plus" else -1.0
                    assert summary["seed"] == seed and summary["case"] == "wire"
                    assert summary["cable_lateral_m"] == expected_offset
                    assert summary["current_direction_deg"] == expected_flow
                    assert summary["nav_heading_bias_deg"] == expected_heading
                    assert summary["nav_position_noise_std_m"] == 0.05
                    assert summary["nav_speed_bias_mps"] == 0.01
                    with csv_path.open(newline="", encoding="utf-8") as stream:
                        rows = list(csv.DictReader(stream))
                    assert all(row["depth_valid"] == "False" for row in rows), stem
                    assert any(row["endpoint_complete"] == "True" for row in rows) == summary["completed"], stem
                    if summary["route_quality_valid"]:
                        assert summary["route_observed_lateral_samples"] >= 200, stem
                        assert summary["route_observed_lateral_mae_m"] <= 1.0, stem
                        assert summary["route_observed_lateral_max_m"] <= 2.0, stem
                    cable_y = float(summary["cable_lateral_m"])
                    forward = [abs(float(row["y_m"]) - cable_y) for row in rows
                               if row["mode"] == "track" and float(row["x_m"]) >= 0]
                    if not forward:
                        raise AssertionError(f"no forward Track samples: {stem}")
                    true_mae = sum(forward) / len(forward)
                    true_max = max(forward)
                    cases.append({
                        "case": stem, "source_dir": str(directory.relative_to(ROOT)),
                        "summary_sha256": sha256(summary_path),
                        "csv_sha256": sha256(csv_path), "completed": summary["completed"],
                        "route_quality_valid": summary["route_quality_valid"],
                        "depth_published": summary["depth_published"],
                        "observed_mae_m": summary["route_observed_lateral_mae_m"],
                        "observed_max_m": summary["route_observed_lateral_max_m"],
                        "observed_samples": summary["route_observed_lateral_samples"],
                        "true_mae_m": true_mae, "true_max_m": true_max,
                        "true_samples": len(forward),
                        "first_hold_reason": summary["first_hold_reason"],
                        "nav_position_noise_std_m": summary["nav_position_noise_std_m"],
                        "nav_speed_bias_mps": summary["nav_speed_bias_mps"],
                        "nav_heading_bias_deg": summary["nav_heading_bias_deg"],
                    })
    result = {
        "role": "three_seed_navigation_quality_corner_audit",
        "source_script_sha256": sha256(Path(__file__)),
        "cases": cases,
        "counts": {
            "runs": len(cases),
            "completed": sum(bool(c["completed"]) for c in cases),
            "online_quality_pass": sum(bool(c["route_quality_valid"]) for c in cases),
            "true_example_1m_2m_pass": sum(c["true_mae_m"] <= 1 and c["true_max_m"] <= 2 for c in cases),
            "depth_published": sum(bool(c["depth_published"]) for c in cases),
        },
        "true_mae_range_m": [min(c["true_mae_m"] for c in cases), max(c["true_mae_m"] for c in cases)],
        "true_max_range_m": [min(c["true_max_m"] for c in cases), max(c["true_max_m"] for c in cases)],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
