#!/usr/bin/env python3
"""R22 native cable closed-loop runner.

This runner connects the R21 factorized native cable scenario generator to the
existing guidance-level MPC and source-specific quality policy.  It is an
offline simulation-proxy closed loop: useful for factor interaction evidence,
but not a native PVS depthHeadingAutopilot validation.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import math
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
for package_root in (
    REPO_ROOT / "brain_linux/src/auv_control",
    REPO_ROOT / "brain_linux/src/auv_controller",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from algorithm.auv_mpc_controller import (  # noqa: E402
    AUVKinematicsModel,
    AUVMPCOptimizer,
)
from algorithm.native_cable_scenario import (  # noqa: E402
    NativeCableScenario,
    NativeScenarioFactors,
)
from auv_controller.quality_control_policy import (  # noqa: E402
    AuthoritySnapshot,
    ConservativeQualityControlPolicy,
)
from auv_decision_ros.tracking_authority import (  # noqa: E402
    QualitySignal,
    TrackingAuthorityMachine,
)
from tools.es_ekf_long_horizon_replay import (  # noqa: E402
    DEFAULT_NOISE_PATH,
    load_measured_noise,
)
from tools.experiment_contract import finalize_bundle, initialize_bundle  # noqa: E402


FACTOR_NAMES = (
    "curved_geometry",
    "terrain_enabled",
    "measured_noise_replay",
    "cross_current_enabled",
)
MODE_NAMES = {
    0: "HOLD",
    1: "SEARCH",
    2: "TRACK",
}
EFFECT_METRICS = (
    "lateral_rmse_m",
    "lateral_p95_m",
    "safety_violation_rate",
    "seabed_penetration_rate",
    "fallback_rate",
    "progress_pct",
    "control_delta_rms",
)


def parse_csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_int_list(value: str) -> list[int]:
    return [int(item) for item in parse_csv_list(value)]


def wrap_angle(angle: float | np.ndarray) -> float | np.ndarray:
    return (angle + np.pi) % (2.0 * np.pi) - np.pi


def factor_label(factors: NativeScenarioFactors) -> str:
    return (
        f"g{int(factors.curved_geometry)}"
        f"_t{int(factors.terrain_enabled)}"
        f"_r{int(factors.measured_noise_replay)}"
        f"_c{int(factors.cross_current_enabled)}"
    )


def factors_from_label(label: str) -> NativeScenarioFactors:
    values: dict[str, bool] = {}
    parts = label.split("_")
    mapping = {
        "g": "curved_geometry",
        "t": "terrain_enabled",
        "r": "measured_noise_replay",
        "c": "cross_current_enabled",
    }
    for part in parts:
        if len(part) != 2 or part[0] not in mapping or part[1] not in "01":
            raise ValueError(f"invalid factor label {label!r}")
        values[mapping[part[0]]] = part[1] == "1"
    missing = [name for name in FACTOR_NAMES if name not in values]
    if missing:
        raise ValueError(f"factor label {label!r} missing {missing}")
    return NativeScenarioFactors(**values)


def make_factor_matrix(args: argparse.Namespace) -> list[NativeScenarioFactors]:
    if args.factor_labels:
        return [factors_from_label(label) for label in parse_csv_list(args.factor_labels)]
    if args.factor_set in {"all", "full"}:
        return [
            NativeScenarioFactors(*values)
            for values in itertools.product((False, True), repeat=4)
        ]
    if args.factor_set == "all_on":
        return [NativeScenarioFactors(True, True, True, True)]
    if args.factor_set == "smoke":
        return [
            NativeScenarioFactors(False, False, False, False),
            NativeScenarioFactors(True, True, True, True),
        ]
    raise ValueError(f"unsupported factor set {args.factor_set!r}")


def cumulative_s(path: np.ndarray) -> np.ndarray:
    d = np.hypot(np.diff(path[:, 0]), np.diff(path[:, 1]))
    return np.concatenate([[0.0], np.cumsum(d)])


def nearest_index(
    path: np.ndarray,
    xy: np.ndarray,
    start: int = 0,
    window: int = 220,
) -> int:
    lo = max(0, start - 30)
    hi = min(len(path), max(lo + 1, start + window))
    delta = path[lo:hi, :2] - xy.reshape(1, 2)
    return lo + int(np.argmin(np.sum(delta * delta, axis=1)))


def sample_by_s(path: np.ndarray, s_values: np.ndarray, s_query: float) -> np.ndarray:
    s = float(np.clip(s_query, s_values[0], s_values[-1]))
    return np.asarray(
        [np.interp(s, s_values, path[:, col]) for col in range(path.shape[1])],
        dtype=float,
    )


def build_native_path(
    scenario: NativeCableScenario,
    *,
    ds: float,
    target_altitude_m: float,
    target_speed_mps: float,
    min_speed_mps: float,
) -> np.ndarray:
    xy_rows: list[tuple[float, float]] = []
    cable_xy = scenario.cable.points[:, :2]
    for start, end in zip(cable_xy[:-1], cable_xy[1:]):
        length = float(np.linalg.norm(end - start))
        count = max(2, int(math.ceil(length / max(ds, 1e-3))))
        for index in range(count):
            alpha = index / count
            xy = start + alpha * (end - start)
            xy_rows.append((float(xy[0]), float(xy[1])))
    xy_rows.append((float(cable_xy[-1, 0]), float(cable_xy[-1, 1])))
    xy_array = np.asarray(xy_rows, dtype=float)

    dx = np.gradient(xy_array[:, 0])
    dy = np.gradient(xy_array[:, 1])
    yaw = np.unwrap(np.arctan2(dy, dx))
    step = np.maximum(np.hypot(dx, dy), 1e-6)
    curvature = np.abs(np.gradient(yaw) / step)
    speed_scale = 1.0 / (1.0 + 4.0 * curvature)
    speed = np.clip(target_speed_mps * speed_scale, min_speed_mps, target_speed_mps)
    depth = np.asarray(
        [
            scenario.terrain_depth(float(x), float(y)) - target_altitude_m
            for x, y in xy_array
        ],
        dtype=float,
    )
    return np.column_stack((xy_array[:, 0], xy_array[:, 1], depth, yaw, speed))


def build_optimizer(mode: str, args: argparse.Namespace) -> AUVMPCOptimizer:
    model = AUVKinematicsModel(
        {
            "mass_u": 50.0,
            "mass_w": 50.0,
            "drag_u": 12.0,
            "drag_w": 20.0,
            "buoyancy_term": 0.0,
            "yaw_rate_gain": args.yaw_rate_gain,
            "pitch_depth_gain": 0.8,
            "depth_to_heave_gain": 12.0,
            "max_pitch_deg": 20.0,
        }
    )
    conservative = mode == "ua"
    return AUVMPCOptimizer(
        model,
        N=args.horizon,
        dt=args.dt,
        max_iter=args.max_iter,
        weights={
            "x": 14.0,
            "y": 14.0,
            "z": 12.0,
            "psi": 45.0,
            "u": 0.4,
            "w": 0.5,
            "psi_cmd": 0.0005,
            "z_cmd": 0.001,
            "T_cmd": 0.004,
            "confidence_threshold": 0.6,
            "low_confidence_scale": 3.0,
            "low_confidence_control_scale": 0.3,
            "confidence_policy": "conservative" if conservative else "legacy_aggressive",
            "low_conf_control_penalty_scale": 3.0,
            "low_conf_tracking_floor": 0.35,
            "delta_psi_cmd": 2.0 if conservative else 0.0,
            "delta_z_cmd": 0.5 if conservative else 0.0,
            "delta_T_cmd": 0.1 if conservative else 0.0,
            "mpc_mode": mode,
        },
        constraints={
            "min_speed_ms": 0.0,
            "min_thrust_percent": 0.0,
            "max_thrust_percent": 35.0,
            "min_z_cmd_m": 0.0,
            "max_z_cmd_m": 30.0,
            "delta_z_max_per_step": 1.0,
            "delta_psi_max_per_step": math.radians(12.0) * args.dt,
            "z_band_m": 5.0,
            "psi_band_rad": math.radians(70.0),
            "enable_rate_constraints": True,
            "enable_band_constraints": True,
            "enable_constraint_slack": True,
            "constraint_slack_weight": 1e4,
        },
    )


def sonar_probability(sonar_peak: float) -> float:
    return float(1.0 / (1.0 + math.exp(-(float(sonar_peak) - 0.25) / 0.08)))


def magnetic_probability(field_t: np.ndarray, noise_floor_t: float) -> float:
    field_norm = float(np.linalg.norm(np.asarray(field_t, dtype=float)))
    floor = max(float(noise_floor_t), 1.0e-12)
    snr = max(0.0, field_norm / floor - 1.0)
    return float(np.clip(1.0 - math.exp(-snr / 4.0), 0.0, 1.0))


def authority_for_measurement(
    machine: TrackingAuthorityMachine,
    measurement: dict[str, object],
    *,
    noise_floor_t: float,
) -> tuple[object, dict[str, float]]:
    sonar_p = sonar_probability(float(measurement["sonar_peak"]))
    magnetic_p = magnetic_probability(
        np.asarray(measurement["magnetic_field_t"], dtype=float),
        noise_floor_t,
    )
    signals = [
        QualitySignal(
            source="sonar",
            validity=1,
            p_detect=sonar_p,
            p_track=sonar_p,
            detection_calibrated=True,
            track_calibrated=True,
            age_s=0.0,
        ),
        QualitySignal(
            source="magnetic",
            validity=1,
            p_detect=magnetic_p,
            p_track=float("nan"),
            detection_calibrated=True,
            track_calibrated=False,
            age_s=0.0,
        ),
    ]
    decision = machine.update(signals, runtime_sensor_health_ok=True)
    return decision, {"sonar_p": sonar_p, "magnetic_p": magnetic_p}


def policy_decision(
    policy: ConservativeQualityControlPolicy,
    authority: object,
    target_speed_mps: float,
) -> tuple[float, float, float, str]:
    snapshot = AuthoritySnapshot(
        mode=int(authority.mode),
        tracking_authorized=bool(authority.tracking_authorized),
        p_track=float(authority.p_track),
        calibration_domain="simulation_proxy",
        shadow_only=True,
        age_s=0.0,
    )
    decision = policy.apply(target_speed_mps, snapshot)
    confidence = float(decision.confidence if decision.confidence is not None else 0.0)
    return (
        float(decision.target_speed_mps),
        confidence,
        float(decision.delta_u_penalty_scale),
        str(decision.reason),
    )


def plant_step_with_current(
    state: np.ndarray,
    control: np.ndarray,
    current_ned: np.ndarray,
    dt: float,
    *,
    yaw_rate_gain: float,
) -> np.ndarray:
    x, y, z, psi, u, w = [float(value) for value in state]
    psi_cmd, z_cmd, thrust_pct = [float(value) for value in control]
    current = np.asarray(current_ned, dtype=float).reshape(3)

    yaw_err = float(wrap_angle(psi_cmd - psi))
    yaw_rate = np.clip(
        yaw_rate_gain * yaw_err,
        -math.radians(12.0),
        math.radians(12.0),
    )
    psi_next = float(wrap_angle(psi + dt * yaw_rate))

    drag_u = 12.0 * u * abs(u)
    u_next = float(np.clip(u + dt * (max(0.0, thrust_pct) - drag_u) / 50.0, 0.0, 1.8))

    depth_error = z_cmd - z
    max_pitch = math.radians(20.0)
    theta_raw = -0.8 * depth_error
    theta = max_pitch * math.tanh(theta_raw / max_pitch)
    dz = -u_next * math.sin(theta) + w * math.cos(theta)
    dw = (-20.0 * w + 12.0 * depth_error) / 50.0
    z_next = float(np.clip(z + dt * dz, 0.0, 30.0))
    w_next = float(np.clip(w + dt * dw, -1.5, 1.5))

    x_next = x + dt * (u_next * math.cos(psi_next) + float(current[0]))
    y_next = y + dt * (u_next * math.sin(psi_next) + float(current[1]))
    return np.asarray([x_next, y_next, z_next, psi_next, u_next, w_next], dtype=float)


def build_reference(
    path: np.ndarray,
    s_values: np.ndarray,
    start_index: int,
    optimizer: AUVMPCOptimizer,
    local_speed_mps: float,
) -> np.ndarray:
    speed = max(float(local_speed_mps), 0.0)
    ref = np.zeros((6, optimizer.N + 1), dtype=float)
    s0 = float(s_values[start_index])
    for preview in range(optimizer.N + 1):
        sample = sample_by_s(path, s_values, s0 + preview * speed * optimizer.dt)
        ref[:, preview] = [
            sample[0],
            sample[1],
            sample[2],
            sample[3],
            speed,
            0.0,
        ]
    return ref


def los_fallback_control(
    state: np.ndarray,
    path: np.ndarray,
    s_values: np.ndarray,
    index: int,
    *,
    lookahead_m: float,
    speed_mps: float,
) -> np.ndarray:
    target = sample_by_s(path, s_values, s_values[index] + lookahead_m)
    heading = math.atan2(float(target[1] - state[1]), float(target[0] - state[0]))
    thrust = 12.0 * max(float(speed_mps), 0.25) ** 2
    return np.asarray([heading, float(target[2]), thrust], dtype=float)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def finite_summary(values: list[float], name: str) -> float:
    finite = np.asarray([value for value in values if math.isfinite(value)], dtype=float)
    if finite.size == 0:
        return float("nan")
    if name == "mean":
        return float(np.mean(finite))
    if name == "p95":
        return float(np.percentile(finite, 95))
    if name == "max":
        return float(np.max(finite))
    if name == "min":
        return float(np.min(finite))
    raise ValueError(name)


def finite_values(values: list[float]) -> np.ndarray:
    return np.asarray([value for value in values if math.isfinite(value)], dtype=float)


def exceed_rate(values: list[float], threshold_ms: float) -> float:
    finite = finite_values(values)
    if finite.size == 0:
        return float("nan")
    return float(np.mean(finite > float(threshold_ms)))


def timing_period_ms(rate_hz: float) -> float:
    return 1000.0 / max(float(rate_hz), 1.0e-9)


def run_case(
    *,
    factors: NativeScenarioFactors,
    seed: int,
    mode: str,
    noise_t: np.ndarray,
    noise_rate_hz: float,
    output_dir: Path,
    args: argparse.Namespace,
) -> dict[str, object]:
    scenario = NativeCableScenario(
        factors=factors,
        seed=seed,
        replay_noise_t=noise_t,
        replay_rate_hz=noise_rate_hz,
        sample_rate_hz=1.0 / args.dt,
    )
    path = build_native_path(
        scenario,
        ds=args.path_ds,
        target_altitude_m=args.target_altitude_m,
        target_speed_mps=args.target_speed_mps,
        min_speed_mps=args.minimum_reference_speed_mps,
    )
    s_values = cumulative_s(path)
    optimizer = build_optimizer(mode, args)
    policy = ConservativeQualityControlPolicy(
        enabled=True,
        accept_shadow=True,
        allowed_calibration_domain="simulation_proxy",
        maximum_age_s=0.75,
        minimum_speed_scale=args.minimum_quality_speed_scale,
        maximum_delta_u_penalty_scale=4.0,
        maximum_safety_margin_scale=1.5,
    )
    authority_machine = TrackingAuthorityMachine()
    noise_floor_t = float(np.sqrt(np.trace(scenario.noise_covariance)))

    state = np.asarray(
        [
            path[0, 0],
            path[0, 1] + args.initial_y_offset_m,
            path[0, 2],
            path[0, 3],
            args.target_speed_mps,
            0.0,
        ],
        dtype=float,
    )
    previous_plan = None
    previous_control = None
    path_index = 0
    steps = max(1, int(round(args.duration / args.dt)))
    label = factor_label(factors)
    run_id = f"{label}__seed{seed}__{mode}"
    trace_rows: list[dict[str, object]] = []

    fallback_count = 0
    blocked_count = 0
    wall_times: list[float] = []
    controls: list[np.ndarray] = []
    states: list[np.ndarray] = []
    cable_distance: list[float] = []
    clearance: list[float] = []
    p_track_values: list[float] = []
    p_detect_values: list[float] = []
    sonar_p_values: list[float] = []
    magnetic_p_values: list[float] = []
    speed_scales: list[float] = []
    delta_scales: list[float] = []
    modes: list[int] = []
    current_speeds: list[float] = []
    sonar_visible_values: list[bool] = []
    fallback_reasons: dict[str, int] = {}
    terminal_reached = False
    terminal_exit_time_s = float("nan")

    for step in range(steps):
        time_s = step * args.dt
        truth, measurement = scenario.sample(
            position_ned=state[:3],
            time_s=time_s,
            sample_index=step,
        )
        authority, quality = authority_for_measurement(
            authority_machine,
            measurement,
            noise_floor_t=noise_floor_t,
        )
        if mode == "ua":
            local_speed, confidence, delta_scale, policy_reason = policy_decision(
                policy,
                authority,
                args.target_speed_mps,
            )
        else:
            local_speed = args.target_speed_mps
            confidence = 1.0
            delta_scale = 1.0
            policy_reason = "baseline_fixed"

        path_index = nearest_index(path, state[:2], path_index)
        if args.terminal_policy == "exit_at_end" and path_index >= len(path) - 1:
            terminal_reached = True
            terminal_exit_time_s = time_s
            break
        reference = build_reference(
            path,
            s_values,
            path_index,
            optimizer,
            local_speed,
        )
        diagnostics: dict[str, object] = {}
        try:
            result = optimizer.solve(
                state,
                reference,
                confidence=confidence,
                warm_start_U=previous_plan,
                delta_u_penalty_scale=delta_scale,
                previous_control=previous_control,
            )
            control = np.asarray(result["U_opt"][:, 0], dtype=float)
            previous_plan = np.asarray(result["U_opt"], dtype=float)
            diagnostics = dict(result)
        except RuntimeError as exc:
            diagnostics = dict(getattr(exc, "diagnostics", {}))
            reason = str(diagnostics.get("solver_status", str(exc))).splitlines()[-1]
            fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1
            fallback_count += 1
            previous_plan = None
            control = los_fallback_control(
                state,
                path,
                s_values,
                path_index,
                lookahead_m=args.fallback_lookahead_m,
                speed_mps=local_speed,
            )

        wall_ms = float(diagnostics.get("solver_wall_time_current_ms", float("nan")))
        if math.isfinite(wall_ms):
            wall_times.append(wall_ms)
            blocked_count += int(wall_ms > args.dt * 1000.0)
        previous_control = control.copy()
        states.append(state.copy())
        controls.append(control.copy())

        terrain_depth = scenario.terrain_depth(float(state[0]), float(state[1]))
        clear = terrain_depth - float(state[2])
        clearance.append(clear)
        cable_distance.append(float(truth["cable_distance_m"]))
        p_track = float(authority.p_track)
        p_detect = float(authority.p_detect)
        p_track_values.append(p_track if math.isfinite(p_track) else 0.0)
        p_detect_values.append(p_detect if math.isfinite(p_detect) else 0.0)
        sonar_p_values.append(float(quality["sonar_p"]))
        magnetic_p_values.append(float(quality["magnetic_p"]))
        speed_scales.append(float(local_speed / max(args.target_speed_mps, 1e-6)))
        delta_scales.append(delta_scale)
        modes.append(int(authority.mode))
        current = np.asarray(truth["current_velocity_ned"], dtype=float)
        current_speeds.append(float(np.linalg.norm(current)))
        sonar_visible_values.append(bool(truth["sonar_visible"]))
        trace_rows.append(
            {
                "time_s": time_s,
                "x_m": float(state[0]),
                "y_m": float(state[1]),
                "z_m": float(state[2]),
                "psi_rad": float(state[3]),
                "u_mps": float(state[4]),
                "w_mps": float(state[5]),
                "ref_index": path_index,
                "cable_distance_m": float(truth["cable_distance_m"]),
                "seabed_clearance_m": clear,
                "current_speed_mps": current_speeds[-1],
                "sonar_visible": int(sonar_visible_values[-1]),
                "sonar_p": sonar_p_values[-1],
                "magnetic_p": magnetic_p_values[-1],
                "p_detect": p_detect_values[-1],
                "p_track": p_track_values[-1],
                "authority_mode": MODE_NAMES.get(int(authority.mode), str(authority.mode)),
                "local_speed_mps": local_speed,
                "confidence": confidence,
                "delta_u_penalty_scale": delta_scale,
                "policy_reason": policy_reason,
                "psi_cmd_rad": float(control[0]),
                "z_cmd_m": float(control[1]),
                "thrust_cmd_pct": float(control[2]),
                "solver_wall_time_ms": wall_ms,
            }
        )
        state = plant_step_with_current(
            state,
            control,
            current,
            args.dt,
            yaw_rate_gain=args.yaw_rate_gain,
        )

    states_array = np.asarray(states, dtype=float)
    controls_array = np.asarray(controls, dtype=float)
    actual_steps = max(1, len(states_array))
    trace_path = output_dir / "traces" / f"{run_id}.csv"
    write_csv(trace_path, trace_rows)

    lateral: list[float] = []
    yaw_errors: list[float] = []
    nearest = 0
    for row in states_array:
        nearest = nearest_index(path, row[:2], nearest)
        lateral.append(float(np.linalg.norm(row[:2] - path[nearest, :2])))
        yaw_errors.append(float(abs(wrap_angle(row[3] - path[nearest, 3]))))
    clear_arr = np.asarray(clearance, dtype=float)
    lateral_arr = np.asarray(lateral, dtype=float)
    yaw_arr = np.asarray(yaw_errors, dtype=float)
    cable_distance_arr = np.asarray(cable_distance, dtype=float)
    control_delta = np.diff(controls_array, axis=0) if len(controls_array) > 1 else np.zeros((1, 3))
    mode_counts = {name: modes.count(code) for code, name in MODE_NAMES.items()}
    fallback_rate = fallback_count / actual_steps
    status = "ok"
    error = ""
    if not np.all(np.isfinite(states_array)):
        status = "failed"
        error = "nonfinite_state"

    return {
        "run_id": run_id,
        "scenario": "native_cable_closed_loop",
        "factor_label": label,
        "curved_geometry": int(factors.curved_geometry),
        "terrain_enabled": int(factors.terrain_enabled),
        "measured_noise_replay": int(factors.measured_noise_replay),
        "cross_current_enabled": int(factors.cross_current_enabled),
        "seed": seed,
        "mpc_mode": mode,
        "status": status,
        "error": error,
        "duration_s": args.duration,
        "dt_s": args.dt,
        "mpc_horizon_steps": args.horizon,
        "mpc_max_iter": args.max_iter,
        "mpc_prediction_horizon_s": args.horizon * args.dt,
        "effective_sample_count": actual_steps,
        "effective_duration_s": actual_steps * args.dt,
        "terminal_policy": args.terminal_policy,
        "terminal_reached": int(terminal_reached),
        "terminal_exit_time_s": terminal_exit_time_s,
        "terminal_tail_excluded": int(args.terminal_policy == "exit_at_end"),
        "failure_event_count": fallback_count,
        "capability_gate_status": "passed" if status == "ok" else "failed",
        "solver_wall_time_current_ms": finite_summary(wall_times, "p95"),
        "fallback_type": "los" if fallback_count else "none",
        "fallback_rate": fallback_rate,
        "fallback_reasons": ";".join(
            f"{key}:{value}" for key, value in sorted(fallback_reasons.items())
        ),
        "control_period_blocked_count": blocked_count,
        "control_period_blocked_rate": blocked_count / actual_steps,
        "solver_wall_time_mean_ms": finite_summary(wall_times, "mean"),
        "solver_wall_time_p95_ms": finite_summary(wall_times, "p95"),
        "solver_wall_time_max_ms": finite_summary(wall_times, "max"),
        "solver_timing_sample_count": int(finite_values(wall_times).size),
        "timing_audit_domain": "offline_python_simulation_proxy_solver_only",
        "timing_runner_period_ms": args.dt * 1000.0,
        "timing_ros_control_period_ms": timing_period_ms(args.ros_control_rate_hz),
        "timing_bridge_command_period_ms": timing_period_ms(args.bridge_command_rate_hz),
        "timing_vxworks_main_period_ms": timing_period_ms(args.vxworks_main_rate_hz),
        "timing_vxworks_net_recv_period_ms": args.vxworks_net_recv_period_s * 1000.0,
        "timing_runner_blocked_rate": exceed_rate(wall_times, args.dt * 1000.0),
        "timing_ros_control_blocked_rate": exceed_rate(
            wall_times,
            timing_period_ms(args.ros_control_rate_hz),
        ),
        "timing_bridge_command_blocked_rate": exceed_rate(
            wall_times,
            timing_period_ms(args.bridge_command_rate_hz),
        ),
        "timing_vxworks_main_blocked_rate": exceed_rate(
            wall_times,
            timing_period_ms(args.vxworks_main_rate_hz),
        ),
        "timing_vxworks_net_recv_blocked_rate": exceed_rate(
            wall_times,
            args.vxworks_net_recv_period_s * 1000.0,
        ),
        "lateral_rmse_m": float(np.sqrt(np.mean(lateral_arr * lateral_arr))),
        "lateral_p95_m": float(np.percentile(lateral_arr, 95)),
        "lateral_max_m": float(np.max(lateral_arr)),
        "cable_distance_mean_m": float(np.mean(cable_distance_arr)),
        "cable_distance_p95_m": float(np.percentile(cable_distance_arr, 95)),
        "cable_distance_max_m": float(np.max(cable_distance_arr)),
        "yaw_rmse_deg": float(math.degrees(np.sqrt(np.mean(yaw_arr * yaw_arr)))),
        "progress_pct": float(100.0 * path_index / max(1, len(path) - 1)),
        "seabed_clearance_min_m": float(np.min(clear_arr)),
        "seabed_clearance_mean_m": float(np.mean(clear_arr)),
        "safety_violation_rate": float(np.mean(clear_arr < args.minimum_clearance_m)),
        "seabed_penetration_rate": float(np.mean(clear_arr < 0.0)),
        "sonar_visible_rate": float(np.mean(sonar_visible_values)),
        "p_detect_mean": float(np.mean(p_detect_values)),
        "p_track_mean": float(np.mean(p_track_values)),
        "sonar_p_mean": float(np.mean(sonar_p_values)),
        "magnetic_p_mean": float(np.mean(magnetic_p_values)),
        "authority_hold_rate": mode_counts["HOLD"] / actual_steps,
        "authority_search_rate": mode_counts["SEARCH"] / actual_steps,
        "authority_track_rate": mode_counts["TRACK"] / actual_steps,
        "speed_scale_min": float(np.min(speed_scales)),
        "speed_scale_mean": float(np.mean(speed_scales)),
        "delta_u_penalty_scale_max": float(np.max(delta_scales)),
        "control_delta_rms": float(np.sqrt(np.mean(control_delta * control_delta))),
        "current_speed_mean_mps": float(np.mean(current_speeds)),
        "truth_measurement_separated": True,
        "trace_csv": str(trace_path.resolve().relative_to(REPO_ROOT.resolve())),
    }


def summarize_timing(
    rows: list[dict[str, object]],
    args: argparse.Namespace,
) -> list[dict[str, object]]:
    valid = [row for row in rows if row.get("status") == "ok"]
    if not valid:
        valid = rows
    max_solver_p95 = finite_summary(
        [float(row.get("solver_wall_time_p95_ms", float("nan"))) for row in valid],
        "max",
    )
    max_solver_max = finite_summary(
        [float(row.get("solver_wall_time_max_ms", float("nan"))) for row in valid],
        "max",
    )
    budgets = [
        ("runner_step", args.dt * 1000.0, "offline runner step; not a real vehicle cycle"),
        (
            "ros_controller_default_20hz",
            timing_period_ms(args.ros_control_rate_hz),
            "ROS controller default period",
        ),
        (
            "bridge_command_default_10hz",
            timing_period_ms(args.bridge_command_rate_hz),
            "Jetson bridge command publish period",
        ),
        (
            "vxworks_main_control_10hz",
            timing_period_ms(args.vxworks_main_rate_hz),
            "AMD/VxWorks main-control task period",
        ),
        (
            "vxworks_net_recv_sem_release",
            args.vxworks_net_recv_period_s * 1000.0,
            "VxWorks NetRecv semaphore release period inferred from watchdog counters",
        ),
    ]
    summary: list[dict[str, object]] = []
    for name, period_ms, note in budgets:
        rates = []
        for row in valid:
            value = row.get(f"timing_{name.split('_default_')[0]}_blocked_rate")
            if value is None:
                if name == "runner_step":
                    value = row.get("timing_runner_blocked_rate")
                elif name == "ros_controller_default_20hz":
                    value = row.get("timing_ros_control_blocked_rate")
                elif name == "bridge_command_default_10hz":
                    value = row.get("timing_bridge_command_blocked_rate")
                elif name == "vxworks_main_control_10hz":
                    value = row.get("timing_vxworks_main_blocked_rate")
                elif name == "vxworks_net_recv_sem_release":
                    value = row.get("timing_vxworks_net_recv_blocked_rate")
            if value is not None and math.isfinite(float(value)):
                rates.append(float(value))
        max_exceed = max(rates) if rates else float("nan")
        summary.append(
            {
                "timing_budget": name,
                "period_ms": period_ms,
                "max_solver_p95_ms": max_solver_p95,
                "max_solver_max_ms": max_solver_max,
                "max_exceed_rate": max_exceed,
                "p95_period_fraction": (
                    max_solver_p95 / period_ms
                    if math.isfinite(max_solver_p95) and period_ms > 0.0
                    else float("nan")
                ),
                "solver_only": True,
                "end_to_end_latency_claim": False,
                "note": note,
            }
        )
    return summary


def mean_for(
    rows: list[dict[str, object]],
    *,
    metric: str,
    mode: str,
    filters: dict[str, int],
) -> float:
    values: list[float] = []
    for row in rows:
        if mode != "all" and row.get("mpc_mode") != mode:
            continue
        if any(int(row.get(key, -1)) != value for key, value in filters.items()):
            continue
        value = float(row.get(metric, float("nan")))
        if math.isfinite(value):
            values.append(value)
    return float(np.mean(values)) if values else float("nan")


def summarize_effects(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    modes = sorted({str(row["mpc_mode"]) for row in rows}) + ["all"]
    summary: list[dict[str, object]] = []
    for mode in modes:
        for metric in EFFECT_METRICS:
            for factor in FACTOR_NAMES:
                on = mean_for(rows, metric=metric, mode=mode, filters={factor: 1})
                off = mean_for(rows, metric=metric, mode=mode, filters={factor: 0})
                summary.append(
                    {
                        "effect_type": "main",
                        "mpc_mode": mode,
                        "metric": metric,
                        "factor_a": factor,
                        "factor_b": "",
                        "mean_on": on,
                        "mean_off": off,
                        "effect": on - off if math.isfinite(on) and math.isfinite(off) else float("nan"),
                    }
                )
            for factor_a, factor_b in itertools.combinations(FACTOR_NAMES, 2):
                m11 = mean_for(
                    rows,
                    metric=metric,
                    mode=mode,
                    filters={factor_a: 1, factor_b: 1},
                )
                m10 = mean_for(
                    rows,
                    metric=metric,
                    mode=mode,
                    filters={factor_a: 1, factor_b: 0},
                )
                m01 = mean_for(
                    rows,
                    metric=metric,
                    mode=mode,
                    filters={factor_a: 0, factor_b: 1},
                )
                m00 = mean_for(
                    rows,
                    metric=metric,
                    mode=mode,
                    filters={factor_a: 0, factor_b: 0},
                )
                values = (m11, m10, m01, m00)
                effect = (
                    m11 - m10 - m01 + m00
                    if all(math.isfinite(value) for value in values)
                    else float("nan")
                )
                summary.append(
                    {
                        "effect_type": "interaction_2way",
                        "mpc_mode": mode,
                        "metric": metric,
                        "factor_a": factor_a,
                        "factor_b": factor_b,
                        "mean_on": m11,
                        "mean_off": m00,
                        "effect": effect,
                    }
                )
    return summary


def summarize_cells(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    metrics = (
        "lateral_rmse_m",
        "lateral_p95_m",
        "lateral_max_m",
        "seabed_clearance_min_m",
        "safety_violation_rate",
        "seabed_penetration_rate",
        "fallback_rate",
        "progress_pct",
        "control_delta_rms",
        "solver_wall_time_p95_ms",
        "solver_wall_time_max_ms",
        "authority_track_rate",
        "authority_search_rate",
        "authority_hold_rate",
        "p_track_mean",
        "current_speed_mean_mps",
    )
    groups: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        key = (str(row["factor_label"]), str(row["mpc_mode"]))
        groups.setdefault(key, []).append(row)

    summary: list[dict[str, object]] = []
    for (label, mode), group in sorted(groups.items()):
        base = {
            "factor_label": label,
            "mpc_mode": mode,
            "run_count": len(group),
            "ok_count": sum(1 for row in group if row.get("status") == "ok"),
            "seeds": ",".join(str(int(row["seed"])) for row in sorted(group, key=lambda item: int(item["seed"]))),
        }
        for metric in metrics:
            values = np.asarray(
                [
                    float(row.get(metric, float("nan")))
                    for row in group
                    if math.isfinite(float(row.get(metric, float("nan"))))
                ],
                dtype=float,
            )
            if values.size:
                base[f"{metric}_mean"] = float(np.mean(values))
                base[f"{metric}_std"] = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
                base[f"{metric}_min"] = float(np.min(values))
                base[f"{metric}_max"] = float(np.max(values))
            else:
                base[f"{metric}_mean"] = float("nan")
                base[f"{metric}_std"] = float("nan")
                base[f"{metric}_min"] = float("nan")
                base[f"{metric}_max"] = float("nan")
        summary.append(base)
    return summary


def worst_cases(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    selected: dict[str, dict[str, object]] = {}
    criteria = {
        "max_lateral_p95": ("lateral_p95_m", True),
        "max_safety_violation": ("safety_violation_rate", True),
        "max_fallback_rate": ("fallback_rate", True),
        "min_clearance": ("seabed_clearance_min_m", False),
        "min_progress": ("progress_pct", False),
    }
    for label, (field, descending) in criteria.items():
        finite_rows = [
            row for row in rows if math.isfinite(float(row.get(field, float("nan"))))
        ]
        if not finite_rows:
            continue
        row = sorted(
            finite_rows,
            key=lambda item: float(item[field]),
            reverse=descending,
        )[0]
        selected[label] = {"criterion": label, **row}
    return list(selected.values())


def plot_worst_path(output_dir: Path, row: dict[str, object]) -> None:
    trace_path = REPO_ROOT / str(row["trace_csv"])
    if not trace_path.is_file():
        return
    with trace_path.open(newline="", encoding="utf-8") as handle:
        trace = list(csv.DictReader(handle))
    if not trace:
        return
    x = np.asarray([float(item["x_m"]) for item in trace])
    y = np.asarray([float(item["y_m"]) for item in trace])
    plt.figure(figsize=(7.2, 4.8), dpi=180)
    plt.plot(x, y, label=str(row["run_id"]), linewidth=2.0)
    plt.scatter([x[0]], [y[0]], s=18, label="start")
    plt.scatter([x[-1]], [y[-1]], s=18, label="end")
    plt.axis("equal")
    plt.grid(alpha=0.3)
    plt.xlabel("x m")
    plt.ylabel("y m")
    plt.title("R22 worst closed-loop trace")
    plt.legend()
    output = output_dir / "figures" / "r22_worst_closed_loop_trace.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output)
    plt.close()


def write_report(
    output_dir: Path,
    rows: list[dict[str, object]],
    effects: list[dict[str, object]],
    worst: list[dict[str, object]],
    timing: list[dict[str, object]],
) -> None:
    valid = [row for row in rows if row.get("status") == "ok"]
    fallback_rates = [float(row["fallback_rate"]) for row in valid]
    violations = [float(row["safety_violation_rate"]) for row in valid]
    lateral = [float(row["lateral_p95_m"]) for row in valid]
    lines = [
        "# R22 Native Cable Closed-Loop Runner",
        "",
        f"- Runs: `{len(valid)}/{len(rows)}` valid",
        f"- Factor combinations: `{len({row['factor_label'] for row in rows})}`",
        f"- Seeds: `{sorted({int(row['seed']) for row in rows})}`",
        f"- MPC modes: `{sorted({str(row['mpc_mode']) for row in rows})}`",
        f"- MPC horizon: `{sorted({int(row['mpc_horizon_steps']) for row in rows})}` steps, "
        f"`{sorted({float(row['mpc_prediction_horizon_s']) for row in rows})}` s",
        f"- Max fallback rate: `{max(fallback_rates) if fallback_rates else float('nan'):.3f}`",
        f"- Max safety violation rate: `{max(violations) if violations else float('nan'):.3f}`",
        f"- Max lateral p95: `{max(lateral) if lateral else float('nan'):.3f} m`",
        "",
        "Boundary: offline `simulation_proxy` closed loop using R21 native factors, "
        "source-specific quality policy and guidance MPC. This is not a native PVS "
        "`depthHeadingAutopilot` validation and not physical-vehicle evidence.",
        "",
        "Timing audit boundary: the timing rows audit MPC solver wall time against "
        "known loop-period budgets only. They do not measure physical Jetson--AMD "
        "UDP latency, packet loss, or the real VxWorks receive/unpack timestamp.",
        "",
        "Timing audit:",
        "",
        "| budget | period ms | solver p95 max ms | solver max ms | exceed rate max | p95/period |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in timing:
        lines.append(
            "| {budget} | {period:.1f} | {p95:.3f} | {max_ms:.3f} | {exceed:.3f} | {frac:.3f} |".format(
                budget=item["timing_budget"],
                period=float(item["period_ms"]),
                p95=float(item["max_solver_p95_ms"]),
                max_ms=float(item["max_solver_max_ms"]),
                exceed=float(item["max_exceed_rate"]),
                frac=float(item["p95_period_fraction"]),
            )
        )
    lines.extend(
        [
        "",
        "Worst cases:",
        "",
        "| criterion | run | lateral p95 m | min clearance m | fallback | safety violation | progress % |",
        "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in worst:
        lines.append(
            "| {criterion} | {run} | {lat:.3f} | {clear:.3f} | {fallback:.3f} | {viol:.3f} | {progress:.1f} |".format(
                criterion=row["criterion"],
                run=row["run_id"],
                lat=float(row["lateral_p95_m"]),
                clear=float(row["seabed_clearance_min_m"]),
                fallback=float(row["fallback_rate"]),
                viol=float(row["safety_violation_rate"]),
                progress=float(row["progress_pct"]),
            )
        )
    interesting = [
        item
        for item in effects
        if item["metric"] in {"lateral_p95_m", "fallback_rate", "safety_violation_rate"}
        and math.isfinite(float(item["effect"]))
    ]
    interesting = sorted(
        interesting,
        key=lambda item: abs(float(item["effect"])),
        reverse=True,
    )[:12]
    lines.extend(
        [
            "",
            "Largest finite effects:",
            "",
            "| type | mode | metric | factor A | factor B | effect |",
            "|---|---|---|---|---|---:|",
        ]
    )
    for item in interesting:
        effect = float(item["effect"])
        lines.append(
            f"| {item['effect_type']} | {item['mpc_mode']} | "
            f"{item['metric']} | {item['factor_a']} | {item['factor_b']} | "
            f"{effect:.6g} |"
        )
    lines.append("")
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default="0,1")
    parser.add_argument("--mpc-modes", default="baseline,ua")
    parser.add_argument(
        "--factor-set",
        choices=["all", "full", "all_on", "smoke"],
        default="all",
        help="'all' and 'full' run the complete 2^4 matrix; 'all_on' runs only g1_t1_r1_c1.",
    )
    parser.add_argument(
        "--factor-labels",
        default="",
        help="Explicit labels such as g1_t1_r1_c1,g0_t0_r0_c0.",
    )
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--dt", type=float, default=0.5)
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--max-iter", type=int, default=60)
    parser.add_argument("--path-ds", type=float, default=0.25)
    parser.add_argument("--target-speed-mps", type=float, default=0.65)
    parser.add_argument("--minimum-reference-speed-mps", type=float, default=0.20)
    parser.add_argument("--target-altitude-m", type=float, default=3.0)
    parser.add_argument("--minimum-clearance-m", type=float, default=1.5)
    parser.add_argument("--initial-y-offset-m", type=float, default=1.0)
    parser.add_argument("--minimum-quality-speed-scale", type=float, default=0.35)
    parser.add_argument("--fallback-lookahead-m", type=float, default=4.0)
    parser.add_argument(
        "--terminal-policy",
        choices=["continue", "exit_at_end"],
        default="continue",
        help=(
            "'continue' preserves fixed-duration historical runs; 'exit_at_end' "
            "ends the mission when the finite reference path is reached."
        ),
    )
    parser.add_argument("--yaw-rate-gain", type=float, default=8.0)
    parser.add_argument("--ros-control-rate-hz", type=float, default=20.0)
    parser.add_argument("--bridge-command-rate-hz", type=float, default=10.0)
    parser.add_argument("--vxworks-main-rate-hz", type=float, default=10.0)
    parser.add_argument("--vxworks-net-recv-period-s", type=float, default=0.3)
    parser.add_argument("--noise-path", type=Path, default=DEFAULT_NOISE_PATH)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.dt <= 0.0:
        raise SystemExit("--dt must be positive")
    if args.duration <= 0.0:
        raise SystemExit("--duration must be positive")
    modes = parse_csv_list(args.mpc_modes)
    for mode in modes:
        if mode not in {"baseline", "ua"}:
            raise SystemExit(f"unsupported --mpc-modes entry {mode!r}")
    seeds = parse_int_list(args.seeds)
    factor_matrix = make_factor_matrix(args)
    noise_t, noise_rate_hz, _metadata = load_measured_noise(args.noise_path.resolve())
    stamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (
        REPO_ROOT / "results/control/r22_native_closed_loop" / stamp
    )
    initialize_bundle(
        output_dir,
        experiment_id=f"r22_native_closed_loop_{stamp}",
        runner="tools/run_native_cable_closed_loop.py",
        argv=sys.argv,
        data_layer="native_factor_simulation_proxy_closed_loop",
        matrix={
            "factor_order": FACTOR_NAMES,
            "factor_labels": [factor_label(item) for item in factor_matrix],
            "seeds": seeds,
            "mpc_modes": modes,
            "duration_s": args.duration,
            "dt_s": args.dt,
            "mpc_horizon_steps": args.horizon,
            "mpc_max_iter": args.max_iter,
            "mpc_prediction_horizon_s": args.horizon * args.dt,
            "terminal_policy": args.terminal_policy,
            "timing_audit": {
                "ros_control_rate_hz": args.ros_control_rate_hz,
                "bridge_command_rate_hz": args.bridge_command_rate_hz,
                "vxworks_main_rate_hz": args.vxworks_main_rate_hz,
                "vxworks_net_recv_period_s": args.vxworks_net_recv_period_s,
                "solver_only": True,
                "end_to_end_latency_claim": False,
            },
        },
        duration_s=args.duration,
        config_paths=[
            Path(__file__),
            REPO_ROOT / "algorithm/native_cable_scenario.py",
            REPO_ROOT / "algorithm/auv_mpc_controller.py",
            REPO_ROOT / "brain_linux/src/auv_control/auv_decision_ros/tracking_authority.py",
            REPO_ROOT / "brain_linux/src/auv_controller/auv_controller/quality_control_policy.py",
            args.noise_path,
        ],
        extra_manifest={
            "hardware_claim": False,
            "native_pvs_depth_heading_autopilot_claim": False,
            "truth_measurement_separation": True,
            "source_specific_quality_proxy": True,
            "timing_audit_solver_only": True,
            "physical_udp_latency_claim": False,
            "terminal_policy": args.terminal_policy,
        },
    )
    rows: list[dict[str, object]] = []
    total = len(factor_matrix) * len(seeds) * len(modes)
    index = 0
    for factors in factor_matrix:
        for seed in seeds:
            for mode in modes:
                index += 1
                run_id = f"{factor_label(factors)}__seed{seed}__{mode}"
                print(f"[r22-native] ({index}/{total}) {run_id}", flush=True)
                row = run_case(
                    factors=factors,
                    seed=seed,
                    mode=mode,
                    noise_t=noise_t,
                    noise_rate_hz=noise_rate_hz,
                    output_dir=output_dir,
                    args=args,
                )
                rows.append(row)
                print(
                    "[r22-native] finished {run_id} status={status} "
                    "lat_p95={lat:.3f} fallback={fallback:.3f}".format(
                        run_id=run_id,
                        status=row["status"],
                        lat=float(row["lateral_p95_m"]),
                        fallback=float(row["fallback_rate"]),
                    ),
                    flush=True,
                )

    effects = summarize_effects(rows)
    cells = summarize_cells(rows)
    worst = worst_cases(rows)
    timing = summarize_timing(rows, args)
    write_csv(output_dir / "native_closed_loop_metrics.csv", rows)
    write_csv(output_dir / "effect_summary.csv", effects)
    write_csv(output_dir / "cell_summary.csv", cells)
    write_csv(output_dir / "worst_cases.csv", worst)
    write_csv(output_dir / "timing_audit.csv", timing)
    if worst:
        plot_worst_path(output_dir, worst[0])
    finalize_bundle(output_dir, rows)
    write_report(output_dir, rows, effects, worst, timing)
    ok_count = sum(1 for row in rows if row.get("status") == "ok")
    print(
        f"[r22-native] done. {ok_count}/{len(rows)} ok. results -> {output_dir}",
        flush=True,
    )
    return 0 if ok_count == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
