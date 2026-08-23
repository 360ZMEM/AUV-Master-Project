#!/usr/bin/env python3
"""Reproduce and visualize Jetson MPC timing evidence.

Default mode runs a clean target-platform benchmark.  ``--existing`` only
re-analyzes archived raw samples and is safe while other installation work is
in progress.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from tools import thesis_plot_style as tps  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXPERIMENT_DIR / "config.yaml")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--existing", action="store_true", help="Only analyze archived evidence; do not run workloads.")
    source.add_argument("--run-dir", type=Path, help="Re-analyze one current run bundle without starting a new workload.")
    source.add_argument(
        "--render-mpc-figure-from-run",
        type=Path,
        help="Only redraw the thesis MPC figure from an archived Jetson run.",
    )
    parser.add_argument("--allow-busy", action="store_true", help="Run despite competing processes and mark contaminated.")
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def resolve_project_root(config_path: Path, cfg: dict) -> Path:
    value = Path(cfg.get("project_root", "../.."))
    return (config_path.parent / value).resolve()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def finite(values) -> np.ndarray:
    parsed = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            parsed.append(number)
    return np.asarray(parsed, dtype=float)


def percentile_summary(values: np.ndarray) -> dict:
    if values.size == 0:
        return {"n": 0, "mean_ms": None, "p50_ms": None, "p95_ms": None, "p99_ms": None, "max_ms": None}
    return {
        "n": int(values.size),
        "mean_ms": float(values.mean()),
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
        "p99_ms": float(np.percentile(values, 99)),
        "max_ms": float(values.max()),
    }


def scalar_summary(values: np.ndarray) -> dict:
    """Summarize a generic scalar without incorrectly attaching ms units."""
    if values.size == 0:
        return {"n": 0, "mean": None, "p50": None, "p95": None, "p99": None, "min": None, "max": None}
    return {
        "n": int(values.size),
        "mean": float(values.mean()),
        "p50": float(np.percentile(values, 50)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
        "min": float(values.min()),
        "max": float(values.max()),
    }


def success_ratio(rows: list[dict[str, str]]) -> float | None:
    if not rows:
        return None
    ok = {"Solve_Succeeded", "Search_Direction_Becomes_Too_Small"}
    return sum(row.get("solver_status", "") in ok for row in rows) / len(rows)


def locate_sources(project_root: Path, cfg: dict, override: dict | None = None) -> dict[str, Path]:
    if override:
        return override
    evidence = cfg["historical_evidence"]
    return {
        "steady": project_root / evidence["steady_dir"],
        "stress": project_root / evidence["stress_dir"],
        "pc104": project_root / evidence["pc104_dir"],
    }


def collect_solver_metrics(source_dir: Path) -> dict:
    result = {"source_dir": str(source_dir), "modes": {}}
    for mode in ("cold", "warm"):
        rows = read_csv(source_dir / f"mpc_solve_microbench_{mode}_raw.csv")
        wall = finite(row.get("wall_ms") for row in rows)
        internal = finite(row.get("ipopt_ms") for row in rows)
        result["modes"][mode] = {
            "wall": percentile_summary(wall),
            "solver_internal": percentile_summary(internal),
            "success_ratio": success_ratio(rows),
            "dominant_status": max(
                ((status, sum(r.get("solver_status") == status for r in rows)) for status in {r.get("solver_status", "") for r in rows}),
                key=lambda item: item[1],
            )[0] if rows else "not_observed",
        }
    return result


def collect_pc104_metrics(source_dir: Path) -> tuple[dict, np.ndarray, np.ndarray]:
    summary_rows = read_csv(source_dir / "udp_timing_summary.csv")
    if not summary_rows:
        raise RuntimeError(f"empty PC104 summary: {source_dir}")
    row = summary_rows[-1]
    samples = read_csv(source_dir / "udp_timing_samples.csv")
    uplink_rows = [sample for sample in samples if sample.get("event_type") == "uplink_recv"]
    frame_gaps = []
    paired = []
    for sample in uplink_rows:
        try:
            frame_gaps.append(int(sample.get("uplink_frame_gap", "")))
        except ValueError:
            pass
        interval = finite([sample.get("uplink_interarrival_ms")])
        elapsed_value = finite([sample.get("elapsed_s")])
        if interval.size and elapsed_value.size:
            paired.append((float(elapsed_value[0]), float(interval[0])))
    elapsed = np.asarray([item[0] for item in paired], dtype=float)
    intervals = np.asarray([item[1] for item in paired], dtype=float)
    metrics = {
        "source_dir": str(source_dir),
        "status": row.get("status"),
        "duration_s": float(row["duration_s"]),
        "downlink_count": int(row["downlink_count"]),
        "uplink_count": int(row["uplink_count"]),
        "parse_error_count": int(row["parse_error_count"]),
        "observed_uplink_rate_hz": float(row["observed_uplink_rate_hz"]),
        "interarrival": percentile_summary(intervals),
        "reported_p50_ms": float(row["uplink_interarrival_p50_ms"]),
        "reported_p95_ms": float(row["uplink_interarrival_p95_ms"]),
        "reported_p99_ms": float(row["uplink_interarrival_p99_ms"]),
        "sequence_gap_count": int(row["uplink_sequence_gap_count"]),
        "estimated_lost_frames": int(row["uplink_estimated_lost_frames"]),
        "repeated_frame_counter_count": sum(value == 0 for value in frame_gaps),
        "forward_gap_over_one_count": sum(value > 1 for value in frame_gaps),
        "one_way_latency_claim": False,
        "round_trip_latency_claim": False,
    }
    return metrics, intervals, elapsed


def collect_resource_metrics(run_dir: Path | None) -> dict:
    if run_dir is None:
        return {"status": "not_observed"}
    path = run_dir / "resource_samples.csv"
    rows = read_csv(path)
    elapsed = finite(row.get("elapsed_s") for row in rows)
    phase_counts = {phase: sum(row.get("phase") == phase for row in rows) for phase in sorted({row.get("phase", "") for row in rows})}
    fields = {
        "cpu_percent": "%",
        "gpu_percent": "%",
        "memory_used_mb": "MiB",
        "load1": "count",
        "max_temp_c": "degC",
    }
    result = {
        "status": "recorded",
        "source": str(path),
        "duration_s": None if elapsed.size == 0 else float(elapsed.max()),
        "sample_count": len(rows),
        "phase_sample_count": phase_counts,
        "sample_interval_s": scalar_summary(np.diff(elapsed)),
        "scope": "system-wide Jetson telemetry; not per-process attribution",
        "by_phase": {},
    }
    for field, unit in fields.items():
        result[field] = {"unit": unit, **scalar_summary(finite(row.get(field) for row in rows))}
    for phase in phase_counts:
        phase_rows = [row for row in rows if row.get("phase") == phase]
        result["by_phase"][phase] = {
            field: {"unit": unit, **scalar_summary(finite(row.get(field) for row in phase_rows))}
            for field, unit in fields.items()
        }
    return result


def collect_repeatability_metrics(run_dir: Path | None) -> dict:
    """Compare compatible clean solver runs without mixing resource profiles."""
    if run_dir is None:
        return {"status": "not_observed"}
    current_env = json.loads((run_dir / "environment.json").read_text(encoding="utf-8"))
    compatible = []
    for candidate in sorted(run_dir.parent.iterdir()):
        env_path = candidate / "environment.json"
        if not env_path.is_file():
            continue
        env = json.loads(env_path.read_text(encoding="utf-8"))
        if env.get("contaminated") or env.get("git_commit") != current_env.get("git_commit"):
            continue
        if env.get("machine") != current_env.get("machine") or env.get("cpu_count") != current_env.get("cpu_count"):
            continue
        if not all((candidate / case / f"mpc_solve_microbench_{mode}_raw.csv").is_file() for case in ("steady", "stress") for mode in ("cold", "warm")):
            continue
        compatible.append(candidate)
    result = {
        "status": "recorded",
        "run_count": len(compatible),
        "run_ids": [candidate.name for candidate in compatible],
        "p95_ms_across_runs": {},
    }
    for case in ("steady", "stress"):
        result["p95_ms_across_runs"][case] = {}
        for mode in ("cold", "warm"):
            values = [collect_solver_metrics(candidate / case)["modes"][mode]["wall"]["p95_ms"] for candidate in compatible]
            result["p95_ms_across_runs"][case][mode] = {
                "values": values,
                "min": min(values),
                "max": max(values),
            }
    return result


def write_summary_csv(path: Path, metrics: dict, budgets: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["evidence", "mode", "n", "mean_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms", "success_ratio", "claim"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for evidence in ("steady", "stress"):
            for mode in ("cold", "warm"):
                values = metrics["mpc"][evidence]["modes"][mode]["wall"]
                writer.writerow({
                    "evidence": evidence,
                    "mode": mode,
                    **values,
                    "success_ratio": metrics["mpc"][evidence]["modes"][mode]["success_ratio"],
                    "claim": "target-platform solver microbenchmark",
                })
        p = metrics["pc104"]["interarrival"]
        writer.writerow({
            "evidence": "pc104_uplink_interarrival",
            "mode": "host_relay",
            **p,
            "success_ratio": None,
            "claim": "arrival interval only; not one-way/RTT/end-to-end latency",
        })


def load_wall(source_dir: Path, mode: str) -> np.ndarray:
    rows = read_csv(source_dir / f"mpc_solve_microbench_{mode}_raw.csv")
    return finite(row.get("wall_ms") for row in rows)


def save_figure(fig, stem: Path) -> None:
    tps.save_figure(fig, stem)


def plot_solver_distributions(fig_dir: Path, sources: dict[str, Path], budgets: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tps.apply_thesis_style(layout="full")
    groups = [
        ("稳态冷启动", load_wall(sources["steady"], "cold"), tps.BASELINE_1),
        ("稳态热启动", load_wall(sources["steady"], "warm"), tps.PROPOSED),
        ("约束压力冷启动", load_wall(sources["stress"], "cold"), tps.BASELINE_2),
        ("约束压力热启动", load_wall(sources["stress"], "warm"), tps.BASELINE_3),
    ]
    fig, axes = plt.subplots(
        1,
        2,
        figsize=tps.figure_size("full", height=2.85),
        gridspec_kw={"width_ratios": [1.08, 0.92]},
        constrained_layout=True,
    )
    ax = axes[0]
    data = [values for _, values, _ in groups]
    box = ax.boxplot(
        data,
        tick_labels=[name for name, _, _ in groups],
        showfliers=False,
        patch_artist=True,
    )
    for patch, (_, _, color) in zip(box["boxes"], groups):
        patch.set_facecolor(color)
        patch.set_alpha(0.72)
    ax.axhline(
        float(budgets["ros_controller_20hz"]),
        color=tps.REFERENCE,
        ls="--",
        lw=1.2,
        label="20 Hz 控制周期 (50 ms)",
    )
    ax.axhline(
        float(budgets["mpc_discretization_dt"]),
        color=tps.NEUTRAL,
        ls=":",
        lw=1.2,
        label="MPC 离散周期 (200 ms)",
    )
    ax.set_yscale("log")
    ax.set_ylabel("求解时延 (ms，对数轴)")
    ax.tick_params(axis="x", rotation=18)
    ax.grid(True, axis="y", alpha=0.28)
    ax.legend(fontsize=8, loc="upper left")
    ax.set_title("(a) 目标平台 MPC 求解时延", loc="left")

    ax = axes[1]
    success = [success_ratio(read_csv(path / f"mpc_solve_microbench_{mode}_raw.csv")) for _, path, mode in [
        ("稳态冷启动", sources["steady"], "cold"),
        ("稳态热启动", sources["steady"], "warm"),
        ("约束压力冷启动", sources["stress"], "cold"),
        ("约束压力热启动", sources["stress"], "warm"),
    ]]
    bars = ax.bar([name for name, _, _ in groups], [100.0 * float(v or 0.0) for v in success], color=[color for _, _, color in groups], alpha=0.8)
    for bar, value in zip(bars, success):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2, f"{100.0 * float(value or 0.0):.0f}%", ha="center", fontsize=9)
    ax.set_ylim(0, 112)
    ax.set_ylabel("求解成功率 (%)")
    ax.tick_params(axis="x", rotation=18)
    ax.grid(True, axis="y", alpha=0.28)
    ax.set_title("(b) 稳态与约束压力下的可行性", loc="left")
    save_figure(fig, fig_dir / "jetson_mpc_latency_and_success")
    plt.close(fig)


def plot_budget_headroom(fig_dir: Path, metrics: dict, budgets: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    warm_p95 = metrics["mpc"]["steady"]["modes"]["warm"]["wall"]["p95_ms"]
    cold_p95 = metrics["mpc"]["steady"]["modes"]["cold"]["wall"]["p95_ms"]
    labels = list(budgets.keys())
    periods = np.asarray([float(budgets[label]) for label in labels])
    fig, ax = plt.subplots(figsize=(7.8, 4.2))
    x = np.arange(len(labels))
    width = 0.36
    ax.bar(x - width / 2, 100.0 * warm_p95 / periods, width, label=f"warm p95 = {warm_p95:.2f} ms", color="#4C72B0")
    ax.bar(x + width / 2, 100.0 * cold_p95 / periods, width, label=f"cold p95 = {cold_p95:.2f} ms", color="#C44E52")
    ax.axhline(100.0, color="#222222", lw=1.2, ls="--", label="period deadline")
    ax.set_xticks(x, [label.replace("_", "\n") for label in labels])
    ax.set_ylabel("p95 / period budget (%)")
    ax.set_title("Steady-state solver budget occupancy")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    save_figure(fig, fig_dir / "jetson_solver_budget_occupancy")
    plt.close(fig)


def plot_pc104_interarrival(fig_dir: Path, intervals: np.ndarray, elapsed: np.ndarray, pc104: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.0))
    ax = axes[0]
    n = min(intervals.size, elapsed.size)
    ax.plot(elapsed[-n:], intervals[-n:], lw=0.85, color="#4C72B0")
    ax.axhline(pc104["reported_p50_ms"], color="#55A868", ls="--", label=f"p50 {pc104['reported_p50_ms']:.2f} ms")
    ax.axhline(pc104["reported_p95_ms"], color="#C44E52", ls="--", label=f"p95 {pc104['reported_p95_ms']:.2f} ms")
    ax.set_xlabel("Probe elapsed time / s")
    ax.set_ylabel("Uplink inter-arrival / ms")
    ax.grid(True, alpha=0.28)
    ax.legend(fontsize=8)
    ax.set_title("Arrival-interval timeline")

    ax = axes[1]
    sorted_values = np.sort(intervals)
    cdf = np.arange(1, sorted_values.size + 1) / max(sorted_values.size, 1)
    ax.step(sorted_values, cdf, where="post", color="#8172B2")
    ax.axvline(pc104["reported_p95_ms"], color="#C44E52", ls="--")
    ax.set_xlabel("Uplink inter-arrival / ms")
    ax.set_ylabel("Empirical CDF")
    ax.grid(True, alpha=0.28)
    ax.set_title("Empirical distribution")
    fig.suptitle("PC104 host-relay uplink timing (arrival interval, not one-way latency)", y=1.02)
    fig.tight_layout()
    save_figure(fig, fig_dir / "pc104_uplink_interarrival")
    plt.close(fig)


def plot_resource_profile(fig_dir: Path, run_dir: Path | None) -> None:
    if run_dir is None:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = read_csv(run_dir / "resource_samples.csv")
    elapsed = finite(row.get("elapsed_s") for row in rows)
    if elapsed.size == 0:
        return
    cpu = finite(row.get("cpu_percent") for row in rows)
    gpu = finite(row.get("gpu_percent") for row in rows)
    memory = finite(row.get("memory_used_mb") for row in rows)
    temp = finite(row.get("max_temp_c") for row in rows)
    phases = [row.get("phase", "") for row in rows]

    fig, axes = plt.subplots(2, 1, figsize=(9.2, 5.8), sharex=True)
    n = min(elapsed.size, cpu.size, gpu.size)
    axes[0].plot(elapsed[:n], cpu[:n], label="CPU", color="#4C72B0")
    axes[0].plot(elapsed[:n], gpu[:n], label="GPU", color="#55A868")
    axes[0].set_ylabel("Utilization / %")
    axes[0].set_ylim(0, 100)
    axes[0].legend(ncol=2)
    axes[0].grid(True, alpha=0.28)

    n = min(elapsed.size, memory.size, temp.size)
    axes[1].plot(elapsed[:n], memory[:n], label="Memory / MiB", color="#8172B2")
    axes[1].set_ylabel("Memory / MiB")
    axes[1].set_xlabel("Benchmark elapsed time / s")
    axes[1].grid(True, alpha=0.28)
    temp_ax = axes[1].twinx()
    temp_ax.plot(elapsed[:n], temp[:n], label="Max temperature / °C", color="#C44E52", alpha=0.8)
    temp_ax.set_ylabel("Max temperature / °C")

    transitions = [index for index in range(1, len(phases)) if phases[index] != phases[index - 1]]
    for index in transitions:
        if index < elapsed.size:
            for ax in axes:
                ax.axvline(elapsed[index], color="#666666", ls="--", lw=0.9)
            axes[0].text(elapsed[index], 96, phases[index], ha="left", va="top", fontsize=8)
    fig.suptitle("Jetson resource profile during clean MPC microbenchmark")
    fig.tight_layout()
    save_figure(fig, fig_dir / "jetson_resource_profile")
    plt.close(fig)


def write_report(path: Path, metrics: dict, budgets: dict, resource_note: str) -> None:
    steady = metrics["mpc"]["steady"]["modes"]
    stress = metrics["mpc"]["stress"]["modes"]
    pc = metrics["pc104"]
    budget_20hz = float(budgets["ros_controller_20hz"])
    steady_deadline = (
        "本轮 warm/cold p95 均低于 50 ms；这只证明独立求解器微基准具备 20 Hz 预算余量，不代表完整 ROS2 控制链已经满足 20 Hz。"
        if max(steady["warm"]["wall"]["p95_ms"], steady["cold"]["wall"]["p95_ms"]) <= budget_20hz
        else "至少一种稳态路径的 p95 超过 50 ms，不能作为 20 Hz 每周期常态路径。"
    )
    stress_success = min(stress["warm"]["success_ratio"], stress["cold"]["success_ratio"])
    stress_interpretation = (
        f"本轮主状态均为 `{stress['warm']['dominant_status']}`，全部样本收敛，但 p95 超过 20 Hz 周期；压力档只能按低频/异步规划或配合降阶、deadline 与 fallback 使用。"
        if stress_success >= 0.999
        else f"主状态为 warm=`{stress['warm']['dominant_status']}`、cold=`{stress['cold']['dominant_status']}`；低成功率要求保留 fallback、setpoint ramp 与可行性检查。"
    )
    resources = metrics["resource_metrics"]
    if resources.get("status") == "recorded":
        idle = resources["by_phase"].get("idle_baseline", {})
        steady_resource = resources["by_phase"].get("steady", {})
        stress_resource = resources["by_phase"].get("stress", {})
        resource_values = (
            f"短时 clean run 共 {resources['sample_count']} 个资源样本、{resources['duration_s']:.3f} s；"
            f"CPU mean/p95/max={resources['cpu_percent']['mean']:.1f}/{resources['cpu_percent']['p95']:.1f}/{resources['cpu_percent']['max']:.1f}%，"
            f"GPU mean/p95/max={resources['gpu_percent']['mean']:.1f}/{resources['gpu_percent']['p95']:.1f}/{resources['gpu_percent']['max']:.1f}%，"
            f"内存 mean/max={resources['memory_used_mb']['mean']:.1f}/{resources['memory_used_mb']['max']:.1f} MiB，"
            f"最高温度={resources['max_temp_c']['max']:.1f} °C，采样间隔 p95={resources['sample_interval_s']['p95']:.3f} s。"
            f"分阶段 CPU mean 为 idle/steady/stress="
            f"{idle.get('cpu_percent', {}).get('mean', float('nan')):.1f}/"
            f"{steady_resource.get('cpu_percent', {}).get('mean', float('nan')):.1f}/"
            f"{stress_resource.get('cpu_percent', {}).get('mean', float('nan')):.1f}%。"
        )
    else:
        resource_values = "本轮未观测 CPU/GPU/内存与温度。"
    repeatability = metrics.get("repeatability", {})
    if repeatability.get("run_count", 0) > 1:
        steady_repeat = repeatability["p95_ms_across_runs"]["steady"]
        stress_repeat = repeatability["p95_ms_across_runs"]["stress"]
        repeatability_text = (
            f"同一 commit/功耗/核数下共有 {repeatability['run_count']} 轮兼容 clean run："
            f"稳态 warm/cold p95 跨轮范围为 {steady_repeat['warm']['min']:.3f}--{steady_repeat['warm']['max']:.3f}/"
            f"{steady_repeat['cold']['min']:.3f}--{steady_repeat['cold']['max']:.3f} ms，"
            f"压力档为 {stress_repeat['warm']['min']:.3f}--{stress_repeat['warm']['max']:.3f}/"
            f"{stress_repeat['cold']['min']:.3f}--{stress_repeat['cold']['max']:.3f} ms。"
        )
    else:
        repeatability_text = "当前只有一轮兼容 clean run，跨轮重复性尚未观测。"
    evidence_label = "当前 clean benchmark " if metrics["evidence_mode"] == "current_benchmark" else "历史原始样本复算"
    text = f"""# Jetson Orin NX 在线算法实时性证据报告

