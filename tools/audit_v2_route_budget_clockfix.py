#!/usr/bin/env python3
"""Audit the installed F-profile current envelope and dual-clock Hold."""
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
RESULTS = ROOT / "AUV-Master-Mag/results/v2/inspection_route_budget_clockfix_20260927"
CONFIG = RESULTS / "sonar_route_budget_sim.yaml"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "61_finite_track_current_envelope_and_clock"
NODE = ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py"
CORE = ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py"
HARNESS = ROOT / "tools/smoke_v2_flythrough_ros_pvs.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str, seed: int) -> tuple[dict, list[dict], dict]:
    directory = RESULTS / name
    summary_path = directory / f"wire_seed_{seed}_summary.json"
    csv_path = directory / f"wire_seed_{seed}.csv"
    log_path = RESULTS / f"{name}.log"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    installed = Path(summary["v2_node_loaded_path"])
    assert summary["seed"] == seed and summary["installed_v2_node_mode"]
    assert "/install/" in str(installed) and digest(installed) == digest(NODE)
    assert len(rows) == summary["ticks"] and summary["ground_velocity_from_position"]
    assert summary["sonar_identity_mode"] == "target"
    assert all(summary[key] for key in ("native_pvs", "ros_dds", "protocol_encoded",
                                        "bridge_and_guard_connected"))
    assert not summary["hardware_connected"] and not summary["depth_published"]
    assert Path(summary["config_file"]).resolve() == CONFIG.resolve()
    assert log_path.is_file() and log_path.stat().st_size > 0
    assert rows[0]["hold_budget_state"] == "MOTION_BUDGET_OK"
    assert abs(float(rows[0]["hold_budget_clearance_m"]) - 25.) < .01
    hashes = {"summary_sha256": digest(summary_path), "csv_sha256": digest(csv_path),
              "log_sha256": digest(log_path)}
    return summary, rows, hashes


