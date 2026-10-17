#!/usr/bin/env python3
"""Plot the opt-in synthetic sonar identity gate and its fail-closed cases."""

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
SOURCE = ROOT / "AUV-Master-Mag/results/v2/inspection_sonar_identity_gate_20260927"
OLD = ROOT / "AUV-Master-Mag/results/v2/inspection_multisource_identity_20260927/broad_map"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "29_runtime_sonar_identity_gate"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(directory: Path, seed: int = 101) -> tuple[dict, list[dict]]:
    summary_path = directory / f"wire_seed_{seed}_summary.json"
    csv_path = directory / f"wire_seed_{seed}.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    summary.update({
        "source_summary": str(summary_path.relative_to(ROOT)),
        "source_summary_sha256": sha(summary_path),
        "source_csv": str(csv_path.relative_to(ROOT)),
        "source_csv_sha256": sha(csv_path),
        "final_pid_thrust_percent": float(rows[-1]["thrust_percent"]),
        "final_udp_rpm": int(rows[-1]["rpm"]),
    })
    return summary, rows


def main() -> None:
    broad, broad_rows = load(OLD)
    clean, clean_rows = load(SOURCE / "locked_clean")
    mixed, mixed_rows = load(SOURCE / "locked_mixed")
    missing, missing_rows = load(SOURCE / "locked_missing")
    uncalibrated, uncalibrated_rows = load(SOURCE / "locked_uncalibrated")
    assert broad["completed"] and broad["last_fwhm_center_m"] > 7.
    assert clean["completed"] and clean["ever_track"] and clean["last_sonar_identity_reason"] == "accepted"
    assert not mixed["completed"] and not mixed["ever_track"]
    assert "runtime_identity_cue_inconsistent" in mixed["last_lateral_reason_codes"]
    assert mixed["last_sonar_identity_reason"] == "accepted"
    for item, reason in ((missing, "runtime_identity_cue_unavailable"),
                         (uncalibrated, "runtime_identity_cue_unavailable")):
        assert not item["completed"] and not item["ever_track"]
        assert reason in item["last_lateral_reason_codes"]
    assert uncalibrated["last_sonar_identity_reason"] == "sonar_identity_quality_unqualified"
    assert all(item["final_pid_thrust_percent"] == item["final_udp_rpm"] == 0.
               for item in (mixed, missing, uncalibrated))
    assert all(not item["depth_published"] for item in (clean, mixed, missing, uncalibrated))

    apply_thesis_style(base_font_size=8)
    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=5.15), constrained_layout=True)
    y = np.linspace(0., 13., 400)
    target = 20. / np.sqrt(1. + ((y - 6.) / 3.) ** 2)
    interferer = 10. / np.sqrt(1. + ((y - 9.) / 3.) ** 2)
    ax = axes[0, 0]
    ax.plot(y, target, color=PROPOSED, lw=1.2, label="单源异常")
    ax.plot(y, target + interferer, color=WARNING, lw=1.3, label="双源合成异常")
    ax.axvspan(5.5, 6.5, color=BASELINE_2, alpha=.18, label="声呐线索最大许可带")
    ax.axvline(6., color=REFERENCE, ls="--", lw=.8)
    ax.set(xlabel="横向位置 / m", ylabel="磁异常包络 / nT",
           title="(a) 单峰外观仍可能偏离目标缆")
    ax.legend(loc="upper left", fontsize=6)

    ax = axes[0, 1]
    labels = ["无声呐／双源", "声呐／单源", "声呐／双源"]
    centers = [broad["last_fwhm_center_m"], clean["last_fwhm_center_m"],
               mixed["last_fwhm_center_m"]]
    colors = [WARNING, BASELINE_2, PROPOSED]
    for i, (label, center, color) in enumerate(zip(labels, centers, colors)):
        ax.plot(center, 2 - i, "o", color=color, markersize=5)
        ax.text(center + .08, 2 - i + .08, f"{center:.2f} m", fontsize=6)
    ax.axvspan(5.5, 6.5, color=BASELINE_2, alpha=.15,
               label="许可带上界：6 ± 0.5 m")
    ax.axvline(6., color=REFERENCE, ls="--", lw=.8)
    ax.set(xlim=(5.2, 8.15), ylim=(-.55, 2.55), yticks=[0, 1, 2],
           yticklabels=labels[::-1], xlabel="确认阶段磁中心 / m",
           title="(b) 独立线索核对目标身份")
    ax.legend(loc="lower right", fontsize=6)

    ax = axes[1, 0]
    for rows, color, label in ((broad_rows, WARNING, "宽地图双源：误完成"),
                               (clean_rows, BASELINE_2, "声呐单源：完成"),
                               (mixed_rows, PROPOSED, "声呐双源：拒绝")):
        subset = [row for row in rows if float(row["x_m"]) >= -110.]
        ax.plot([float(row["x_m"]) for row in subset],
                [float(row["y_m"]) for row in subset],
                color=color, lw=1.05, label=label)
    ax.axhline(6., color=REFERENCE, ls="--", lw=.8)
    ax.axhline(9., color=WARNING, ls=":", lw=.7)
    ax.set(xlim=(-110., 85.), ylim=(-18., 18.), xlabel="沿先验方向 / m",
           ylabel="横向位置 / m", title="(c) ROS/PID/UDP/PVS 任务终态")
    ax.legend(loc="lower right", fontsize=5.8)

    ax = axes[1, 1]
    ax.set_axis_off()
    ax.set(title="(d) 确认门控的许可与拒绝")
    entries = [
        ("单源 + 合格声呐", "进入 Track，任务完成", BASELINE_2),
        ("双源 + 合格声呐", "中心不一致，零推进", PROPOSED),
        ("单源 + 声呐缺失", "证据不足，零推进", WARNING),
        ("单源 + 概率未标定", "质量不合格，零推进", WARNING),
    ]
    for i, (condition, outcome, color) in enumerate(entries):
        ypos = .87 - i * .2
        ax.text(.04, ypos, condition, transform=ax.transAxes, fontsize=7, va="center")
        ax.text(.97, ypos, outcome, transform=ax.transAxes, fontsize=7,
                ha="right", va="center", color=color)
        if i < len(entries) - 1:
            ax.plot([.04, .97], [ypos - .10, ypos - .10], transform=ax.transAxes,
                    color="#B8B8B8", lw=.5)
    ax.text(.04, .02, "声呐线与概率均为合成夹具；不代表物理声呐验收。",
            transform=ax.transAxes, fontsize=6, va="bottom")

    figures = PUBLICATION / "figures"
    save_figure(fig, figures / STEM, dpi=600)
    plt.close(fig)
    data = PUBLICATION / "data"
    payload = {
        "role": "opt_in_runtime_sonar_identity_gate_synthetic_dds_audit",
        "synthetic_caveat": "Sonar line and calibrated probability are injected fixtures; multi-source magnetic field is scalar-envelope superposition.",
        "target_y_m": 6., "interferer_y_m": 9., "maximum_sonar_half_width_m": .5,
        "implementation_sha256": {
            str(path): sha(ROOT / path) for path in (
                "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py",
                "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/identity_cue.py",
                "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py",
                "brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_sonar_identity_sim.yaml",
                "tools/smoke_v2_flythrough_ros_pvs.py",
            )
        },
        "cases": {"prior_broad_map_failure": broad, "final_clean": clean,
                  "final_mixed": mixed, "missing": missing, "uncalibrated": uncalibrated},
    }
    summary_path = data / f"{STEM}_summary.json"
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"script_sha256": sha(Path(__file__)), "summary_sha256": sha(summary_path),
                "png_sha256": sha(figures / f"{STEM}.png"),
                "pdf_sha256": sha(figures / f"{STEM}.pdf")}
    (data / f"{STEM}_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {key: item[key] for key in ("completed", "ever_track",
                       "last_lateral_reason_codes", "final_udp_rpm")}
                      for name, item in payload["cases"].items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
