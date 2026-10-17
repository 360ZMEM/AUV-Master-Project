#!/usr/bin/env python3
"""Audit opt-in runtime identity authority with a displaced static side hint."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from thesis_plot_style import (BASELINE_1, BASELINE_2, PROPOSED, REFERENCE,  # noqa: E402
                               WARNING, apply_thesis_style, figure_size)

OLD = ROOT / "AUV-Master-Mag/results/v2/inspection_static_hint_bias_20260927"
NEW = ROOT / "AUV-Master-Mag/results/v2/inspection_sonar_map_bias_recovery_20260927"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
CASES = {
    "map_only_clean": (OLD / "biased_clean", False, False, False),
    "map_only_double": (OLD / "biased_double", True, False, False),
    "sonar_old_order_clean": (NEW / "old_order_clean", False, True, False),
    "sonar_authority_clean": (NEW / "clean_sonar_target", False, True, True),
    "sonar_authority_double": (NEW / "double_sonar_target", True, True, True),
    "sonar_authority_dropout": (NEW / "sonar_dropout_hold", False, True, True),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_case(name: str, folder: Path, neighbor: bool, sonar: bool,
              authority: bool) -> tuple[dict, list[dict]]:
    summary_file = folder / "wire_seed_101_summary.json"
    csv_file = folder / "wire_seed_101.csv"
    summary = json.loads(summary_file.read_text())
    with csv_file.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    error = [abs(float(row["y_m"]) - 6.) for row in rows
             if row["mode"] == "track" and float(row["x_m"]) >= 0.]
    assert summary["seed"] == 101 and summary["cable_lateral_m"] == 6.
    assert summary["secondary_cable_gain_nt"] == (10. if neighbor else 0.)
    assert summary["sonar_identity_mode"] == ("target" if sonar else "off")
    assert not summary["depth_published"]
    assert all(row["depth_valid"] == "False" for row in rows)
    return ({
        "name": name,
        "neighbor": neighbor,
        "runtime_sonar": sonar,
        "runtime_identity_supersedes_side_hint_center": authority,
        "summary_path": str(summary_file.relative_to(ROOT)),
        "csv_path": str(csv_file.relative_to(ROOT)),
        "summary_sha256": sha(summary_file),
        "csv_sha256": sha(csv_file),
        "completed": summary["completed"],
        "ever_track": summary["ever_track"],
        "duration_s": summary["duration_s"],
        "magnetic_center_m": summary["last_fwhm_center_m"],
        "last_lateral_reason_codes": summary["last_lateral_reason_codes"],
        "sonar_reason": summary["last_sonar_identity_reason"],
        "sonar_track_fault": summary["sonar_track_fault"],
        "first_hold_reason": summary["first_hold_reason"],
        "first_hold_s": summary["first_hold_s"],
        "hold_to_final_displacement_m": summary["hold_to_final_displacement_m"],
        "hold_samples": sum(row["mode"] == "hold" for row in rows),
        "hold_nonzero_target_samples": sum(
            row["mode"] == "hold" and float(row["target_speed_mps"]) != 0. for row in rows),
        "hold_nonzero_pid_samples": sum(
            row["mode"] == "hold" and float(row["thrust_percent"]) != 0. for row in rows),
        "hold_nonzero_udp_samples": sum(
            row["mode"] == "hold" and int(row["rpm"]) != 0 for row in rows),
        "online_track_mae_m": summary["route_observed_lateral_mae_m"],
        "target_true_track_mae_m": float(np.mean(error)) if error else None,
        "target_true_track_max_m": max(error) if error else None,
        "target_true_track_samples": len(error),
        "depth_published": summary["depth_published"],
        "final_pid_thrust_percent": float(rows[-1]["thrust_percent"]),
        "final_udp_rpm": int(rows[-1]["rpm"]),
    }, rows)


def segments(rows: list[dict]) -> list[tuple[str, float, float]]:
    out = []
    current = rows[0]["mode"]
    start = float(rows[0]["time_s"])
    previous = start
    for row in rows[1:]:
        moment = float(row["time_s"])
        if row["mode"] != current:
            out.append((current, start, moment))
            current, start = row["mode"], moment
        previous = moment
    out.append((current, start, previous + .25))
    return out


def plot(cases: dict[str, dict], rows: dict[str, list[dict]], path: Path) -> None:
    apply_thesis_style(layout="full")
    import matplotlib.pyplot as plt
    fig, (left, right) = plt.subplots(
        1, 2, figsize=figure_size(height=3.95),
        gridspec_kw={"width_ratios": [1., 1.45]},
    )
    # At first Track sample, the real software cue has a 0.430 m half-width.
    accepted_row = next(row for row in rows["sonar_authority_clean"]
                        if row["mode"] == "track")
    sonar_center = float(accepted_row["runtime_identity_center_m"])
    sonar_half = float(accepted_row["runtime_identity_half_width_m"])
    left.plot([6.6, 7.5], [3, 3], linewidth=9, color=BASELINE_1,
              solid_capstyle="butt", label="偏移静态地图")
    left.plot([sonar_center - sonar_half, sonar_center + sonar_half], [2, 2],
              linewidth=9, color=PROPOSED, solid_capstyle="butt", label="运行时声呐区间")
    left.scatter([cases["sonar_authority_clean"]["magnetic_center_m"]], [1],
                 s=68, color=BASELINE_2, zorder=3)
    left.scatter([cases["sonar_authority_double"]["magnetic_center_m"]], [0],
                 s=68, color=WARNING, zorder=3)
    left.axvline(6., color=REFERENCE, linestyle="--", linewidth=1.)
    left.set(xlim=(5., 8.15), ylim=(-.45, 3.5), xlabel="相对先验横向位置 / m",
             yticks=(0, 1, 2, 3),
             yticklabels=("融合峰：拒绝", "单源峰：准入", "声呐目标线", "偏移地图"),
             title="(a) 身份线索的授权顺序")
    left.tick_params(axis="y", labelsize=8, pad=2)
    left.text(6.04, 3.35, "目标真值", fontsize=7, color=REFERENCE)

    names = ("map_only_double", "sonar_old_order_clean",
             "sonar_authority_clean", "sonar_authority_double",
             "sonar_authority_dropout")
    labels = ("地图单独·邻源", "声呐＋旧序·单源",
              "声呐主导·单源", "声呐主导·邻源", "声呐主导·失鲜")
    colors = {"search": "#8C8C8C", "confirm": BASELINE_1,
              "track": PROPOSED, "hold": WARNING}
    for y, name in enumerate(names):
        for mode, start, end in segments(rows[name]):
            right.broken_barh([(start, end - start)], (y - .29, .58),
                              facecolors=colors.get(mode, "#CCCCCC"), edgecolors="none")
        item = cases[name]
        right.scatter([item["duration_s"]], [y],
                      marker="o" if item["completed"] else "X",
                      s=35, color=PROPOSED if item["completed"] else WARNING, zorder=4)
    right.set(xlim=(0., 1165.), ylim=(-.55, 4.55),
              yticks=range(len(labels)), yticklabels=labels,
              xlabel="任务时间 / s", title="(b) 同一偏移地图的任务出口")
    right.tick_params(axis="y", labelsize=8, pad=2)
    right.invert_yaxis()
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    right.legend(handles=[Patch(color=colors[k], label=v)
                          for k, v in (("search", "搜索"), ("confirm", "确认"),
                                       ("track", "跟踪"))]
                 + [Line2D([], [], marker="X", color=WARNING, linestyle="None",
                           markersize=6, label="拒止")],
                 loc="upper left", bbox_to_anchor=(0., -.28), ncol=4,
                 fontsize=7, borderaxespad=0.)
    fig.subplots_adjust(wspace=.68, bottom=.25, top=.87)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".png"), dpi=600)
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)


def main() -> None:
    cases, rows = {}, {}
    for name, (folder, neighbor, sonar, authority) in CASES.items():
        cases[name], rows[name] = read_case(name, folder, neighbor, sonar, authority)
    assert not cases["map_only_clean"]["completed"]
    assert cases["map_only_double"]["completed"]
    assert not cases["sonar_old_order_clean"]["completed"]
    assert "side_hint_observation_inconsistent" in cases["sonar_old_order_clean"]["last_lateral_reason_codes"]
    assert cases["sonar_authority_clean"]["completed"]
    assert cases["sonar_authority_clean"]["target_true_track_mae_m"] < 1.
    assert not cases["sonar_authority_double"]["completed"]
    assert "runtime_identity_cue_inconsistent" in cases["sonar_authority_double"]["last_lateral_reason_codes"]
    assert cases["sonar_authority_double"]["final_pid_thrust_percent"] == 0.
    assert cases["sonar_authority_double"]["final_udp_rpm"] == 0
    dropout = cases["sonar_authority_dropout"]
    assert dropout["sonar_track_fault"] == "dropout"
    assert dropout["ever_track"] and not dropout["completed"]
    assert dropout["first_hold_reason"] == "flythrough_runtime_identity_lost"
    assert dropout["hold_samples"] == 61
    assert dropout["hold_nonzero_target_samples"] == 0
    assert dropout["hold_nonzero_pid_samples"] == 0
    assert dropout["hold_nonzero_udp_samples"] == 0
    installed_launch_log = NEW / "installed_launch_idle.log"
    launch_text = installed_launch_log.read_text()
    assert "cable tracking v2 active: flythrough" in launch_text
    assert "auv_controller_node started" in launch_text
    assert "ModuleNotFoundError" not in launch_text
    payload = {
        "role": "synthetic_runtime_sonar_authority_displaced_map_closed_loop",
        "source_script_sha256": sha(Path(__file__)),
        "harness_sha256": sha(ROOT / "tools/smoke_v2_flythrough_ros_pvs.py"),
        "flythrough_source_sha256": sha(ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py"),
        "sonar_authority_config_sha256": sha(NEW / "sonar_authoritative_biased_map.yaml"),
        "sonar_old_order_config_sha256": sha(NEW / "sonar_old_order_biased_map.yaml"),
        "magnetic_package_setup_sha256": sha(ROOT / "AUV-Master-Mag/setup.py"),
        "installed_launch_idle_log_sha256": sha(installed_launch_log),
        "target_y_m": 6., "neighbor_y_m": 9., "neighbor_gain_nt": 10.,
        "biased_hint_m": [6.6, 7.5], "seed": 101,
        "caveat": "Sonar target line/quality and scalar magnetic envelopes are synthetic; PVS/ROS/UDP loop has no physical sonar or PC104.",
        "cases": cases,
    }
    output = PUBLICATION / "data/55_sonar_map_bias_recovery.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    plot(cases, rows, PUBLICATION / "figures/55_sonar_map_bias_recovery")
    print(json.dumps({name: {"completed": item["completed"],
                             "center_m": item["magnetic_center_m"],
                             "true_mae_m": item["target_true_track_mae_m"]}
                      for name, item in cases.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
