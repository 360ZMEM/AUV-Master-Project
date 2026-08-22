#!/usr/bin/env python3
"""Behavior-tree fault-injection experiment (27 号文 §5, 组 D).

The existing BT/FSM benchmarks (``tests/benchmark_bt_vs_fsm.py``,
``tools/decision_hysteresis_benchmark.py``) already inject leak / battery /
penetration and study chatter, but they (a) never exercise *heartbeat timeout*
or *solver timeout* as explicit fault types and (b) only emit PNGs — there is no
per-run BT state-timeline CSV for figures / provenance. This runner fills both
gaps by driving the **unmodified** ``DecisionTreeEngine`` through scripted
inspection missions and recording every tick.

How the two new fault types flow through the *real* engine (no engine change):
  * ``heartbeat_timeout``  ->  ``auto_state='LOCKED'`` so the real
    ``Wait_For_Arbiter_Authorization`` node latches the vehicle into the IDLE
    standby hold (mapped role ``SAFE_HOVER``). This is the engine's genuine
    authorization-loss path, used here as the heartbeat-loss proxy.
  * ``solver_timeout``     ->  ``anomaly_detected=True`` so the real
    ``AnomalySpeedLimiter`` decorator throttles the tracking command (mapped role
    ``DEGRADED_MODE``). It is an *injection proxy*: it flips an anomaly flag, it
    does NOT reproduce real MPC solver wall-time load (see 27 号文 §5 边界).

Perception faults (``dvl_dropout`` / ``mag_dropout`` / ``sonar_dropout`` /
``target_loss``) collapse the fused perception confidence, so the routing
selector falls back to the zigzag re-search branch (mapped ``RELOCALIZATION``).
Emergency faults (``leak`` / ``battery`` / ``penetration``) drive the
top-priority emergency subtree (mapped ``RETURN_OR_ABORT``).

The engine only exposes a handful of raw motion modes; the user-facing behavior
roles (SEARCH_ZIGZAG / CABLE_CAPTURE / PARALLEL_TRACKING / RELOCALIZATION /
SAFE_HOVER / RETURN_OR_ABORT / DEGRADED_MODE) are **derived semantic
annotations** over those raw modes — the raw engine mode is always kept in the
``state`` column so the mapping stays auditable.

Usage:
    python3 tools/run_bt_fault_injection.py --seeds 0,1,2 \
        --output-dir results/decision/bt_fault_injection/<ts>
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "brain_linux" / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "brain_linux" / "src"))

from auv_decision.auv_decision_core.bt_engine import DecisionTreeEngine  # noqa: E402
from auv_decision.auv_decision_core.models import SensorStatusData  # noqa: E402
from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402

TICK_HZ = 10
TICK_S = 1.0 / TICK_HZ
CONFIDENCE_THRESHOLD = 0.7
# Deployed anti-chatter gate (R17 schmitt_debounce): the engine's real
# hysteresis/debounce config, enabled here so threshold noise near the gate does
# not masquerade as spurious relocalization. Emergency conditions are never
# debounced (they stay immediate inside the engine).
CONFIDENCE_HYSTERESIS = 0.08
CONFIDENCE_DEBOUNCE_TICKS = 3
ACQUIRE_TIME_S = 6.0  # initial target-acquisition search window
CAPTURE_WINDOW_S = 2.0  # first seconds of a fresh track segment = CABLE_CAPTURE
DETECTION_GRACE_S = 6.0  # allowance after fault onset to accept a safe response
HIGH_CONF = 0.85
LOW_CONF = 0.15
CONF_SIGMA = 0.02
# Perception confidence is a lagged state, not an instant flag: a sensor dropout
# takes a short but finite time to collapse the fused confidence below the gate
# (detection latency), and reacquisition after the dropout clears takes longer
# (search + relock). Emergency / heartbeat / solver flags stay instantaneous.
TAU_CONF_DECAY_S = 2.5   # first-order time constant while confidence falls
TAU_CONF_RECOVER_S = 2.0  # first-order time constant while confidence rises

# Raw engine mode -> the fault that produces it flows through the *real* engine.
EXPECTED_RESPONSE_ROLE: dict[str, str] = {
    "leak": "RETURN_OR_ABORT",
    "battery": "RETURN_OR_ABORT",
    "penetration": "RETURN_OR_ABORT",
    "dvl_dropout": "RELOCALIZATION",
    "mag_dropout": "RELOCALIZATION",
    "sonar_dropout": "RELOCALIZATION",
    "target_loss": "RELOCALIZATION",
    "heartbeat_timeout": "SAFE_HOVER",
    "solver_timeout": "DEGRADED_MODE",
}
EMERGENCY_FAULTS = {"leak", "battery", "penetration"}
PERCEPTION_FAULTS = {"dvl_dropout", "mag_dropout", "sonar_dropout", "target_loss"}
TRACKING_ROLES = {"PARALLEL_TRACKING", "CABLE_CAPTURE"}
SAFE_ROLES = {"RETURN_OR_ABORT", "SAFE_HOVER", "DEGRADED_MODE", "RELOCALIZATION"}
ROLE_Y = {
    "RETURN_OR_ABORT": 0,
    "SAFE_HOVER": 1,
    "DEGRADED_MODE": 2,
    "RELOCALIZATION": 3,
    "SEARCH_ZIGZAG": 4,
    "CABLE_CAPTURE": 5,
    "PARALLEL_TRACKING": 6,
}


@dataclass(frozen=True)
class FaultWindow:
    fault_type: str
    start_s: float
    end_s: float


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    duration_s: float
    windows: tuple[FaultWindow, ...] = ()
    description: str = ""


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("baseline_patrol", "基准巡检", 70.0, (),
             "搜索→捕获→沿线跟踪，无故障（假阳性核查基线）"),
    Scenario("leak_abort", "漏水安全中止", 90.0,
             (FaultWindow("leak", 45.0, 90.0),),
             "漏水持续注入，验证紧急上浮中止"),
    Scenario("battery_abort", "低电安全中止", 90.0,
             (FaultWindow("battery", 50.0, 90.0),),
             "低电持续注入，验证紧急上浮中止"),
    Scenario("penetration_recover", "近底穿越-恢复", 90.0,
             (FaultWindow("penetration", 45.0, 53.0),),
             "瞬时穿底告警→紧急上浮→回到跟踪"),
    Scenario("dvl_dropout", "DVL 丢失-重定位", 90.0,
             (FaultWindow("dvl_dropout", 35.0, 55.0),),
             "DVL 丢失导致感知置信塌陷→之字重定位→重捕获"),
    Scenario("perception_loss", "声磁感知丢失", 90.0,
             (FaultWindow("sonar_dropout", 30.0, 48.0),
              FaultWindow("mag_dropout", 30.0, 48.0)),
             "声呐+磁同时丢失→重定位→重捕获"),
    Scenario("heartbeat_timeout", "心跳超时-安全悬停", 90.0,
             (FaultWindow("heartbeat_timeout", 40.0, 52.0),),
             "心跳/授权丢失→安全悬停待命→授权恢复"),
    Scenario("solver_timeout", "求解超时-降级", 90.0,
             (FaultWindow("solver_timeout", 38.0, 58.0),),
             "求解超时注入代理→降级限速跟踪→恢复"),
    Scenario("multi_fault", "复合故障序列", 110.0,
             (FaultWindow("dvl_dropout", 22.0, 34.0),
              FaultWindow("solver_timeout", 46.0, 62.0),
              FaultWindow("leak", 80.0, 110.0)),
             "重定位→降级→漏水安全中止的级联"),
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--scenarios", default=",".join(s.key for s in SCENARIOS))
    parser.add_argument("--no-figure", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def _active_faults(scenario: Scenario, t_s: float) -> list[str]:
    return [w.fault_type for w in scenario.windows if w.start_s <= t_s < w.end_s]


def _sensor_for_tick(t_s: float, active: Sequence[str], rng: np.random.Generator,
                     conf_state: float) -> tuple[SensorStatusData, float]:
    """Build the per-tick sensor snapshot from the nominal mission + faults.

    ``conf_state`` is the previous filtered perception confidence; it is driven
    toward the current target confidence by a first-order lag so sensor-dropout
    faults produce a realistic (non-instant) detection/reacquisition latency.
    Returns the sensor snapshot and the updated confidence state.
    """
    depth = min(4.0, 0.5 + 0.5 * t_s)  # dive ramp then hold ~4 m
    # Nominal perception target: low during the initial acquisition search.
    target_conf = LOW_CONF if t_s < ACQUIRE_TIME_S else HIGH_CONF
    perception_fault = any(ft in PERCEPTION_FAULTS for ft in active)
    if perception_fault:
        target_conf = LOW_CONF

    tau = TAU_CONF_DECAY_S if target_conf < conf_state else TAU_CONF_RECOVER_S
    alpha = 1.0 - math.exp(-TICK_S / tau)
    conf_state = conf_state + alpha * (target_conf - conf_state)
    conf = conf_state + float(rng.normal(0.0, CONF_SIGMA))

    kwargs: dict[str, object] = {
        "depth_m": depth,
        "seabed_depth_m": 15.0,
        "seabed_clearance_m": max(0.0, 15.0 - depth),
        "heading_rad": 0.0,
        "auto_state": "ACTIVE",
        "leak_level": 0,
        "battery_low": False,
        "seabed_penetration_warning": False,
        "anomaly_detected": False,
    }
    for ft in active:
        if ft == "leak":
            kwargs["leak_level"] = 1
        elif ft == "battery":
            kwargs["battery_low"] = True
        elif ft == "penetration":
            kwargs["seabed_penetration_warning"] = True
            kwargs["seabed_clearance_m"] = 0.0
        elif ft == "heartbeat_timeout":
            kwargs["auto_state"] = "LOCKED"
        elif ft == "solver_timeout":
            kwargs["anomaly_detected"] = True
    kwargs["confidence"] = float(min(1.0, max(0.0, conf)))
    return SensorStatusData(**kwargs), conf_state


def _derive_role(raw: str, target: dict, ticks_in_track: int, ever_tracked: bool) -> str:
    """Map the raw engine motion mode to a user-facing behavior role.

    The raw mode stays authoritative (kept in the CSV ``state`` column); this is
    a documented semantic annotation, never an engine change.
    """
    if raw == "EMERGENCY_SURFACE":
        return "RETURN_OR_ABORT"
    if raw in ("STABILIZE_HOLD", "IDLE"):
        return "SAFE_HOVER"
    if raw == "ZIGZAG_SEARCH":
        return "RELOCALIZATION" if ever_tracked else "SEARCH_ZIGZAG"
    if raw == "PARALLEL_TRACKING":
        note = str(target.get("note", ""))
        if "异常装饰器" in note:  # AnomalySpeedLimiter throttled the command
            return "DEGRADED_MODE"
        if ticks_in_track <= max(1, int(round(CAPTURE_WINDOW_S * TICK_HZ))):
            return "CABLE_CAPTURE"
        return "PARALLEL_TRACKING"
    return raw or "UNKNOWN"


def run_scenario(scenario: Scenario, seed: int) -> dict[str, object]:
    scenario_seed = zlib.crc32(scenario.key.encode("utf-8")) % 104729
    rng = np.random.default_rng(seed * 7919 + scenario_seed)
    engine = DecisionTreeEngine(
        confidence_threshold=CONFIDENCE_THRESHOLD,
        confidence_hysteresis=CONFIDENCE_HYSTERESIS,
        confidence_debounce_ticks=CONFIDENCE_DEBOUNCE_TICKS,
    )

    n_ticks = int(round(scenario.duration_s * TICK_HZ))
    rows: list[dict[str, object]] = []
    prev_role = ""
    ticks_in_track = 0
    ever_tracked = False
    conf_state = LOW_CONF  # cold-start perception confidence

    for i in range(n_ticks):
        t_s = i * TICK_S
        active = _active_faults(scenario, t_s)
        sensor, conf_state = _sensor_for_tick(t_s, active, rng, conf_state)
        engine.set_sensor_status(sensor)
        engine.tick()
        target = engine.get_target_motion_state() or {}
        raw = str(target.get("mode", "UNKNOWN"))

        if raw == "PARALLEL_TRACKING":
            ticks_in_track += 1
        else:
            ticks_in_track = 0
        role = _derive_role(raw, target, ticks_in_track, ever_tracked)
        if role in TRACKING_ROLES:
            ever_tracked = True

        changed = role != prev_role
        trigger = ""
        if changed:
            if active and prev_role not in SAFE_ROLES:
                trigger = "fault_onset:" + "|".join(active)
            elif role in TRACKING_ROLES and prev_role in ("RELOCALIZATION", "SEARCH_ZIGZAG", "SAFE_HOVER"):
                trigger = "target_reacquired" if ever_tracked and prev_role != "SEARCH_ZIGZAG" else "target_acquired"
            elif role in ("RELOCALIZATION",) and prev_role in TRACKING_ROLES:
                trigger = "target_lost"
            elif not active and prev_role in SAFE_ROLES:
                trigger = "fault_cleared"
            else:
                trigger = "transition"

        rows.append({
            "scenario": scenario.key,
            "seed": seed,
            "time": round(t_s, 3),
            "state": raw,
            "role": role,
            "previous_state": rows[-1]["state"] if rows else "",
            "previous_role": prev_role,
            "trigger": trigger,
            "confidence": round(float(sensor.confidence), 4),
            "fault_type": "|".join(active) if active else "none",
            "recovery_mode": role if role in SAFE_ROLES else "",
        })
        prev_role = role

    metrics = _score_run(scenario, seed, rows)
    metrics["_timeline"] = rows
    return metrics


def _score_run(scenario: Scenario, seed: int, rows: list[dict[str, object]]) -> dict[str, object]:
    times = np.array([float(r["time"]) for r in rows])
    roles = [str(r["role"]) for r in rows]
    active_sets = [set(str(r["fault_type"]).split("|")) if r["fault_type"] != "none" else set()
                   for r in rows]

    fault_records: list[dict[str, object]] = []
    for w in scenario.windows:
        expected = EXPECTED_RESPONSE_ROLE[w.fault_type]
        persistent = w.end_s >= scenario.duration_s - 1.0
        detect_t = math.nan
        for idx in range(len(rows)):
            if times[idx] < w.start_s or times[idx] > w.end_s + DETECTION_GRACE_S:
                continue
            if roles[idx] == expected and w.fault_type in active_sets[idx]:
                detect_t = float(times[idx] - w.start_s)
                break
        missed = math.isnan(detect_t)

        recover_t = math.nan
        reacquired = False
        if persistent and w.fault_type in EMERGENCY_FAULTS:
            # Safe abort: success == the emergency response fired; no re-track required.
            reacquired = not missed
        else:
            for idx in range(len(rows)):
                if times[idx] < w.end_s:
                    continue
                if roles[idx] in TRACKING_ROLES:
                    recover_t = float(times[idx] - w.end_s)
                    reacquired = True
                    break
        fault_records.append({
            "scenario": scenario.key, "seed": seed, "fault_type": w.fault_type,
            "expected_role": expected, "persistent_abort": persistent,
            "detection_time_s": detect_t, "recovery_time_s": recover_t,
            "reacquired": reacquired, "missed": missed,
        })

    # False triggers: entering a safe/recovery role while no fault is active.
    false_triggers = 0
    safe_triggers = 0
    prev = ""
    for idx, role in enumerate(roles):
        if role != prev and role in SAFE_ROLES:
            safe_triggers += 1
            if not active_sets[idx]:
                false_triggers += 1
        prev = role

    tracking_fraction = float(np.mean([1.0 if r in TRACKING_ROLES else 0.0 for r in roles]))
    detected = [fr for fr in fault_records if not fr["missed"]]
    det_times = [float(fr["detection_time_s"]) for fr in detected]
    rec_times = [float(fr["recovery_time_s"]) for fr in fault_records
                 if isinstance(fr["recovery_time_s"], float) and math.isfinite(fr["recovery_time_s"])]
    reacq = [fr for fr in fault_records if fr["reacquired"]]
    missed_count = sum(1 for fr in fault_records if fr["missed"])
    no_reacq = sum(1 for fr in fault_records if not fr["reacquired"])

    if not scenario.windows:
        outcome = "nominal_ok" if false_triggers == 0 else "nominal_false_trigger"
        success = false_triggers == 0
    elif missed_count:
        outcome, success = "failed_missed", False
    elif no_reacq:
        outcome, success = "failed_no_reacquire", False
    else:
        outcome, success = "success", True

    return {
        "scenario": scenario.key,
        "seed": seed,
        "mpc_mode": "not_applicable",
        "status": "ok",
        "n_ticks": len(rows),
        "duration_s": scenario.duration_s,
        "faults_injected": len(scenario.windows),
        "faults_detected": len(detected),
        "mean_detection_time_s": float(np.mean(det_times)) if det_times else float("nan"),
        "mean_recovery_time_s": float(np.mean(rec_times)) if rec_times else float("nan"),
        "reacquire_success_ratio": (len(reacq) / len(scenario.windows)) if scenario.windows else float("nan"),
        "safe_mode_trigger_count": safe_triggers,
        "false_trigger_count": false_triggers,
        "missed_trigger_count": missed_count,
        "tracking_fraction": tracking_fraction,
        "mission_outcome": outcome,
        "mission_success": success,
        "_fault_records": fault_records,
        "effective_sample_count": len(rows),
        "failure_event_count": missed_count + false_triggers,
        "capability_gate_status": "not_applicable_decision_core",
        "solver_wall_time_current_ms": "not_applicable",
        "fallback_type": "|".join(sorted({fr["expected_role"] for fr in fault_records})) or "not_applicable",
    }


def _write_csv(path: Path, rows: list[dict[str, object]], fields: Sequence[str] | None = None) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields and not key.startswith("_"):
                    fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _fmt(row.get(k, "")) for k in fields})


def _fmt(value: object) -> object:
    if isinstance(value, float):
        return "nan" if math.isnan(value) else f"{value:.6g}"
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def summarize_faults(fault_records: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for fr in fault_records:
        groups.setdefault(str(fr["fault_type"]), []).append(fr)
    summary: list[dict[str, object]] = []
    for ft, items in sorted(groups.items()):
        det = [float(it["detection_time_s"]) for it in items if not it["missed"]]
        rec = [float(it["recovery_time_s"]) for it in items
               if isinstance(it["recovery_time_s"], float) and math.isfinite(it["recovery_time_s"])]
        summary.append({
            "fault_type": ft,
            "expected_role": items[0]["expected_role"],
            "run_count": len(items),
            "detection_rate": float(np.mean([0.0 if it["missed"] else 1.0 for it in items])),
            "reacquire_rate": float(np.mean([1.0 if it["reacquired"] else 0.0 for it in items])),
            "detection_time_mean_s": float(np.mean(det)) if det else float("nan"),
            "detection_time_std_s": float(np.std(det)) if len(det) >= 2 else 0.0,
            "recovery_time_mean_s": float(np.mean(rec)) if rec else float("nan"),
            "recovery_time_std_s": float(np.std(rec)) if len(rec) >= 2 else 0.0,
        })
    return summary


def _setup_font():
    import os
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    zh_font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    if os.path.exists(zh_font):
        fm.fontManager.addfont(zh_font)
        plt.rcParams["font.family"] = fm.FontProperties(fname=zh_font).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    return plt


FAULT_SHADE = {
    "leak": "#e15759", "battery": "#f28e2b", "penetration": "#b07aa1",
    "dvl_dropout": "#4e79a7", "mag_dropout": "#76b7b2", "sonar_dropout": "#59a14f",
    "target_loss": "#9c755f", "heartbeat_timeout": "#edc948", "solver_timeout": "#ff9da7",
}


def plot_timeline(plt, scenario: Scenario, rows: list[dict[str, object]], out_dir: Path) -> None:
    times = [float(r["time"]) for r in rows]
    ys = [ROLE_Y.get(str(r["role"]), -1) for r in rows]
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    for w in scenario.windows:
        ax.axvspan(w.start_s, w.end_s, color=FAULT_SHADE.get(w.fault_type, "#cccccc"),
                   alpha=0.22, zorder=0)
        ax.text((w.start_s + w.end_s) / 2, len(ROLE_Y) - 0.4, w.fault_type,
                ha="center", va="top", fontsize=7, color="#333333")
    ax.step(times, ys, where="post", color="#1f77b4", lw=1.6, zorder=3)
    ax.set_yticks(list(ROLE_Y.values()))
    ax.set_yticklabels(list(ROLE_Y.keys()), fontsize=8)
    ax.set_ylim(-0.5, len(ROLE_Y) - 0.5)
    ax.set_xlabel("时间 [s]")
    ax.set_title(f"BT 故障注入时间线：{scenario.label}（seed 0）")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out_dir / "figures" / f"timeline_{scenario.key}.{ext}", bbox_inches="tight")
    plt.close(fig)


def plot_recovery_summary(plt, summary: list[dict[str, object]], out_dir: Path) -> None:
    if not summary:
        return
    fts = [s["fault_type"] for s in summary]
    det = [s["detection_time_mean_s"] if math.isfinite(s["detection_time_mean_s"]) else 0.0 for s in summary]
    det_e = [s["detection_time_std_s"] for s in summary]
    rec = [s["recovery_time_mean_s"] if math.isfinite(s["recovery_time_mean_s"]) else 0.0 for s in summary]
    rec_e = [s["recovery_time_std_s"] for s in summary]
    x = np.arange(len(fts))
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    ax.bar(x - 0.2, det, 0.4, yerr=det_e, capsize=3, label="检测/切换时间", color="#4e79a7")
    ax.bar(x + 0.2, rec, 0.4, yerr=rec_e, capsize=3, label="重捕获恢复时间", color="#59a14f")
    ax.set_xticks(x)
    ax.set_xticklabels(fts, rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("时间 [s]")
    ax.set_title("各故障类型 BT 检测与恢复时间（多种子均值±std）")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out_dir / "figures" / f"recovery_summary.{ext}", bbox_inches="tight")
    plt.close(fig)


def write_summary_md(out_dir: Path, run_rows: list[dict[str, object]],
                     fault_summary: list[dict[str, object]]) -> None:
    lines = [
        "# 行为树故障注入实验小结（组 D）",
        "",
        "驱动**未改动**的 `DecisionTreeEngine` 逐 tick 回放，注入故障流经真实节点：",
        "漏水/低电/穿底→紧急子树（RETURN_OR_ABORT）；感知丢失→之字重定位（RELOCALIZATION）；",
        "心跳超时→授权丢失待命（SAFE_HOVER）；求解超时→异常降速装饰器（DEGRADED_MODE，注入代理）。",
        "",
        "## 各故障类型检测/恢复（跨种子）",
        "",
        "| 故障类型 | 期望行为 | 样本 | 检测率 | 重捕获率 | 检测时间均值[s] | 恢复时间均值[s] |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for s in fault_summary:
        det = f"{s['detection_time_mean_s']:.2f}" if math.isfinite(s["detection_time_mean_s"]) else "—"
        rec = f"{s['recovery_time_mean_s']:.2f}" if math.isfinite(s["recovery_time_mean_s"]) else "—"
        lines.append(
            f"| {s['fault_type']} | {s['expected_role']} | {s['run_count']} | "
            f"{s['detection_rate']*100:.0f}% | {s['reacquire_rate']*100:.0f}% | {det} | {rec} |")
    lines += [
        "",
        "## 各场景任务结局",
        "",
        "| 场景 | 种子 | 结局 | 安全模式触发 | 假阳性 | 漏报 | 跟踪占比 |",
        "|---|---:|---|---:|---:|---:|---:|",
    ]
    for r in run_rows:
        lines.append(
            f"| {r['scenario']} | {r['seed']} | {r['mission_outcome']} | "
            f"{r['safe_mode_trigger_count']} | {r['false_trigger_count']} | "
            f"{r['missed_trigger_count']} | {r['tracking_fraction']*100:.0f}% |")
    lines += [
        "",
        "## 边界说明",
        "",
        "- `solver_timeout` 为**注入代理**：置 `anomaly_detected` 标志触发 `AnomalySpeedLimiter` 降速，"
        "并非真机 MPC 求解器 wall-time 负载（故 `solver_wall_time_current_ms=not_applicable`）。",
        "- `heartbeat_timeout` 复用 `Wait_For_Arbiter_Authorization` 的授权丢失路径作为心跳丢失代理。",
        "- 行为角色（SEARCH_ZIGZAG/CABLE_CAPTURE/RELOCALIZATION/DEGRADED_MODE 等）为对引擎原始模式的"
        "**语义标注**，原始模式保留在时间线 CSV 的 `state` 列，映射可审计。",
        "",
    ]
    (out_dir / "fault_injection_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    seeds = [int(s) for s in str(args.seeds).split(",") if s.strip()]
    wanted = {x.strip() for x in args.scenarios.split(",") if x.strip()}
    selected = [s for s in SCENARIOS if s.key in wanted]
    if not selected:
        print(f"[bt-fault] no matching scenarios in {args.scenarios}", file=sys.stderr)
        return 2

    stamp = time.strftime("%Y%m%dT%H%M%S")
    out = args.output_dir or (REPO_ROOT / "results" / "decision" / "bt_fault_injection" / stamp)
    initialize_bundle(
        out,
        experiment_id=f"bt_fault_injection_{stamp}",
        runner="tools/run_bt_fault_injection.py",
        argv=list(argv) if argv is not None else sys.argv,
        data_layer="decision_core_scripted_fault_injection",
        matrix={
            "scenarios": [s.key for s in selected],
            "seeds": seeds,
            "fault_types": sorted(EXPECTED_RESPONSE_ROLE),
            "tick_hz": TICK_HZ,
        },
        duration_s=max(s.duration_s for s in selected),
        config_paths=[
            Path(__file__),
            REPO_ROOT / "brain_linux/src/auv_decision/auv_decision_core/bt_engine.py",
            REPO_ROOT / "brain_linux/src/auv_decision/auv_decision_core/behaviors.py",
            REPO_ROOT / "brain_linux/src/auv_decision/auv_decision_core/decorators.py",
            REPO_ROOT / "brain_linux/src/auv_decision/auv_decision_core/decision_filters.py",
        ],
        extra_manifest={
            "hardware_claim": False,
            "confidence_gate": {
                "threshold": CONFIDENCE_THRESHOLD,
                "hysteresis": CONFIDENCE_HYSTERESIS,
                "debounce_ticks": CONFIDENCE_DEBOUNCE_TICKS,
                "note": "R17 schmitt_debounce deployed config; emergency never debounced",
            },
            "solver_timeout_role": "injection_proxy_anomaly_flag_not_real_solver_load",
            "heartbeat_timeout_role": "authorization_loss_path_proxy",
            "behavior_role_note": "derived_semantic_annotation_over_raw_engine_mode",
        },
    )

    run_rows: list[dict[str, object]] = []
    all_timeline: list[dict[str, object]] = []
    all_faults: list[dict[str, object]] = []
    seed0_timelines: dict[str, list[dict[str, object]]] = {}

    for scenario in selected:
        for seed in seeds:
            result = run_scenario(scenario, seed)
            timeline = result.pop("_timeline")
            faults = result.pop("_fault_records")
            all_timeline.extend(timeline)
            all_faults.extend(faults)
            if seed == seeds[0]:
                seed0_timelines[scenario.key] = timeline
            run_rows.append(result)
            if not args.quiet:
                print(f"[bt-fault] {scenario.key:20s} seed{seed} "
                      f"outcome={result['mission_outcome']:20s} "
                      f"safe_trig={result['safe_mode_trigger_count']} "
                      f"false={result['false_trigger_count']} "
                      f"track={result['tracking_fraction']*100:.0f}%")

    fault_summary = summarize_faults(all_faults)

    timeline_fields = ["scenario", "seed", "time", "state", "role", "previous_state",
                       "previous_role", "trigger", "confidence", "fault_type", "recovery_mode"]
    _write_csv(out / "behavior_tree.csv", all_timeline, timeline_fields)
    _write_csv(out / "fault_records.csv", all_faults)
    _write_csv(out / "fault_summary.csv", fault_summary)
    (out / "fault_summary.json").write_text(
        json.dumps({"schema_version": 1, "fault_summary": fault_summary}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    if not args.no_figure:
        plt = _setup_font()
        for scenario in selected:
            plot_timeline(plt, scenario, seed0_timelines[scenario.key], out)
        plot_recovery_summary(plt, fault_summary, out)

    write_summary_md(out, run_rows, fault_summary)
    finalize_bundle(out, run_rows, success_statuses={"ok"})
    if not args.quiet:
        print(f"[bt-fault] {len(run_rows)} runs, {len(all_timeline)} ticks -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