def main() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["cable_tracking"]["v2"]
    budget = config["hold_budget"]
    assert budget["current_bound_mps"] == .05
    assert budget["maximum_hold_s"] == 30.
    assert config["route_hold_admission"] == {"enabled": True, "route_deviation_bound_m": 2.}
    assert config["flythrough"]["runtime_target_exclusive_min_m"] == 5.45
    assert config["flythrough"]["runtime_target_exclusive_max_m"] == 6.55
    required_clearance = (budget["boundary_stop_margin_m"]
                          + budget["zero_effort_coast_bound_m"]
                          + budget["navigation_margin_m"]
                          + budget["current_bound_mps"] *
                          (budget["maximum_hold_s"] + budget["disposition_delay_s"])
                          + config["route_hold_admission"]["route_deviation_bound_m"])
    assert abs(required_clearance - 19.6) < 1e-9

    cases: dict[str, dict] = {}
    rows: dict[str, list[dict]] = {}
    for seed in (101, 102, 103):
        for side, direction in (("plus", 90.), ("minus", 270.)):
            name = f"steady_{side}_{seed}"
            summary, case_rows, hashes = load(name, seed)
            assert summary["inspection_current_step_mps"] is None
            assert summary["current_speed_mps"] == .05
            assert summary["current_direction_deg"] == direction
            assert summary["completed"] and summary["first_hold_s"] is None
            assert summary["route_observed_lateral_max_m"] < 2.
            assert all(row["runtime_identity_reason"] == "accepted"
                       for row in case_rows if row["mode"] == "track")
            cases[name] = {"completed": True,
                           "route_observed_lateral_max_m": summary["route_observed_lateral_max_m"],
                           "route_observed_lateral_mae_m": summary["route_observed_lateral_mae_m"],
                           "duration_s": summary["duration_s"], **hashes}
            rows[name] = case_rows

    for name, direction in (("step_plus_101", 90.),
                            ("step_minus_coast_101", 270.)):
        summary, case_rows, hashes = load(name, 101)
        if name == "step_minus_coast_101":
            negative_summary = summary
        assert summary["current_speed_mps"] == 0.
        assert summary["inspection_current_step_mps"] == .05
        assert summary["inspection_current_step_direction_deg"] == direction
        cases[name] = {"completed": summary["completed"],
                       "first_hold_s": summary["first_hold_s"],
                       "first_hold_reason": summary["first_hold_reason"],
                       "first_recovery_required_s": summary["first_recovery_required_s"],
                       "first_recovery_reason": summary["first_recovery_reason"],
                       "route_observed_lateral_max_m": summary["route_observed_lateral_max_m"],
                       "hold_to_final_displacement_m": summary["hold_to_final_displacement_m"],
                       **hashes}
        rows[name] = case_rows
    assert cases["step_plus_101"]["completed"]
    assert cases["step_plus_101"]["route_observed_lateral_max_m"] < 2.
    negative = cases["step_minus_coast_101"]
    assert not negative["completed"]
    assert negative["first_hold_reason"] == "flythrough_route_deviation_exceeded"
    assert negative["route_observed_lateral_max_m"] > 2.
    assert abs(negative["first_hold_s"] - 883.5) <= .25
    assert abs(negative["first_recovery_required_s"] - (negative["first_hold_s"] + 30.)) <= .25
    assert negative["first_recovery_reason"] == "hold_time_budget_exhausted"
    coast = [row for row in rows["step_minus_coast_101"]
             if negative["first_hold_s"] <= float(row["time_s"])
             <= negative["first_hold_s"] + 60.]
    assert len(coast) == 241
    assert all(row["mode"] == "hold" and float(row["target_speed_mps"]) == 0.
               and float(row["thrust_percent"]) == 0. and int(row["rpm"]) == 0
               for row in coast)
    assert negative["hold_to_final_displacement_m"] < 7.
    assert all(-40. < float(row["y_m"]) < 40. for row in coast)
    hold_row = coast[0]
    assert hold_row["hold_budget_state"] == "WITHIN_BUDGET"
    assert float(hold_row["hold_budget_clearance_m"]) > 35.
    assert coast[-1]["hold_budget_state"] == "RECOVERY_REQUIRED"

    apply_thesis_style(base_font_size=8.5)
    fig, axes = plt.subplot_mosaic([["route", "heading"], ["error", "error"]],
                                   figsize=figure_size(height=4.1), constrained_layout=True)
    ax = axes["route"]
    center_m = float(negative_summary["last_fwhm_center_m"])
    ax.axhspan(center_m-2., center_m+2., color=PROPOSED, alpha=.10,
               label="估计线 $\\pm2$ m")
    for name, color, label, style in (
            ("steady_minus_101", PROPOSED, "稳态 $-0.05$ m/s", "--"),
            ("step_minus_coast_101", WARNING, "阶跃 $-0.05$ m/s", "-")):
        subset = [row for row in rows[name] if 839. <= float(row["time_s"]) <= 944.]
        ax.plot([float(row["time_s"]) for row in subset],
                [float(row["y_m"]) for row in subset],
                color=color, ls=style, lw=1.2, label=label)
    ax.axvline(negative["first_hold_s"], color=REFERENCE, ls=":", lw=.8,
               label="撤权")
    ax.axvline(negative["first_recovery_required_s"], color=REFERENCE, ls="-.", lw=.8,
               label="30 s 处置请求")
    ax.set(xlim=(839, 944), ylim=(0, 8.5), xlabel="仿真时间 / s",
           ylabel="PVS 横向位置 / m", title="(a) 稳态跟踪与突变撤权")
    ax.legend(fontsize=6.2, ncol=2, loc="upper left")

    ax = axes["heading"]
    subset = [row for row in rows["step_minus_coast_101"]
              if 844. <= float(row["time_s"]) <= negative["first_hold_s"]]
    times = [float(row["time_s"]) for row in subset]
    ax.plot(times, [float(row["target_heading_deg"]) for row in subset],
            color=WARNING, lw=1.2, label="期望航向")
    ax.plot(times, [float(row["heading_deg"]) for row in subset],
            color=PROPOSED, lw=1.2, label="实际航向")
    ax.axvline(negative["first_hold_s"], color=REFERENCE, ls=":", lw=.8)
    ax.set(xlim=(844, 885), ylim=(-10, 20), xlabel="仿真时间 / s",
           ylabel="航向角 / $^\\circ$", title="(b) 低速转向响应滞后")
    ax.legend(fontsize=7., loc="upper left")

    ax = axes["error"]
    for i, side in enumerate(("plus", "minus")):
        for offset, seed in ((-.06, 101), (0., 102), (.06, 103)):
            name = f"steady_{side}_{seed}"
            ax.scatter(i+offset, cases[name]["route_observed_lateral_max_m"],
                       color=PROPOSED, s=17, zorder=3)
    for i, name in ((2, "step_plus_101"), (3, "step_minus_coast_101")):
        ax.scatter(i, cases[name]["route_observed_lateral_max_m"],
                   color=WARNING, marker="x" if i == 3 else "o", s=29, zorder=4)
    ax.axhline(2., color=REFERENCE, ls="-.", lw=.8, label="2 m 沿程上限")
    ax.set(xlim=(-.4, 3.4), ylim=(0, 2.25), xticks=range(4),
           xticklabels=["稳态 +0.05", "稳态 $-0.05$", "阶跃 +0.05", "阶跃 $-0.05$"],
           ylabel="相对估计线最大横偏 / m", title="(c) 稳态各 3 磁噪声种子；阶跃各 1 种子")
    ax.legend(fontsize=7., loc="upper left")

    stem = PUBLICATION / "figures" / STEM
    save_figure(fig, stem)
    plt.close(fig)
    payload = {
        "role": "synthetic_installed_ros_stable_current_vs_track_step_with_dual_clock_disposition",
        "scope": "eight independent ROS/PID/guard/localhost-UDP/native-PVS synthetic runs; ideal position-derived ground velocity; magnetic noise seeds only; no physical sonar/current/PC104",
        "route_minimum_clearance_m": 25.,
        "route_required_clearance_m": required_clearance,
        "declared_current_bound_mps": .05,
        "steady_cases_completed": 6,
        "steady_cases_total": 6,
        "negative_post_hold_zero_command_cycles": len(coast),
        "cases": cases,
        "source_script_sha256": digest(Path(__file__)),
        "harness_sha256": digest(HARNESS),
        "flythrough_sha256": digest(CORE),
        "ros_node_sha256": digest(NODE),
        "config_sha256": digest(CONFIG),
        "png_sha256": digest(stem.with_suffix(".png")),
        "pdf_sha256": digest(stem.with_suffix(".pdf")),
    }
    path = PUBLICATION / "data" / f"{STEM}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"steady_completed": "6/6", "step_positive_completed": True,
                      "step_negative_hold_s": negative["first_hold_s"],
                      "step_negative_recovery_s": negative["first_recovery_required_s"],
                      "step_negative_coast_m": negative["hold_to_final_displacement_m"]},
                     ensure_ascii=False))


