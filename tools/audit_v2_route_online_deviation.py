#!/usr/bin/env python3
"""Audit finite-Track route deviation withdrawal and post-Hold drift."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yaml

from thesis_plot_style import (PROPOSED, REFERENCE, WARNING, apply_thesis_style,
                               figure_size, save_figure)


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "AUV-Master-Mag/results/v2/inspection_route_online_deviation_20260927"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "60_route_deviation_withdrawal_and_drift"
NODE = ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py"
CORE = ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py"
HARNESS = ROOT / "tools/smoke_v2_flythrough_ros_pvs.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> tuple[dict, list[dict], dict]:
    directory = RESULTS / name
    summary_path = directory / "wire_seed_101_summary.json"
    csv_path = directory / "wire_seed_101.csv"
    log_path = RESULTS / f"{name}.log"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    installed = Path(summary["v2_node_loaded_path"])
    assert summary["installed_v2_node_mode"] and "/install/" in str(installed)
    assert digest(installed) == digest(NODE)
    assert all(summary[key] for key in ("native_pvs", "ros_dds", "protocol_encoded",
                                        "bridge_and_guard_connected"))
    assert not summary["hardware_connected"] and not summary["depth_published"]
    assert len(rows) == summary["ticks"] and summary["seed"] == 101
    assert log_path.is_file() and log_path.stat().st_size > 0
    hashes = {"summary_sha256": digest(summary_path), "csv_sha256": digest(csv_path),
              "log_sha256": digest(log_path)}
    return summary, rows, hashes


def main() -> None:
    normal, normal_rows, normal_hashes = load("normal_final")
    bounded, bounded_rows, bounded_hashes = load("current_step_0p04")
    fault, fault_rows, fault_hashes = load("current_step_0p4_live")
    assert len({item["config_file"] for item in (normal, bounded, fault)}) == 1
    config = yaml.safe_load((ROOT / normal["config_file"]).read_text(encoding="utf-8"))
    assert "hold_budget" not in config["cable_tracking"]["v2"]
    assert all(item["first_inspection_s"] == 839.5 for item in (normal, bounded, fault))
    assert normal["inspection_current_step_mps"] is None and normal["completed"]
    assert bounded["inspection_current_step_mps"] == .04 and bounded["completed"]
    assert fault["inspection_current_step_mps"] == .4 and not fault["completed"]
    assert normal["first_hold_s"] is None and bounded["first_hold_s"] is None
    assert normal["route_observed_lateral_max_m"] < 2.
    assert bounded["route_observed_lateral_max_m"] < 2.
    assert fault["first_hold_s"] == 850.
    assert fault["first_hold_reason"] == "flythrough_route_deviation_exceeded"
    assert fault["route_observed_lateral_max_m"] > 2.
    assert fault["post_hold_nonzero_rpm_ticks"] == 0
    assert fault["hold_to_final_displacement_m"] > 20.
    assert fault["max_abs_y_m"] > 30.
    first_hold_index = next(i for i, row in enumerate(fault_rows) if row["mode"] == "hold")
    first_hold = fault_rows[first_hold_index]
    previous = fault_rows[first_hold_index - 1]
    assert float(first_hold["time_s"]) == 850.
    assert float(previous["route_observed_lateral_max_m"]) <= 2.
    assert float(first_hold["route_observed_lateral_max_m"]) > 2.
    assert first_hold["hold_budget_reason"] == "hold_budget_unconfigured"
    hold_rows = [row for row in fault_rows if 850. <= float(row["time_s"]) <= 910.]
    assert len(hold_rows) == 241
    assert all(row["mode"] == "hold" and float(row["target_speed_mps"]) == 0.
               and float(row["thrust_percent"]) == 0. and int(row["rpm"]) == 0
               for row in hold_rows)
    boundary_cross = next(float(row["time_s"]) for row in fault_rows
                          if float(row["time_s"]) >= 850. and float(row["y_m"]) > 30.)
    assert boundary_cross > 850.

    apply_thesis_style(base_font_size=8.5)
    fig, axes = plt.subplot_mosaic([["error", "speed"], ["drift", "drift"]],
                                   figsize=figure_size(height=4.25), constrained_layout=True)
    ax = axes["error"]
    for rows, color, label, line in (
            (normal_rows, REFERENCE, "零流正常", ":"),
            (bounded_rows, PROPOSED, "+0.04 m/s 横流", "--"),
            (fault_rows, WARNING, "+0.40 m/s 横流", "-")):
        subset = [row for row in rows if 839. <= float(row["time_s"]) <= 852.
                  and row["route_observed_lateral_max_m"]]
        ax.plot([float(row["time_s"]) for row in subset],
                [float(row["route_observed_lateral_max_m"]) for row in subset],
                color=color, ls=line, lw=1.2, label=label)
    ax.axhline(2., color=REFERENCE, ls="-.", lw=.8, label="巡检横偏上限 2 m")
    ax.axvline(850., color=WARNING, ls=":", lw=.8)
    ax.set(xlim=(839, 852), ylim=(0, 2.4), xlabel="仿真时间 / s",
           ylabel="相对估计线累计最大横偏 / m", title="(a) 首次越界即撤权")
    ax.legend(fontsize=7.0, ncol=1, loc="upper left")

    ax = axes["speed"]
    subset = [row for row in fault_rows if 843. <= float(row["time_s"]) <= 856.]
    ax.step([float(row["time_s"]) for row in subset],
            [float(row["target_speed_mps"]) for row in subset],
            where="post", color=WARNING, lw=1.4)
    ax.axvline(844.5, color=REFERENCE, ls=":", lw=.8, label="横流突增")
    ax.axvline(850., color=PROPOSED, ls="--", lw=.9, label="三层零命令")
    ax.set(xlim=(843, 856), ylim=(-.03, .36), xlabel="仿真时间 / s",
           ylabel="目标速度 / (m/s)", title="(b) ROS--PID--UDP 撤权")
    ax.legend(fontsize=7.2, loc="upper right")

    ax = axes["drift"]
    subset = [row for row in fault_rows if 848. <= float(row["time_s"]) <= 910.]
    ax.plot([float(row["time_s"]) for row in subset],
            [float(row["y_m"]) for row in subset],
            color=WARNING, lw=1.3, label="PVS 实际横向位置")
    estimate_upper_m = float(fault["last_fwhm_center_m"]) + 2.
    ax.axhline(estimate_upper_m, color=PROPOSED, ls="--", lw=.9,
               label="冻结估计线 + 2 m")
    ax.axhline(30., color=REFERENCE, ls="-.", lw=.9, label="合成搜索边界")
    ax.axvline(850., color=PROPOSED, ls=":", lw=.8)
    ax.axvline(boundary_cross, color=WARNING, ls=":", lw=.8)
    ax.set(xlim=(848, 910), ylim=(5., 33.), xlabel="仿真时间 / s",
           ylabel="实际横向位置 / m", title="(c) 零命令后仍受超界横流推动")
    ax.legend(fontsize=7.3, loc="upper left")

    stem = PUBLICATION / "figures" / STEM
    save_figure(fig, stem)
    plt.close(fig)
    payload = {
        "role": "installed_ros_native_pvs_route_deviation_withdrawal_and_coast_boundary",
        "scope": "three independent seed-101 synthetic ROS/PID/guard/localhost-UDP/native-PVS runs; no physical current or stopping evidence",
        "configured_online_lateral_limit_m": 2.,
        "hold_budget_configured": False,
        "fault_hold_budget_reason": "hold_budget_unconfigured",
        "current_step_start_s": 844.5,
        "fault_first_hold_s": 850.,
        "fault_post_hold_zero_command_cycles": len(hold_rows),
        "fault_boundary_cross_s": boundary_cross,
        "cases": {
            name: {"completed": summary["completed"],
                   "first_hold_s": summary["first_hold_s"],
                   "first_hold_reason": summary["first_hold_reason"],
                   "route_observed_lateral_max_m": summary["route_observed_lateral_max_m"],
                   "hold_to_final_displacement_m": summary["hold_to_final_displacement_m"],
                   **hashes}
            for name, summary, hashes in (
                ("normal_final", normal, normal_hashes),
                ("current_step_0p04", bounded, bounded_hashes),
                ("current_step_0p4_live", fault, fault_hashes))},
        "source_script_sha256": digest(Path(__file__)),
        "harness_sha256": digest(HARNESS),
        "flythrough_sha256": digest(CORE),
        "ros_node_sha256": digest(NODE),
        "config_sha256": digest(ROOT / normal["config_file"]),
        "png_sha256": digest(stem.with_suffix(".png")),
        "pdf_sha256": digest(stem.with_suffix(".pdf")),
    }
    path = PUBLICATION / "data" / f"{STEM}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"normal_completed": normal["completed"],
                      "bounded_completed": bounded["completed"],
                      "fault_first_hold_s": fault["first_hold_s"],
                      "fault_coast_m": fault["hold_to_final_displacement_m"],
                      "fault_boundary_cross_s": boundary_cross}, ensure_ascii=False))


def verify_historical_snapshot() -> None:
    """Keep an earlier installed-node run immutable after its source changes."""
    frozen_path = PUBLICATION / "data" / f"{STEM}.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    for label, key in (("audit_script", "source_script_sha256"),
                       ("harness", "harness_sha256"),
                       ("ros_node", "ros_node_sha256")):
        snapshot = PUBLICATION / frozen["source_snapshots"][label]
        assert digest(snapshot) == frozen[key]
    assert digest(CORE) == frozen["flythrough_sha256"]
    assert digest(stem := (PUBLICATION / "figures" / STEM).with_suffix(".png")) == frozen["png_sha256"]
    assert digest(stem.with_suffix(".pdf")) == frozen["pdf_sha256"]
    for name, hashes in frozen["cases"].items():
        directory = RESULTS / name
        assert digest(directory / "wire_seed_101_summary.json") == hashes["summary_sha256"]
        assert digest(directory / "wire_seed_101.csv") == hashes["csv_sha256"]
        assert digest(RESULTS / f"{name}.log") == hashes["log_sha256"]
    print(json.dumps({"historical_snapshot_verified": True,
                      "cases": len(frozen["cases"]),
                      "regeneration_requires_frozen_sources": True}, ensure_ascii=False))


if __name__ == "__main__":
    frozen = json.loads((PUBLICATION / "data" / f"{STEM}.json").read_text(encoding="utf-8"))
    if (digest(Path(__file__)) == frozen["source_script_sha256"]
            and digest(HARNESS) == frozen["harness_sha256"]
            and digest(NODE) == frozen["ros_node_sha256"]):
        main()
    else:
        verify_historical_snapshot()