## 结论

在 Jetson Orin NX 25 W / 8 核的{evidence_label}中，当前 `N=20, dt=0.2 s` MPC 的稳态 warm-start wall-time p95 为 {steady['warm']['wall']['p95_ms']:.3f} ms，cold-start p95 为 {steady['cold']['wall']['p95_ms']:.3f} ms，成功率分别为 {steady['warm']['success_ratio']:.1%}/{steady['cold']['success_ratio']:.1%}。相对 20 Hz ROS 控制周期，warm/cold p95 占用分别为 {100.0 * steady['warm']['wall']['p95_ms'] / budget_20hz:.1f}% 和 {100.0 * steady['cold']['wall']['p95_ms'] / budget_20hz:.1f}%。{steady_deadline}

约束压力档中，warm/cold wall-time p95 分别为 {stress['warm']['wall']['p95_ms']:.3f}/{stress['cold']['wall']['p95_ms']:.3f} ms，成功率为 {stress['warm']['success_ratio']:.1%}/{stress['cold']['success_ratio']:.1%}。{stress_interpretation}该档位反映更困难工况下的求解行为，不能简化为“Jetson 算力不足”。

{repeatability_text}

PC104 的 30 s host-relay 零推力记录包含 {pc['downlink_count']} 帧下行和 {pc['uplink_count']} 帧可解析上行，解析错误 {pc['parse_error_count']}，上行到达间隔 p50/p95/p99 为 {pc['reported_p50_ms']:.3f}/{pc['reported_p95_ms']:.3f}/{pc['reported_p99_ms']:.3f} ms。帧号审计中有 {pc['repeated_frame_counter_count']} 次零增量（重复帧号），大于 1 的前向跳号为 {pc['forward_gap_over_one_count']}、估算丢帧为 {pc['estimated_lost_frames']}；因此原摘要中的 `sequence_gap_count={pc['sequence_gap_count']}` 应解释为重复计数，而非 150 帧丢失。该量是 host-relay/Docker 路径后的到达间隔，不是 Jetson--PC104 单向物理时延、RTT 或端到端闭环时延。

