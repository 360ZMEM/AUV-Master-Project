#!/usr/bin/env python3
"""Show how phase-conditioned sonar identity monitoring survives rejoin and stops faults."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from thesis_plot_style import (BASELINE_2, PROPOSED, REFERENCE, WARNING,
                               apply_thesis_style, figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "AUV-Master-Mag/results/v2/inspection_identity_continuity_20260927"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "30_runtime_identity_continuity"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric(rows: list[dict], key: str) -> np.ndarray:
    return np.asarray([float(row[key]) if row.get(key) not in (None, "")
                       else float("nan") for row in rows], dtype=float)


def load(name: str) -> tuple[dict, list[dict]]:
    directory = SOURCE / name
    summary_path = directory / "wire_seed_101_summary.json"
    csv_path = directory / "wire_seed_101.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    true_error = np.asarray([abs(float(row["y_m"]) - 6.) for row in rows
                             if row["mode"] == "track" and float(row["x_m"]) >= 0.])
    track_width = np.asarray([float(row["runtime_identity_half_width_m"])
                              for row in rows if row["mode"] == "track"
                              and row["runtime_identity_half_width_m"]], dtype=float)
    summary.update({
        "source_summary": str(summary_path.relative_to(ROOT)),
        "source_summary_sha256": sha(summary_path),
        "source_csv": str(csv_path.relative_to(ROOT)),
        "source_csv_sha256": sha(csv_path),
        "last_pid_thrust_percent": float(rows[-1]["thrust_percent"]),
        "last_udp_rpm": int(rows[-1]["rpm"]),
        "max_accepted_cue_half_width_m": float(np.nanmax(numeric(rows, "runtime_identity_half_width_m"))),
        "max_track_cue_half_width_m": float(np.max(track_width)) if len(track_width) else None,
        "true_track_samples": int(len(true_error)),
        "true_track_mae_m": float(np.mean(true_error)) if len(true_error) else None,
        "true_track_max_m": float(np.max(true_error)) if len(true_error) else None,
    })
    return summary, rows


def main() -> None:
    clean, clean_rows = load("true_clean")
    dropout, dropout_rows = load("true_dropout")
    switched, switch_rows = load("true_switch")
    perturbed, perturbed_rows = load("true_nav_perturbed")
    assert clean["completed"] and clean["ever_track"] and not clean["depth_published"]
    assert perturbed["completed"] and perturbed["true_track_mae_m"] < 1.
    assert perturbed["true_track_max_m"] < 2. and not perturbed["depth_published"]
    assert clean["max_track_cue_half_width_m"] > .5
    assert clean["max_accepted_cue_half_width_m"] <= .6 + 1e-9
    assert dropout["first_hold_reason"] == "flythrough_runtime_identity_lost"
    assert switched["first_hold_reason"] == "flythrough_runtime_identity_diverged"
    assert all(not item["completed"] and item["ever_track"]
               and item["last_pid_thrust_percent"] == item["last_udp_rpm"] == 0.
               and not item["depth_published"] for item in (dropout, switched))

    apply_thesis_style(base_font_size=8.2)
    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=5.1), constrained_layout=True)
    cases = (("持续合格：完成", clean_rows, BASELINE_2),
             ("线索丢失：保持", dropout_rows, WARNING),
             ("改指邻缆：保持", switch_rows, PROPOSED))

    ax = axes[0, 0]
    for label, rows, color in cases:
        t = numeric(rows, "time_s")
        keep = (t >= 575.) & (t <= 620.)
        ax.plot(t[keep], numeric(rows, "y_m")[keep], color=color, lw=1.1, label=label)
    t_perturbed = numeric(perturbed_rows, "time_s")
    keep_perturbed = (t_perturbed >= 575.) & (t_perturbed <= 620.)
    ax.plot(t_perturbed[keep_perturbed], numeric(perturbed_rows, "y_m")[keep_perturbed],
            color=BASELINE_2, ls="--", lw=.9, label="导航受扰：完成")
    ax.set(xlim=(575., 620.), ylim=(14.25, 17.2), xlabel="任务时间 / s", ylabel="车辆横向位置 / m",
           title="(a) 确认后接入段：异常即停止")
    ax.legend(loc="lower right", fontsize=5.8)

    ax = axes[0, 1]
    for label, rows, color in cases:
        t = numeric(rows, "time_s")
        keep = (t >= 577.) & (t <= 590.)
        ax.plot(t[keep], numeric(rows, "runtime_identity_center_m")[keep],
                color=color, lw=1.15, label=label)
    ax.axhline(6.014, color=REFERENCE, ls="--", lw=.8, label="已确认磁中心")
    ax.axvline(585., color=REFERENCE, ls=":", lw=.7)
    ax.set(xlim=(577., 590.), ylim=(5.4, 9.5), xlabel="任务时间 / s",
           ylabel="有效声呐线横向中心 / m", title="(b) 声呐线索丢失或改指")
    ax.legend(loc="upper left", fontsize=5.8)

    ax = axes[1, 0]
    for label, rows, color in cases:
        t = numeric(rows, "time_s")
        keep = (t >= 577.) & (t <= 590.)
        ax.plot(t[keep], numeric(rows, "rpm")[keep], color=color, lw=1.1,
                label=label)
    ax.set(xlim=(577., 590.), ylim=(-5., 220.), xlabel="任务时间 / s",
           ylabel="UDP 解码主推转速 / rpm", title="(c) 异常后双层零推进")
    ax.legend(loc="upper right", fontsize=5.8)

    ax = axes[1, 1]
    t = numeric(clean_rows, "time_s")
    width = numeric(clean_rows, "runtime_identity_half_width_m")
    keep = (t >= 615.) & (t <= 645.)
    ax.plot(t[keep], width[keep], color=PROPOSED, lw=1.1,
            label="正常接入段观测半宽")
    ax.axhspan(.5, .6, color=PROPOSED, alpha=.08)
    ax.axhline(.5, color=WARNING, ls="--", lw=.85, label="Confirm 上限 0.5 m")
    ax.axhline(.6, color=BASELINE_2, ls="-.", lw=.85, label="Track 上限 0.6 m")
    ax.set(xlim=(615., 645.), ylim=(.48, .62), xlabel="任务时间 / s",
           ylabel="两倍标准差半宽 / m", title="(d) 跟踪期半宽跨过确认门限")
    ax.legend(loc="lower right", fontsize=5.8)

    figures = PUBLICATION / "figures"
    save_figure(fig, figures / STEM, dpi=600)
    plt.close(fig)
    data = PUBLICATION / "data"
    payload = {
        "role": "synthetic_runtime_sonar_identity_continuity_audit",
        "fixture_caveat": "Sonar line and calibrated probability are injected; no physical sonar or field cable was tested.",
        "confirm_half_width_limit_m": .5,
        "track_half_width_limit_m": .6,
        "maximum_cue_gap_s": 2.,
        "implementation_sha256": {
            str(path): sha(ROOT / path) for path in (
                "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py",
                "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/identity_cue.py",
                "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py",
                "brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_sonar_identity_sim.yaml",
                "tools/smoke_v2_flythrough_ros_pvs.py",
            )
        },
        "cases": {"clean": clean, "dropout": dropout, "switch": switched,
                  "navigation_perturbed": perturbed},
    }
    summary_path = data / f"{STEM}_summary.json"
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"script_sha256": sha(Path(__file__)), "summary_sha256": sha(summary_path),
                "png_sha256": sha(figures / f"{STEM}.png"),
                "pdf_sha256": sha(figures / f"{STEM}.pdf")}
    (data / f"{STEM}_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {key: item[key] for key in ("completed", "first_hold_reason",
                       "max_accepted_cue_half_width_m", "last_udp_rpm")}
                      for name, item in payload["cases"].items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
