#!/usr/bin/env python3
"""Native-PVS exit-side probe for three or four shallow crossings.

This isolates route following and actual spatial samples. It is not a ROS,
PC104, target-identity or hardware release test.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "AUV-Master-Mag/src"),
                str(ROOT / "brain_linux/src/auv_controller")]
from auv_mag_tracking.v2 import (  # noqa: E402
    CorridorSurveyConfig, FwhmConfig, InspectionConfig, ShallowZigzagConfig,
    SurveyProfile, build_shallow_zigzag_survey, estimate_survey_line,
)
from auv_controller.pid_controller import PIDController  # noqa: E402
from common.protocol import (  # noqa: E402
    KEY_BOTTOM, KEY_CONTROL_MODE_BYTE, KEY_LEFT, KEY_ORIENTATION_DEG,
    KEY_RIGHT, KEY_TARGET_DEPTH_M, KEY_THRUST, KEY_TOP,
    build_downlink_packet_from_payload, parse_downlink_packet,
)
from sim_holoocean.interfaces.pvs_sim_wrapper import PVSSimWrapper  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(seed: int, output_dir: Path, max_time_s: float = 2400.,
        lookahead_m: float = 25., case: str = "wire",
        current_speed_mps: float = 0., current_direction_deg: float = 0.,
        current_compensation: bool = False, start_side: int = -1,
        station_count: int = 4, amplitude_m: float = 27.) -> dict:
    if case not in {"wire", "intermediate", "no_source", "transient_middle",
                    "separated_neighbor", "fused_neighbor_1m"}:
        raise ValueError("unknown synthetic magnetic case")
    if (not math.isfinite(current_speed_mps) or current_speed_mps < 0
            or not math.isfinite(current_direction_deg)):
        raise ValueError("current must be finite and speed nonnegative")
    output_dir.mkdir(parents=True, exist_ok=True)
    policy = ShallowZigzagConfig(
        waypoint_spacing_m=.5, initial_lateral_sign=start_side,
        station_count=station_count, amplitude_m=amplitude_m,
    )
    survey_length_m = policy.station_count * policy.half_wavelength_m
    boundary_half_width_m = policy.amplitude_m + 18.
    boundary = np.array([[-10., -boundary_half_width_m],
                         [survey_length_m + 10., -boundary_half_width_m],
                         [survey_length_m + 10., boundary_half_width_m],
                         [-10., boundary_half_width_m]])
    plan = build_shallow_zigzag_survey(
        np.array([[0., 0.], [survey_length_m, 0.]]), boundary, policy)
    quality = CorridorSurveyConfig(
        half_width_m=policy.amplitude_m, station_spacing_m=policy.half_wavelength_m,
        station_count=policy.station_count,
        maximum_along_excursion_m=policy.half_wavelength_m + 2.,
    )
    params = yaml.safe_load((ROOT / "brain_linux/config/params.yaml").read_text())
    controller = PIDController(params["control"], params["limits"], params["mappers"])
    controller._pid.speed_ff_b = 40.
    plant = PVSSimWrapper(config={"simulation": {"dt": .05}, "pvs": {
        "control_mode": "depthHeadingAutopilot", "autonomy_motion_model": "native",
        "initial_depth_m": 10., "initial_heading_deg": 0.,
        "initial_speed_mps": .3, "initial_rpm": 0., "reference_rpm": 0.,
        "current_speed_mps": current_speed_mps,
        "current_direction_deg": current_direction_deg,
    }}, scenario_cfg={}, agent_name="auv").open()
    plant.eta[:2] = plan.waypoints_xy_m[0]
    rng = np.random.default_rng(seed)
    rows = []
    samples: list[list[tuple[np.ndarray, float]]] = [[] for _ in range(policy.station_count)]
    previous_x = None
    previous_nav_xy = None
    estimated_disturbance_xy = np.zeros(2)
    phase = "survey"
    try:
        for index in range(round(max_time_s / .25)):
            t = index * .25
            x, y = map(float, plant.eta[:2])
            heading = math.degrees(float(plant.eta[5]))
            speed = float(plant.nu[0])
            if previous_nav_xy is not None and current_compensation:
                ground_velocity = (np.array([x, y]) - previous_nav_xy) / .25
                heading_rad = math.radians(heading)
                forward = speed * np.array([math.cos(heading_rad), math.sin(heading_rad)])
                estimated_disturbance_xy = (.95 * estimated_disturbance_xy
                                            + .05 * (ground_velocity - forward))
            previous_nav_xy = np.array([x, y])
            reference_y = float(np.interp(np.clip(x, 0., survey_length_m), plan.waypoints_xy_m[:, 0],
                                          plan.waypoints_xy_m[:, 1]))
            target_y = 6. + .02 * x
            anomaly_center_y = (-5. + .02 * x if case == "transient_middle"
                                and policy.half_wavelength_m <= x < 2. * policy.half_wavelength_m else target_y)
            exponent = .7 if case == "intermediate" else .5
            envelope = (2. if case == "no_source" else
                        2. + 20. / (1. + ((y - anomaly_center_y) / 3.) ** 2) ** exponent)
            if case in {"separated_neighbor", "fused_neighbor_1m"}:
                separation = 7. if case == "separated_neighbor" else 1.
                envelope += 20. / np.sqrt(1. + ((y - target_y - separation) / 3.) ** 2)
            envelope += rng.normal(0., .02)
            if phase == "survey" and index % 4 == 0 and 0. <= x <= survey_length_m:
                station = min(int(x // policy.half_wavelength_m), policy.station_count - 1)
                samples[station].append((np.array([x, y]), envelope))
            if not np.isfinite([*plant.eta, *plant.nu, *plant.u_actual]).all():
                phase = "nonfinite_plant_state"
            if phase == "survey" and (abs(y) >= boundary_half_width_m - 5.
                                       or x < -5. or x > survey_length_m + 5.):
                phase = "boundary_margin_exhausted"
            if phase == "survey" and x >= survey_length_m:
                phase = "survey_path_end"
            if phase == "survey":
                look_x = float(np.clip(x + lookahead_m, 0., survey_length_m))
                look_y = float(np.interp(look_x, plan.waypoints_xy_m[:, 0],
                                         plan.waypoints_xy_m[:, 1]))
                ground_direction = np.array([max(look_x - x, .1), look_y - y])
                ground_direction /= np.linalg.norm(ground_direction)
                throughwater = (policy.velocity_mps * ground_direction
                                - estimated_disturbance_xy)
                desired_heading = math.degrees(math.atan2(throughwater[1], throughwater[0]))
                target_speed = policy.velocity_mps
            else:
                desired_heading, target_speed = heading, 0.
            state = {"x": x, "y": y, "z": -float(plant.eta[2]), "u": speed,
                     "v": float(plant.nu[1]), "w": float(plant.nu[2]),
                     "roll": float(plant.eta[3]), "pitch": float(plant.eta[4]),
                     "yaw": float(plant.eta[5]), "p": float(plant.nu[3]),
                     "q": float(plant.nu[4]), "r": float(plant.nu[5]),
                     "depth": float(plant.eta[2])}
            thrust = (controller.compute(state, {
                "target_speed_mps": target_speed,
                "target_heading_rad": math.radians(desired_heading),
                "target_depth_m": 10., "dt": .25,
            }).thrust_percent if target_speed > 0 else 0.)
            packet = build_downlink_packet_from_payload({
                KEY_CONTROL_MODE_BYTE: 238,
                KEY_ORIENTATION_DEG: desired_heading % 360.,
                KEY_TARGET_DEPTH_M: 10., KEY_THRUST: thrust,
                KEY_RIGHT: 0., KEY_LEFT: 0., KEY_TOP: 0., KEY_BOTTOM: 0.,
            }, main_motor_rpm_scale=15.)
            decoded = parse_downlink_packet(packet, main_motor_rpm_scale=15.)
            heading_ref = heading + (decoded.orientation_deg - heading + 180.) % 360. - 180.
            plant.set_reference(depth_m=decoded.target_depth_m,
                                heading_rad=math.radians(heading_ref),
                                propeller_rpm=max(0., decoded.main_motor_rpm))
            for _ in range(5):
                plant.step([0, 0, 0, 0, 0])
            rows.append({"time_s": t, "x_m": x, "y_m": y, "reference_y_m": reference_y,
                         "target_cable_y_m": target_y, "heading_deg": heading,
                         "heading_target_deg": desired_heading, "speed_mps": speed,
                         "rpm": decoded.main_motor_rpm, "phase": phase,
                         "magnetic_envelope_nt": envelope,
                         "estimated_disturbance_x_mps": estimated_disturbance_xy[0],
                         "estimated_disturbance_y_mps": estimated_disturbance_xy[1]})
            if phase != "survey":
                break
            if previous_x is not None and x < previous_x - .5:
                phase = "progress_reversed"
            previous_x = x
    finally:
        plant.close()
    csv_path = output_dir / "trajectory.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    profiles = [SurveyProfile(idx, np.asarray([point for point, _ in data], dtype=float),
                              np.asarray([value for _, value in data], dtype=float), .02)
                for idx, data in enumerate(samples)]
    estimate = estimate_survey_line(plan, profiles, quality,
                                    FwhmConfig(shape_model="thesis_dipole", altitude_m=0.),
                                    InspectionConfig(enabled=True))
    reference_error = [abs(row["y_m"] - row["reference_y_m"]) for row in rows if row["phase"] == "survey"]
    center_error = (None if not estimate.geometry_valid else float(np.mean(np.abs(
        estimate.station_centers_xy_m[:, 1] - (6. + .02 * estimate.station_centers_xy_m[:, 0])))))
    end_x, end_y = rows[-1]["x_m"], rows[-1]["y_m"]
    target_at_end_m = 6. + .02 * end_x
    exit_error_m = abs(end_y - target_at_end_m)
    summary = {
        "evidence_level": "native_pvs_protocol_encoded_geometry_probe",
        "not_ros_or_pc104_or_field_acceptance": True,
        "case": case, "current_speed_mps": current_speed_mps,
        "current_direction_deg": current_direction_deg,
        "start_side": start_side,
        "current_compensation": current_compensation,
        "final_estimated_disturbance_xy_mps": estimated_disturbance_xy.tolist(),
        "seed": seed, "terminal_phase": phase, "elapsed_s": rows[-1]["time_s"],
        "planned_distance_m": plan.estimated_distance_m,
        "survey_length_m": survey_length_m,
        "amplitude_m": policy.amplitude_m,
        "half_wavelength_m": policy.half_wavelength_m,
        "station_count": policy.station_count,
        "navigation_lateral_margin_m": policy.navigation_lateral_margin_m,
        "last_xy_m": [rows[-1]["x_m"], rows[-1]["y_m"]],
        "truth_target_at_survey_end_y_m": target_at_end_m,
        "survey_exit_truth_lateral_error_m": exit_error_m,
        "minimum_rejoin_distance_at_10deg_m": exit_error_m / math.tan(math.radians(10.)),
        "reference_track_mae_m": float(np.mean(reference_error)) if reference_error else None,
        "reference_track_max_m": float(np.max(reference_error)) if reference_error else None,
        "profile_sample_counts": [len(item) for item in samples],
        "geometry_valid": estimate.geometry_valid,
        "geometry_reason_codes": estimate.reason_codes,
        "center_mae_m": center_error,
        "heading_deviation_deg": estimate.heading_deviation_deg,
        "burial_depth_m": estimate.burial_depth_m,
        "trajectory_sha256": sha(csv_path),
        "source_sha256": {str(path.relative_to(ROOT)): sha(path) for path in (
            Path(__file__).resolve(),
            ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/corridor_survey.py",
            ROOT / "brain_linux/src/auv_controller/auv_controller/pid_controller.py",
            ROOT / "sim_holoocean/interfaces/pvs_sim_wrapper.py")},
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--max-time-s", type=float, default=2400.)
    parser.add_argument("--lookahead-m", type=float, default=25.)
    parser.add_argument("--case", choices=("wire", "intermediate", "no_source",
                                           "transient_middle", "separated_neighbor",
                                           "fused_neighbor_1m"), default="wire")
    parser.add_argument("--current-speed-mps", type=float, default=0.)
    parser.add_argument("--current-direction-deg", type=float, default=0.)
    parser.add_argument("--current-compensation", action="store_true")
    parser.add_argument("--start-side", type=int, choices=(-1, 1), default=-1)
    parser.add_argument("--station-count", type=int, default=4)
    parser.add_argument("--amplitude-m", type=float, default=27.)
    parser.add_argument("--output-dir", type=Path, default=ROOT /
                        "AUV-Master-Mag/results/v2/shallow_zigzag_exit_parity_20260927")
    args = parser.parse_args()
    print(json.dumps(run(args.seed, args.output_dir, args.max_time_s,
                         args.lookahead_m, args.case,
                         args.current_speed_mps, args.current_direction_deg,
                         args.current_compensation, args.start_side,
                         args.station_count, args.amplitude_m),
                     ensure_ascii=False))
