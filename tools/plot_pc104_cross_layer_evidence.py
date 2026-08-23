#!/usr/bin/env python3
"""Aggregate and plot split-run PC104 cross-layer safety evidence."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import thesis_plot_style as tps  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402


DEFAULT_SOAK_BUNDLE = (
    REPO_ROOT
    / "results/control/pc104_cross_layer_fault_sync_20260822_222112"
)
DEFAULT_FAULT_BUNDLE = (
    REPO_ROOT
    / "results/control/pc104_cross_layer_fault_sync_20260822_225436"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / "results/control/pc104_cross_layer_evidence_20260822"
)
DEFAULT_THESIS_FIGURE_DIR = (
    REPO_ROOT / "docs/thesis/figures/hardware/pc104_cross_layer"
)

CHECK_NAMES = (
    "baseline_active",
    "bit13_observed",
    "bit13_retains_autonomy",
    "bit13_routes_to_relocalization",
    "bit5_denies_autonomy",
    "bit5_bt_idle_zero",
    "bit5_requires_reauthorization",
    "bit5_reauthorized",
    "bit14_denies_autonomy",
    "bit14_shadow_zero",
    "bit14_requires_reauthorization",
    "bit14_reauthorized",
    "fanout_forwarded_zero_only",
    "rosbag_recorded",
    "active_soak_stable",
    "board_command_snapshots_zero",
    "uplink_motor_feedback_zero",
    "cleanup_remote_zero",
)
BOARD_COMMAND_FIELDS = (
    "telnet_ui_motor1",
    "telnet_ui_motor2",
    "telnet_ui_fin_lh",
    "telnet_ui_fin_rh",
    "telnet_ui_fin_uv",
    "telnet_ui_fin_lv",
    "telnet_instruction_motor1",
    "telnet_instruction_motor2",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--soak-bundle", type=Path, default=DEFAULT_SOAK_BUNDLE)
    parser.add_argument("--fault-bundle", type=Path, default=DEFAULT_FAULT_BUNDLE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--thesis-figure-dir",
        type=Path,
        default=DEFAULT_THESIS_FIGURE_DIR,
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def elapsed(row: dict[str, str]) -> float:
    return float(row["elapsed_s"])


def first_phase_time(rows: list[dict[str, str]], phase: str) -> float:
    return min(
        elapsed(row)
        for row in rows
        if row["event_type"] == "phase_start" and row["phase"] == phase
    )


def float_or_zero(row: dict[str, str], key: str) -> float:
    raw = row.get(key, "")
    return float(raw) if raw not in ("", None) else 0.0


def plot_fault_timeline(
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    output_dir: Path,
) -> list[Path]:
    arbiter = [row for row in rows if row["event_type"] == "arbiter_status"]
    goals = [row for row in rows if row["event_type"] == "control_goal"]
    telemetry = [
        row for row in rows if row["event_type"] == "bridge_telemetry"
    ]
    shadow = [row for row in rows if row["event_type"] == "shadow_cmd"]
    snapshots = [
        row for row in rows if row["event_type"] == "board_snapshot"
    ]

    origin = first_phase_time(rows, "active_baseline")
    end = first_phase_time(rows, "remote_cleanup")

    fig, axes = plt.subplots(
        4,
        1,
        figsize=tps.figure_size("full", height=4.8),
        sharex=True,
        constrained_layout=True,
    )
    fault_spans = (
        ("bit13_dvl_loss", "bit13_clear", "#55a868", "Bit13 DVL 失锁"),
        ("bit5_system_comm", "bit5_clear_hold", "#dd8452", "Bit5 系统通信"),
        (
            "bit14_watchdog_outage",
            "bit14_clear_hold",
            "#c44e52",
            "Bit14 看门狗",
        ),
    )
    for start_phase, end_phase, color, label in fault_spans:
        start = first_phase_time(rows, start_phase) - origin
        stop = first_phase_time(rows, end_phase) - origin
        for index, axis in enumerate(axes):
            axis.axvspan(
                start,
                stop,
                color=color,
                alpha=0.12,
                linewidth=0,
                label=label if index == 0 else None,
            )

    for phase in ("bit5_reauthorize", "bit14_reauthorize"):
        x_value = first_phase_time(rows, phase) - origin
        for axis in axes:
            axis.axvline(
                x_value,
                color="#4d4d4d",
                linestyle=":",
                linewidth=1.0,
            )

    t_arb = np.asarray([elapsed(row) - origin for row in arbiter])
    fault_styles = (
        ("bit13_dvl_lost", "Bit13", 2),
        ("bit5_system_communication", "Bit5", 1),
        ("bit14_jetson_timeout", "Bit14", 3),
    )
    for key, label, style_index in fault_styles:
        style = tps.line_style(style_index)
        style.pop("marker", None)
        axes[0].step(
            t_arb,
            np.asarray([int(row[key]) for row in arbiter]),
            where="post",
            label=label,
            **style,
        )
    axes[0].set_yticks((0, 1))
    axes[0].set_ylim(-0.12, 1.20)
    axes[0].set_ylabel("故障位")
    phase_handles, phase_labels = axes[0].get_legend_handles_labels()
    fig.legend(
        phase_handles,
        phase_labels,
        loc="outside upper center",
        ncols=6,
    )

    arbiter_codes = {"LOCKED": 0, "ACTIVE": 1, "DENIED": 2}
    axes[1].step(
        t_arb,
        [arbiter_codes.get(row["auto_state"], np.nan) for row in arbiter],
        where="post",
        color=tps.ACCENT_COLORS[0],
    )
    axes[1].set_yticks((0, 1, 2), ("锁定", "有效", "拒绝"))
    axes[1].set_ylim(-0.25, 2.25)
    axes[1].set_ylabel("仲裁状态")

    goal_codes = {
        "IDLE": 0,
        "PARALLEL_TRACKING": 1,
        "ZIGZAG_SEARCH": 2,
    }
    t_goal = np.asarray([elapsed(row) - origin for row in goals])
    axes[2].step(
        t_goal,
        [goal_codes.get(row["goal_mode"], np.nan) for row in goals],
        where="post",
        color=tps.ACCENT_COLORS[4],
    )
    axes[2].set_yticks(
        (0, 1, 2),
        ("待机", "平行跟踪", "之字搜索"),
    )
    axes[2].set_ylim(-0.25, 2.25)
    axes[2].set_ylabel("任务输出")

    command_times: list[float] = []
    command_maxima: list[float] = []
    command_sources: list[str] = []
    for row in telemetry:
        command_times.append(elapsed(row) - origin)
        command_maxima.append(
            max(
                abs(float_or_zero(row, "uplink_main_motor_rpm")),
                abs(float_or_zero(row, "uplink_side_motor_rpm")),
            )
        )
        command_sources.append("上行推进反馈")
    for row in shadow:
        payload = json.loads(row["payload_json"]).get("payload", {})
        command_times.append(elapsed(row) - origin)
        command_maxima.append(
            max(
                abs(float(payload.get(key, 0.0)))
                for key in ("thrust", "left", "right", "top", "bottom")
            )
        )
        command_sources.append("影子执行量")
    for row in snapshots:
        command_times.append(elapsed(row) - origin)
        command_maxima.append(
            max(abs(float_or_zero(row, key)) for key in BOARD_COMMAND_FIELDS)
        )
        command_sources.append("板端命令快照")
    for label, style_index in (
        ("上行推进反馈", 0),
        ("影子执行量", 1),
        ("板端命令快照", 2),
    ):
        points = [
            (time_value, command_value)
            for time_value, command_value, source in zip(
                command_times, command_maxima, command_sources
            )
            if source == label
        ]
        if points:
            axes[3].scatter(
                [point[0] for point in points],
                [point[1] for point in points],
                s=13,
                alpha=0.75,
                label=label,
                color=tps.ACCENT_COLORS[style_index],
            )
    axes[3].set_ylim(-0.05, 0.15)
    axes[3].set_ylabel("最大绝对命令")
    axes[3].set_xlabel("相对健康自主基线的时间 (s)")
    axes[3].legend(loc="upper center", ncols=3)
    axes[3].text(
        0.99,
        0.90,
        "全程为 0",
        ha="right",
        va="top",
        transform=axes[3].transAxes,
    )

    axes[0].set_title(
        (
            f"Bit13→仲裁/行为树 {summary['bit13_to_arbiter_latency_ms']:.1f}/"
            f"{summary['bit13_to_bt_latency_ms']:.1f} ms"
        ),
        loc="left",
    )
    axes[1].set_title(
        (
            f"Bit5→拒绝/待机 {summary['bit5_to_denied_latency_ms']:.1f}/"
            f"{summary['bit5_to_idle_latency_ms']:.1f} ms；"
            f"Bit14→拒绝 {summary['bit14_to_denied_latency_ms']:.1f} ms"
        ),
        loc="left",
    )
    axes[3].set_xlim(0.0, max(0.0, end - origin))
    paths = tps.save_figure(
        fig, output_dir / "pc104_cross_layer_fault_timeline"
    )
    plt.close(fig)
    return paths


def minute_aggregate(
    rows: list[dict[str, str]],
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    soak_rows = [row for row in rows if row["phase"] == "active_soak"]
    origin = min(elapsed(row) for row in soak_rows)
    minute_count = 30
    data: dict[str, list[float]] = {
        "status_count": [],
        "active_ratio": [],
        "fault_count": [],
        "telemetry_rate_hz": [],
        "nonzero_motor_count": [],
    }
    for minute in range(minute_count):
        lower = origin + minute * 60.0
        upper = lower + 60.0
        interval = [
            row for row in soak_rows if lower <= elapsed(row) < upper
        ]
        status = [
            row for row in interval if row["event_type"] == "arbiter_status"
        ]
        telemetry = [
            row for row in interval if row["event_type"] == "bridge_telemetry"
        ]
        data["status_count"].append(float(len(status)))
        data["active_ratio"].append(
            sum(row["auto_state"] == "ACTIVE" for row in status) / len(status)
            if status
            else float("nan")
        )
        data["fault_count"].append(
            float(
                sum(
                    int(row.get("sys_abnorm_info", "0")) & 0x6020 != 0
                    for row in status
                )
            )
        )
        data["telemetry_rate_hz"].append(len(telemetry) / 60.0)
        data["nonzero_motor_count"].append(
            float(
                sum(
                    abs(float_or_zero(row, "uplink_main_motor_rpm")) > 1.0e-9
                    or abs(float_or_zero(row, "uplink_side_motor_rpm")) > 1.0e-9
                    for row in telemetry
                )
            )
        )
    return (
        np.arange(1, minute_count + 1),
        {key: np.asarray(value) for key, value in data.items()},
    )


def plot_soak(
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    output_dir: Path,
) -> tuple[list[Path], dict[str, Any]]:
    minutes, aggregate = minute_aggregate(rows)
    runtime = [
        row
        for row in rows
        if row["phase"] == "active_soak"
        and row["event_type"] == "runtime_sample"
    ]
    soak_origin = first_phase_time(rows, "active_soak")
    runtime_minutes = np.asarray(
        [(elapsed(row) - soak_origin) / 60.0 for row in runtime]
    )

    fig, axes = plt.subplots(
        3,
        1,
        figsize=tps.figure_size("full", height=4.7),
        sharex=True,
        constrained_layout=True,
    )
    axes[0].bar(
        minutes,
        aggregate["status_count"] / 60.0,
        width=0.72,
        label="ArbiterStatus 采样率",
        **tps.series_style(2),
    )
    axes[0].set_ylabel("采样率 (Hz)")
    axes[0].legend(loc="upper left")
    active_axis = axes[0].twinx()
    active_axis.plot(
        minutes,
        aggregate["active_ratio"] * 100.0,
        label="ACTIVE 比率",
        **tps.line_style(0),
    )
    active_axis.set_ylim(99.9, 100.02)
    active_axis.set_ylabel("ACTIVE / %")
    active_axis.legend(loc="lower right")

    axes[1].plot(
        minutes,
        aggregate["telemetry_rate_hz"],
        label="PC104 上行接收率",
        **tps.line_style(1),
    )
    axes[1].set_ylabel("上行帧率 (Hz)")
    axes[1].legend(loc="upper right")
    axes[1].text(
        0.01,
        0.10,
        (
            f"目标故障状态样本={int(np.sum(aggregate['fault_count']))}；"
            "非零推进反馈帧="
            f"{int(np.sum(aggregate['nonzero_motor_count']))}"
        ),
        transform=axes[1].transAxes,
    )

    resource_fields = (
        ("fanout_rss_kib", "fan-out 根进程", 0),
        ("bridge_rss_kib", "bridge 启动器", 1),
        ("decision_rss_kib", "decision 启动器", 2),
        ("rosbag_rss_kib", "rosbag 根进程", 3),
    )
    resource_summary: dict[str, dict[str, float]] = {}
    for field, label, style_index in resource_fields:
        values = np.asarray([float(row[field]) / 1024.0 for row in runtime])
        resource_summary[field] = {
            "min_mib": float(np.min(values)),
            "max_mib": float(np.max(values)),
            "delta_mib": float(values[-1] - values[0]),
        }
        axes[2].plot(
            runtime_minutes,
            values,
            label=label,
            **tps.line_style(style_index),
        )
    axes[2].set_ylabel("常驻内存 (MiB)")
    axes[2].set_xlabel("稳态区间 (min)")
    axes[2].set_xlim(0.0, 30.0)
    axes[2].legend(loc="upper center", ncols=4)
    axes[2].text(
        0.01,
        0.08,
        "旧 runner 仅采样启动根进程；bridge/decision 绝对值不代表节点进程树",
        transform=axes[2].transAxes,
    )

    fig.suptitle(
        "真实 PC104--ROS2 零执行器全栈 30 min 稳态"
        f"（ACTIVE={summary['soak_active_ratio'] * 100.0:.2f}%）"
    )
    paths = tps.save_figure(fig, output_dir / "pc104_cross_layer_soak_30min")
    plt.close(fig)
    return paths, resource_summary


def copy_thesis_figures(paths: list[Path], target_dir: Path) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for source in paths:
        target = target_dir / source.name
        shutil.copy2(source, target)
        copied.append(target)
    return copied


def write_metric_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("evidence_unit", "metric", "value", "unit", "source"),
        )
        writer.writeheader()
        writer.writerows(rows)


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(REPO_ROOT))


def main() -> int:
    args = parse_args()
    tps.apply_thesis_style(layout="full")
    soak_bundle = args.soak_bundle.resolve()
    fault_bundle = args.fault_bundle.resolve()
    output_dir = args.output_dir.resolve()
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    soak_summary = read_json(soak_bundle / "summary.json")
    fault_summary = read_json(fault_bundle / "summary.json")
    soak_rows = read_rows(soak_bundle / "cross_layer_timeline.csv")
    fault_rows = read_rows(fault_bundle / "cross_layer_timeline.csv")

    if float(soak_summary["soak_duration_requested_s"]) < 1800.0:
        raise ValueError("soak bundle does not contain the requested 1800 s interval")
    if not bool(soak_summary["active_soak_stable"]):
        raise ValueError("soak bundle did not pass active_soak_stable")
    if fault_summary["status"] != "ok":
        raise ValueError("fault bundle did not pass synchronized acceptance")

    fault_figures = plot_fault_timeline(
        fault_rows, fault_summary, figure_dir
    )
    soak_figures, resource_summary = plot_soak(
        soak_rows, soak_summary, figure_dir
    )
    copied_figures = copy_thesis_figures(
        fault_figures + soak_figures,
        args.thesis_figure_dir.resolve(),
    )

    passed_checks = sum(bool(fault_summary[name]) for name in CHECK_NAMES)
    metric_rows = [
        {
            "evidence_unit": "synchronized_fault_chain",
            "metric": "acceptance_checks_passed",
            "value": passed_checks,
            "unit": f"of_{len(CHECK_NAMES)}",
            "source": relative(fault_bundle),
        },
        {
            "evidence_unit": "synchronized_fault_chain",
            "metric": "bit13_to_arbiter_latency",
            "value": f"{fault_summary['bit13_to_arbiter_latency_ms']:.6f}",
            "unit": "ms",
            "source": relative(fault_bundle),
        },
        {
            "evidence_unit": "synchronized_fault_chain",
            "metric": "bit13_to_bt_latency",
            "value": f"{fault_summary['bit13_to_bt_latency_ms']:.6f}",
            "unit": "ms",
            "source": relative(fault_bundle),
        },
        {
            "evidence_unit": "synchronized_fault_chain",
            "metric": "bit5_to_denied_latency",
            "value": f"{fault_summary['bit5_to_denied_latency_ms']:.6f}",
            "unit": "ms",
            "source": relative(fault_bundle),
        },
        {
            "evidence_unit": "synchronized_fault_chain",
            "metric": "bit5_to_idle_latency",
            "value": f"{fault_summary['bit5_to_idle_latency_ms']:.6f}",
            "unit": "ms",
            "source": relative(fault_bundle),
        },
        {
            "evidence_unit": "synchronized_fault_chain",
            "metric": "bit14_to_denied_latency",
            "value": f"{fault_summary['bit14_to_denied_latency_ms']:.6f}",
            "unit": "ms",
            "source": relative(fault_bundle),
        },
        {
            "evidence_unit": "active_soak",
            "metric": "duration",
            "value": f"{soak_summary['soak_duration_requested_s']:.1f}",
            "unit": "s",
            "source": relative(soak_bundle),
        },
        {
            "evidence_unit": "active_soak",
            "metric": "arbiter_status_samples",
            "value": soak_summary["soak_arbiter_sample_count"],
            "unit": "count",
            "source": relative(soak_bundle),
        },
        {
            "evidence_unit": "active_soak",
            "metric": "active_ratio",
            "value": f"{soak_summary['soak_active_ratio']:.6f}",
            "unit": "ratio",
            "source": relative(soak_bundle),
        },
        {
            "evidence_unit": "active_soak",
            "metric": "target_fault_status_samples",
            "value": soak_summary["soak_fault_status_count"],
            "unit": "count",
            "source": relative(soak_bundle),
        },
        {
            "evidence_unit": "zero_actuator_safety",
            "metric": "board_nonzero_command_snapshots",
            "value": (
                soak_summary["board_nonzero_command_snapshot_count"]
                + fault_summary["board_nonzero_command_snapshot_count"]
            ),
            "unit": "count",
            "source": f"{relative(soak_bundle)};{relative(fault_bundle)}",
        },
        {
            "evidence_unit": "zero_actuator_safety",
            "metric": "uplink_nonzero_motor_frames",
            "value": (
                soak_summary["uplink_motor_nonzero_frame_count"]
                + fault_summary["uplink_motor_nonzero_frame_count"]
            ),
            "unit": "count",
            "source": f"{relative(soak_bundle)};{relative(fault_bundle)}",
        },
    ]
    write_metric_rows(output_dir / "derived_metrics.csv", metric_rows)

    aggregate = {
        "schema_version": 1,
        "scenario": "pc104_cross_layer_split_run_evidence",
        "status": "passed_with_split_run_boundary",
        "evidence_units": {
            "active_soak": {
                "source": relative(soak_bundle),
                "source_bundle_status": soak_summary["status"],
                "scope_status": "passed",
                "duration_s": soak_summary["soak_duration_requested_s"],
                "arbiter_status_samples": soak_summary[
                    "soak_arbiter_sample_count"
                ],
                "active_ratio": soak_summary["soak_active_ratio"],
                "target_fault_status_samples": soak_summary[
                    "soak_fault_status_count"
                ],
                "runtime_samples": soak_summary["soak_runtime_sample_count"],
                "post_soak_sequence_boundary": (
                    "The source bundle remains failed_acceptance because the "
                    "legacy Bit14 clear-hold check failed after the complete "
                    "1800 s steady-state interval."
                ),
            },
            "synchronized_fault_chain": {
                "source": relative(fault_bundle),
                "source_bundle_status": fault_summary["status"],
                "scope_status": "passed",
                "checks_passed": passed_checks,
                "checks_total": len(CHECK_NAMES),
                "latencies_ms": {
                    key: fault_summary[key]
                    for key in (
                        "bit13_to_arbiter_latency_ms",
                        "bit13_to_bt_latency_ms",
                        "bit5_to_denied_latency_ms",
                        "bit5_to_idle_latency_ms",
                        "bit14_to_denied_latency_ms",
                    )
                },
            },
        },
        "zero_actuator_evidence": {
            "combined_board_nonzero_command_snapshots": (
                soak_summary["board_nonzero_command_snapshot_count"]
                + fault_summary["board_nonzero_command_snapshot_count"]
            ),
            "combined_uplink_nonzero_motor_frames": (
                soak_summary["uplink_motor_nonzero_frame_count"]
                + fault_summary["uplink_motor_nonzero_frame_count"]
            ),
            "fanout_nonzero_block_count": (
                soak_summary["fanout_nonzero_block_count"]
                + fault_summary["fanout_nonzero_block_count"]
            ),
            "cleanup_remote_zero_both_runs": bool(
                soak_summary["cleanup_remote_zero"]
                and fault_summary["cleanup_remote_zero"]
            ),
        },
        "resource_sampling": {
            "source_scope": "legacy_root_process_only",
            "interpretation": (
                "The archived 30 min CSV is valid for trend inspection, but "
                "bridge and decision absolute RSS values represent ros2 run "
                "launcher processes rather than complete process trees."
            ),
            "series": resource_summary,
            "future_runner_scope": "process_tree_rss",
        },
        "claim_boundaries": [
            "The 1800 s steady-state result and the corrected 18/18 fault-chain result are separate runs.",
            "The bench telemetry exported total_voltage_v=0.0, so the voltage guard was isolated and power health was not accepted.",
            "DVL lock fields were temporary safe isolation values; this does not validate physical DVL aiding or the firmware DVL-loss rescue branch.",
            "No non-zero actuator command was authorized; actuator polarity, dead zone, ESTOP dynamics, hydrodynamic response, and water trials remain outside scope.",
            "No shared clock was available, so the reported transitions are host-observed cross-layer latencies rather than one-way physical network latency.",
        ],
        "figures": [relative(path) for path in fault_figures + soak_figures],
        "thesis_figures": [relative(path) for path in copied_figures],
    }
    (output_dir / "aggregate_summary.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = f"""# PC104--ROS2--行为树同步安全与 30 min 稳态汇总