## 资源与完整链路状态

{resource_note}

{resource_values}这些是 Jetson 整机遥测而非求解器进程独占归因，且该短时负载剖面不替代 30 min 全栈 thermal soak。

## 图表

- `figures/jetson_mpc_latency_and_success.png`：稳态/压力档 wall-time 分布与成功率。
- `figures/jetson_solver_budget_occupancy.png`：稳态 p95 相对 20 Hz、10 Hz 与 `dt=0.2 s` 周期预算的占用率。
- `figures/jetson_resource_profile.png`：本轮 clean benchmark 的 CPU/GPU、内存和温度时序。
- `figures/pc104_uplink_interarrival.png`：真实 PC104 上行到达间隔时序与经验分布，标题中显式保留非单程时延边界。

## 论文落点

主结果进入第 5 章 §5.6“面向实物的证据基础与迁移路径”，新增“Jetson Orin NX 在线求解实时性实测”子节；第 2 章只保留双脑职责与周期预算的设计依据；微基准、压力档和通信口径限制收束到 §5.7；尚未完成的 ADC/EKF/BT/ROS2 全栈 30 min soak 与 firmware echo 进入第 6 章 §6.3。
"""
    path.write_text(text, encoding="utf-8")


def process_snapshot() -> str:
    proc = subprocess.run(["ps", "-eo", "pid,comm,%cpu,%mem,etime,args", "--sort=-%cpu"], text=True, capture_output=True, check=False)
    return "\n".join(proc.stdout.splitlines()[:40]) + "\n"


def busy_processes(patterns: list[str]) -> list[str]:
    proc = subprocess.run(
        ["ps", "-eo", "pid,comm,%cpu,%mem,etime,args", "--sort=-%cpu"],
        text=True,
        capture_output=True,
        check=False,
    )
    snapshot = proc.stdout.splitlines()
    own_pid = os.getpid()
    matches = []
    for line in snapshot[1:]:
        if str(own_pid) in line:
            continue
        if any(pattern.lower() in line.lower() for pattern in patterns):
            matches.append(line.strip())
    return matches


def read_number(path: Path, scale: float = 1.0) -> float | None:
    try:
        return float(path.read_text(encoding="utf-8").strip()) / scale
    except (OSError, ValueError):
        return None


def resource_sampler(path: Path, phase_ref: dict, stop: threading.Event, interval_s: float) -> None:
    import psutil

    thermal = []
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        try:
            thermal.append((zone.joinpath("type").read_text().strip(), zone / "temp"))
        except OSError:
            pass
    gpu_path = Path("/sys/devices/platform/bus@0/17000000.gpu/load")
    fields = ["utc", "elapsed_s", "phase", "cpu_percent", "gpu_percent", "memory_used_mb", "load1", "max_temp_c"]
    start = time.monotonic()
    psutil.cpu_percent(interval=None)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        while not stop.wait(interval_s):
            temps = [value for _, temp_path in thermal if (value := read_number(temp_path, 1000.0)) is not None]
            gpu = read_number(gpu_path, 10.0)
            writer.writerow({
                "utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_s": f"{time.monotonic() - start:.3f}",
                "phase": phase_ref["value"],
                "cpu_percent": f"{psutil.cpu_percent(interval=None):.3f}",
                "gpu_percent": "not_observed" if gpu is None else f"{gpu:.3f}",
                "memory_used_mb": f"{psutil.virtual_memory().used / (1024 ** 2):.3f}",
                "load1": f"{os.getloadavg()[0]:.3f}",
                "max_temp_c": "not_observed" if not temps else f"{max(temps):.3f}",
            })
            handle.flush()


def run_command(command: list[str], cwd: Path, log_path: Path, phase_ref: dict, phase: str) -> None:
    phase_ref["value"] = phase
    with log_path.open("w", encoding="utf-8") as handle:
        proc = subprocess.run(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"phase {phase} failed with exit {proc.returncode}; see {log_path}")


def run_benchmark(project_root: Path, cfg: dict, allow_busy: bool) -> tuple[dict[str, Path], Path, str]:
    bench = cfg["benchmark"]
    busy = busy_processes(list(bench.get("busy_process_patterns", [])))
    nvp = subprocess.run(["nvpmodel", "-q"], text=True, capture_output=True, check=False)
    nvp_text = (nvp.stdout + nvp.stderr).strip()
    platform_mismatches = []
    if platform.machine() != str(bench["expected_arch"]):
        platform_mismatches.append(f"architecture={platform.machine()} expected={bench['expected_arch']}")
    if os.cpu_count() != int(bench["expected_cpu_count"]):
        platform_mismatches.append(f"cpu_count={os.cpu_count()} expected={bench['expected_cpu_count']}")
    if str(bench["expected_power_mode"]) not in nvp_text:
        platform_mismatches.append(f"nvpmodel={nvp_text!r} expected to contain {bench['expected_power_mode']!r}")
    contaminated = bool(busy or platform_mismatches)
    if contaminated and not allow_busy:
        details = "\n".join([*busy, *platform_mismatches])
        raise SystemExit(f"Refusing clean benchmark because preflight is not clean:\n{details}\nUse --allow-busy only for diagnostics.")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = EXPERIMENT_DIR / "data" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "process_snapshot.txt").write_text(process_snapshot(), encoding="utf-8")
    env = {
        "run_id": run_id,
        "utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=project_root, text=True, capture_output=True).stdout.strip(),
        "contaminated": contaminated,
        "busy_processes": busy,
    }
    env["nvpmodel"] = nvp_text
    env["platform_mismatches"] = platform_mismatches
    (run_dir / "environment.json").write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")

    phase_ref = {"value": "preflight"}
    stop = threading.Event()
    sampler = threading.Thread(
        target=resource_sampler,
        args=(run_dir / "resource_samples.csv", phase_ref, stop, float(bench["sample_interval_s"])),
        daemon=True,
    )
    sampler.start()
    tegra_log = run_dir / "tegrastats.log"
    tegra_proc = None
    if shutil.which("tegrastats"):
        tegra_proc = subprocess.Popen(["tegrastats", "--interval", "500", "--logfile", str(tegra_log)])

    try:
        phase_ref["value"] = "idle_baseline"
        time.sleep(float(bench.get("baseline_duration_s", 5.0)))
        steady_dir = run_dir / "steady"
        stress_dir = run_dir / "stress"
        run_command(
            [sys.executable, "tools/mpc_solve_microbench.py", "--iters", str(bench["steady_iters"]), "--params", str(project_root / bench["params"]), "--output-dir", str(steady_dir)],
            project_root,
            run_dir / "steady.log",
            phase_ref,
            "steady",
        )
        run_command(
            [sys.executable, "tools/mpc_solve_microbench.py", "--iters", str(bench["stress_iters"]), "--start-depth", str(bench["stress_start_depth_m"]), "--params", str(project_root / bench["params"]), "--output-dir", str(stress_dir)],
            project_root,
            run_dir / "stress.log",
            phase_ref,
            "stress",
        )
    finally:
        phase_ref["value"] = "finalize"
        stop.set()
        sampler.join(timeout=3.0)
        if tegra_proc is not None:
            tegra_proc.terminate()
            try:
                tegra_proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                tegra_proc.kill()

    resource_note = (
        f"本轮生成 `data/runs/{run_id}/resource_samples.csv` 与 `tegrastats.log`；"
        + ("检测到竞争负载，结果标记为 contaminated，不进入正式论文表。" if contaminated else "preflight 未检测到配置列出的竞争进程，可作为 clean solver benchmark 候选。")
    )
    historical = cfg["historical_evidence"]
    return {
        "steady": steady_dir,
        "stress": stress_dir,
        "pc104": project_root / historical["pc104_dir"],
    }, run_dir, resource_note


def analyze(project_root: Path, cfg: dict, sources: dict[str, Path], run_dir: Path | None, resource_note: str) -> None:
    fig_dir = EXPERIMENT_DIR / "figures"
    data_dir = EXPERIMENT_DIR / "data"
    fig_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    pc104, intervals, elapsed = collect_pc104_metrics(sources["pc104"])
    metrics = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_mode": "current_benchmark" if run_dir else "historical_reanalysis",
        "run_dir": None if run_dir is None else str(run_dir.relative_to(EXPERIMENT_DIR)),
        "target_platform": "Jetson Orin NX",
        "mpc": {
            "steady": collect_solver_metrics(sources["steady"]),
            "stress": collect_solver_metrics(sources["stress"]),
        },
        "pc104": pc104,
        "resource_metrics": collect_resource_metrics(run_dir),
        "repeatability": collect_repeatability_metrics(run_dir),
        "full_adc_ekf_bt_ros2_end_to_end_latency": "not_observed",
        "one_way_latency_claim": False,
        "round_trip_latency_claim": False,
        "end_to_end_latency_claim": False,
    }
    (EXPERIMENT_DIR / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary_csv(data_dir / "latency_summary.csv", metrics, cfg["timing_budgets_ms"])
    plot_solver_distributions(fig_dir, sources, cfg["timing_budgets_ms"])
    plot_budget_headroom(fig_dir, metrics, cfg["timing_budgets_ms"])
    plot_pc104_interarrival(fig_dir, intervals, elapsed, pc104)
    plot_resource_profile(fig_dir, run_dir)
    write_report(EXPERIMENT_DIR / "report.md", metrics, cfg["timing_budgets_ms"], resource_note)


def main() -> None:
    args = parse_args()
    config_path = args.config.resolve()
    cfg = load_yaml(config_path)
    project_root = resolve_project_root(config_path, cfg)
    if args.render_mpc_figure_from_run:
        run_dir = args.render_mpc_figure_from_run.resolve()
        sources = {
            "steady": run_dir / "steady",
            "stress": run_dir / "stress",
        }
        figure_dir = EXPERIMENT_DIR / "figures"
        figure_dir.mkdir(parents=True, exist_ok=True)
        plot_solver_distributions(
            figure_dir,
            sources,
            cfg["timing_budgets_ms"],
        )
        print(
            "[jetson_realtime] figure -> "
            f"{figure_dir / 'jetson_mpc_latency_and_success.pdf'}"
        )
        return
    if args.run_dir:
        run_dir = args.run_dir.resolve()
        if not run_dir.is_dir():
            raise SystemExit(f"run directory does not exist: {run_dir}")
        historical = cfg["historical_evidence"]
        sources = {
            "steady": run_dir / "steady",
            "stress": run_dir / "stress",
            "pc104": project_root / historical["pc104_dir"],
        }
        note = (
            f"本轮复算现有 `{run_dir.relative_to(EXPERIMENT_DIR)}`，未启动新负载；"
            "其 clean/contaminated 状态以该目录的 `environment.json` 为准。"
        )
        analyze(project_root, cfg, sources, run_dir, note)
    elif args.existing:
        sources = locate_sources(project_root, cfg)
        note = (
            "本轮使用 `--existing` 复算历史原始样本，没有产生当前 CPU/GPU/内存曲线；"
            "这些字段按 `not_observed` 保留。正式资源占用与 30 min thermal soak 须待系统安装和桌面竞争负载结束后运行默认 clean benchmark/全栈 profile。"
        )
        analyze(project_root, cfg, sources, None, note)
    else:
        sources, run_dir, note = run_benchmark(project_root, cfg, args.allow_busy)
        analyze(project_root, cfg, sources, run_dir, note)
    print(f"[jetson_realtime] metrics -> {EXPERIMENT_DIR / 'metrics.json'}")
    print(f"[jetson_realtime] report  -> {EXPERIMENT_DIR / 'report.md'}")
    print(f"[jetson_realtime] figures -> {EXPERIMENT_DIR / 'figures'}")


if __name__ == "__main__":
    main()
