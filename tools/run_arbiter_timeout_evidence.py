#!/usr/bin/env python3
"""Generate deterministic timeout evidence from the production command arbiter."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_SRC = REPO_ROOT / "brain_linux" / "src" / "auv_bridge"
for path in (REPO_ROOT, BRIDGE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from auv_bridge.arbiter import CommandArbiter  # noqa: E402
from common.enums import ArbiterMode, ArbiterSource, ControlModeByte, WorkInstruction  # noqa: E402
from common.protocol import (  # noqa: E402
    KEY_BOTTOM,
    KEY_CONTROL_MODE_BYTE,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_SIDE_MOTOR_RPM,
    KEY_THRUST,
    KEY_TOP,
    KEY_WORK_INSTRUCTION,
)
from tools import thesis_plot_style as tps  # noqa: E402
from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402

ACTUATORS = (KEY_RIGHT, KEY_TOP, KEY_LEFT, KEY_BOTTOM, KEY_THRUST, KEY_SIDE_MOTOR_RPM)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--step-ms", type=float, default=10.0)
    parser.add_argument("--mpc-timeout-s", type=float, default=0.5)
    parser.add_argument("--pc-soft-warning-s", type=float, default=1.0)
    parser.add_argument("--pc-timeout-s", type=float, default=1.5)
    return parser.parse_args()


def command(mode: int, *, work: int = 0) -> dict[str, Any]:
    return {
        KEY_CONTROL_MODE_BYTE: mode,
        KEY_WORK_INSTRUCTION: work,
        KEY_RIGHT: 0.0,
        KEY_TOP: 0.0,
        KEY_LEFT: 0.0,
        KEY_BOTTOM: 0.0,
        KEY_THRUST: 0.0,
        KEY_SIDE_MOTOR_RPM: 0,
    }


def mpc_command() -> dict[str, Any]:
    return {
        "right_fin_deg": 4.0,
        "top_fin_deg": -3.0,
        "left_fin_deg": -4.0,
        "bottom_fin_deg": 3.0,
        "thrust_percent": 25.0,
        "valid": True,
        "healthy": True,
    }


def enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def run(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    step_s = args.step_ms / 1000.0
    arbiter = CommandArbiter(
        mpc_timeout_s=args.mpc_timeout_s,
        pc_soft_warning_s=args.pc_soft_warning_s,
        pc_timeout_s=args.pc_timeout_s,
    )
    start = 100.0
    mpc_time = start + step_s
    recovery_elapsed = args.pc_timeout_s + 0.5
    rows: list[dict[str, Any]] = []
    remote_forced = False
    arbiter.update_pc_raw_command(command(int(ControlModeByte.JETSON_PROTOCOL)), now=start)
    arbiter.update_mpc_command(mpc_command(), now=mpc_time)

    sample_count = int(round((recovery_elapsed + 0.2 - step_s) / step_s)) + 1
    for index in range(sample_count):
        now = mpc_time + index * step_s
        event = "sample"
        if now - start >= recovery_elapsed and remote_forced:
            arbiter.update_pc_raw_command(command(int(ControlModeByte.JETSON_PROTOCOL)), now=now)
            decision = arbiter.update_mpc_command(mpc_command(), now=now)
            remote_forced = False
            event = "explicit_pc_reauthorization"
        else:
            link = arbiter.check_pc_link_health(now=now)
            if link == "LOST" and not remote_forced:
                decision = arbiter.force_remote(
                    command(int(ControlModeByte.REMOTE_CONTROL), work=int(WorkInstruction.TASK_CANCEL)),
                    now=now,
                    refresh_pc_timestamp=False,
                )
                remote_forced = True
                event = "bridge_policy_force_remote"
            else:
                decision = arbiter.decide(now=now)
        payload = decision.command_payload
        rows.append({
            "elapsed_s": now - start,
            "event": event,
            "active_arbiter": enum_value(decision.active_arbiter),
            "arbiter_source": enum_value(decision.arbiter_source),
            "pc_link_status": arbiter.check_pc_link_health(now=now),
            "mpc_command_valid": int(decision.mpc_command_valid),
            "control_mode_byte": int(payload[KEY_CONTROL_MODE_BYTE]),
            "work_instruction": int(payload[KEY_WORK_INSTRUCTION]),
            "right_fin_deg": float(payload[KEY_RIGHT]),
            "top_fin_deg": float(payload[KEY_TOP]),
            "left_fin_deg": float(payload[KEY_LEFT]),
            "bottom_fin_deg": float(payload[KEY_BOTTOM]),
            "thrust_percent": float(payload[KEY_THRUST]),
            "side_motor_rpm": int(payload[KEY_SIDE_MOTOR_RPM]),
            "actuator_abs_max": max(abs(float(payload.get(key, 0.0))) for key in ACTUATORS),
        })

    def first(predicate) -> dict[str, Any]:
        return next(row for row in rows if predicate(row))

    mpc_fallback = first(lambda row: row["arbiter_source"] == ArbiterSource.SAFETY_FALLBACK.value)
    pc_weak = first(lambda row: row["pc_link_status"] == "WEAK")
    pc_lost = first(lambda row: row["pc_link_status"] == "LOST")
    remote = first(lambda row: row["event"] == "bridge_policy_force_remote")
    recovered = first(lambda row: row["event"] == "explicit_pc_reauthorization")
    safety_rows = [row for row in rows if row["arbiter_source"] == ArbiterSource.SAFETY_FALLBACK.value]
    lost_rows = [row for row in rows if row["pc_link_status"] == "LOST" and row["active_arbiter"] == ArbiterMode.REMOTE.value]
    fallback_zero = bool(safety_rows) and all(row["actuator_abs_max"] == 0.0 for row in safety_rows)
    remote_zero = bool(lost_rows) and all(row["actuator_abs_max"] == 0.0 for row in lost_rows)
    mpc_observed_ms = (mpc_fallback["elapsed_s"] - step_s) * 1000.0
    weak_ms = pc_weak["elapsed_s"] * 1000.0
    lost_ms = pc_lost["elapsed_s"] * 1000.0
    remote_ms = remote["elapsed_s"] * 1000.0
    recovery_ms = recovered["elapsed_s"] * 1000.0
    passed = (
        mpc_observed_ms >= args.mpc_timeout_s * 1000.0
        and weak_ms >= args.pc_soft_warning_s * 1000.0
        and lost_ms >= args.pc_timeout_s * 1000.0
        and abs(remote_ms - lost_ms) <= args.step_ms + 1.0e-6
        and fallback_zero and remote_zero and len(lost_rows) >= 2
    )
    return rows, {
        "scenario": "production_command_arbiter_timeout_timeline",
        "status": "ok" if passed else "failed_acceptance",
        "error": "" if passed else "one or more timeout acceptance criteria failed",
        "step_ms": args.step_ms,
        "mpc_timeout_config_s": args.mpc_timeout_s,
        "mpc_fallback_observed_ms": mpc_observed_ms,
        "pc_soft_warning_config_s": args.pc_soft_warning_s,
        "pc_weak_observed_ms": weak_ms,
        "pc_timeout_config_s": args.pc_timeout_s,
        "pc_lost_observed_ms": lost_ms,
        "remote_fallback_observed_ms": remote_ms,
        "explicit_reauthorization_observed_ms": recovery_ms,
        "mpc_fallback_zero": fallback_zero,
        "pc_lost_remote_zero": remote_zero,
        "pc_lost_persists_after_local_fallback": len(lost_rows) >= 2,
        "effective_sample_count": len(rows),
        "failure_event_count": 0 if passed else 1,
        "capability_gate_status": "not_applicable",
        "solver_wall_time_current_ms": "not_applicable_timeout_age_injection",
        "fallback_type": "safety_fallback_then_remote_zero",
    }


def write_timeline(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_timeline(path: Path, rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    t = np.asarray([row["elapsed_s"] for row in rows])
    mode = np.asarray([row["active_arbiter"] == ArbiterMode.AUTONOMOUS.value for row in rows])
    source_map = {"PC_RAW": 0, "NONE": 0, "SAFETY_FALLBACK": 1, "JETSON_MPC": 2}
    source = np.asarray([source_map[row["arbiter_source"]] for row in rows])
    link = np.asarray([{"LOST": 0, "WEAK": 1, "OK": 2}[row["pc_link_status"]] for row in rows])
    actuator = np.asarray([row["actuator_abs_max"] for row in rows])
    fig, axes = plt.subplots(4, 1, figsize=(10.8, 7.8), sharex=True)
    axes[0].step(t, mode, where="post", color=tps.ACCENT_COLORS[0])
    axes[0].set_yticks((0, 1), ("Remote", "Autonomous"))
    axes[0].set_ylabel("仲裁模式")
    axes[1].step(t, source, where="post", color=tps.ACCENT_COLORS[1])
    axes[1].set_yticks((0, 1, 2), ("PC_RAW", "SAFETY", "MPC"))
    axes[1].set_ylabel("命令源")
    axes[2].step(t, link, where="post", color=tps.ACCENT_COLORS[2])
    axes[2].set_yticks((0, 1, 2), ("LOST", "WEAK", "OK"))
    axes[2].set_ylabel("PC 链路")
    axes[3].plot(t, actuator, color=tps.ACCENT_COLORS[3])
    axes[3].set_ylabel("最大执行器值")
    axes[3].set_xlabel("距 PC 心跳时间 / s")
    markers = (
        (args.mpc_timeout_s, "MPC 超时"),
        (args.pc_soft_warning_s, "PC 弱链路"),
        (args.pc_timeout_s, "PC 丢失"),
        (args.pc_timeout_s + 0.5, "显式重授权"),
    )
    for axis in axes:
        for value, label in markers:
            axis.axvline(value, color="black", linestyle="--", linewidth=0.8,
                         alpha=0.6, label=label if axis is axes[0] else None)
    axes[0].legend(loc="upper center", ncols=4)
    fig.suptitle("生产 CommandArbiter 分层超时与零输出时间线")
    fig.tight_layout()
    tps.save_figure(fig, path / "arbiter_timeout_timeline")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    if not (0 < args.mpc_timeout_s < args.pc_soft_warning_s < args.pc_timeout_s):
        raise SystemExit("require 0 < MPC timeout < PC warning < PC timeout")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    output = args.output_dir or REPO_ROOT / "results/control" / f"arbiter_timeout_evidence_{stamp}"
    initialize_bundle(
        output,
        experiment_id=f"arbiter_timeout_evidence_{stamp}",
        runner="tools/run_arbiter_timeout_evidence.py",
        argv=sys.argv,
        data_layer="production_arbiter_deterministic_time_replay",
        matrix={
            "step_ms": args.step_ms,
            "mpc_timeout_s": args.mpc_timeout_s,
            "pc_soft_warning_s": args.pc_soft_warning_s,
            "pc_timeout_s": args.pc_timeout_s,
        },
        duration_s=args.pc_timeout_s + 0.7,
        config_paths=[
            Path(__file__),
            BRIDGE_SRC / "auv_bridge/arbiter.py",
            BRIDGE_SRC / "auv_bridge/bridge_node.py",
        ],
        extra_manifest={
            "hardware_claim": False,
            "ros_executor_timing_claim": False,
            "bridge_policy_replayed": "LOST -> force_remote(degraded_zero)",
            "explicit_reauthorization_required": True,
        },
    )
    rows, summary = run(args)
    write_timeline(output / "arbiter_timeline.csv", rows)
    plot_timeline(output / "figures", rows, args)
    finalize_bundle(output, [summary])
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    report = (
        "# CommandArbiter timeout evidence\n\n"
        f"- Status: {summary['status']}\n"
        f"- MPC fallback: {summary['mpc_fallback_observed_ms']:.1f} ms; zero={summary['mpc_fallback_zero']}\n"
        f"- PC weak/lost: {summary['pc_weak_observed_ms']:.1f}/{summary['pc_lost_observed_ms']:.1f} ms\n"
        f"- Remote fallback: {summary['remote_fallback_observed_ms']:.1f} ms; zero={summary['pc_lost_remote_zero']}\n"
        f"- LOST persists after local fallback: {summary['pc_lost_persists_after_local_fallback']}\n\n"
        "Deterministic pure-core replay of production CommandArbiter plus the bridge LOST policy; "
        "not a ROS executor or physical-hardware timing claim.\n"
    )
    (output / "report.md").write_text(report, encoding="utf-8")
    print(f"[arbiter-timeout] status={summary['status']} -> {output}")
    return 0 if summary["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
