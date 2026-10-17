#!/usr/bin/env python3
"""Audit route-wide target-association withdrawal after a close sonar switch."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from thesis_plot_style import (PROPOSED, REFERENCE, WARNING, apply_thesis_style,
                               figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "AUV-Master-Mag/results/v2/inspection_track_identity_reassociation_20260927"
OLD_CONFIG = ROOT / "AUV-Master-Mag/results/v2/inspection_joint_wrong_target_20260927/sonar_with_independent_anchor_sim.yaml"
NEW_CONFIG = ROOT / "AUV-Master-Mag/results/v2/inspection_target_exclusive_corridor_20260927/sonar_with_exclusive_corridor_sim.yaml"
TIGHT_CONFIG = RESULTS / "sonar_with_route_exclusive_corridor_sim.yaml"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "59_track_identity_route_corridor"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> tuple[dict, list[dict]]:
    directory = RESULTS / name
    summary_path = directory / "wire_seed_101_summary.json"
    csv_path = directory / "wire_seed_101.csv"
    log_path = RESULTS / f"{name}.log"
    summary = json.loads(summary_path.read_text())
    with csv_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    installed = Path(summary["v2_node_loaded_path"])
    assert summary["installed_v2_node_mode"] and "/install/" in str(installed)
    assert digest(installed) == digest(ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py")
    true_errors = [abs(float(row["y_m"]) - 6.) for row in rows
                   if row["mode"] == "track" and float(row["x_m"]) >= 0.]
    hold_rows = [row for row in rows if row["mode"] == "hold"
                 and float(row["time_s"]) >= float(summary["first_hold_s"])] if summary["first_hold_s"] is not None else []
    switched_rows = [row for row in rows if float(row["time_s"]) >= 585.
                     and row["mode"] == "track"]
    record = {
        "case": name,
        "summary_path": str(summary_path.relative_to(ROOT)),
        "summary_sha256": digest(summary_path),
        "csv_path": str(csv_path.relative_to(ROOT)),
        "csv_sha256": digest(csv_path),
        "log_path": str(log_path.relative_to(ROOT)),
        "log_sha256": digest(log_path),
        "installed_node_path": str(installed),
        "installed_node_sha256": digest(installed),
        "completed": summary["completed"],
        "ever_track": summary["ever_track"],
        "first_track_s": summary["first_track_s"],
        "first_hold_s": summary["first_hold_s"],
        "first_hold_reason": summary["first_hold_reason"],
        "duration_s": summary["duration_s"],
        "switch_offset_m": summary["sonar_track_switch_offset_m"],
        "switch_position_variance_m2": summary["sonar_track_position_variance_m2"],
        "accepted_track_ticks_after_585_s": sum(row["runtime_identity_reason"] == "accepted"
                                                 for row in switched_rows),
        "positive_speed_track_ticks_after_585_s": sum(float(row["target_speed_mps"]) > 0.
                                                       for row in switched_rows),
        "post_hold_ticks": len(hold_rows),
        "post_hold_all_three_commands_zero": all(
            float(row["target_speed_mps"]) == float(row["thrust_percent"]) == int(row["rpm"]) == 0.
            for row in hold_rows),
        "post_hold_pvs_displacement_m": summary["hold_to_final_displacement_m"],
        "target_true_track_mae_m": statistics.mean(true_errors) if true_errors else None,
        "target_true_track_max_m": max(true_errors) if true_errors else None,
        "depth_published": summary["depth_published"],
    }
    return record, rows


def main() -> None:
    old_config = yaml.safe_load(OLD_CONFIG.read_text())
    new_config = yaml.safe_load(NEW_CONFIG.read_text())
    new_fly = new_config["cable_tracking"]["v2"]["flythrough"]
    assert (new_fly.pop("runtime_target_exclusive_min_m"),
            new_fly.pop("runtime_target_exclusive_max_m")) == (5.45, 6.55)
    assert old_config == new_config, "fault-case YAMLs differ beyond the exclusive corridor"

    data = {name: load(name) for name in (
        "old_switch_final", "new_switch_final", "normal_final",
        "route_corridor_normal_v2")}
    cases = {name: record for name, (record, _) in data.items()}
    old, protected, normal, tight = cases.values()
    old_rows, protected_rows, normal_rows = [data[name][1] for name in
                                            ("old_switch_final", "new_switch_final", "normal_final")]
    assert old["first_track_s"] == protected["first_track_s"] == normal["first_track_s"] == 577.
    assert old["switch_offset_m"] == protected["switch_offset_m"] == .565
    assert old["switch_position_variance_m2"] == protected["switch_position_variance_m2"] == .0415
    assert old["first_hold_s"] == 669.5 and old["first_hold_reason"] == "flythrough_runtime_identity_diverged"
    assert old["positive_speed_track_ticks_after_585_s"] > 300
    assert protected["first_hold_s"] == 585.
    assert protected["first_hold_reason"] == "flythrough_runtime_identity_exclusive_corridor_inconsistent"
    assert protected["accepted_track_ticks_after_585_s"] == 0
    assert protected["post_hold_ticks"] >= 241 and protected["post_hold_all_three_commands_zero"]
    assert not protected["completed"] and normal["completed"]
    assert not tight["completed"] and tight["first_hold_s"] == 623.5
    assert tight["first_hold_reason"] == "flythrough_runtime_identity_exclusive_corridor_inconsistent"
    tight_config = yaml.safe_load(TIGHT_CONFIG.read_text())
    assert tight_config["cable_tracking"]["v2"]["flythrough"]["runtime_target_exclusive_max_m"] == 6.5
    assert all(not case["depth_published"] for case in cases.values())
    first_old = next(row for row in old_rows if float(row["time_s"]) == 585.)
    first_protected = next(row for row in protected_rows if float(row["time_s"]) == 585.)
    assert first_old["runtime_identity_reason"] == first_protected["runtime_identity_reason"] == "accepted"
    assert first_old["mode"] == "track" and first_protected["mode"] == "hold"
    assert float(first_old["runtime_identity_center_m"]) > 6.5
    assert float(first_old["runtime_identity_track_residual_m"]) < float(first_old["runtime_identity_half_width_m"])

    apply_thesis_style(base_font_size=8)
    fig, axes = plt.subplots(1, 2, figsize=figure_size(height=2.65),
                             constrained_layout=True)
    ax = axes[0]
    cue = [row for row in old_rows if 575. <= float(row["time_s"]) <= 678.
           and row["runtime_identity_center_m"]]
    time = np.array([float(row["time_s"]) for row in cue])
    center = np.array([float(row["runtime_identity_center_m"]) for row in cue])
    half = np.array([float(row["runtime_identity_half_width_m"]) for row in cue])
    ax.axhspan(5.45, 6.55, color=PROPOSED, alpha=.12, label="目标专属走廊")
    ax.fill_between(time, center-half, center+half,
                    color=WARNING, alpha=.19, label="声呐 2σ 区间")
    ax.plot(time, center, color=WARNING, lw=1.1, label="声呐线中心")
    ax.axhline(6., color=REFERENCE, ls=":", lw=.8, label="指定目标 6 m")
    ax.axvline(585., color=REFERENCE, ls="--", lw=.8)
    ax.set(xlim=(575, 680), ylim=(5.3, 7.3),
           xlabel="仿真时间 / s", ylabel="横向位置 / m",
           title="(a) 合格声呐线索在 Track 中改指邻线")
    ax.legend(fontsize=5.6, ncol=2, loc="upper left")

    ax = axes[1]
    for rows, color, label, style, order in (
            (normal_rows, REFERENCE, "全程专属：正常任务", ":", 1),
            (old_rows, WARNING, "仅锚点：迟 84.5 s 撤权", "-", 3),
            (protected_rows, PROPOSED, "全程专属：首周期撤权", "-", 4)):
        subset = [row for row in rows if 575. <= float(row["time_s"]) <= 680.]
        ax.step([float(row["time_s"]) for row in subset],
                [float(row["target_speed_mps"]) for row in subset],
                where="post", lw=1.2, color=color, ls=style, zorder=order,
                label=label)
    ax.axvline(585., color=REFERENCE, ls="--", lw=.8)
    ax.set(xlim=(575, 680), ylim=(-.025, .35),
           xlabel="仿真时间 / s", ylabel="目标速度 / (m/s)",
           title="(b) 错目标线索下的许可撤销")
    handles, labels = ax.get_legend_handles_labels()
    ax.legend([handles[1], handles[2], handles[0]],
              [labels[1], labels[2], labels[0]], fontsize=5.7, loc="lower right")

    stem = PUBLICATION / "figures" / STEM
    save_figure(fig, stem)
    plt.close(fig)
    payload = {
        "role": "synthetic_installed_ros_route_target_association_continuity_counterexample_and_fix",
        "scope": "four independent seed-101 ROS/PID/guard/localhost-UDP/native-PVS runs including tight-corridor false rejection; synthetic sonar, target corridor and map; not physical association or success probability",
        "target_lateral_m": 6.,
        "exclusive_lateral_m": [5.45, 6.55],
        "switch_at_s": 585.,
        "cases": cases,
        "source_script_sha256": digest(Path(__file__)),
        "harness_sha256": digest(ROOT / "tools/smoke_v2_flythrough_ros_pvs.py"),
        "flythrough_sha256": digest(ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py"),
        "ros_node_sha256": digest(ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py"),
        "anchor_validator_sha256": digest(ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/runtime_target_anchor.py"),
        "old_config_sha256": digest(OLD_CONFIG),
        "new_config_sha256": digest(NEW_CONFIG),
        "tight_config_sha256": digest(TIGHT_CONFIG),
        "png_sha256": digest(stem.with_suffix(".png")),
        "pdf_sha256": digest(stem.with_suffix(".pdf")),
    }
    path = PUBLICATION / "data" / f"{STEM}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: {"completed": case["completed"],
                             "first_hold_s": case["first_hold_s"],
                             "accepted_track_ticks_after_585_s": case["accepted_track_ticks_after_585_s"]}
                      for name, case in cases.items()}, ensure_ascii=False))


def verify_historical_snapshot() -> None:
    """Verify Figure 59 without attributing old runs to evolved source files."""
    frozen = json.loads((PUBLICATION / "data" / f"{STEM}.json").read_text(encoding="utf-8"))
    for label, key in (("audit_script", "source_script_sha256"),
                       ("harness", "harness_sha256"),
                       ("flythrough", "flythrough_sha256"),
                       ("ros_node", "ros_node_sha256")):
        assert digest(PUBLICATION / frozen["source_snapshots"][label]) == frozen[key]
    for key, path in (("anchor_validator_sha256", ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/runtime_target_anchor.py"),
                      ("old_config_sha256", OLD_CONFIG), ("new_config_sha256", NEW_CONFIG),
                      ("tight_config_sha256", TIGHT_CONFIG),
                      ("png_sha256", PUBLICATION / "figures" / f"{STEM}.png"),
                      ("pdf_sha256", PUBLICATION / "figures" / f"{STEM}.pdf")):
        assert digest(path) == frozen[key]
    for case in frozen["cases"].values():
        for suffix in ("summary", "csv", "log"):
            assert digest(ROOT / case[f"{suffix}_path"]) == case[f"{suffix}_sha256"]
    print(json.dumps({"historical_snapshot_verified": True,
                      "cases": len(frozen["cases"]),
                      "regeneration_requires_frozen_sources": True}, ensure_ascii=False))


if __name__ == "__main__":
    frozen = json.loads((PUBLICATION / "data" / f"{STEM}.json").read_text(encoding="utf-8"))
    if (digest(Path(__file__)) == frozen["source_script_sha256"]
            and digest(ROOT / "tools/smoke_v2_flythrough_ros_pvs.py") == frozen["harness_sha256"]
            and digest(ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py") == frozen["flythrough_sha256"]
            and digest(ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py") == frozen["ros_node_sha256"]):
        main()
    else:
        verify_historical_snapshot()
