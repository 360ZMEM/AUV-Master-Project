#!/usr/bin/env python3
"""R17 equivalent hysteresis/debounce benchmark for BT and FSM."""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "brain_linux" / "src"))

from auv_decision.auv_decision_core.bt_engine import DecisionTreeEngine  # noqa: E402
from auv_decision.auv_decision_core.fsm_baseline import (  # noqa: E402
    FiniteStateMachineEngine,
)
from auv_decision.auv_decision_core.models import SensorStatusData  # noqa: E402
from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402


TICK_HZ = 10
TICK_MS = 100.0
THRESHOLD = 0.7
CONFIGS = {
    "legacy_single_threshold": {"hysteresis": 0.0, "debounce_ticks": 1},
    "schmitt_debounce": {"hysteresis": 0.08, "debounce_ticks": 3},
}


def make_engine(architecture: str, config: dict[str, float | int]):
    kwargs = {
        "confidence_threshold": THRESHOLD,
        "confidence_hysteresis": float(config["hysteresis"]),
        "confidence_debounce_ticks": int(config["debounce_ticks"]),
    }
    if architecture == "BT":
        return DecisionTreeEngine(**kwargs)
    return FiniteStateMachineEngine(**kwargs)


def tick(engine, architecture: str, sensor: SensorStatusData) -> str:
    if architecture == "BT":
        engine.set_sensor_status(sensor)
        engine.tick()
        return str((engine.get_target_motion_state() or {}).get("mode", "UNKNOWN"))
    return str(engine.tick(sensor).mode)


def sensor(confidence: float, **kwargs) -> SensorStatusData:
    return SensorStatusData(
        confidence=confidence,
        depth_m=4.0,
        auto_state="ACTIVE",
        **kwargs,
    )


def warmup(engine, architecture: str) -> None:
    value = sensor(0.8)
    for _ in range(3):
        tick(engine, architecture, value)


def reaction_latency(
    architecture: str,
    config: dict[str, float | int],
    runs: int,
) -> list[int]:
    latencies: list[int] = []
    for _ in range(runs):
        engine = make_engine(architecture, config)
        warmup(engine, architecture)
        fault = sensor(0.8, leak_level=1)
        latency = -1
        for offset in range(5):
            if tick(engine, architecture, fault) == "EMERGENCY_SURFACE":
                latency = offset + 1
                break
        latencies.append(latency)
    return latencies


def chattering(
    architecture: str,
    config: dict[str, float | int],
    trials: int,
    duration_s: float,
    sigma: float,
) -> list[int]:
    switches: list[int] = []
    sample_count = int(duration_s * TICK_HZ)
    for trial in range(trials):
        rng = random.Random(1700 + trial)
        engine = make_engine(architecture, config)
        warmup(engine, architecture)
        previous = ""
        count = 0
        for _ in range(sample_count):
            confidence = min(1.0, max(0.0, THRESHOLD + rng.gauss(0.0, sigma)))
            mode = tick(engine, architecture, sensor(confidence))
            if previous and mode != previous:
                count += 1
            previous = mode
        switches.append(count)
    return switches


def combined_faults(
    architecture: str,
    config: dict[str, float | int],
    runs: int,
) -> dict[str, int]:
    missed = 0
    deadlocks = 0
    nuisance_switches = 0
    for run in range(runs):
        rng = random.Random(9100 + run)
        engine = make_engine(architecture, config)
        warmup(engine, architecture)
        fault_kind = ("leak", "battery", "penetration")[run % 3]
        fault_tick = rng.randint(30, 70)
        responded = False
        previous = ""
        no_goal_ticks = 0
        for index in range(120):
            kwargs = {}
            if index >= fault_tick:
                if fault_kind == "leak":
                    kwargs["leak_level"] = 1
                elif fault_kind == "battery":
                    kwargs["battery_low"] = True
                else:
                    kwargs["seabed_penetration_warning"] = True
            confidence = min(1.0, max(0.0, THRESHOLD + rng.gauss(0.0, 0.07)))
            mode = tick(engine, architecture, sensor(confidence, **kwargs))
            if mode in ("", "UNKNOWN"):
                no_goal_ticks += 1
            else:
                no_goal_ticks = 0
            if no_goal_ticks >= 5:
                deadlocks += 1
                break
            if index >= fault_tick and mode == "EMERGENCY_SURFACE":
                responded = True
            if index < fault_tick and previous and mode != previous:
                nuisance_switches += 1
            previous = mode
        if not responded:
            missed += 1
    return {
        "missed": missed,
        "deadlocks": deadlocks,
        "survived": runs - missed - deadlocks,
        "nuisance_switches": nuisance_switches,
    }


