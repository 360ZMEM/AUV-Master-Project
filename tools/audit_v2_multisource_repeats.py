#!/usr/bin/env python3
"""Audit three-seed full-chain cable-identity counterexamples."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "AUV-Master-Mag/results/v2/inspection_multisource_identity_20260927"
OUTPUT = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results/data/28_multisource_identity_three_seed_audit.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    cases = []
    for seed in (101, 102, 103):
        for kind in ("broad_map", "narrow_cue", "narrow_cue_clean"):
            directory = INPUT / (kind if seed == 101 else f"{kind}_seed{seed}")
            summary_path = directory / f"wire_seed_{seed}_summary.json"
            csv_path = directory / f"wire_seed_{seed}.csv"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            with csv_path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            true_errors = [abs(float(row["y_m"]) - 6.) for row in rows
                           if row["mode"] == "track" and float(row["x_m"]) >= 0.]
            true_mae = sum(true_errors) / len(true_errors) if true_errors else None
            true_max = max(true_errors) if true_errors else None
            assert summary["seed"] == seed and summary["cable_lateral_m"] == 6.
            assert summary["secondary_cable_gain_nt"] == (0. if kind == "narrow_cue_clean" else 10.)
            assert summary["secondary_cable_lateral_m"] == (None if kind == "narrow_cue_clean" else 9.)
            assert not summary["depth_published"] and all(row["depth_valid"] == "False" for row in rows)
            if kind == "broad_map":
                assert summary["completed"] and summary["route_quality_valid"]
                assert true_mae > 1. and true_max > 2.
            elif kind == "narrow_cue":
                assert not summary["completed"] and not summary["ever_track"]
                assert "side_hint_observation_inconsistent" in summary["last_lateral_reason_codes"]
                assert float(rows[-1]["thrust_percent"]) == 0. and int(rows[-1]["rpm"]) == 0
            else:
                assert summary["completed"] and summary["route_quality_valid"]
                assert true_mae < 1. and true_max < 2.
            cases.append({
                "seed": seed, "kind": kind, "source_dir": str(directory.relative_to(ROOT)),
                "summary_sha256": sha(summary_path), "csv_sha256": sha(csv_path),
                "magnetic_center_m": summary["last_fwhm_center_m"],
                "completed": summary["completed"], "route_quality_valid": summary["route_quality_valid"],
                "first_hold_reason": summary["first_hold_reason"],
                "online_mae_m": summary["route_observed_lateral_mae_m"],
                "online_max_m": summary["route_observed_lateral_max_m"],
                "true_mae_m": true_mae, "true_max_m": true_max,
                "true_track_samples": len(true_errors),
                "depth_published": summary["depth_published"],
                "last_lateral_reason_codes": summary["last_lateral_reason_codes"],
                "final_pid_thrust_percent": float(rows[-1]["thrust_percent"]),
                "final_udp_rpm": int(rows[-1]["rpm"]),
            })
    result = {
        "role": "three_seed_closed_loop_multi_source_identity_audit",
        "source_script_sha256": sha(Path(__file__)),
        "model_caveat": "synthetic scalar-envelope superposition; not a measured multi-cable electromagnetic field",
        "cases": cases,
        "counts": {
            "broad_wrong_completions": sum(c["kind"] == "broad_map" and c["completed"] and
                                           c["true_mae_m"] > 1. and c["true_max_m"] > 2. for c in cases),
            "narrow_interference_rejections": sum(c["kind"] == "narrow_cue" and not c["completed"] for c in cases),
            "narrow_clean_qualified_completions": sum(c["kind"] == "narrow_cue_clean" and c["completed"]
                                                       and c["true_mae_m"] < 1. and c["true_max_m"] < 2. for c in cases),
            "depth_publications": sum(c["depth_published"] for c in cases),
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
