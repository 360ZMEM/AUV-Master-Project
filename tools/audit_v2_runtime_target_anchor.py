#!/usr/bin/env python3
"""Archive a joint sonar/magnetic wrong-line counterexample and its anchor gate."""
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
SOURCE = ROOT / "AUV-Master-Mag/results/v2/inspection_joint_wrong_target_20260927"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "57_runtime_target_anchor_joint_wrong"
TARGET_Y_M = 6.


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> tuple[dict, list[dict]]:
    directory = SOURCE / f"final_{name}"
    summary_path = directory / "wire_seed_101_summary.json"
    csv_path = directory / "wire_seed_101.csv"
    log_path = SOURCE / f"final_{name}.log"
    summary = json.loads(summary_path.read_text())
    installed_path = Path(summary["v2_node_loaded_path"])
    assert summary["installed_v2_node_mode"] and "/install/" in str(installed_path)
    assert digest(installed_path) == digest(
        ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py")
    with csv_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    errors = [abs(float(row["y_m"]) - TARGET_Y_M) for row in rows
              if row["mode"] == "track" and float(row["x_m"]) >= 0.]
    transitions = []
    previous = None
    for row in rows:
        if row["mode"] != previous:
            transitions.append({"time_s": float(row["time_s"]), "mode": row["mode"]})
            previous = row["mode"]
    decision_row = next((row for row in rows if row["mode"] in {"track", "hold"}), None)
    return ({
        "case": name, "summary_source": str(summary_path.relative_to(ROOT)),
        "summary_sha256": digest(summary_path),
        "csv_source": str(csv_path.relative_to(ROOT)), "csv_sha256": digest(csv_path),
        "log_source": str(log_path.relative_to(ROOT)), "log_sha256": digest(log_path),
        "installed_v2_node_path": str(installed_path),
        "installed_v2_node_sha256": digest(installed_path),
        "completed": summary["completed"], "ever_track": summary["ever_track"],
        "duration_s": summary["duration_s"],
        "magnetic_center_m": summary["last_fwhm_center_m"],
        "lateral_reason_codes": summary["last_lateral_reason_codes"],
        "online_track_mae_m": summary["route_observed_lateral_mae_m"],
        "target_true_track_mae_m": float(np.mean(errors)) if errors else None,
        "target_true_track_max_m": float(np.max(errors)) if errors else None,
        "target_true_track_samples": len(errors),
        "depth_published": summary["depth_published"],
        "sonar_line_lateral_m": summary["sonar_line_lateral_m"],
        "last_identity_reason": summary["last_sonar_identity_reason"],
        "confirm_sonar_center_m": (float(decision_row["runtime_identity_center_m"])
                                   if decision_row is not None and decision_row["runtime_identity_center_m"] else None),
        "confirm_sonar_half_width_m": (float(decision_row["runtime_identity_half_width_m"])
                                       if decision_row is not None and decision_row["runtime_identity_half_width_m"] else None),
        "final_target_speed_mps": float(rows[-1]["target_speed_mps"]),
        "final_pid_thrust_percent": float(rows[-1]["thrust_percent"]),
        "final_udp_rpm": int(rows[-1]["rpm"]),
        "transitions": transitions,
    }, rows)


def main() -> None:
    cases = {}
    raw = {}
    for name in ("before_anchor", "wrong_with_anchor", "correct_with_anchor"):
        cases[name], raw[name] = load(name)
    old, rejected, correct = [cases[name] for name in
                              ("before_anchor", "wrong_with_anchor", "correct_with_anchor")]
    assert old["completed"] and old["target_true_track_mae_m"] > 1.
    assert not rejected["completed"] and not rejected["ever_track"]
    assert "runtime_target_anchor_inconsistent" in rejected["lateral_reason_codes"]
    assert rejected["final_target_speed_mps"] == rejected["final_pid_thrust_percent"] == rejected["final_udp_rpm"] == 0.
    assert correct["completed"] and correct["target_true_track_mae_m"] < 1.
    assert all(not case["depth_published"] for case in cases.values())
    assert abs(old["magnetic_center_m"] - rejected["magnetic_center_m"]) < 1e-9
    assert old["last_identity_reason"] == rejected["last_identity_reason"] == "accepted"

    apply_thesis_style(base_font_size=8)
    fig, axes = plt.subplots(2, 2, figsize=figure_size(height=5.1), constrained_layout=True)
    lateral = np.linspace(-3., 15., 500)
    target = 20. / np.sqrt(1. + ((lateral - 6.) / 3.) ** 2)
    neighbor = 10. / np.sqrt(1. + ((lateral - 9.) / 3.) ** 2)
    ax = axes[0, 0]
    ax.plot(lateral, target, color=PROPOSED, lw=1.0, label="目标缆")
    ax.plot(lateral, neighbor, color=BASELINE_2, lw=1.0, label="合成邻源")
    ax.plot(lateral, target + neighbor, color=WARNING, lw=1.3, label="融合磁包络")
    ax.axvspan(6.6, 7.5, color=WARNING, alpha=.12, label="偏移搜索地图")
    ax.axvspan(5.8, 6.2, color=PROPOSED, alpha=.16, label="独立目标锚点")
    ax.axvline(7.026, color=WARNING, ls=":", lw=1.1, label="共同错线 7.026 m")
    ax.set(xlabel="横向位置 / m", ylabel="异常磁包络 / nT",
           xlim=(2.5, 11.5), title="(a) 声磁一致仍可能属于错误目标")
    ax.legend(fontsize=5.7, ncol=2, loc="upper left")

    ax = axes[0, 1]
    for name, color, label in (("before_anchor", WARNING, "无锚点：错误完成"),
                               ("wrong_with_anchor", REFERENCE, "有锚点：确认拒绝"),
                               ("correct_with_anchor", PROPOSED, "有锚点：真目标完成")):
        rows = [row for row in raw[name] if float(row["x_m"]) >= -110.]
        ax.plot([float(row["x_m"]) for row in rows],
                [float(row["y_m"]) for row in rows],
                color=color, lw=1.0, label=label)
    refused = raw["wrong_with_anchor"][-1]
    ax.scatter([float(refused["x_m"])], [float(refused["y_m"])],
               marker="x", s=38, linewidth=1.3, color=REFERENCE, zorder=4)
    ax.axhline(6., color=PROPOSED, ls="--", lw=.7)
    ax.axhline(9., color=BASELINE_2, ls=":", lw=.7)
    ax.set(xlabel="沿先验方向 / m", ylabel="横向位置 / m", xlim=(-110, 85),
           ylim=(-15, 17), title="(b) 同一 ROS/UDP/PVS 执行链的航迹")
    ax.legend(fontsize=5.8, loc="lower right")

    ax = axes[1, 0]
    labels = ["共同错线\n无锚点", "共同错线\n有锚点", "真实单源\n有锚点"]
    for i, (name, color) in enumerate((("before_anchor", WARNING),
                                       ("wrong_with_anchor", REFERENCE),
                                       ("correct_with_anchor", PROPOSED))):
        case = cases[name]
        ax.barh(2 - i, case["duration_s"], color=color, alpha=.78, height=.45)
        ax.text(case["duration_s"] + 12., 2 - i,
                "完成" if case["completed"] else "Confirm 拒绝",
                fontsize=6.2, va="center")
    ax.set(yticks=[2, 1, 0], yticklabels=labels,
           xlim=(0, 1280), xlabel="终态时间 / s",
           title="(c) 错目标在 Confirm 被独立锚点拦截")
    ax.grid(axis="y", visible=False)

    ax = axes[1, 1]
    for i, name in enumerate(("before_anchor", "correct_with_anchor")):
        case = cases[name]
        ax.bar(i - .18, case["online_track_mae_m"], width=.34,
               color=BASELINE_2, label="在线贴峰 MAE" if i == 0 else None)
        ax.bar(i + .18, case["target_true_track_mae_m"], width=.34,
               color=WARNING, label="目标真值 MAE" if i == 0 else None)
    ax.axhline(1., color=REFERENCE, ls="--", lw=.7, label="示例 1 m 门")
    ax.set(xticks=[0, 1], xticklabels=["共同错线", "真实单源"],
           ylim=(0, 1.35), ylabel="完整正向 Track 横偏 / m",
           title="(d) 贴峰质量与目标真值分离")
    ax.legend(fontsize=5.9, loc="upper right")

    figure = PUBLICATION / "figures" / STEM
    figure.parent.mkdir(parents=True, exist_ok=True)
    save_figure(fig, figure)
    plt.close(fig)

    old_config = SOURCE.parent / "inspection_sonar_map_bias_recovery_20260927" / "sonar_authoritative_biased_map.yaml"
    new_config = SOURCE / "sonar_with_independent_anchor_sim.yaml"
    payload = {
        "role": "synthetic_joint_wrong_sonar_magnetic_target_association_counterexample_and_optional_anchor_fix",
        "scope": "three separate seed-101 installed-v2 ROS/PID/guard/localhost-UDP/native-PVS runs; synthetic sonar, magnetic sources, and anchor; not physical success rates",
        "target_lateral_m": 6., "neighbor_lateral_m": 9., "neighbor_gain_nt": 10.,
        "biased_search_hint_m": [6.6, 7.5], "independent_anchor_m": [5.8, 6.2],
        "joint_wrong_sonar_line_m": 7.026, "seed": 101,
        "cases": cases,
        "source_script_sha256": digest(Path(__file__)),
        "harness_sha256": digest(ROOT / "tools/smoke_v2_flythrough_ros_pvs.py"),
        "flythrough_sha256": digest(ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py"),
        "ros_node_sha256": digest(ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py"),
        "anchor_validator_sha256": digest(ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/runtime_target_anchor.py"),
        "old_config_sha256": digest(old_config), "new_config_sha256": digest(new_config),
        "png_sha256": digest(figure.with_suffix(".png")),
        "pdf_sha256": digest(figure.with_suffix(".pdf")),
    }
    data = PUBLICATION / "data" / f"{STEM}.json"
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {"completed": case["completed"],
                             "true_track_mae_m": case["target_true_track_mae_m"],
                             "reason_codes": case["lateral_reason_codes"]}
                      for name, case in cases.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