def write_report(output_dir: Path, rows: list[dict[str, object]]) -> None:
    lines = [
        "# R17 BT/FSM Hysteresis and Composite-Fault Benchmark",
        "",
        "Both architectures use the same stateful confidence gate. Emergency "
        "conditions remain immediate and are not debounced.",
        "",
        "| architecture | decision rule | latency ms | chatter switches/30s | missed faults | survival |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['architecture']} | {row['decision_config']} | "
            f"{float(row['reaction_latency_mean_ms']):.1f} | "
            f"{float(row['chatter_switches_mean']):.2f} | "
            f"{int(row['combined_fault_missed_count'])} | "
            f"{float(row['combined_fault_survival_rate']):.3f} |"
        )
    lines.extend(
        [
            "",
            "The runtime safety metrics are expected to remain equal. The "
            "architectural distinction is the placement and maintenance cost "
            "of cross-cutting fault logic, not a faster tick response.",
            "",
            "- BT emergency condition declaration sites: 1",
            "- FSM state handlers containing emergency checks: 5",
            "",
        ]
    )
    (output_dir / "report.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_figure(output_dir: Path, rows: list[dict[str, object]]) -> str:
    labels = [f"{row['architecture']}\n{row['decision_config']}" for row in rows]
    values = [float(row["chatter_switches_mean"]) for row in rows]
    fig, ax = plt.subplots(figsize=(7.5, 4.4), dpi=180)
    bars = ax.bar(labels, values, color=["#4C78A8", "#4C78A8", "#F58518", "#F58518"])
    ax.set_ylabel("Mean mode switches per 30 s")
    ax.set_title("Equivalent hysteresis/debounce suppresses threshold chatter")
    ax.grid(axis="y", alpha=0.25)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{value:.1f}",
            ha="center",
            va="bottom",
        )
    fig.tight_layout()
    target = output_dir / "figures" / "decision_chattering_comparison.png"
    fig.savefig(target)
    plt.close(fig)
    return str(target.relative_to(output_dir))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--latency-runs", type=int, default=1000)
    parser.add_argument("--chatter-trials", type=int, default=100)
    parser.add_argument("--chatter-duration-s", type=float, default=30.0)
    parser.add_argument("--combined-runs", type=int, default=500)
    parser.add_argument("--sigma", type=float, default=0.05)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%dT%H%M%S")
    output_dir = args.output_dir or (
        REPO_ROOT / "results" / "decision" / "r17_hysteresis" / stamp
    )
    initialize_bundle(
        output_dir,
        experiment_id=f"r17_decision_hysteresis_{stamp}",
        runner=str(Path(__file__).resolve().relative_to(REPO_ROOT)),
        argv=sys.argv,
        data_layer="decision_core_monte_carlo",
        matrix={
            "architectures": ["BT", "FSM"],
            "configs": CONFIGS,
            "latency_runs": args.latency_runs,
            "chatter_trials": args.chatter_trials,
            "combined_runs": args.combined_runs,
        },
        duration_s=args.chatter_duration_s,
        config_paths=[
            Path(__file__),
            REPO_ROOT
            / "brain_linux/src/auv_decision/auv_decision_core/decision_filters.py",
            REPO_ROOT / "brain_linux/src/auv_decision/auv_decision_core/bt_engine.py",
            REPO_ROOT
            / "brain_linux/src/auv_decision/auv_decision_core/fsm_baseline.py",
        ],
        extra_manifest={"hardware_claim": False, "tick_hz": TICK_HZ},
    )

    rows: list[dict[str, object]] = []
    for architecture in ("BT", "FSM"):
        for config_name, config in CONFIGS.items():
            print(f"[R17] {architecture} / {config_name}", flush=True)
            latencies = reaction_latency(
                architecture,
                config,
                args.latency_runs,
            )
            chatter = chattering(
                architecture,
                config,
                args.chatter_trials,
                args.chatter_duration_s,
                args.sigma,
            )
            faults = combined_faults(
                architecture,
                config,
                args.combined_runs,
            )
            valid_latencies = [value for value in latencies if value > 0]
            row = {
                "run_id": f"{architecture}__{config_name}",
                "scenario": "decision_stress",
                "seed": "deterministic_sequence_set",
                "mpc_mode": "not_applicable",
                "status": "ok",
                "architecture": architecture,
                "decision_config": config_name,
                "hysteresis": config["hysteresis"],
                "debounce_ticks": config["debounce_ticks"],
                "reaction_latency_runs": args.latency_runs,
                "reaction_latency_mean_ms": float(np.mean(valid_latencies)) * TICK_MS,
                "reaction_missed_count": len(latencies) - len(valid_latencies),
                "chatter_trial_count": args.chatter_trials,
                "chatter_switches_mean": float(np.mean(chatter)),
                "chatter_switches_std": float(np.std(chatter)),
                "chattering_hz_mean": float(np.mean(chatter))
                / args.chatter_duration_s,
                "combined_fault_runs": args.combined_runs,
                "combined_fault_missed_count": faults["missed"],
                "combined_fault_deadlock_count": faults["deadlocks"],
                "combined_fault_survival_rate": faults["survived"]
                / args.combined_runs,
                "pre_fault_nuisance_switches": faults["nuisance_switches"],
                "effective_sample_count": args.latency_runs
                + args.chatter_trials
                + args.combined_runs,
                "failure_event_count": faults["missed"] + faults["deadlocks"],
                "capability_gate_status": "not_applicable_decision_core",
                "solver_wall_time_current_ms": "not_applicable",
                "fallback_type": "not_applicable",
            }
            rows.append(row)

    status = finalize_bundle(output_dir, rows)
    figure = write_figure(output_dir, rows)
    write_report(output_dir, rows)
    (output_dir / "summary.json").write_text(
        json.dumps(
            {"status": status, "rows": rows, "figures": [figure]},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[R17] output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