def verify_historical_snapshot() -> None:
    """Verify frozen data and source versions after the live stack evolves."""
    frozen = json.loads((PUBLICATION / "data" / f"{STEM}.json").read_text(encoding="utf-8"))
    for label, key in (("audit_script", "source_script_sha256"),
                       ("harness", "harness_sha256"),
                       ("flythrough", "flythrough_sha256"),
                       ("ros_node", "ros_node_sha256")):
        assert digest(PUBLICATION / frozen["source_snapshots"][label]) == frozen[key]
    assert digest(CONFIG) == frozen["config_sha256"]
    for suffix in ("png", "pdf"):
        assert digest(PUBLICATION / "figures" / f"{STEM}.{suffix}") == frozen[f"{suffix}_sha256"]
    for name, case in frozen["cases"].items():
        seed = int(name.rsplit("_", 1)[1])
        directory = RESULTS / name
        assert digest(directory / f"wire_seed_{seed}_summary.json") == case["summary_sha256"]
        assert digest(directory / f"wire_seed_{seed}.csv") == case["csv_sha256"]
        assert digest(RESULTS / f"{name}.log") == case["log_sha256"]
    print(json.dumps({"historical_snapshot_verified": True,
                      "cases": len(frozen["cases"]),
                      "regeneration_requires_frozen_sources": True}, ensure_ascii=False))


if __name__ == "__main__":
    frozen = json.loads((PUBLICATION / "data" / f"{STEM}.json").read_text(encoding="utf-8"))
    if (digest(Path(__file__)) == frozen["source_script_sha256"]
            and digest(HARNESS) == frozen["harness_sha256"]
            and digest(CORE) == frozen["flythrough_sha256"]
            and digest(NODE) == frozen["ros_node_sha256"]):
        main()
    else:
        verify_historical_snapshot()
