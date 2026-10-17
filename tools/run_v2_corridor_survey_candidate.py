#!/usr/bin/env python3
"""Reproduce the isolated three-crossing magnetic corridor candidate and figure 45."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_1, BASELINE_2, PROPOSED, REFERENCE,
                               WARNING, apply_thesis_style, figure_size, save_figure)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "AUV-Master-Mag/src"))
from auv_mag_tracking.v2 import (  # noqa: E402
    CorridorSurveyConfig, FwhmConfig, InspectionConfig, SurveyProfile,
    assess_turn_feasibility, build_corridor_survey, estimate_survey_line,
)

RESULT = ROOT / "AUV-Master-Mag/results/v2/corridor_survey_candidate_20260927"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "45_corridor_survey_geometry_candidate"
CASES = ("isolated_wire", "intermediate_shape", "transient_middle",
         "separated_neighbor", "fused_neighbor_1m")
LABELS = ("单源直导线", "中间场形", "单站暂态", "分离邻源", "近距融合邻源")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def profiles_for(plan, case: str, seed: int) -> list[SurveyProfile]:
    rng = np.random.default_rng(seed)
    result = []
    for idx, along_m in enumerate(plan.station_along_m):
        lateral = np.linspace(-15., 15., 151)
        true_center = 6. + .05 * along_m
        q = ((lateral - true_center) / 3.) ** 2
        exponent = .7 if case == "intermediate_shape" else .5
        anomaly = 20. / (1. + q) ** exponent
        if case in {"separated_neighbor", "fused_neighbor_1m"}:
            separation = 7. if case == "separated_neighbor" else 1.
            anomaly += 20. / np.sqrt(1. + ((lateral - true_center - separation) / 3.) ** 2)
        if case == "transient_middle" and idx == 1:
            anomaly = 20. / np.sqrt(1. + ((lateral + 5.) / 3.) ** 2)
        position = plan.station_centers_xy_m[idx] + lateral[:, None] * plan.prior_normal_xy
        result.append(SurveyProfile(idx, position, 2. + anomaly + rng.normal(0., .02, len(lateral)), .02))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=50)
    parser.add_argument("--output-dir", type=Path, default=RESULT)
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("--seeds must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    policy = CorridorSurveyConfig()
    boundary = np.array([[-10., -24.], [75., -24.], [75., 24.], [-10., 24.]])
    plan = build_corridor_survey(np.array([[0., 0.], [60., 0.]]), boundary, policy)
    turn_check = assess_turn_feasibility(plan, 50.)
    fwhm = FwhmConfig(shape_model="thesis_dipole", altitude_m=0.)
    inspection = InspectionConfig(enabled=True)
    records = []
    for case in CASES:
        for seed in range(101, 101 + args.seeds):
            estimate = estimate_survey_line(plan, profiles_for(plan, case, seed),
                                            policy, fwhm, inspection)
            true_center = 6. + .05 * plan.station_along_m
            error = (None if not estimate.geometry_valid else float(np.mean(np.abs(
                estimate.station_centers_xy_m[:, 1] - true_center))))
            records.append({"case": case, "seed": seed,
                            "geometry_valid": estimate.geometry_valid,
                            "center_mae_m": error,
                            "heading_error_deg": (None if not estimate.geometry_valid else
                                                  abs(estimate.heading_deviation_deg - np.degrees(np.arctan(.05)))),
                            "burial_depth_m": estimate.burial_depth_m,
                            "reason_codes": "|".join(estimate.reason_codes)})
    csv_path = args.output_dir / "cases.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    metrics = {}
    for case in CASES:
        selected = [record for record in records if record["case"] == case]
        accepted = [record for record in selected if record["geometry_valid"]]
        metrics[case] = {
            "geometry_accepted": len(accepted), "total": len(selected),
            "accepted_center_mae_mean_m": (float(np.mean([r["center_mae_m"] for r in accepted]))
                                           if accepted else None),
            "accepted_heading_error_mean_deg": (float(np.mean([r["heading_error_deg"] for r in accepted]))
                                                if accepted else None),
            "reason_codes": sorted({reason for record in selected for reason in record["reason_codes"].split("|") if reason}),
        }
    summary = {
        "evidence_level": "isolated_analytic_magnetic_candidate",
        "target_identity_verified": False,
        "physical_motion_verified": False,
        "representative_50m_turn_radius_straight_runs_sufficient": turn_check.straight_run_sufficient,
        "representative_50m_turn_radius_reason_codes": turn_check.reason_codes,
        "depth_published": False,
        "experiment": {"seeds": args.seeds, "seed_start": 101,
                       "prior_lateral_m": 0., "target_start_lateral_m": 6.,
                       "target_slope_m_per_m": .05, "station_count": 3,
                       "station_spacing_m": policy.station_spacing_m,
                       "crossing_half_width_m": policy.half_width_m,
                       "planned_waypoint_distance_m": plan.estimated_distance_m,
                       "ideal_travel_time_without_turns_s": plan.estimated_distance_m / policy.velocity_mps,
                       "magnetic_noise_sigma_nt": .02},
        "metrics": metrics,
        "cases_csv_sha256": sha(csv_path),
        "source_sha256": {str(path.relative_to(ROOT)): sha(path) for path in (
            ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/corridor_survey.py",
            ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/fwhm.py",
            ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/lateral.py",
            Path(__file__).resolve())},
    }
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    apply_thesis_style(base_font_size=8.1)
    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=5.4), constrained_layout=True)
    ax = axes[0, 0]
    ax.plot([0, 60], [0, 0], ls="--", color=REFERENCE, label="粗先验")
    x_true = np.linspace(0, 60, 100)
    ax.plot(x_true, 6 + .05*x_true, color=PROPOSED, lw=1.6, label="合成目标线")
    ax.plot(plan.waypoints_xy_m[:, 0], plan.waypoints_xy_m[:, 1],
            color=BASELINE_1, lw=1., marker="o", ms=2.5, label="三次横切几何")
    representative = estimate_survey_line(plan, profiles_for(plan, "isolated_wire", 101),
                                          policy, fwhm, inspection)
    ax.scatter(representative.station_centers_xy_m[:, 0], representative.station_centers_xy_m[:, 1],
               color=WARNING, marker="x", s=40, zorder=3, label="测得磁中心")
    ax.set(xlim=(-3, 63), ylim=(-18, 18), xlabel="沿先验位置 / m", ylabel="横向位置 / m",
           title="(a) 宽先验横切几何（尚非可执行航迹）")
    ax.legend(loc="lower right", fontsize=6.5)

    ax = axes[0, 1]
    for case, label, color in (("isolated_wire", "单源", PROPOSED),
                               ("fused_neighbor_1m", "1 m 邻源融合", WARNING),
                               ("separated_neighbor", "7 m 邻源", BASELINE_2)):
        profile = profiles_for(plan, case, 101)[0]
        ax.plot(profile.positions_xy_m[:, 1], profile.envelope_nt,
                label=label, color=color, lw=1.1)
    ax.axvline(6., color=REFERENCE, ls="--", lw=.8, label="目标真值")
    ax.set(xlim=(-15, 15), xlabel="横切位置 / m", ylabel="磁包络 / nT",
           title="(b) 单峰、可分双源与不可辨融合")
    ax.legend(loc="upper left", fontsize=6.5)

    ax = axes[1, 0]
    counts = [metrics[case]["geometry_accepted"] for case in CASES]
    ax.bar(np.arange(len(CASES)), counts, color=[PROPOSED, PROPOSED, BASELINE_2,
                                                BASELINE_2, WARNING])
    ax.set_xticks(range(len(CASES)), LABELS, rotation=18, ha="right")
    ax.set(ylabel=f"几何许可次数 / {args.seeds}", ylim=(0, args.seeds*1.12),
           title="(c) 三横切几何门：拒绝不连续或可分邻源")
    for i, count in enumerate(counts):
        ax.text(i, count + args.seeds*.015, str(count), ha="center", fontsize=7)

    ax = axes[1, 1]
    for idx, case in enumerate(CASES):
        errors = [r["center_mae_m"] for r in records if r["case"] == case and r["geometry_valid"]]
        if errors:
            ax.scatter(np.full(len(errors), idx), errors, alpha=.35, s=12,
                       color=WARNING if case == "fused_neighbor_1m" else PROPOSED)
            ax.plot(idx, np.mean(errors), marker="_", ms=15, color="black", lw=1.5)
    ax.axhline(.5, color=REFERENCE, ls="--", lw=.8)
    ax.set_xticks(range(len(CASES)), LABELS, rotation=18, ha="right")
    ax.set(ylabel="获许可中心相对目标真值 MAE / m", ylim=(0, .75),
           title="(d) 融合邻源仍可获几何许可，身份需外部约束")
    paths = save_figure(fig, PUBLICATION / "figures" / STEM)
    plt.close(fig)
    manifest = {"summary_sha256": sha(summary_path), "cases_csv_sha256": sha(csv_path),
                "figure_paths": [str(path.relative_to(ROOT)) for path in paths],
                "figure_sha256": {str(path.relative_to(ROOT)): sha(path) for path in paths}}
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": str(summary_path), "metrics": metrics}, ensure_ascii=False))


if __name__ == "__main__":
    main()
