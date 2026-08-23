#!/usr/bin/env python3
"""Plot and independently derive metrics from a PC104 fault-injection bundle."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Callable

import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import thesis_plot_style as tps  # noqa: E402


REMOTE_MODE = 0x01
JETSON_MODE = 0xEE
COMMAND_FIELDS = (
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
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def elapsed(row: dict[str, str]) -> float:
    return float(row["elapsed_s"])


def first_time(
    rows: list[dict[str, str]],
    phase: str,
    event_type: str,
    predicate: Callable[[dict[str, str]], bool] | None = None,
) -> float | None:
    for row in rows:
        if row["phase"] != phase or row["event_type"] != event_type:
            continue
        if predicate is None or predicate(row):
            return elapsed(row)
    return None


def phase_trials(rows: list[dict[str, str]], prefix: str) -> list[int]:
    trials: set[int] = set()
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    for row in rows:
        match = pattern.match(row["phase"])
        if match:
            trials.add(int(match.group(1)))
    return sorted(trials)


def delta_ms(event_time: float | None, origin: float | None) -> float:
    if event_time is None or origin is None:
        return float("nan")
    return (event_time - origin) * 1000.0


def derive_trials(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for trial in phase_trials(rows, "heartbeat_outage"):
        outage = f"heartbeat_outage_{trial}"
        recovery = f"heartbeat_recovery_{trial}"
        outage_start = first_time(rows, outage, "phase_start")
        recovery_start = first_time(rows, recovery, "phase_start")
        trigger = first_time(
            rows,
            outage,
            "uplink_recv",
            lambda row: int(row["bit14_jetson_timeout"]) == 1,
        )
        remote = first_time(
            rows,
            outage,
            "uplink_recv",
            lambda row: int(row["control_mode_byte"]) == REMOTE_MODE,
        )
        recovered = first_time(
            rows,
            recovery,
            "uplink_recv",
            lambda row: int(row["control_mode_byte"]) == JETSON_MODE,
        )
        cleared = first_time(
            rows,
            recovery,
            "uplink_recv",
            lambda row: int(row["bit14_jetson_timeout"]) == 0,
        )
        metrics.append(
            {
                "test_type": "natural_heartbeat_outage",
                "trial": trial,
                "trigger_ms": delta_ms(trigger, outage_start),
                "remote_mode_ms": delta_ms(remote, outage_start),
                "recovery_mode_ms": delta_ms(recovered, recovery_start),
                "bit_clear_ms": delta_ms(cleared, recovery_start),
            }
        )

    for trial in phase_trials(rows, "forced_timeout"):
        fault = f"forced_timeout_{trial}"
        recovery = f"forced_timeout_recovery_{trial}"
        injected = first_time(
            rows,
            fault,
            "telnet_injection",
            lambda row: row["note"] == "Not_Recv_From_Jetson_No=10",
        )
        recovery_start = first_time(rows, recovery, "phase_start")
        trigger = first_time(
            rows,
            fault,
            "uplink_recv",
            lambda row: int(row["bit14_jetson_timeout"]) == 1,
        )
        remote = first_time(
            rows,
            fault,
            "uplink_recv",
            lambda row: int(row["control_mode_byte"]) == REMOTE_MODE,
        )
        recovered = first_time(
            rows,
            recovery,
            "uplink_recv",
            lambda row: (
                int(row["control_mode_byte"]) == JETSON_MODE
                and int(row["bit14_jetson_timeout"]) == 0
            ),
        )
        metrics.append(
            {
                "test_type": "telnet_forced_timeout",
                "trial": trial,
                "trigger_ms": delta_ms(trigger, injected),
                "remote_mode_ms": delta_ms(remote, injected),
                "recovery_mode_ms": delta_ms(recovered, recovery_start),
                "bit_clear_ms": delta_ms(recovered, recovery_start),
            }
        )
    return metrics


def finite(values: list[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    return array[np.isfinite(array)]


def distribution(values: list[float]) -> dict[str, float | int | None]:
    array = finite(values)
    if not array.size:
        return {
            "count": 0,
            "min_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "max_ms": None,
        }
    return {
        "count": int(array.size),
        "min_ms": float(np.min(array)),
        "p50_ms": float(np.quantile(array, 0.50)),
        "p95_ms": float(np.quantile(array, 0.95)),
        "max_ms": float(np.max(array)),
    }


def phase_spans(rows: list[dict[str, str]]) -> list[tuple[str, float, float]]:
    starts: dict[str, float] = {}
    spans: list[tuple[str, float, float]] = []
    for row in rows:
        if row["event_type"] == "phase_start":
            starts[row["phase"]] = elapsed(row)
        elif row["event_type"] == "phase_end" and row["phase"] in starts:
            spans.append((row["phase"], starts[row["phase"]], elapsed(row)))
    return spans


def add_fault_spans(axes, spans: list[tuple[str, float, float]]) -> None:
    styles = (
        ("heartbeat_outage_", "#c44e52", "自然心跳中断"),
        ("controlled_loss", "#dd8452", "30% 应用层丢包"),
        ("controlled_delay", "#4c72b0", "200 ms 排队延迟"),
        ("forced_timeout_", "#8172b3", "telnet 强制超时"),
        ("error_feedback_injected", "#7f7f7f", "Bit5 错误注入"),
    )
    labelled: set[str] = set()
    for phase, start, end in spans:
        for prefix, color, label in styles:
            if not phase.startswith(prefix):
                continue
            plot_label = label if label not in labelled else None
            for axis in axes:
                axis.axvspan(
                    start,
                    end,
                    color=color,
                    alpha=0.10,
                    linewidth=0,
                    label=plot_label if axis is axes[0] else None,
                )
            labelled.add(label)
            break


def plot_timeline(
    rows: list[dict[str, str]],
    output_dir: Path,
) -> list[Path]:
    uplinks = [row for row in rows if row["event_type"] == "uplink_recv"]
    snapshots = [row for row in rows if row["event_type"] == "telnet_snapshot"]
    t_up = np.asarray([elapsed(row) for row in uplinks])
    t_snap = np.asarray([elapsed(row) for row in snapshots])
    mode = np.asarray(
        [
            1.0 if int(row["control_mode_byte"]) == JETSON_MODE else 0.0
            for row in uplinks
        ]
    )
    bit14 = np.asarray([int(row["bit14_jetson_timeout"]) for row in uplinks])
    bit5 = np.asarray([int(row["bit5_system_communication"]) for row in uplinks])
    watchdog = np.asarray([int(row["watchdog_count"]) for row in snapshots])
    command_max = np.asarray(
        [max(abs(int(row[key])) for key in COMMAND_FIELDS) for row in snapshots]
    )

    fig, axes = plt.subplots(
        4,
        1,
        figsize=tps.figure_size("full", height=4.8),
        sharex=True,
        constrained_layout=True,
    )
    add_fault_spans(axes, phase_spans(rows))

    axes[0].step(t_up, mode, where="post", color=tps.ACCENT_COLORS[0])
    axes[0].set_yticks((0, 1), ("遥控", "Jetson"))
    axes[0].set_ylabel("控制模式")
    phase_handles, phase_labels = axes[0].get_legend_handles_labels()
    fig.legend(
        phase_handles,
        phase_labels,
        loc="outside upper center",
        ncols=5,
    )

    bit14_style = tps.line_style(3)
    bit5_style = tps.line_style(1)
    bit14_style.pop("marker", None)
    bit5_style.pop("marker", None)
    axes[1].step(t_up, bit14, where="post", label="Bit14 Jetson 超时", **bit14_style)
    axes[1].step(t_up, bit5, where="post", label="Bit5 系统通信", **bit5_style)
    axes[1].set_yticks((0, 1))
    axes[1].set_ylabel("故障位")
    axes[1].legend(loc="upper right")

    axes[2].plot(t_snap, watchdog, label="watchdog 计数", **tps.line_style(2))
    axes[2].axhline(10, color="black", linestyle="--", linewidth=1.2, label="阈值 10")
    axes[2].set_ylabel("计数")
    axes[2].legend(loc="upper right")

    axes[3].plot(t_snap, command_max, label="命令绝对值最大值", **tps.line_style(0))
    axes[3].set_ylim(-0.05, max(0.5, float(np.max(command_max)) + 0.5))
    axes[3].set_ylabel("命令值")
    axes[3].set_xlabel("实验时间 (s)")
    axes[3].legend(loc="upper right")
    paths = tps.save_figure(fig, output_dir / "pc104_fault_timeline")
    plt.close(fig)
    return paths


def plot_latencies(
    trials: list[dict[str, Any]],
    output_dir: Path,
) -> list[Path]:
    natural = [row for row in trials if row["test_type"] == "natural_heartbeat_outage"]
    forced = [row for row in trials if row["test_type"] == "telnet_forced_timeout"]
    categories = [
        ("自然触发", [float(row["trigger_ms"]) for row in natural]),
        ("自然降级", [float(row["remote_mode_ms"]) for row in natural]),
        ("模式恢复", [float(row["recovery_mode_ms"]) for row in natural]),
        ("故障位清除", [float(row["bit_clear_ms"]) for row in natural]),
        ("强制触发", [float(row["trigger_ms"]) for row in forced]),
        ("强制恢复", [float(row["recovery_mode_ms"]) for row in forced]),
    ]
    fig, axis = plt.subplots(
        figsize=tps.figure_size("full", height=3.2),
        constrained_layout=True,
    )
    for index, (label, values) in enumerate(categories):
        array = finite(values)
        x = np.full(array.size, index + 1, dtype=float)
        if array.size > 1:
            x += np.linspace(-0.08, 0.08, array.size)
        axis.scatter(
            x,
            array,
            s=34,
            color=tps.ACCENT_COLORS[index % len(tps.ACCENT_COLORS)],
            edgecolor="black",
            linewidth=0.5,
            zorder=3,
        )
        if array.size:
            median = float(np.median(array))
            axis.hlines(
                median,
                index + 0.72,
                index + 1.28,
                colors="black",
                linewidth=2.0,
            )
            axis.text(
                index + 1,
                median + 24,
                f"{median:.1f}",
                ha="center",
                va="bottom",
                fontsize=9,
            )
    axis.set_xticks(range(1, len(categories) + 1), [item[0] for item in categories])
    axis.set_ylabel("时延 (ms)")
    axis.set_title("逐轮故障触发、降级与恢复时延")
    axis.set_ylim(bottom=0)
    paths = tps.save_figure(fig, output_dir / "pc104_fault_latency_trials")
    plt.close(fig)
    return paths


def plot_impairments(
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    output_dir: Path,
) -> list[Path]:
    delay = finite(
        [
            float(row["generation_to_send_ms"])
            for row in rows
            if row["event_type"] == "downlink_send"
            and row["phase"] == "controlled_delay"
            and row["generation_to_send_ms"]
        ]
    )
    counters = [
        int(summary["uplink_parse_error_count"]),
        int(summary["dvl_interference_frame_count"]),
        int(summary["loss_phase_timeout_frame_count"]),
        int(summary["delay_phase_timeout_frame_count"]),
        int(summary["nonzero_uplink_motor_frame_count"]),
        int(summary["nonzero_telnet_command_snapshot_count"]),
    ]
    counter_labels = ("解析错误", "DVL干扰", "丢包超时", "延迟超时", "电机反馈", "非零命令")

    fig, axes = plt.subplots(
        1,
        3,
        figsize=tps.figure_size("full", height=2.7),
        constrained_layout=True,
    )
    configured = float(summary["controlled_loss_configured_rate"]) * 100.0
    actual = float(summary["controlled_loss_actual_rate"]) * 100.0
    axes[0].bar(
        (0, 1),
        (configured, actual),
        tick_label=("配置率", "实现率"),
        **tps.series_style(1),
    )
    axes[0].set_ylabel("丢包率 (%)")
    axes[0].set_title(
        f"固定种子丢包 ({summary['deliberate_drop_count']}/"
        f"{summary['controlled_loss_generated_count']})"
    )
    axes[0].set_ylim(0, max(35.0, configured + 5.0))

    axes[1].hist(
        delay,
        bins=min(20, max(8, int(round(math.sqrt(delay.size))))),
        alpha=0.78,
        **tps.series_style(0),
    )
    axes[1].axvline(
        float(summary["controlled_delay_p95_ms"]),
        color=tps.ACCENT_COLORS[3],
        linestyle="--",
        linewidth=1.5,
        label=f"p95={float(summary['controlled_delay_p95_ms']):.1f} ms",
    )
    axes[1].set_xlabel("生成至发送时延 (ms)")
    axes[1].set_ylabel("样本数")
    axes[1].set_title("200 ms 排队延迟实现值")
    axes[1].legend()

    bars = axes[2].bar(
        np.arange(len(counters)),
        counters,
        **tps.series_style(2),
    )
    axes[2].set_xticks(np.arange(len(counters)), counter_labels, rotation=25, ha="right")
    axes[2].set_ylabel("事件/帧数")
    axes[2].set_title("安全与隔离异常计数")
    axes[2].set_ylim(0, max(1.0, max(counters, default=0) + 0.5))
    axes[2].bar_label(bars, padding=3)

    paths = tps.save_figure(fig, output_dir / "pc104_impairment_summary")
    plt.close(fig)
    return paths


def write_trial_csv(path: Path, trials: list[dict[str, Any]]) -> None:
    fields = (
        "test_type",
        "trial",
        "trigger_ms",
        "remote_mode_ms",
        "recovery_mode_ms",
        "bit_clear_ms",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(trials)


def write_derived_summary(
    path: Path,
    bundle: Path,
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    trials: list[dict[str, Any]],
    plots: list[Path],
) -> None:
    natural = [row for row in trials if row["test_type"] == "natural_heartbeat_outage"]
    forced = [row for row in trials if row["test_type"] == "telnet_forced_timeout"]
    payload = {
        "source_bundle": str(bundle),
        "source_timeline": str(bundle / "fault_timeline.csv"),
        "source_status": summary["status"],
        "natural_timeout": {
            "trigger": distribution([float(row["trigger_ms"]) for row in natural]),
            "remote_mode": distribution(
                [float(row["remote_mode_ms"]) for row in natural]
            ),
            "recovery_mode": distribution(
                [float(row["recovery_mode_ms"]) for row in natural]
            ),
            "bit_clear": distribution(
                [float(row["bit_clear_ms"]) for row in natural]
            ),
        },
        "forced_timeout": {
            "trigger": distribution([float(row["trigger_ms"]) for row in forced]),
            "recovery": distribution(
                [float(row["recovery_mode_ms"]) for row in forced]
            ),
        },
        "impairment": {
            "loss_configured_rate": summary["controlled_loss_configured_rate"],
            "loss_actual_rate": summary["controlled_loss_actual_rate"],
            "loss_generated_count": summary["controlled_loss_generated_count"],
            "loss_dropped_count": summary["deliberate_drop_count"],
            "delay_p50_ms": summary["controlled_delay_p50_ms"],
            "delay_p95_ms": summary["controlled_delay_p95_ms"],
        },
        "safety": {
            "uplink_parse_error_count": summary["uplink_parse_error_count"],
            "dvl_interference_frame_count": summary["dvl_interference_frame_count"],
            "loss_timeout_frame_count": summary["loss_phase_timeout_frame_count"],
            "delay_timeout_frame_count": summary["delay_phase_timeout_frame_count"],
            "nonzero_uplink_motor_frame_count": summary[
                "nonzero_uplink_motor_frame_count"
            ],
            "nonzero_telnet_command_snapshot_count": summary[
                "nonzero_telnet_command_snapshot_count"
            ],
            "cleanup_remote_zero": summary["cleanup_remote_zero"],
            "fin_feedback_note": (
                "The constant +/-180 deg uplink values are FMCU position "
                "feedback from zero/default raw positions, not PC104 commands."
            ),
        },
        "sample_count": sum(row["event_type"] == "uplink_recv" for row in rows),
        "plots": [str(plot) for plot in plots],
        "boundary": (
            "Loss and delay were injected at the container sender before the "
            "host relay. Bit5 was injected into PC104 runtime state via telnetd."
        ),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    bundle = args.bundle.resolve()
    timeline_path = bundle / "fault_timeline.csv"
    summary_path = bundle / "summary.json"
    if not timeline_path.is_file() or not summary_path.is_file():
        raise SystemExit(f"missing fault-injection artifacts under {bundle}")
    output_dir = (args.output_dir or (bundle / "figures")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_rows(timeline_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    trials = derive_trials(rows)
    if not trials:
        raise SystemExit("no timeout trials found in timeline")

    tps.apply_thesis_style(layout="full")
    plots = [
        *plot_timeline(rows, output_dir),
        *plot_latencies(trials, output_dir),
        *plot_impairments(rows, summary, output_dir),
    ]
    write_trial_csv(output_dir / "fault_trial_metrics.csv", trials)
    write_derived_summary(
        output_dir / "fault_derived_summary.json",
        bundle,
        rows,
        summary,
        trials,
        plots,
    )
    print(
        f"[pc104-fault-plot] trials={len(trials)} plots={len(plots)} "
        f"-> {output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
