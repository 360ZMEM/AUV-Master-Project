#!/usr/bin/env python3
"""Synthetic ROS -> PID -> 72-byte protocol -> native PVS shallow survey.

The sonar line and crosscurrent message are explicit truth fixtures. No PC104
or physical sensor is connected. A dedicated ROS_DOMAIN_ID is required.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "AUV-Master-Mag/src"),
                str(ROOT / "brain_linux/src/auv_control"),
                str(ROOT / "brain_linux/src/auv_controller"),
                str(ROOT / "brain_linux/src/auv_cable_tracking_v2")]

import numpy as np
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from nav_msgs.msg import Odometry
from sensor_msgs.msg import MagneticField
from std_msgs.msg import Bool, Float32MultiArray, String
from rosgraph_msgs.msg import Clock
from auv_interfaces.msg import ArbiterStatus, MpcCmd, PerceptionQuality, Setpoint, SonarCableObservation
from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
from auv_cable_tracking_v2.inspection_controller_node import InspectionControllerNode
from common.protocol import (
    KEY_BOTTOM, KEY_CONTROL_MODE_BYTE, KEY_LEFT, KEY_ORIENTATION_DEG,
    KEY_RIGHT, KEY_TARGET_DEPTH_M, KEY_THRUST, KEY_TOP,
    build_downlink_packet_from_payload, parse_downlink_packet,
)
from sim_holoocean.interfaces.pvs_sim_wrapper import PVSSimWrapper


def run(case: str, seed: int, output_dir: Path, *, current_y_mps: float = .04,
        maximum_time_s: float = 2800., post_hold_s: float = 15.,
        with_bridge: bool = False) -> dict:
    if case not in {"wire", "fused_neighbor", "identity_dropout", "no_source"}:
        raise ValueError("unknown case")
    if not .02 <= abs(current_y_mps) <= .05:
        raise ValueError("current magnitude outside synthetic candidate")
    if os.environ.get("ROS_LOCALHOST_ONLY") != "1" or not os.environ.get("ROS_DOMAIN_ID"):
        raise RuntimeError("set ROS_LOCALHOST_ONLY=1 and isolated ROS_DOMAIN_ID")
    bridge = None
    sink = None
    if with_bridge:
        import yaml
        from auv_cable_tracking_v2.inspection_bridge_node import InspectionBridgeNode
        from common.enums import ControlModeByte
        from common.protocol import KEY_TOTAL_VOLTAGE_V
        output_dir.mkdir(parents=True, exist_ok=True)
        data_root = output_dir / "bridge_data"
        data_root.mkdir(exist_ok=True)
        os.environ["AUV_DATA_ROOT"] = str(data_root)
        sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sink.bind(("127.0.0.1", 0))
        sink.settimeout(1.)
        bridge_params = yaml.safe_load((ROOT /
            "brain_linux/src/auv_cable_tracking_v2/config/inspection_bridge_passive.yaml").read_text())
        bridge_params["bridge"]["protocol_udp"]["remote_port"] = sink.getsockname()[1]
        bridge_config = output_dir / "bridge_loopback_params.yaml"
        bridge_config.write_text(yaml.safe_dump(bridge_params), encoding="utf-8")
    config = ROOT / "brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_shallow_survey_sim.yaml"
    provenance_paths = [
        Path(__file__).resolve(),
        ROOT / "AUV-Master-Mag/src/auv_mag_tracking/v2/shallow_survey.py",
        ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py",
        ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/hold_budget.py",
        ROOT / "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_controller_node.py",
        ROOT / "sim_holoocean/interfaces/pvs_sim_wrapper.py", config,
    ]
    if with_bridge:
        provenance_paths.append(ROOT /
            "brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_bridge_node.py")
    source_sha256_at_start = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in provenance_paths
    }
    ros_args = ["--ros-args", "-p", f"config_file:={config}",
                "-p", "use_sim_time:=true", "-p", "publish_arbiter_command:=true",
                "-p", "inspection_speed_feedforward_b:=40.0"]
    if with_bridge:
        ros_args += ["-p", f"auv_inspection_bridge_node:params_file:={bridge_config}",
                     "-p", "auv_inspection_bridge_node:passive_mode:=false",
                     "-p", "auv_inspection_bridge_node:bridge_backend:=protocol_udp"]
    rclpy.init(args=ros_args)
    decision = CableTrackingV2Node()
    controller = InspectionControllerNode()
    if with_bridge:
        bridge = InspectionBridgeNode()
        bridge._command_keepalive_timer.cancel()
    peer = Node("shallow_survey_pvs_audit_peer")
    decision.timer.cancel()
    controller._control_timer.cancel()
    executor = SingleThreadedExecutor()
    for node in (decision, controller, peer, bridge):
        if node is None:
            continue
        executor.add_node(node)
    commands, tracking, efforts, depths = [], [], [], []
    peer.create_subscription(Setpoint, "/auv/control/setpoint", commands.append, 10)
    peer.create_subscription(String, "/auv/cable/tracking", lambda msg: tracking.append(json.loads(msg.data)), 10)
    peer.create_subscription(MpcCmd, "/auv/control/mpc_cmd", efforts.append, 10)
    peer.create_subscription(Bool, "/auv/cable/depth_valid", lambda msg: depths.append(msg.data), 10)
    mission_pub = peer.create_publisher(String, "/auv/cable/mission_command", 10)
    arbiter_pub = (None if with_bridge else
                   peer.create_publisher(ArbiterStatus, "/auv/arbiter/status", 10))
    clock_pub = peer.create_publisher(Clock, "/clock", 10)
    odom_pub = peer.create_publisher(Odometry, "/auv/state/filtered", 10)
    mag_pub = peer.create_publisher(MagneticField, "/auv/sensors/magnetic", 10)
    covariance_pub = peer.create_publisher(Float32MultiArray, "/auv/state/covariance", 10)
    current_pub = peer.create_publisher(String, "/auv/state/cross_current_evidence", 10)
    sonar_pub = peer.create_publisher(SonarCableObservation, "/auv/sensors/cable_sonar_observation", 10)
    quality_pub = peer.create_publisher(PerceptionQuality, "/auv/perception/quality/sonar", 10)

    def wait_for(predicate, timeout_s=10.):
        deadline = time.monotonic() + timeout_s
        while not predicate():
            if bridge is not None:
                bridge.latest_protocol_telemetry_ts = time.time()
            if time.monotonic() >= deadline:
                raise AssertionError("ROS DDS delivery timeout")
            executor.spin_once(timeout_sec=.005)

    core = decision.pipeline.core
    start_side = -1 if current_y_mps > 0 else 1
    amplitude = 24. if start_side < 0 else 27.
    plant = PVSSimWrapper(config={"simulation": {"dt": .05}, "pvs": {
        "control_mode": "depthHeadingAutopilot", "autonomy_motion_model": "native",
        "initial_depth_m": 10., "initial_heading_deg": 0.,
        "initial_speed_mps": .3, "initial_rpm": 0., "reference_rpm": 0.,
        "current_speed_mps": abs(current_y_mps),
        "current_direction_deg": 90. if current_y_mps > 0 else 270.,
    }}, scenario_cfg={}, agent_name="auv").open()
    plant.eta[:2] = [0., start_side * amplitude]
    rng = np.random.default_rng(seed)
    rows = []
    first_hold_t = None
    first_hold_xy = None
    track_start_x = None
    zero_after_hold = 0
    try:
        wait_for(lambda: mission_pub.get_subscription_count() > 0 and clock_pub.get_subscription_count() >= 2)
        mission_pub.publish(String(data=json.dumps({
            "mission_type": "CABLE_INSPECTION", "target_depth": 10., "target_speed_mps": .3,
        })))
        wait_for(lambda: decision.latest_mission is not None)
        if bridge is None:
            wait_for(lambda: arbiter_pub.get_subscription_count() >= 2)
            arbiter = ArbiterStatus()
            arbiter.active_arbiter, arbiter.autonomy_allowed = "AUTONOMOUS", True
            arbiter_pub.publish(arbiter)
            wait_for(lambda: controller.latest_arbiter_status is not None)
        else:
            bridge.latest_sensor_status_payload.update(confidence=1., leak_level=0)
            bridge.latest_bridge_telemetry_payload = {KEY_TOTAL_VOLTAGE_V: 50.}
            bridge.latest_protocol_telemetry_ts = time.time()
            pc = {KEY_CONTROL_MODE_BYTE: int(ControlModeByte.JETSON_PROTOCOL),
                  "work_instruction": 0, KEY_THRUST: 0., KEY_RIGHT: 0.,
                  KEY_TOP: 0., KEY_LEFT: 0., KEY_BOTTOM: 0.}
            bridge.handle_pc_raw_command(pc)
            wait_for(lambda: controller.latest_arbiter_status is not None
                     and controller.latest_arbiter_status.autonomy_allowed)
        for index in range(round(maximum_time_s / .25)):
            t = 1. + index * .25
            clock = Clock()
            clock.clock.sec = int(t)
            clock.clock.nanosec = int(round((t - int(t)) * 1e9))
            clock_pub.publish(clock)
            wait_for(lambda: decision.get_clock().now().nanoseconds >= round(t * 1e9))
            x, y = map(float, plant.eta[:2])
            heading = float(plant.eta[5])
            speed = float(plant.nu[0])
            target_y = 5.5 + .02 * x
            anomaly = (0. if case == "no_source" else
                       20. / np.sqrt(1. + ((y - target_y) / 3.) ** 2))
            if case == "fused_neighbor":
                anomaly += 20. / np.sqrt(1. + ((y - target_y - 1.) / 3.) ** 2)
            envelope = 2. + anomaly + rng.normal(0., .02)
            odom = Odometry()
            odom.header.stamp = clock.clock
            odom.header.frame_id = "world"
            odom.pose.pose.position.x, odom.pose.pose.position.y = x, y
            odom.pose.pose.position.z = -float(plant.eta[2])
            odom.pose.pose.orientation.z = math.sin(heading / 2.)
            odom.pose.pose.orientation.w = math.cos(heading / 2.)
            sway = float(plant.nu[1])
            odom.twist.twist.linear.x = speed * math.cos(heading) - sway * math.sin(heading)
            odom.twist.twist.linear.y = speed * math.sin(heading) + sway * math.cos(heading)
            odom.twist.twist.linear.z = float(plant.nu[2])
            mag = MagneticField()
            mag.header.stamp = clock.clock
            mag.magnetic_field.x = envelope * 1e-9
            previous_odom, previous_mag = decision.latest_odom_wall_time_s, decision.latest_magnetic_wall_time_s
            odom_pub.publish(odom)
            mag_pub.publish(mag)
            wait_for(lambda: decision.latest_odom_wall_time_s > previous_odom
                     and decision.latest_magnetic_wall_time_s > previous_mag)
            covariance = np.eye(15) * .0004
            covariance[0, 0] = covariance[1, 1] = .01
            covariance[8, 8] = math.radians(.2) ** 2
            old_covariance = decision._latest_nav_uncertainty_wall_time_s
            covariance_pub.publish(Float32MultiArray(data=covariance.reshape(-1).tolist()))
            wait_for(lambda: decision._latest_nav_uncertainty_wall_time_s > old_covariance)
            old_current = core._survey_current_evidence
            current_pub.publish(String(data=json.dumps({
                "time_s": t, "velocity_xy_mps": [0., current_y_mps],
                "sigma_mps": .004, "source": "synthetic_current_fixture", "frame": "world",
            })))
            wait_for(lambda: core._survey_current_evidence is not old_current)
            dropout = (case == "identity_dropout" and core._survey_phase == "track"
                       and track_start_x is not None and x >= track_start_x + 8.)
            if not dropout:
                line_heading = math.atan(.02) - heading
                cross_track = (target_y - y) / math.sqrt(1. + .02 ** 2)
                tangent = np.array([math.cos(line_heading), math.sin(line_heading)])
                normal = np.array([-tangent[1], tangent[0]])
                points = cross_track * normal + np.linspace(-4., 4., 20)[:, None] * tangent
                sonar = SonarCableObservation()
                sonar.header.stamp = clock.clock
                sonar.header.frame_id = "sonar_link"
                sonar.valid = True
                sonar.detector_id = "synthetic_identity_fixture"
                sonar.point_x_m = points[:, 0].tolist()
                sonar.point_y_m = points[:, 1].tolist()
                sonar.point_weight = [1.] * 20
                quality = PerceptionQuality()
                quality.header = sonar.header
                quality.source = "sonar_cable"
                quality.validity = PerceptionQuality.VALIDITY_VALID
                quality.p_track = .99
                quality.track_probability_calibrated = True
                quality.estimate = [cross_track, line_heading, float("nan")]
                quality.covariance = [.0025, 0., 0., 0., .000001, 0., 0., 0., float("nan")]
                quality.sample_count = 20
                quality.data_completeness = 1.
                quality.calibration_id = "synthetic_identity_fixture_20260927"
                sonar_pub.publish(sonar)
                quality_pub.publish(quality)
                wait_for(lambda: decision._latest_sonar_observation is not None
                         and decision._latest_sonar_quality is not None
                         and decision._latest_sonar_observation.header.stamp == clock.clock
                         and decision._latest_sonar_quality.header.stamp == clock.clock)
            n_command, n_track, n_depth = len(commands), len(tracking), len(depths)
            decision._on_tick()
            wait_for(lambda: len(commands) > n_command and len(tracking) > n_track
                     and len(depths) > n_depth)
            command, result = commands[-1], tracking[-1]
            wait_for(lambda: controller.latest_setpoint is not None
                     and controller.latest_setpoint.header.stamp == command.header.stamp
                     and controller.latest_filtered_state is not None
                     and controller.latest_filtered_state.header.stamp == odom.header.stamp)
            n_effort = len(efforts)
            if bridge is not None:
                bridge.latest_protocol_telemetry_ts = time.time()
                bridge.handle_pc_raw_command(pc)
                sink.setblocking(False)
                try:
                    while True:
                        sink.recvfrom(2048)
                except BlockingIOError:
                    pass
                sink.settimeout(1.)
            controller._on_timer()
            wait_for(lambda: len(efforts) > n_effort)
            effort = efforts[-1]
            if bridge is None:
                payload = {KEY_CONTROL_MODE_BYTE: 238,
                           KEY_ORIENTATION_DEG: math.degrees(command.target_heading_rad) % 360.,
                           KEY_TARGET_DEPTH_M: command.target_depth_m,
                           KEY_THRUST: effort.thrust_percent,
                           KEY_RIGHT: effort.right_fin_deg, KEY_LEFT: effort.left_fin_deg,
                           KEY_TOP: effort.top_fin_deg, KEY_BOTTOM: effort.bottom_fin_deg}
                packet = build_downlink_packet_from_payload(payload, main_motor_rpm_scale=15.)
            else:
                wait_for(lambda: bridge.command_arbiter._last_mpc_ts is not None
                         and abs(bridge.command_arbiter._last_mpc_ts - t) < .01)
                packet, _ = sink.recvfrom(2048)
            decoded = parse_downlink_packet(packet, main_motor_rpm_scale=15.)
            if len(packet) != 72 or result.get("burial_depth_m") is not None or depths[-1]:
                raise AssertionError("packet/depth contract violated")
            if not np.isfinite([command.target_speed_mps, command.target_heading_rad,
                                effort.thrust_percent, decoded.main_motor_rpm]).all():
                raise AssertionError("nonfinite control output")
            if bridge is not None and decoded.main_motor_rpm != round(effort.thrust_percent * 15):
                raise AssertionError("guard UDP packet differs from PID effort")
            bridge_source = (None if bridge is None else
                             bridge.last_arbiter_decision.arbiter_source.value)
            if (bridge is not None and decoded.main_motor_rpm > 0
                    and bridge_source != "JETSON_MPC"):
                raise AssertionError("nonzero packet did not come from admitted Jetson PID")
            if result["mode"] == "hold" and first_hold_t is None:
                first_hold_t, first_hold_xy = t, np.array([x, y])
            if first_hold_t is not None:
                if command.target_speed_mps != 0. or effort.thrust_percent != 0. or decoded.main_motor_rpm != 0:
                    raise AssertionError("Hold did not maintain zero command")
                zero_after_hold += 1
            heading_deg = math.degrees(heading)
            heading_ref = heading_deg + (decoded.orientation_deg - heading_deg + 180.) % 360. - 180.
            plant.set_reference(depth_m=decoded.target_depth_m,
                                heading_rad=math.radians(heading_ref),
                                propeller_rpm=max(0., decoded.main_motor_rpm))
            for _ in range(5):
                plant.step([0, 0, 0, 0, 0])
            if not np.isfinite([*plant.eta, *plant.nu, *plant.u_actual]).all():
                raise AssertionError("nonfinite native PVS state")
            if core._survey_phase == "track" and track_start_x is None:
                track_start_x = x
            survey_ref_y = float(np.interp(
                np.clip(x, 0., core._survey_policy.station_count * core.survey_config.half_wavelength_m),
                core._survey_plan.waypoints_xy_m[:, 0], core._survey_plan.waypoints_xy_m[:, 1]))
            rows.append({"time_s": t, "x_m": x, "y_m": y, "target_y_m": target_y,
                         "survey_reference_y_m": survey_ref_y,
                         "heading_deg": math.degrees(heading),
                         "command_heading_deg": math.degrees(command.target_heading_rad),
                         "phase": core._survey_phase, "mode": result["mode"],
                         "reason": result["diagnostics"].get("continuity_reason"),
                         "identity_reason": decision._latest_identity_reason,
                         "command_speed_mps": command.target_speed_mps,
                         "thrust_percent": effort.thrust_percent,
                         "udp_rpm": decoded.main_motor_rpm,
                         "bridge_arbiter_source": bridge_source,
                         "depth_valid": bool(depths[-1]),
                         "route_budget_state": (result["diagnostics"].get("hold_budget") or {}).get("state"),
                         "route_admitted": (result["diagnostics"].get("route_hold_admission") or {}).get("admitted")})
            if result["mode"] == "complete":
                break
            if first_hold_t is not None and t >= first_hold_t + post_hold_s:
                break
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"{case}_{'positive' if current_y_mps > 0 else 'negative'}_seed{seed}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        trajectory_sha256 = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        track_rows = [row for row in rows if row["phase"] == "track"]
        summary = {"evidence_level": "ros_pid_protocol_native_pvs_synthetic_current_and_sonar",
                   "case": case, "seed": seed, "current_y_mps": current_y_mps,
                   "terminal_mode": rows[-1]["mode"], "terminal_phase": rows[-1]["phase"],
                   "terminal_reason": rows[-1]["reason"], "duration_s": rows[-1]["time_s"],
                   "ticks": len(rows), "survey_station_count": None if core._survey_policy is None else core._survey_policy.station_count,
                   "geometry_valid": None if core._survey_estimate is None else core._survey_estimate.geometry_valid,
                   "track_samples": len(track_rows),
                   "track_truth_lateral_mae_m": None if not track_rows else float(np.mean([
                       abs(row["y_m"] - row["target_y_m"]) for row in track_rows])),
                   "route_hold_admitted": None if decision._route_hold_admission_result is None else
                       decision._route_hold_admission_result["admitted"],
                   "hold_zero_ticks": zero_after_hold,
                   "hold_to_final_displacement_m": None if first_hold_xy is None else
                       float(np.linalg.norm(plant.eta[:2] - first_hold_xy)),
                   "bridge_arbiter_sources": (None if bridge is None else
                       sorted({row["bridge_arbiter_source"] for row in rows})),
                   "trajectory_sha256": trajectory_sha256,
                   "source_sha256_at_start": source_sha256_at_start,
                   "identity_source": "synthetic_truth_line_fixture_not_physical_sonar",
                   "current_source": "synthetic_current_fixture_not_measured",
                   "burial_depth_published": any(row["depth_valid"] for row in rows),
                   "native_pvs": True, "ros_dds": True, "protocol_encoded": True,
                   "guard_connected": with_bridge, "pc104_or_field_connected": False,
                   "trajectory_file": str(csv_path)}
        (output_dir / (csv_path.stem + "_summary.json")).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return summary
    finally:
        plant.close()
        for node in (decision, controller, peer, bridge):
            if node is None:
                continue
            executor.remove_node(node)
            node.destroy_node()
        executor.shutdown()
        rclpy.shutdown()
        if sink is not None:
            sink.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("wire", "fused_neighbor", "identity_dropout", "no_source"),
                        default="wire")
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--current-y-mps", type=float, default=.04)
    parser.add_argument("--maximum-time-s", type=float, default=2800.)
    parser.add_argument("--post-hold-s", type=float, default=15.)
    parser.add_argument("--with-bridge", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT /
                        "AUV-Master-Mag/results/v2/shallow_survey_ros_pvs_20260927")
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.seed, args.output_dir,
                         current_y_mps=args.current_y_mps,
                         maximum_time_s=args.maximum_time_s,
                         post_hold_s=args.post_hold_s,
                         with_bridge=args.with_bridge), ensure_ascii=False, indent=2))
