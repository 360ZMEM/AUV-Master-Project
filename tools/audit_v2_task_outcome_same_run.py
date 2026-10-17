#!/usr/bin/env python3
"""Audit orthogonal task, depth, and execution statuses in two installed runs."""
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
RESULTS = ROOT / "AUV-Master-Mag/results/v2/inspection_task_status_20260927"
PUBLICATION = ROOT / "AUV-Master-Mag/docs/v2/publication/fwhm_v2_experiment_results"
STEM = "62_inspection_task_depth_authority_outcomes"
CONFIG = ROOT / "AUV-Master-Mag/results/v2/inspection_route_budget_clockfix_20260927/sonar_route_budget_sim.yaml"
SOURCES = {
    "audit_script": Path(__file__),
    "bridge": ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_bridge_node.py",
    "task_status": ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_task_status.py",
    "algorithm_node": ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py",
    "harness": ROOT / "tools/smoke_v2_flythrough_ros_pvs.py",
    "console_view": ROOT / "console_soft/auv_console_pyside6/src/ui/inspection_operational_view.py",
    "console_window": ROOT / "console_soft/auv_console_pyside6/src/ui/main_window.py",
}


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
    assert log_path.exists() and log_path.stat().st_size
    assert len(rows) == summary["ticks"] and summary["seed"] == 101
    assert summary["installed_v2_node_mode"] and summary["bridge_and_guard_connected"]
    assert summary["ros_dds"] and summary["native_pvs"] and summary["protocol_encoded"]
    assert not summary["hardware_connected"] and not summary["depth_published"]
    assert summary["ground_velocity_from_position"] and summary["sonar_identity_mode"] == "target"
    assert Path(summary["config_file"]).resolve() == CONFIG.resolve()
    assert digest(Path(summary["v2_node_loaded_path"])) == digest(SOURCES["algorithm_node"])
    for row in rows:
        assert row["operational_task_status"] in (
            "UNKNOWN", "IN_PROGRESS", "SOFTWARE_ROUTE_COMPLETE", "SUSPENDED")
        assert row["depth_valid"] == "False"
    hashes = {"summary_sha256": digest(summary_path),
              "csv_sha256": digest(csv_path), "log_sha256": digest(log_path)}
    return summary, rows, hashes