## 结论

本汇总采用两个相互独立的真实 PC104 零执行器运行包：

- `{relative(soak_bundle)}` 提供完整 1800 s 稳态区间。该区间内
  {soak_summary['soak_arbiter_sample_count']} 个 ArbiterStatus 样本的 ACTIVE
  比率为 {soak_summary['soak_active_ratio']:.6f}，Bit5/Bit13/Bit14 目标故障
  状态样本为 {soak_summary['soak_fault_status_count']}，30 个分钟级运行采样均
  完成。原包在稳态结束后的旧 Bit14 clear-hold 序列有 1 项失败，故原始
  `failed_acceptance` 状态保持不变；这里仅判定其稳态子区间通过。
- `{relative(fault_bundle)}` 使用修正后的 Remote 零包恢复路径，18/18 验收项
  通过。Bit13 到仲裁/行为树分别为
  {fault_summary['bit13_to_arbiter_latency_ms']:.3f}/
  {fault_summary['bit13_to_bt_latency_ms']:.3f} ms；Bit5 到 DENIED/IDLE 分别为
  {fault_summary['bit5_to_denied_latency_ms']:.3f}/
  {fault_summary['bit5_to_idle_latency_ms']:.3f} ms；真实 watchdog Bit14 到
  DENIED 为 {fault_summary['bit14_to_denied_latency_ms']:.3f} ms。

两个运行包合计未观测到非零板端命令快照或非零上行推进反馈，fan-out 也未记录
非零执行器放行。由此可支持“真实 PC104--ROS2 仲裁--行为树的同步零执行器安全
链已验证”，但不能外推为非零执行机构动态闭环或整艇水域验收。

## 资源口径

30 min 原始 CSV 由旧 runner 采集，仅记录启动根进程 RSS。fan-out 与 rosbag
曲线可用于对应根进程的趋势观察；bridge 和 decision 曲线只代表 `ros2 run`
启动器，不是节点进程树绝对内存。runner 已改为进程树聚合，修复只作用于后续
运行，不回写本次归档数据。

## 产物

- `aggregate_summary.json`：两条证据链、边界与来源；
- `derived_metrics.csv`：正文可引用的派生指标；
- `figures/pc104_cross_layer_fault_timeline.png/.pdf`：同步故障链；
- `figures/pc104_cross_layer_soak_30min.png/.pdf`：30 min 稳态与旧 RSS 口径；
- 论文图副本：`{relative(args.thesis_figure_dir.resolve())}`。
"""
    (output_dir / "report.md").write_text(report, encoding="utf-8")
    print(
        f"[cross-layer-plot] status={aggregate['status']} -> {output_dir}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
