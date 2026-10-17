#!/usr/bin/env python3
"""Plot the bounded-Hold disposition alarm without changing frozen Figure 31."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import PROPOSED, REFERENCE, WARNING, apply_thesis_style, figure_size, save_figure


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "AUV-Master-Mag/results/v2/inspection_hold_budget_20260927/switch_cross"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "32_bounded_hold_disposition"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    csv_path = RUN / "wire_seed_101.csv"
    summary_path = RUN / "wire_seed_101_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    held = [row for row in rows if row["mode"] == "hold"]
    assert held and float(held[0]["time_s"]) == summary["first_hold_s"]
    assert summary["first_recovery_required_s"] == summary["first_hold_s"]
    assert summary["first_recovery_reason"] == "hold_boundary_budget_exhausted"
    assert summary["post_hold_nonzero_rpm_ticks"] == 0
    t = np.array([float(row["time_s"]) - summary["first_hold_s"] for row in held])
    clearance = np.array([float(row["hold_budget_clearance_m"]) for row in held])
    remaining = np.array([float(row["hold_budget_remaining_m"]) for row in held])
    required = clearance - remaining
    rpm = np.array([int(row["rpm"]) for row in held])
    assert np.all(rpm == 0) and np.all(remaining < 0)

    apply_thesis_style(base_font_size=8.4)
    fig, axes = plt.subplots(1, 2, figsize=figure_size(height=2.9), constrained_layout=True)
    axes[0].plot(t, clearance, color=PROPOSED, lw=1.5, label="实有边界净距")
    axes[0].plot(t, required, color=WARNING, lw=1.4, ls="--", label="保守所需净距")
    axes[0].axhline(10., color=REFERENCE, lw=.9, ls=":", label="候选停止余量")
    axes[0].set(xlabel="Hold 后仿真时间 / s", ylabel="边界净距 / m",
                title="(a) 零推力不满足限时处置空间预算")
    axes[0].legend(loc="lower left", fontsize=6.7)
    axes[1].plot(t, remaining, color=WARNING, lw=1.5, label="剩余空间预算")
    axes[1].axhline(0., color=REFERENCE, lw=.9, ls="--")
    axes[1].fill_between(t, remaining, 0., where=remaining < 0, color=WARNING, alpha=.15)
    axes[1].set(xlabel="Hold 后仿真时间 / s", ylabel="净距减所需预算 / m",
                title="(b) 首周期上报需要上级处置")
    axes[1].legend(loc="lower left", fontsize=6.7)
    figures = PUBLICATION / "figures"
    save_figure(fig, figures / STEM, dpi=600)
    plt.close(fig)
    payload = {
        "role": "synthetic_hold_budget_alarm_without_recovery_action",
        "first_hold_s": summary["first_hold_s"],
        "first_recovery_required_s": summary["first_recovery_required_s"],
        "first_recovery_reason": summary["first_recovery_reason"],
        "clearance_at_hold_m": float(clearance[0]),
        "required_clearance_at_hold_m": float(required[0]),
        "remaining_budget_at_hold_m": float(remaining[0]),
        "zero_rpm_hold_ticks": int(len(held)),
        "source_csv": str(csv_path.relative_to(ROOT)),
        "source_csv_sha256": sha(csv_path),
        "source_summary": str(summary_path.relative_to(ROOT)),
        "source_summary_sha256": sha(summary_path),
        "caveat": "PVS and synthetic sonar; alarm only, without an accepted upper-level/PC104 recovery action.",
    }
    data = PUBLICATION / "data"
    data_path = data / f"{STEM}_summary.json"
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"plot_script_sha256": sha(Path(__file__)),
                "summary_sha256": sha(data_path),
                "png_sha256": sha(figures / f"{STEM}.png"),
                "pdf_sha256": sha(figures / f"{STEM}.pdf")}
    (data / f"{STEM}_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
