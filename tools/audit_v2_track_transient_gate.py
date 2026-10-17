#!/usr/bin/env python3
"""Audit the opt-in track disturbance change gate and draw Figure 63."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from thesis_plot_style import PROPOSED, REFERENCE, WARNING, apply_thesis_style, figure_size, save_figure


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "AUV-Master-Mag/results/v2/inspection_track_transient_gate_20260927"
OLD = ROOT / "AUV-Master-Mag/results/v2/inspection_task_status_20260927/fault_final"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "63_track_transient_early_withdrawal_and_coast"
CONFIG = ROOT / "brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_transient_gate_sim.yaml"
SOURCES = {
    "audit": Path(__file__),
    "flythrough": ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/flythrough.py",
    "node": ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py",
    # The three included complete runs used this exact frozen harness.  Later
    # diagnostics extended the live harness after the runs were recorded.
    "harness": PUBLICATION / "repro_sources/62_harness_original.py",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_case(folder: Path) -> tuple[dict, list[dict], dict]:
    summary_path = folder / "wire_seed_101_summary.json"
    csv_path = folder / "wire_seed_101.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows and len(rows) == summary["ticks"]
    assert summary["installed_v2_node_mode"] and summary["bridge_and_guard_connected"]
    assert summary["native_pvs"] and summary["ros_dds"] and summary["protocol_encoded"]
    assert summary["ground_velocity_from_position"] and not summary["hardware_connected"]
    assert summary["sonar_identity_mode"] == "target" and not summary["depth_published"]
    assert sha(Path(summary["v2_node_loaded_path"])) == sha(SOURCES["node"])
    log_path = (RESULTS / f"{folder.name}.log" if folder != OLD else OLD.parent / "fault_final.log")
    assert log_path.exists() and log_path.stat().st_size > 0
    return summary, rows, {
        "summary_sha256": sha(summary_path), "csv_sha256": sha(csv_path), "log_sha256": sha(log_path),
    }


def main() -> None:
    names = ("steady_minus", "step_plus", "step_minus")
    cases = {name: read_case(RESULTS / name) for name in names}
    old, old_rows, old_hashes = read_case(OLD)
    assert old["first_hold_reason"] == "flythrough_route_deviation_exceeded"
    assert old["first_hold_s"] == 883.5 and not old["completed"]
    for name in names:
        summary, rows, _ = cases[name]
        assert Path(summary["config_file"]).resolve() == CONFIG.resolve()
        assert all(row["depth_valid"] == "False" for row in rows)
        if name != "step_minus":
            assert summary["completed"] and summary["route_quality_valid"] is True
            assert summary["first_hold_s"] is None
            assert summary["final_bridge_task_status"] == "SOFTWARE_ROUTE_COMPLETE"
        else:
            assert not summary["completed"]
            assert summary["first_hold_reason"] == "flythrough_track_disturbance_changed"
            assert summary["first_hold_s"] < old["first_hold_s"]
            assert summary["route_observed_lateral_max_m"] < 2.
            assert summary["final_bridge_task_status"] == "SUSPENDED"
            assert summary["first_recovery_reason"] == "hold_time_budget_exhausted"
            assert abs(summary["first_recovery_required_s"] - summary["first_hold_s"] - 30.) <= .25
            hold = [row for row in rows if summary["first_hold_s"] <= float(row["time_s"])
                    <= summary["first_hold_s"] + 60.]
            assert len(hold) == 241
            assert all(row["bridge_task_status"] == "SUSPENDED"
                       and row["operational_task_status"] == "SUSPENDED"
                       and all(float(row[key]) == 0. for key in
                               ("target_speed_mps", "thrust_percent", "rpm"))
                       for row in hold)
            assert not any(row["endpoint_complete"] == "True" for row in rows)

    gate, gate_rows, _ = cases["step_minus"]
    physical_band_exit = next(float(row["time_s"]) for row in gate_rows
                              if float(row["time_s"]) >= gate["first_hold_s"]
                              and abs(float(row["y_m"]) - 6.) > 2.)
    assert physical_band_exit > gate["first_recovery_required_s"]

    apply_thesis_style(base_font_size=8.5)
    fig, axes = plt.subplot_mosaic(
        [["proxy", "proxy"], ["deviation", "speed"]],
        figsize=figure_size(height=4.7), constrained_layout=True)
    ax = axes["proxy"]
    for name, color, linestyle, label in (
        ("steady_minus", REFERENCE, "--", "稳态 −0.05"),
        ("step_plus", PROPOSED, "-", "阶跃 +0.05"),
        ("step_minus", WARNING, "-", "阶跃 −0.05"),
    ):
        rows = cases[name][1]
        track = [row for row in rows if 840. <= float(row["time_s"]) <= 885.
                 and row["estimated_disturbance_y_mps"]]
        times, values = [], []
        for i in range(16, len(track)):
            if abs(float(track[i]["time_s"]) - float(track[i-16]["time_s"]) - 4.) < .01:
                times.append(float(track[i]["time_s"]))
                values.append(float(track[i]["estimated_disturbance_y_mps"])
                              - float(track[i-16]["estimated_disturbance_y_mps"]))
        ax.plot(times, values, color=color, ls=linestyle, lw=1.15, label=label)
    ax.axhline(-.01, color="black", ls=":", lw=.8, label="候选变化门")
    ax.axhline(.01, color="black", ls=":", lw=.8)
    ax.set(xlim=(840, 885), xlabel="仿真时间 / s", ylabel="4 s 横向代理变化 / (m/s)",
           title="(a) 同幅横流，时序不同")
    ax.legend(fontsize=6.0, loc="lower left")

    ax = axes["deviation"]
    for rows, color, label in ((old_rows, REFERENCE, "旧门"), (gate_rows, WARNING, "提前撤权")):
        subset = [row for row in rows if 835. <= float(row["time_s"]) <= 910.]
        ax.plot([float(row["time_s"]) for row in subset],
                [float(row["y_m"]) - 6. for row in subset], color=color, lw=1.25, label=label)
    ax.axhspan(-2., 2., color="#E5F2EC", alpha=.55)
    ax.axhline(-2., color="#55917E", ls=":", lw=.8)
    ax.axvline(gate["first_hold_s"], color=WARNING, ls="--", lw=.85)
    ax.axvline(old["first_hold_s"], color=REFERENCE, ls="--", lw=.85)
    ax.set(xlim=(835, 910), ylim=(-5.8, 1.), xlabel="仿真时间 / s",
           ylabel="相对合成目标线的横偏 / m", title="(b) 早撤权仍有惯性与流致侧移")
    ax.legend(fontsize=6.4, loc="lower left")

    ax = axes["speed"]
    subset = [row for row in gate_rows if 840. <= float(row["time_s"]) <= 910.]
    ax.step([float(row["time_s"]) for row in subset],
            [float(row["target_speed_mps"]) for row in subset], where="post",
            color=PROPOSED, lw=1.1, label="目标速度")
    ax.plot([float(row["time_s"]) for row in subset],
            [abs(float(row["nav_ground_velocity_y_mps"])) for row in subset],
            color=WARNING, lw=1.1, label="横向地速绝对值")
    ax.axvline(gate["first_hold_s"], color=REFERENCE, ls="--", lw=.8, label="撤权")
    ax.axvline(gate["first_recovery_required_s"], color=REFERENCE, ls=":", lw=.8,
               label="处置请求")
    ax.axvline(physical_band_exit, color="#775B9A", ls="-.", lw=.8, label="物理越带")
    ax.set(xlim=(840, 910), ylim=(-.02, .35), xlabel="仿真时间 / s",
           ylabel="速度 / (m/s)", title="(c) 零命令不能替代艇体处置")
    ax.legend(fontsize=6.0, loc="upper right")
    stem = PUBLICATION / "figures" / STEM
    save_figure(fig, stem)
    plt.close(fig)

    payload = {
        "role": "candidate_track_disturbance_change_early_withdrawal",
        "scope": "three completed seed-101 synthetic installed ROS/PID/guard/UDP/native-PVS runs, ideal position-derived world ground speed and synthetic sonar; separate steady-plus attempts aborted after fail-closed navigation-age withdrawal; threshold selected after Figure 61 observation, no physical current or upper-level recovery",
        "candidate_limit_mps_per_4s": .01,
        "cases": {name: {"completed": summary["completed"],
                         "first_hold_s": summary["first_hold_s"],
                         "first_hold_reason": summary["first_hold_reason"],
                         "route_observed_lateral_max_m": summary["route_observed_lateral_max_m"],
                         **hashes} for name, (summary, _, hashes) in cases.items()},
        "old_fault": {"first_hold_s": old["first_hold_s"], **old_hashes},
        "early_withdrawal_lead_s": old["first_hold_s"] - gate["first_hold_s"],
        "first_physical_2m_band_exit_s_after_hold": physical_band_exit,
        "recovery_request_to_band_exit_s": physical_band_exit - gate["first_recovery_required_s"],
        "post_hold_zero_cycles": 241,
        "uncompleted_diagnostic_logs": {
            name: sha(RESULTS / name) for name in (
                "steady_plus_interrupted.log", "steady_plus.log",
                "steady_plus_diagnostic.log", "steady_plus_diagnostic_2.log",
                "steady_plus_budget_fallback.log")
        },
        "config_sha256": sha(CONFIG),
        "source_sha256": {name: sha(path) for name, path in SOURCES.items()},
        "png_sha256": sha(stem.with_suffix(".png")),
        "pdf_sha256": sha(stem.with_suffix(".pdf")),
    }
    path = PUBLICATION / "data" / f"{STEM}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"early_hold_s": gate["first_hold_s"],
                      "old_hold_s": old["first_hold_s"],
                      "physical_band_exit_s": physical_band_exit,
                      "positive_completed": 2}, ensure_ascii=False))


def verify_snapshot() -> None:
    frozen = json.loads((PUBLICATION / "data" / f"{STEM}.json").read_text(encoding="utf-8"))
    assert sha(CONFIG) == frozen["config_sha256"]
    for name, relative in frozen["source_snapshots"].items():
        assert sha(PUBLICATION / relative) == frozen["source_sha256"][name]
    for name, case in frozen["cases"].items():
        folder = RESULTS / name
        assert sha(folder / "wire_seed_101_summary.json") == case["summary_sha256"]
        assert sha(folder / "wire_seed_101.csv") == case["csv_sha256"]
        assert sha(RESULTS / f"{name}.log") == case["log_sha256"]
    assert sha(OLD / "wire_seed_101_summary.json") == frozen["old_fault"]["summary_sha256"]
    assert sha(OLD / "wire_seed_101.csv") == frozen["old_fault"]["csv_sha256"]
    assert sha(OLD.parent / "fault_final.log") == frozen["old_fault"]["log_sha256"]
    for name, expected in frozen["uncompleted_diagnostic_logs"].items():
        assert sha(RESULTS / name) == expected
    for suffix in ("png", "pdf"):
        assert sha(PUBLICATION / "figures" / f"{STEM}.{suffix}") == frozen[f"{suffix}_sha256"]
    print(json.dumps({"historical_snapshot_verified": True, "cases": 3}, ensure_ascii=False))


if __name__ == "__main__":
    data = PUBLICATION / "data" / f"{STEM}.json"
    if data.exists():
        frozen = json.loads(data.read_text(encoding="utf-8"))
        if "source_snapshots" in frozen or not all(
                sha(path) == frozen["source_sha256"][name] for name, path in SOURCES.items()):
            verify_snapshot()
        else:
            main()
    else:
        main()
