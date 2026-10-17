#!/usr/bin/env python3
"""Figure 48: analytic route-feasibility window and measured PVS track budget."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_1, GRID_COLOR, PROPOSED, REFERENCE,
                               WARNING, apply_thesis_style, figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "AUV-Master-Mag/results/v2/shallow_zigzag_pvs_envelope_3m_20260927"
PUB = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
THESIS = ROOT / "docs/thesis/figures/experiments/fwhm_v2"
STEM = "48_shallow_zigzag_geometry_budget_insight"
CASES = ("zero_wire", "positive_current", "negative_mirrored", "negative_wrong_side")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    data = {name: json.loads((RESULTS / name / "summary.json").read_text(encoding="utf-8"))
            for name in CASES}
    source = data["zero_wire"]["source_sha256"]
    assert all(item["source_sha256"] == source for item in data.values())
    assert all(sha(ROOT / path) == digest for path, digest in source.items())
    assert all(data[name]["geometry_valid"] and data[name]["terminal_phase"] == "survey_path_end"
               for name in CASES[:3])
    assert data["negative_wrong_side"]["terminal_phase"] == "boundary_margin_exhausted"
    assert data["negative_wrong_side"]["geometry_valid"] is False
    assert all(data[name]["navigation_lateral_margin_m"] == 3.0 for name in CASES)

    apply_thesis_style(base_font_size=8)
    fig, axes = plt.subplots(1, 2, figsize=figure_size(height=3.25), constrained_layout=True)
    ax = axes[0]
    L = np.linspace(90, 175, 350)
    required = 6.0 + np.tan(np.deg2rad(1.15)) * 3.0 * L + 5.2 + 1.5 + 3.0
    curvature_limit = L ** 2 / (50.0 * np.pi ** 2)
    boundary_limit = np.full_like(L, 37.0)
    upper = np.minimum(curvature_limit, boundary_limit)
    feasible = upper >= required
    ax.fill_between(L, required, upper, where=feasible, color=PROPOSED, alpha=.16,
                    label="几何可行域")
    ax.plot(L, required, color=PROPOSED, lw=1.5, label="覆盖所需最小振幅")
    ax.plot(L, curvature_limit, color=REFERENCE, lw=1.2, ls="--", label="50 m 曲率半径上限")
    ax.plot(L, boundary_limit, color=BASELINE_1, lw=1., ls=":", label="走廊净距上限")
    ax.scatter([125], [22], marker="x", s=40, color=WARNING, zorder=5)
    ax.annotate("旧 22/125\n按 3 m 预算不足", (125, 22), xytext=(101, 27.5),
                fontsize=6.3, arrowprops=dict(arrowstyle="-", color=WARNING, lw=.6))
    ax.scatter([135], [24], marker="o", s=35, color=PROPOSED, edgecolor="white", zorder=6)
    ax.annotate("本次 24/135\n仅余 0.17 m", (135, 24), xytext=(143, 20.5),
                fontsize=6.3, arrowprops=dict(arrowstyle="-", color=PROPOSED, lw=.6))
    ax.set(xlim=(90, 175), ylim=(18, 38), xlabel="单次半波沿线距离 L / m",
           ylabel="横向振幅 A / m", title="(a) 覆盖、转弯与走廊三重预算")
    ax.legend(loc="upper left", fontsize=6.1)

    ax = axes[1]
    names = CASES[:3]
    labels = ("零流", "+0.05 m/s，选对侧", "-0.05 m/s，选对侧")
    errors = [data[name]["reference_track_max_m"] for name in names]
    assert all(value <= 3.0 for value in errors)
    bars = ax.barh(np.arange(3), errors, height=.5,
                   color=(PROPOSED, BASELINE_1, BASELINE_1), edgecolor=REFERENCE)
    for bar, value in zip(bars, errors):
        ax.text(value + .08, bar.get_y() + bar.get_height() / 2., f"{value:.3f} m",
                va="center", fontsize=7)
    ax.axvline(3.0, color=WARNING, lw=1.2, ls="--", label="声明导航余量 3 m")
    ax.set_yticks(np.arange(3), labels)
    ax.set(xlim=(0, 3.9), ylim=(2.95, -.6), xlabel="PVS 最大参考轨迹横偏 / m",
           title="(b) 正确起始侧的动力学复核")
    ax.legend(loc="upper right", fontsize=6.5)
    ax.text(.1, 2.72, "错侧起步：边界余量耗尽，最大横偏 30.494 m（图外）",
            fontsize=6.2, color=WARNING)
    pub_paths = save_figure(fig, PUB / "figures" / STEM)
    thesis_paths = save_figure(fig, THESIS / STEM)
    plt.close(fig)

    summary = {
        "evidence_level": "analytic_geometry_and_native_pvs_one_seed",
        "case_source_sha256": source,
        "case_summary_sha256": {name: sha(RESULTS / name / "summary.json") for name in CASES},
        "conditions": {
            "station_count": 3, "prior_offset_bound_m": 6.0,
            "prior_heading_error_bound_deg": 1.15, "half_crossing_bound_m": 5.2,
            "tail_margin_m": 1.5, "navigation_lateral_margin_m": 3.0,
            "minimum_turn_radius_m": 50.0, "boundary_halfwidth_m": 42.0,
            "boundary_margin_m": 5.0,
        },
        "candidate": {"amplitude_m": 24.0, "half_wavelength_m": 135.0,
                      "coverage_required_m": float(6 + math.tan(math.radians(1.15)) * 405 + 5.2 + 1.5 + 3),
                      "minimum_curvature_radius_m": 135**2 / (24 * math.pi**2)},
        "maximum_reference_track_error_m": {name: data[name]["reference_track_max_m"]
                                            for name in CASES},
        "field_release_authorized": False,
    }
    path = PUB / "data" / f"{STEM}_summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"summary_sha256": sha(path), "figure_sha256": {
        str(item.relative_to(ROOT)): sha(item) for item in (*pub_paths, *thesis_paths)},
        "plot_script_sha256": sha(Path(__file__).resolve())}
    (PUB / "data" / f"{STEM}_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": str(path), "candidate_slack_m": 24-summary["candidate"]["coverage_required_m"]}))


if __name__ == "__main__":
    main()
