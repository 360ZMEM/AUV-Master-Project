#!/usr/bin/env python3
"""Summarize frozen PVS short-scan shape decisions without rerunning the plant."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "AUV-Master-Mag/results/v2/inspection_flythrough_pvs_final_20260926"
DEFAULT_OUTPUT = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data/28_dynamic_shape_decision_summary.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(input_dir: Path) -> dict[str, object]:
    cases = []
    for shape in ("wire", "dipole"):
        for seed in (101, 102, 103):
            path = input_dir / f"{shape}_seed_{seed}.csv"
            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            scan = next(row for row in rows if row["fwhm_width_m"])
            width = float(scan["fwhm_width_m"])
            declared = float(scan["inspection_declared_residual"])
            competing = float(scan["inspection_competing_residual"])
            support = float(scan["fwhm_shape_support_widths"])
            reasons = scan["fwhm_reasons"].split("|")
            assert any(row["lateral_valid"] == "True" for row in rows)
            assert all(row["depth_valid"] == "False" for row in rows)
            assert "depth_shape_support_insufficient" in reasons
            if shape == "wire":
                assert "depth_shape_ambiguous" in reasons
            cases.append({
                "shape": shape, "seed": seed, "source_csv": str(path.relative_to(ROOT)),
                "source_sha256": digest(path), "first_decision_time_s": float(scan["time_s"]),
                "width_m": width,
                "counterfactual_declared_dipole_distance_m": 0.5 * width,
                "counterfactual_error_to_synthetic_3m_m": abs(0.5 * width - 3.0),
                "equal_dof_declared_residual": declared,
                "equal_dof_competing_residual": competing,
                "declared_advantage": competing - declared,
                "minimum_side_support_widths": support,
                "reason_codes": reasons,
                "any_lateral_valid": True,
                "any_depth_valid": False,
            })
    return {
        "role": "frozen_dynamic_pvs_shape_decision_audit",
        "source_script_sha256": digest(Path(__file__)),
        "synthetic_true_vertical_separation_m": 3.0,
        "declared_shape": "thesis_dipole",
        "counterfactual_caveat": "width/2 is a diagnostic of wrong-coefficient risk, not a published estimate",
        "cases": cases,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = audit(args.input_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"audited {len(result['cases'])} frozen PVS runs: {args.output}")