def main() -> None:
    normal, normal_rows, normal_hashes = load("normal_final")
    fault, fault_rows, fault_hashes = load("fault_final")
    assert normal["completed"] and normal["route_quality_valid"] is True
    assert normal["first_hold_s"] is None
    assert normal_rows[-1]["endpoint_complete"] == "True"
    assert normal_rows[-1]["bridge_task_status"] == "SOFTWARE_ROUTE_COMPLETE"
    assert normal_rows[-1]["operational_task_status"] == "SOFTWARE_ROUTE_COMPLETE"
    assert normal["final_bridge_task_status"] == "SOFTWARE_ROUTE_COMPLETE"
    assert normal["final_inspection_status"] == "LOCALIZED_DEPTH_PENDING"
    assert normal["final_operational_status"]["task_status"] == "SOFTWARE_ROUTE_COMPLETE"
    assert normal["final_operational_status"]["task_status_fresh"]
    assert not normal["final_operational_status"]["autonomous_execution_authorized"]
    assert all(float(normal_rows[-1][key]) == 0. for key in (
        "target_speed_mps", "thrust_percent", "rpm"))
    assert not fault["completed"] and fault["first_hold_reason"] == "flythrough_route_deviation_exceeded"
    assert fault["first_recovery_reason"] == "hold_time_budget_exhausted"
    assert abs(fault["first_recovery_required_s"] - fault["first_hold_s"] - 30.) <= .25
    assert fault["final_bridge_task_status"] == "SUSPENDED"
    assert fault["final_inspection_status"] == "RECOVERY_REQUIRED"
    assert fault["final_operational_status"]["task_status"] == "SUSPENDED"
    assert fault["final_operational_status"]["task_status_fresh"]
    assert not fault["final_operational_status"]["autonomous_execution_authorized"]
    assert not any(row["endpoint_complete"] == "True" for row in fault_rows)
    hold = [row for row in fault_rows if fault["first_hold_s"] <= float(row["time_s"])
            <= fault["first_hold_s"] + 60.]
    assert len(hold) == 241
    assert all(row["bridge_task_status"] == "SUSPENDED"
               and row["operational_task_status"] == "SUSPENDED"
               and row["autonomous_execution_authorized"] == "False"
               and all(float(row[key]) == 0. for key in ("target_speed_mps", "thrust_percent", "rpm"))
               for row in hold)

    apply_thesis_style(base_font_size=8.6)
    fig, axes = plt.subplot_mosaic([["normal", "fault"], ["summary", "summary"]],
                                   figsize=figure_size(height=3.9), constrained_layout=True)
    ax = axes["normal"]
    subset = [row for row in normal_rows if 1098. <= float(row["time_s"]) <= normal["duration_s"]]
    ax.step([float(row["time_s"]) for row in subset],
            [float(row["target_speed_mps"]) for row in subset],
            where="post", color=PROPOSED, lw=1.35, label="目标速度")
    ax.axvline(normal["duration_s"], color=REFERENCE, ls=":", lw=.9, label="软件路线到端")
    ax.set(xlim=(1098, normal["duration_s"] + .8), ylim=(-.03, .36),
           xlabel="仿真时间 / s", ylabel="目标速度 / (m/s)",
           title="(a) 正常：到端当周期零命令，埋深未许可")
    ax.legend(fontsize=6.8, loc="upper right")

    ax = axes["fault"]
    subset = [row for row in fault_rows if 876. <= float(row["time_s"]) <= 944.]
    ax.step([float(row["time_s"]) for row in subset],
            [float(row["target_speed_mps"]) for row in subset],
            where="post", color=WARNING, lw=1.35, label="目标速度")
    ax.axvline(fault["first_hold_s"], color=REFERENCE, ls=":", lw=.9, label="撤权")
    ax.axvline(fault["first_recovery_required_s"], color=REFERENCE, ls="-.", lw=.9,
               label="30 s 处置请求")
    ax.set(xlim=(876, 944), ylim=(-.03, .36),
           xlabel="仿真时间 / s", ylabel="目标速度 / (m/s)",
           title="(b) 反向阶跃：暂停且不报完成")
    ax.legend(fontsize=6.8, loc="upper right")

    ax = axes["summary"]
    ax.axis("off")
    cells = [
        ["正常到端", "软件路线完成", "埋深未许可", "自治命令关闭"],
        ["反向阶跃", "暂停／撤权", "埋深未许可", "自治命令关闭"],
    ]
    table = ax.table(cellText=cells,
                     colLabels=["案例", "任务结果", "深度发布", "终态执行许可"],
                     loc="center", cellLoc="center", colLoc="center",
                     colWidths=[.16, .28, .27, .29])
    table.auto_set_font_size(False)
    table.set_fontsize(8.3)
    table.scale(1., 1.55)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#C3CBD3")
        if row == 0:
            cell.set_facecolor("#E9EDF1")
        elif col == 1:
            cell.set_facecolor("#DCECF4" if row == 1 else "#FAE5D6")
    ax.set_title("(c) 任务到端、埋深与执行许可是三条独立结论", pad=1.)
    stem = PUBLICATION / "figures" / STEM
    save_figure(fig, stem)
    plt.close(fig)
    payload = {
        "role": "installed_ros_two_case_task_depth_execution_status_contract",
        "scope": "two independent seed-101 synthetic ROS/PID/guard/localhost-UDP/native-PVS runs; software route completion only; no physical sonar/current/PC104",
        "cases": {
            "normal_final": {
                "completed": normal["completed"], "terminal_task_status": normal["final_bridge_task_status"],
                "terminal_localization_status": normal["final_inspection_status"],
                "terminal_autonomous_authorized": normal["final_operational_status"]["autonomous_execution_authorized"],
                "route_observed_lateral_max_m": normal["route_observed_lateral_max_m"], **normal_hashes},
            "fault_final": {
                "completed": fault["completed"], "terminal_task_status": fault["final_bridge_task_status"],
                "terminal_localization_status": fault["final_inspection_status"],
                "first_hold_s": fault["first_hold_s"],
                "first_recovery_required_s": fault["first_recovery_required_s"],
                "post_hold_zero_command_cycles": len(hold),
                "hold_to_final_displacement_m": fault["hold_to_final_displacement_m"],
                **fault_hashes},
        },
        "config_sha256": digest(CONFIG),
        "source_sha256": {name: digest(path) for name, path in SOURCES.items()},
        "png_sha256": digest(stem.with_suffix(".png")),
        "pdf_sha256": digest(stem.with_suffix(".pdf")),
    }
    path = PUBLICATION / "data" / f"{STEM}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"normal_task": normal["final_bridge_task_status"],
                      "fault_task": fault["final_bridge_task_status"],
                      "fault_zero_cycles": len(hold)}, ensure_ascii=False))


def verify_historical_snapshot() -> None:
    """Prevent later source changes from silently relabelling Figure 62."""
    frozen = json.loads((PUBLICATION / "data" / f"{STEM}.json").read_text(encoding="utf-8"))
    for name, relative in frozen["source_snapshots"].items():
        assert digest(PUBLICATION / relative) == frozen["source_sha256"][name]
    assert digest(CONFIG) == frozen["config_sha256"]
    for suffix in ("png", "pdf"):
        assert digest(PUBLICATION / "figures" / f"{STEM}.{suffix}") == frozen[f"{suffix}_sha256"]
    for name, case in frozen["cases"].items():
        directory = RESULTS / name
        assert digest(directory / "wire_seed_101_summary.json") == case["summary_sha256"]
        assert digest(directory / "wire_seed_101.csv") == case["csv_sha256"]
        assert digest(RESULTS / f"{name}.log") == case["log_sha256"]
    print(json.dumps({"historical_snapshot_verified": True,
                      "cases": len(frozen["cases"]),
                      "regeneration_requires_frozen_sources": True}, ensure_ascii=False))


if __name__ == "__main__":
    frozen = json.loads((PUBLICATION / "data" / f"{STEM}.json").read_text(encoding="utf-8"))
    if all(digest(path) == frozen["source_sha256"][name]
           for name, path in SOURCES.items()):
        main()
    else:
        verify_historical_snapshot()
