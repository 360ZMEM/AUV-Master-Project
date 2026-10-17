#!/usr/bin/env python3
"""Isolated ROS inspection + PID + packet codec + native PVS flythrough loop.

Requires an installed ROS Humble workspace and ROS_LOCALHOST_ONLY=1 with a
dedicated ROS_DOMAIN_ID. --with-bridge adds the real guard/UDP bridge to a
local socket. Physical PC104 is never connected.
"""
from __future__ import annotations

import argparse
import cProfile
import csv
import io
import json
import math
import os
from pathlib import Path
import pstats
import socket
import sys
import time
from threading import Event, Lock, Thread

ROOT = Path(__file__).resolve().parents[1]
INSTALLED_V2_NODE = os.environ.get('AUV_V2_HARNESS_INSTALLED_NODE') == '1'
source_paths = [str(ROOT), str(ROOT / 'AUV-Master-Mag/src'),
                str(ROOT / 'brain_linux/src/auv_control'),
                str(ROOT / 'brain_linux/src/auv_controller')]
if not INSTALLED_V2_NODE:
    source_paths.append(str(ROOT / 'brain_linux/src/auv_cable_tracking_v2'))
sys.path[:0] = source_paths

import numpy as np
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from nav_msgs.msg import Odometry
from sensor_msgs.msg import MagneticField
from std_msgs.msg import Bool, Float32MultiArray, String
from rosgraph_msgs.msg import Clock
from auv_interfaces.msg import (ArbiterStatus, MpcCmd, PerceptionQuality,
                                Setpoint, SonarCableObservation)
from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
import auv_cable_tracking_v2.cable_tracking_v2_node as v2_node_module
from auv_cable_tracking_v2.inspection_controller_node import InspectionControllerNode
from common.protocol import (KEY_BOTTOM, KEY_CONTROL_MODE_BYTE, KEY_LEFT,
                             KEY_ORIENTATION_DEG, KEY_RIGHT, KEY_TARGET_DEPTH_M,
                             KEY_THRUST, KEY_TOP,
                             build_downlink_packet_from_payload, parse_downlink_packet)
from sim_holoocean.interfaces.pvs_sim_wrapper import PVSSimWrapper


def run(case: str, seed: int, output_dir: Path, max_time_s: float = 1600.,
        *, current_speed_mps: float = 0., current_direction_deg: float = 0.,
        cable_lateral_m: float = 6., config_file: Path | None = None,
        with_bridge: bool = False, nav_position_noise_std_m: float = 0.,
        nav_speed_bias_mps: float = 0., nav_heading_bias_deg: float = 0.,
        ground_velocity_from_position: bool = False,
        primary_cable_gain_nt: float = 20.,
        secondary_cable_lateral_m: float | None = None,
        secondary_cable_gain_nt: float = 0.,
        sonar_identity_mode: str = 'off',
        sonar_line_lateral_m: float | None = None,
        sonar_track_fault: str = 'none',
        sonar_track_switch_offset_m: float = 3.,
        sonar_track_position_variance_m2: float | None = None,
        inspection_current_step_mps: float | None = None,
        inspection_current_step_direction_deg: float = 90.,
        post_hold_coast_s: float = 0.,
        retransmit_mission_on_hold: bool = False,
        record_source_wall_map: bool = False) -> dict:
    if case not in {'wire', 'dipole', 'no_source', 'wire_magnetic_dropout',
                    'wire_navigation_dropout',
                    'wire_magnetic_persistent', 'wire_manual_cancel',
                    'wire_guard_telemetry_loss'}:
        raise ValueError(case)
    if case in {'wire_manual_cancel', 'wire_guard_telemetry_loss'} and not with_bridge:
        raise ValueError('guard intervention requires --with-bridge')
    if not math.isfinite(current_speed_mps) or current_speed_mps < 0 or not math.isfinite(current_direction_deg):
        raise ValueError('current parameters must be finite and speed nonnegative')
    if not math.isfinite(cable_lateral_m):
        raise ValueError('cable lateral offset must be finite')
    if not math.isfinite(primary_cable_gain_nt) or primary_cable_gain_nt < 0.:
        raise ValueError('primary cable gain must be finite and nonnegative')
    if (not math.isfinite(secondary_cable_gain_nt) or secondary_cable_gain_nt < 0.
            or (secondary_cable_gain_nt > 0. and
                (secondary_cable_lateral_m is None or not math.isfinite(secondary_cable_lateral_m)))):
        raise ValueError('secondary cable gain needs a finite lateral offset')
    if (not math.isfinite(nav_position_noise_std_m) or nav_position_noise_std_m < 0.
            or not math.isfinite(nav_speed_bias_mps)
            or not math.isfinite(nav_heading_bias_deg)):
        raise ValueError('navigation perturbations must be finite; position noise must be nonnegative')
    if sonar_identity_mode not in {'off', 'target', 'missing', 'uncalibrated', 'wrong_line', 'fixed_line'}:
        raise ValueError('unknown sonar identity fixture mode')
    if sonar_identity_mode == 'fixed_line' and (
            sonar_line_lateral_m is None or not math.isfinite(sonar_line_lateral_m)):
        raise ValueError('fixed_line sonar fixture requires a finite line lateral position')
    if sonar_track_fault not in {'none', 'dropout', 'switch'}:
        raise ValueError('unknown sonar track fault')
    if sonar_track_fault != 'none' and sonar_identity_mode != 'target':
        raise ValueError('sonar track fault requires target identity fixture')
    if not math.isfinite(sonar_track_switch_offset_m):
        raise ValueError('sonar track switch offset must be finite')
    if sonar_track_position_variance_m2 is not None and (
            sonar_track_fault == 'none'
            or not math.isfinite(sonar_track_position_variance_m2)
            or sonar_track_position_variance_m2 <= 0.):
        raise ValueError('sonar track position variance requires a positive fault fixture')
    if inspection_current_step_mps is not None and (
            not math.isfinite(inspection_current_step_mps)
            or inspection_current_step_mps < 0.
            or not math.isfinite(inspection_current_step_direction_deg)):
        raise ValueError('inspection current step must be finite and nonnegative')
    if not math.isfinite(post_hold_coast_s) or post_hold_coast_s < 0.:
        raise ValueError('post-hold observation time must be finite and nonnegative')
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        raise RuntimeError('set ROS_LOCALHOST_ONLY=1 and an isolated ROS_DOMAIN_ID')
    sink = None
    bridge = None
    bridge_config = None
    if with_bridge:
        import yaml
        from auv_cable_tracking_v2.inspection_bridge_node import InspectionBridgeNode
        from common.enums import ControlModeByte
        from common.protocol import KEY_TOTAL_VOLTAGE_V
        output_dir.mkdir(parents=True, exist_ok=True)
        data_root = output_dir / 'bridge_data'
        data_root.mkdir(exist_ok=True)
        os.environ['AUV_DATA_ROOT'] = str(data_root)
        sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sink.bind(('127.0.0.1', 0))
        sink.settimeout(1.)
        bridge_config = yaml.safe_load((ROOT / 'brain_linux/src/auv_cable_tracking_v2/config/inspection_bridge_passive.yaml').read_text())
        bridge_config['bridge']['protocol_udp']['remote_port'] = sink.getsockname()[1]
        bridge_config_path = output_dir / 'bridge_loopback_params.yaml'
        bridge_config_path.write_text(yaml.safe_dump(bridge_config))
    config = config_file or ROOT / 'brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough.yaml'
    if not config.is_file():
        raise FileNotFoundError(config)
    ros_args = ['--ros-args', '-p', f'config_file:={config}',
                '-p', 'use_sim_time:=true', '-p', 'publish_arbiter_command:=true',
                '-p', 'inspection_speed_feedforward_b:=40.0']
    if with_bridge:
        ros_args += ['-p', f'auv_inspection_bridge_node:params_file:={bridge_config_path}',
                     '-p', 'auv_inspection_bridge_node:passive_mode:=false',
                     '-p', 'auv_inspection_bridge_node:bridge_backend:=protocol_udp']
    rclpy.init(args=ros_args)
    node = CableTrackingV2Node()
    controller = InspectionControllerNode()
    if with_bridge:
        bridge = InspectionBridgeNode()
        bridge._command_keepalive_timer.cancel()
    peer = Node('flythrough_pvs_audit_peer')
    node.timer.cancel()
    controller._control_timer.cancel()
    executor = SingleThreadedExecutor()
    for item in (node, controller, peer, bridge):
        if item is None:
            continue
        executor.add_node(item)
    commands, tracking, depths, efforts, bridge_stop_reasons, inspection_statuses = [], [], [], [], [], []
    operational_statuses = []
    peer.create_subscription(Setpoint, '/auv/control/setpoint', commands.append, 10)
    peer.create_subscription(String, '/auv/cable/tracking', lambda msg: tracking.append(json.loads(msg.data)), 10)
    peer.create_subscription(Bool, '/auv/cable/depth_valid', lambda msg: depths.append(msg.data), 10)
    peer.create_subscription(MpcCmd, '/auv/control/mpc_cmd', efforts.append, 10)
    peer.create_subscription(String, '/auv/cable/bridge_stop_reason',
                             lambda msg: bridge_stop_reasons.append(msg.data), 10)
    peer.create_subscription(String, '/auv/cable/inspection_status',
                             lambda msg: inspection_statuses.append(msg.data), 10)
    peer.create_subscription(String, '/auv/cable/operational_status',
                             lambda msg: operational_statuses.append(json.loads(msg.data)), 10)
    arbiter_pub = None if with_bridge else peer.create_publisher(ArbiterStatus, '/auv/arbiter/status', 10)
    odom_pub = peer.create_publisher(Odometry, '/auv/state/filtered', 10)
    mag_pub = peer.create_publisher(MagneticField, '/auv/sensors/magnetic', 10)
    mission_pub = peer.create_publisher(String, '/auv/cable/mission_command', 10)
    clock_pub = peer.create_publisher(Clock, '/clock', 10)
    covariance_pub = peer.create_publisher(Float32MultiArray, '/auv/state/covariance', 10)
    sonar_pub = peer.create_publisher(SonarCableObservation, '/auv/sensors/cable_sonar_observation', 10)
    sonar_quality_pub = peer.create_publisher(PerceptionQuality, '/auv/perception/quality/sonar', 10)
    fixture_telemetry_suspended = False
    telemetry_fixture_lock = Lock()
    telemetry_fixture_stop = Event()
    telemetry_fixture_thread = None
    if with_bridge:
        def refresh_synthetic_uplink():
            while not telemetry_fixture_stop.is_set():
                with telemetry_fixture_lock:
                    if not fixture_telemetry_suspended:
                        bridge.latest_protocol_telemetry_ts = time.time()
                telemetry_fixture_stop.wait(.02)

        telemetry_fixture_thread = Thread(target=refresh_synthetic_uplink,
                                          name='synthetic_amd_uplink', daemon=True)
        telemetry_fixture_thread.start()

    def wait_for(predicate, timeout_s=10., label='DDS message'):
        deadline = time.monotonic() + timeout_s
        while True:
            # This harness has no physical uplink publisher. Keep its synthetic
            # healthy telemetry fresh during potentially slow DDS delivery;
            # the explicit guard-loss case below disables this fixture.
            if with_bridge and bridge is not None and not fixture_telemetry_suspended:
                bridge.latest_protocol_telemetry_ts = time.time()
            if predicate():
                return
            if time.monotonic() >= deadline:
                raise AssertionError(f'DDS delivery timeout: {label}')
            # ROS /clock may stop after a budget latch.  Process at most one
            # ready callback without a waitset delay, then enforce a separate
            # wall-clock deadline even when simulation time is frozen.
            executor.spin_once(timeout_sec=0.)
            time.sleep(.001)

    core = node.pipeline.core
    if bool(core.flythrough_config.require_runtime_identity_cue) != (sonar_identity_mode != 'off'):
        raise ValueError('sonar identity fixture mode must match the configured runtime gate')
    start = core._fly_start
    direction = core._fly_end - start
    initial_heading = math.degrees(math.atan2(direction[1], direction[0]))
    pvs_cfg = {'simulation': {'dt': .05}, 'pvs': {
        'control_mode': 'depthHeadingAutopilot', 'autonomy_motion_model': 'native',
        'initial_depth_m': 10., 'initial_heading_deg': initial_heading,
        'initial_speed_mps': .3, 'initial_rpm': 0., 'reference_rpm': 0.,
        'current_speed_mps': current_speed_mps,
        'current_direction_deg': current_direction_deg,
    }}
    plant = PVSSimWrapper(config=pvs_cfg, scenario_cfg={}, agent_name='auv').open()
    plant.eta[:2] = start
    rng = np.random.default_rng(seed)
    nav_rng = np.random.default_rng(seed + 1000003)
    rows = []
    source_wall_stream = None
    source_wall_writer = None
    stage_wall_stream = None
    stage_wall_writer = None
    if record_source_wall_map:
        output_dir.mkdir(parents=True, exist_ok=True)
        source_wall_stream = (output_dir / 'fixture_source_wall_map.csv').open(
            'w', newline='', encoding='utf-8')
        source_wall_writer = csv.DictWriter(source_wall_stream, fieldnames=(
            'source_stamp_s', 'tick_start_monotonic_s',
            'navigation_publish_before_monotonic_s',
            'navigation_publish_after_monotonic_s',
            'magnetic_publish_before_monotonic_s',
            'magnetic_publish_after_monotonic_s'))
        source_wall_writer.writeheader()
        stage_wall_stream = (output_dir / 'fixture_stage_wall_timing.csv').open(
            'w', newline='', encoding='utf-8')
        stage_wall_writer = csv.DictWriter(stage_wall_stream, fieldnames=(
            'source_stamp_s', 'stage', 'monotonic_s'))
        stage_wall_writer.writeheader()

    def mark_stage(stamp_s: float, stage: str) -> None:
        if stage_wall_writer is not None:
            stage_wall_writer.writerow({'source_stamp_s': stamp_s,
                                        'stage': stage,
                                        'monotonic_s': time.monotonic()})
            stage_wall_stream.flush()
    tick_profiler = cProfile.Profile() if os.environ.get('AUV_V2_PROFILE_TICK') == '1' else None
    first_track_s = None
    first_inspection_s = None
    previous_true_position: tuple[float, np.ndarray] | None = None
    fault_ticks = 0
    navigation_fault_ticks = 0
    cancel_ticks = 0
    guard_loss_ticks = 0
    cancelled = False
    positive_rpm_ticks = 0
    budget_fallback_ticks = 0
    first_budget_fallback_s = None
    first_hold_s = None
    first_hold_xy = None
    mission_retransmitted = False
    try:
        wait_for(lambda: mission_pub.get_subscription_count() > 0 and clock_pub.get_subscription_count() >= 2)
        mission_pub.publish(String(data=json.dumps({
            'mission_type': 'CABLE_INSPECTION', 'target_depth': 10., 'target_speed_mps': .3,
        })))
        wait_for(lambda: node.latest_mission is not None)
        accepted_mission = node.latest_mission
        if with_bridge:
            bridge.latest_sensor_status_payload.update(confidence=1., leak_level=0)
            bridge.latest_bridge_telemetry_payload = {KEY_TOTAL_VOLTAGE_V: 50.}
            bridge.latest_protocol_telemetry_ts = time.time()
            pc = {KEY_CONTROL_MODE_BYTE: int(ControlModeByte.JETSON_PROTOCOL),
                  'work_instruction': 0, KEY_THRUST: 0., KEY_RIGHT: 0.,
                  KEY_TOP: 0., KEY_LEFT: 0., KEY_BOTTOM: 0.}
            remote_pc = {**pc, KEY_CONTROL_MODE_BYTE: int(ControlModeByte.REMOTE_CONTROL)}
            bridge.handle_pc_raw_command(pc)
            wait_for(lambda: controller.latest_arbiter_status is not None and
                     controller.latest_arbiter_status.autonomy_allowed)
        else:
            wait_for(lambda: arbiter_pub.get_subscription_count() >= 2)
            arbiter = ArbiterStatus()
            arbiter.active_arbiter, arbiter.autonomy_allowed = 'AUTONOMOUS', True
            arbiter_pub.publish(arbiter)
            wait_for(lambda: controller.latest_arbiter_status is not None)
        for index in range(round(max_time_s / .25)):
            tick_wall_start_s = time.monotonic()
            t = 1. + index * .25
            if (inspection_current_step_mps is not None
                    and first_inspection_s is not None
                    and t >= first_inspection_s + 5.):
                plant.current_speed_mps = inspection_current_step_mps
                plant.current_direction_deg = inspection_current_step_direction_deg
                # The native REMUS model copies these values at open().
                # Update its live state as well; changing wrapper metadata
                # alone leaves the actual dynamics unchanged.
                plant.vehicle.V_c = inspection_current_step_mps
                plant.vehicle.beta_c = math.radians(inspection_current_step_direction_deg)
            clock = Clock()
            clock.clock.sec = int(t)
            clock.clock.nanosec = int(round((t - int(t)) * 1e9))
            clock_pub.publish(clock)
            wait_for(lambda: node.get_clock().now().nanoseconds >= round(t * 1e9))

            x, y = map(float, plant.eta[:2])
            heading = math.degrees(float(plant.eta[5]))
            speed = float(plant.nu[0])
            measured_xy = np.array([x, y])
            if nav_position_noise_std_m:
                measured_xy += nav_rng.normal(0., nav_position_noise_std_m, size=2)
            measured_heading_rad = float(plant.eta[5]) + math.radians(nav_heading_bias_deg)
            odom = Odometry()
            odom.header.stamp = clock.clock
            odom.header.frame_id = 'world'
            fault_start = first_track_s is not None and t >= first_track_s + 8
            with telemetry_fixture_lock:
                fixture_telemetry_suspended = case == 'wire_guard_telemetry_loss' and fault_start
                if fixture_telemetry_suspended:
                    bridge.latest_protocol_telemetry_ts = time.time() - 1.
            nav_fault = case == 'wire_navigation_dropout' and fault_start and t < first_track_s + 23
            odom.pose.pose.position.x = float('nan') if nav_fault else float(measured_xy[0])
            odom.pose.pose.position.y = float(measured_xy[1])
            odom.pose.pose.position.z = -float(plant.eta[2])
            odom.pose.pose.orientation.z = math.sin(measured_heading_rad / 2.)
            odom.pose.pose.orientation.w = math.cos(measured_heading_rad / 2.)
            sway = float(plant.nu[1])
            yaw_true = float(plant.eta[5])
            if ground_velocity_from_position and previous_true_position is not None:
                previous_time_s, previous_xy = previous_true_position
                ground_xy = (np.array([x, y]) - previous_xy) / (t - previous_time_s)
                ground_vx, ground_vy = map(float, ground_xy)
            else:
                ground_vx = speed * math.cos(yaw_true) - sway * math.sin(yaw_true)
                ground_vy = speed * math.sin(yaw_true) + sway * math.cos(yaw_true)
            previous_true_position = t, np.array([x, y])
            odom.twist.twist.linear.x = ground_vx + nav_speed_bias_mps * math.cos(measured_heading_rad)
            odom.twist.twist.linear.y = ground_vy + nav_speed_bias_mps * math.sin(measured_heading_rad)
            odom.twist.twist.linear.z = float(plant.nu[2])
            odom.twist.twist.angular.x = float(plant.nu[3])
            odom.twist.twist.angular.y = float(plant.nu[4])
            odom.twist.twist.angular.z = float(plant.nu[5])
            q = ((y - cable_lateral_m) / 3.) ** 2
            exponent = .5 if case.startswith('wire') else 1.
            primary = 0. if case == 'no_source' else primary_cable_gain_nt / (1. + q) ** exponent
            secondary = 0.
            if secondary_cable_gain_nt > 0. and case != 'no_source':
                q_secondary = ((y - secondary_cable_lateral_m) / 3.) ** 2
                secondary = secondary_cable_gain_nt / (1. + q_secondary) ** exponent
            value = 1. + primary + secondary + rng.normal(0., .03)
            fault = fault_start and (
                case == 'wire_magnetic_persistent' or
                (case == 'wire_magnetic_dropout' and t < first_track_s + 23)
            )
            mag = MagneticField()
            mag.header.stamp = clock.clock
            mag.magnetic_field.x = float('nan') if fault else float(value * 1e-9)
            previous_odom, previous_mag = node.latest_odom_wall_time_s, node.latest_magnetic_wall_time_s
            if source_wall_writer is None:
                odom_pub.publish(odom)
                mag_pub.publish(mag)
            else:
                nav_pub_before = time.monotonic()
                odom_pub.publish(odom)
                nav_pub_after = time.monotonic()
                mag_pub_before = time.monotonic()
                mag_pub.publish(mag)
                mag_pub_after = time.monotonic()
                source_wall_writer.writerow({
                    'source_stamp_s': t,
                    'tick_start_monotonic_s': tick_wall_start_s,
                    'navigation_publish_before_monotonic_s': nav_pub_before,
                    'navigation_publish_after_monotonic_s': nav_pub_after,
                    'magnetic_publish_before_monotonic_s': mag_pub_before,
                    'magnetic_publish_after_monotonic_s': mag_pub_after,
                })
                source_wall_stream.flush()
            mark_stage(t, 'sensors_published')
            wait_for(lambda: node.latest_odom_wall_time_s > previous_odom and node.latest_magnetic_wall_time_s > previous_mag)
            mark_stage(t, 'sensors_accepted_by_algorithm')
            if sonar_identity_mode != 'off':
                covariance = np.eye(15) * .0004
                fault_active = first_track_s is not None and t >= first_track_s + 8.
                position_variance = (sonar_track_position_variance_m2
                                     if fault_active and sonar_track_position_variance_m2 is not None
                                     else .01)
                covariance[0, 0] = covariance[1, 1] = position_variance
                covariance[8, 8] = math.radians(1.) ** 2
                previous_covariance = node._latest_nav_uncertainty_wall_time_s
                covariance_pub.publish(Float32MultiArray(data=covariance.reshape(-1).tolist()))
                wait_for(lambda: node._latest_nav_uncertainty_wall_time_s > previous_covariance)
                sonar_dropped = (sonar_track_fault == 'dropout' and fault_active)
                if sonar_identity_mode != 'missing' and not sonar_dropped:
                    fixture_shift = (sonar_track_switch_offset_m if sonar_track_fault == 'switch' and fault_active
                                     else 2. if sonar_identity_mode == 'wrong_line' else 0.)
                    fixture_y = (sonar_line_lateral_m if sonar_identity_mode == 'fixed_line'
                                 else cable_lateral_m + fixture_shift)
                    # The synthetic sonar belongs to the plant, while the
                    # converter receives independently perturbed odometry.
                    # Generating both from measured pose would hide nav bias.
                    cross_track = fixture_y - y
                    line_heading = -float(plant.eta[5])
                    tangent_sonar = np.array([math.cos(line_heading), math.sin(line_heading)])
                    normal_sonar = np.array([-tangent_sonar[1], tangent_sonar[0]])
                    sonar_points = cross_track * normal_sonar + np.linspace(-5., 5., 20)[:, None] * tangent_sonar
                    sonar = SonarCableObservation()
                    sonar.header.stamp = clock.clock
                    sonar.header.frame_id = 'sonar_link'
                    sonar.valid = True
                    sonar.detector_score = 12.
                    sonar.point_x_m = sonar_points[:, 0].tolist()
                    sonar.point_y_m = sonar_points[:, 1].tolist()
                    sonar.point_weight = [1.] * 20
                    sonar.contrast_to_noise_ratio = 10.
                    sonar.visible_length_m = 10.
                    sonar.ambiguity_margin = 5.
                    sonar.detector_id = 'synthetic_identity_fixture'
                    quality = PerceptionQuality()
                    quality.header = sonar.header
                    quality.source = 'sonar_cable'
                    quality.validity = PerceptionQuality.VALIDITY_VALID
                    quality.p_track = .99
                    quality.track_probability_calibrated = sonar_identity_mode != 'uncalibrated'
                    quality.estimate = [cross_track, line_heading, float('nan')]
                    quality.covariance = [.0025, 0., 0., 0., .0001, 0., 0., 0., float('nan')]
                    quality.sample_count = 20
                    quality.data_completeness = 1.
                    quality.calibration_id = 'synthetic_identity_fixture_20260927'
                    sonar_pub.publish(sonar)
                    sonar_quality_pub.publish(quality)
                    wait_for(lambda: node._latest_sonar_observation is not None and
                             node._latest_sonar_quality is not None and
                             node._latest_sonar_observation.header.stamp == clock.clock and
                             node._latest_sonar_quality.header.stamp == clock.clock,
                             label=f'sonar stamp at plant t={t:.2f}s')
            count, track_count, depth_count = len(commands), len(tracking), len(depths)
            nav_age_before_tick_s = time.monotonic() - node.latest_odom_wall_time_s
            covariance_age_before_tick_s = (time.monotonic() - node._latest_nav_uncertainty_wall_time_s
                                            if node._latest_nav_uncertainty is not None else None)
            if tick_profiler is not None:
                tick_profiler.enable()
            node._on_tick()
            mark_stage(t, 'algorithm_tick_returned')
            if tick_profiler is not None:
                tick_profiler.disable()
            nav_age_after_tick_s = time.monotonic() - node.latest_odom_wall_time_s
            covariance_age_after_tick_s = (time.monotonic() - node._latest_nav_uncertainty_wall_time_s
                                           if node._latest_nav_uncertainty is not None else None)
            wait_for(lambda: len(commands) > count and len(tracking) > track_count and len(depths) > depth_count)
            mark_stage(t, 'peer_received_algorithm_outputs')
            command, result = commands[-1], tracking[-1]
            wait_for(lambda: controller.latest_setpoint is not None and
                     controller.latest_setpoint.header.stamp == command.header.stamp and
                     controller.latest_filtered_state is not None and
                     controller.latest_filtered_state.header.stamp == odom.header.stamp)
            mark_stage(t, 'controller_received_inputs')
            count_effort = len(efforts)
            guard_loss = case == 'wire_guard_telemetry_loss' and fault_start
            prior_bridge_sequence = bridge._operational_command_sequence if with_bridge else None
            if with_bridge:
                bridge.latest_protocol_telemetry_ts = time.time() - (1. if guard_loss else 0.)
                if case == 'wire_manual_cancel' and fault_start and not cancelled:
                    from common.enums import WorkInstruction
                    bridge.handle_pc_raw_command({**remote_pc,
                        'work_instruction': int(WorkInstruction.TASK_CANCEL)})
                    cancelled = True
                else:
                    bridge.handle_pc_raw_command(remote_pc if cancelled else pc)
                if cancelled or guard_loss:
                    wait_for(lambda: controller.latest_arbiter_status is not None and
                             controller.latest_arbiter_status.active_arbiter == 'REMOTE')
                # The heartbeat can emit a fallback packet based on the last
                # command. The next packet must be the fresh PID decision.
                if not cancelled and not guard_loss:
                    sink.setblocking(False)
                    try:
                        while True:
                            sink.recvfrom(2048)
                    except BlockingIOError:
                        pass
                    sink.settimeout(1.)
            mark_stage(t, 'controller_tick_started')
            controller._on_timer()
            mark_stage(t, 'controller_tick_returned')
            wait_for(lambda: len(efforts) > count_effort)
            mark_stage(t, 'peer_received_pid_output')
            effort = efforts[-1]
            if not np.isfinite([command.target_speed_mps, command.target_depth_m,
                                command.target_heading_rad, effort.thrust_percent,
                                effort.right_fin_deg, effort.left_fin_deg,
                                effort.top_fin_deg, effort.bottom_fin_deg]).all():
                raise AssertionError('nonfinite command')
            if result.get('burial_depth_m') is not None or depths[-1]:
                raise AssertionError('uncalibrated depth was published')
            if fault:
                fault_ticks += 1
                if command.target_speed_mps != 0 or effort.thrust_percent != 0:
                    raise AssertionError('magnetic fault did not stop thrust')
            if nav_fault:
                navigation_fault_ticks += 1
                if command.target_speed_mps != 0 or effort.thrust_percent != 0:
                    raise AssertionError('navigation fault did not stop thrust')
            if (cancelled or guard_loss) and any(abs(float(value)) > 1e-9 for value in (
                    effort.thrust_percent, effort.right_fin_deg, effort.left_fin_deg,
                    effort.top_fin_deg, effort.bottom_fin_deg)):
                raise AssertionError(f'guard intervention did not zero PID effort at t={t}')
            if with_bridge:
                try:
                    if cancelled or guard_loss:
                        # Revoking autonomy may suppress the next MPC message.
                        # Require a new bridge decision and inspect its actual
                        # UDP packet instead of waiting for a fresh MPC input.
                        wait_for(lambda: bridge._operational_command_sequence > prior_bridge_sequence
                                 and bridge.command_arbiter.active_mode.value == 'REMOTE')
                    else:
                        wait_for(lambda: bridge.command_arbiter._last_mpc_ts is not None and
                                 abs(bridge.command_arbiter._last_mpc_ts - t) < .01)
                except AssertionError:
                    print(json.dumps({
                        'bridge_timeout_t': t, 'mode': result.get('mode'),
                        'bridge_last_mpc_ts': bridge.command_arbiter._last_mpc_ts,
                        'bridge_mode': bridge.command_arbiter.active_mode.value,
                        'bridge_source': bridge.last_arbiter_decision.arbiter_source.value,
                        'guard_state': bridge.autonomy_guard.auto_state.value,
                        'guard_reason': bridge.autonomy_guard.deny_reason.value,
                        'bridge_sensor_status': bridge.latest_sensor_status_payload,
                        'bridge_telemetry_status': bridge._current_telemetry_status(now=time.time()),
                        'hold_budget_reason': node._hold_budget.reason,
                        'inspection_status': inspection_statuses[-1] if inspection_statuses else None,
                        'command_mode': command.mode,
                        'command_speed_mps': command.target_speed_mps,
                        'effort_note': effort.note,
                    }, default=str), file=sys.stderr)
                    raise
                packet, _ = sink.recvfrom(2048)
                mark_stage(t, 'bridge_udp_received')
                if len(packet) != 72:
                    raise AssertionError('bridge produced a non-72-byte packet')
                expected_status_sequence = bridge._operational_command_sequence
                wait_for(lambda: operational_statuses and
                         operational_statuses[-1]['command_sequence'] >= expected_status_sequence)
                wait_for(lambda: bridge.latest_cable_monitor_payload is not None and
                         bridge.latest_cable_monitor_payload.get('operational_status', {}).get('command_sequence', -1)
                         >= expected_status_sequence)
                if (cancelled or guard_loss) and operational_statuses[-1]['autonomous_execution_authorized']:
                    raise AssertionError(f'bridge status still permits autonomy after intervention at t={t}')
            else:
                payload = {KEY_CONTROL_MODE_BYTE: 238,
                           KEY_ORIENTATION_DEG: math.degrees(command.target_heading_rad) % 360.,
                           KEY_TARGET_DEPTH_M: command.target_depth_m,
                           KEY_THRUST: effort.thrust_percent,
                           KEY_RIGHT: effort.right_fin_deg, KEY_LEFT: effort.left_fin_deg,
                           KEY_TOP: effort.top_fin_deg, KEY_BOTTOM: effort.bottom_fin_deg}
                packet = build_downlink_packet_from_payload(payload, main_motor_rpm_scale=15.)
            decoded = parse_downlink_packet(packet, main_motor_rpm_scale=15.)
            if with_bridge:
                source = bridge.last_arbiter_decision.arbiter_source.value
                expected_rpm = round(effort.thrust_percent * 15)
                if cancelled or guard_loss:
                    cancel_ticks += int(cancelled)
                    guard_loss_ticks += int(guard_loss)
                    if decoded.main_motor_rpm != 0 or bridge.command_arbiter.active_mode.value != 'REMOTE':
                        raise AssertionError(f'guard intervention did not retain zero REMOTE command at t={t}')
                elif decoded.main_motor_rpm != expected_rpm or (expected_rpm > 0 and source != 'JETSON_MPC'):
                    # A stale-navigation Hold budget may latch between the
                    # PID computation and UDP send.  The guard must then win
                    # with zero effort; record this as a failed *task*, not a
                    # protocol mismatch or a successful nominal run.
                    authorized_budget_fallback = (
                        source == 'SAFETY_FALLBACK'
                        and decoded.main_motor_rpm == 0
                        and node._hold_budget.recovery_required
                        and bridge._budget_problem() == 'inspection_recovery_required'
                    )
                    if authorized_budget_fallback:
                        budget_fallback_ticks += 1
                        if first_budget_fallback_s is None:
                            first_budget_fallback_s = t
                    else:
                        raise AssertionError(
                            f'bridge command differs at t={t}: source={source}, '
                            f'PID={expected_rpm} RPM, UDP={decoded.main_motor_rpm} RPM, '
                            f'budget_problem={bridge._budget_problem()}, '
                            f'budget_age_s={time.monotonic() - bridge._budget_seen_wall_time_s:.3f}, '
                            f'budget_reason={node._hold_budget.reason}, '
                            f'nav_age_s={time.monotonic() - node.latest_odom_wall_time_s:.3f}, '
                            f'authority_reason={operational_statuses[-1].get("authority_reason") if operational_statuses else None}'
                        )
            positive_rpm_ticks += int(decoded.main_motor_rpm > 0)
            if nav_fault and decoded.main_motor_rpm != 0:
                raise AssertionError('navigation fault did not zero the UDP packet')
            # This unwraps only the PVS continuous autopilot reference. The
            # controller and binary packet still use the normal protocol.
            heading_ref = heading + (decoded.orientation_deg - heading + 180.) % 360. - 180.
            plant.set_reference(depth_m=decoded.target_depth_m,
                                heading_rad=math.radians(heading_ref),
                                propeller_rpm=max(0., decoded.main_motor_rpm))
            mark_stage(t, 'pvs_step_started')
            for _ in range(5):
                plant.step([0, 0, 0, 0, 0])
            mark_stage(t, 'pvs_step_returned')
            assert np.isfinite([*plant.eta, *plant.nu, *plant.u_actual]).all()
            if result['mode'] == 'track' and first_track_s is None:
                first_track_s = t
            if (result['mode'] == 'track'
                    and result['diagnostics'].get('tracking_stage') == 'inspect_along_cable'
                    and first_inspection_s is None):
                first_inspection_s = t
            rows.append({
                'time_s': t, 'x_m': x, 'y_m': y, 'heading_deg': heading,
                'nav_x_m': float(measured_xy[0]), 'nav_y_m': float(measured_xy[1]),
                'estimated_disturbance_x_mps': (result['diagnostics'].get('flythrough_estimated_current_xy_mps') or [None, None])[0],
                'estimated_disturbance_y_mps': (result['diagnostics'].get('flythrough_estimated_current_xy_mps') or [None, None])[1],
                'nav_ground_velocity_x_mps': float(odom.twist.twist.linear.x),
                'nav_ground_velocity_y_mps': float(odom.twist.twist.linear.y),
                'target_heading_deg': math.degrees(float(command.target_heading_rad)),
                'speed_mps': speed, 'mode': result['mode'],
                'stage': result['diagnostics'].get('tracking_stage', ''),
                'reason': result['diagnostics'].get('continuity_reason', ''),
                'route_observed_lateral_mae_m': result['diagnostics'].get('route_observed_lateral_mae_m'),
                'route_observed_lateral_max_m': result['diagnostics'].get('route_observed_lateral_max_m'),
                'route_observed_lateral_samples': result['diagnostics'].get('route_observed_lateral_samples'),
                'route_quality_valid': result['diagnostics'].get('route_quality_valid'),
                'runtime_identity_reason': result['diagnostics'].get('runtime_identity_reason'),
                'runtime_identity_center_m': result['diagnostics'].get('runtime_identity_center_m'),
                'runtime_identity_half_width_m': result['diagnostics'].get('runtime_identity_half_width_m'),
                'runtime_identity_track_residual_m': result['diagnostics'].get('runtime_identity_track_residual_m'),
                'runtime_identity_last_seen_s': result['diagnostics'].get('runtime_identity_last_seen_s'),
                'hold_budget_state': (result['diagnostics'].get('hold_budget') or {}).get('state'),
                'hold_budget_reason': (result['diagnostics'].get('hold_budget') or {}).get('reason'),
                'hold_budget_remaining_m': (result['diagnostics'].get('hold_budget') or {}).get('remaining_budget_m'),
                'hold_budget_clearance_m': (result['diagnostics'].get('hold_budget') or {}).get('boundary_clearance_m'),
                'lateral_reason_codes': json.dumps(result['diagnostics'].get('lateral_reason_codes', [])),
                'lateral_valid': bool(result['diagnostics'].get('lateral_valid')),
                'depth_valid': bool(depths[-1]),
                'target_speed_mps': command.target_speed_mps,
                'thrust_percent': effort.thrust_percent,
                'rpm': decoded.main_motor_rpm,
                'controller_note': effort.note,
                'arbiter_mode': bridge.command_arbiter.active_mode.value if with_bridge else 'AUTONOMOUS',
                'arbiter_source': bridge.last_arbiter_decision.arbiter_source.value if with_bridge else 'DIRECT_PACKET',
                'autonomous_execution_authorized': (operational_statuses[-1]['autonomous_execution_authorized']
                                                    if with_bridge else None),
                'authority_reason': operational_statuses[-1]['authority_reason'] if with_bridge else None,
                'operational_localization_status': (operational_statuses[-1]['localization_status']
                                                     if with_bridge else None),
                'operational_task_status': (operational_statuses[-1].get('task_status')
                                            if with_bridge else None),
                'bridge_task_status': bridge._task_status if with_bridge else None,
                'endpoint_complete': bool(result['diagnostics'].get('endpoint_complete')),
                'wall_tick_elapsed_s': time.monotonic() - tick_wall_start_s,
                'nav_age_before_tick_s': nav_age_before_tick_s,
                'nav_age_after_tick_s': nav_age_after_tick_s,
                'covariance_age_before_tick_s': covariance_age_before_tick_s,
                'covariance_age_after_tick_s': covariance_age_after_tick_s,
            })
            mark_stage(t, 'tick_row_completed')
            if result['mode'] == 'hold' and first_hold_s is None:
                first_hold_s = t
                first_hold_xy = np.array([x, y], dtype=float)
                if retransmit_mission_on_hold:
                    count_rejected = node._rejected_rearm_count
                    mission_pub.publish(String(data=json.dumps({
                        'mission_type': 'CABLE_INSPECTION', 'target_depth': 10.,
                        'target_speed_mps': .3,
                    })))
                    wait_for(lambda: node._rejected_rearm_count > count_rejected)
                    mission_pub.publish(String(data=json.dumps({
                        'mission_type': 'CABLE_INSPECTION', 'target_depth': 10.,
                        'target_speed_mps': .2,
                    })))
                    wait_for(lambda: node._rejected_rearm_count > count_rejected + 1)
                    assert node.latest_mission is accepted_mission
                    assert (node._hold_budget.recovery_required
                            or node.pipeline.core._fly_failed)
                    mission_retransmitted = True
            if first_hold_s is not None and post_hold_coast_s > 0.:
                if effort.thrust_percent != 0. or decoded.main_motor_rpm != 0:
                    raise AssertionError(f'identity hold did not keep zero propulsion at t={t}')
            long_hold_done = first_track_s is not None and t >= first_track_s + 68
            held_terminal = (result['mode'] in {'hold', 'complete'} and not fault
                             and not nav_fault and not cancelled and not guard_loss)
            if (rows[-1]['endpoint_complete'] or
                    (held_terminal and (post_hold_coast_s == 0. or first_hold_s is None
                                        or t >= first_hold_s + post_hold_coast_s)) or
                    (long_hold_done and (case == 'wire_magnetic_persistent' or cancelled or guard_loss))):
                break
        output_dir.mkdir(parents=True, exist_ok=True)
        name = f'{case}_seed_{seed}'
        if tick_profiler is not None:
            tick_profiler.dump_stats(str(output_dir / f'{name}_tick_profile.pstats'))
            profile_text = io.StringIO()
            pstats.Stats(tick_profiler, stream=profile_text).sort_stats('cumulative').print_stats(40)
            (output_dir / f'{name}_tick_profile.txt').write_text(profile_text.getvalue())
        with (output_dir / f'{name}.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader(); writer.writerows(rows)
        summary = {
            'case': case, 'seed': seed, 'ticks': len(rows),
            'duration_s': rows[-1]['time_s'],
            'wall_tick_max_s': max(row['wall_tick_elapsed_s'] for row in rows),
            'wall_tick_p95_s': float(np.percentile([row['wall_tick_elapsed_s'] for row in rows], 95)),
            'nav_age_before_tick_max_s': max(row['nav_age_before_tick_s'] for row in rows),
            'nav_age_before_tick_over_half_second_count': sum(
                row['nav_age_before_tick_s'] > .5 for row in rows),
            'completed': rows[-1]['endpoint_complete'],
            'ever_confirm': any(row['mode'] == 'confirm' for row in rows),
            'ever_track': any(row['mode'] == 'track' for row in rows),
            'first_track_s': first_track_s,
            'lateral_valid': any(row['lateral_valid'] for row in rows),
            'depth_published': any(row['depth_valid'] for row in rows),
            'first_hold_reason': next((row['reason'] for row in rows if row['mode'] == 'hold'), None),
            'first_hold_s': first_hold_s,
            'mission_retransmitted_on_hold': mission_retransmitted,
            'mission_retransmission_rejections': node._rejected_rearm_count,
            'bridge_budget_latched': bridge._budget_latched if with_bridge else None,
            'budget_fallback_ticks': budget_fallback_ticks,
            'first_budget_fallback_s': first_budget_fallback_s,
            'bridge_recovery_stop_observed': (
                any(reason == 'inspection_recovery_required' for reason in bridge_stop_reasons)
                if with_bridge else None),
            'bridge_stale_budget_stop_observed': (
                any(reason == 'inspection_budget_status_stale' for reason in bridge_stop_reasons)
                if with_bridge else None),
            'final_inspection_status': inspection_statuses[-1] if inspection_statuses else None,
            'final_operational_status': operational_statuses[-1] if operational_statuses else None,
            'final_bridge_task_status': bridge._task_status if with_bridge else None,
            'recovery_status_observed': 'RECOVERY_REQUIRED' in inspection_statuses,
            'first_recovery_required_s': next((row['time_s'] for row in rows
                                               if row['hold_budget_state'] == 'RECOVERY_REQUIRED'), None),
            'first_recovery_reason': next((row['hold_budget_reason'] for row in rows
                                           if row['hold_budget_state'] == 'RECOVERY_REQUIRED'), None),
            'post_hold_coast_s': post_hold_coast_s,
            'hold_to_final_displacement_m': (float(np.linalg.norm(plant.eta[:2] - first_hold_xy))
                                             if first_hold_xy is not None else None),
            'hold_to_final_lateral_m': (float(plant.eta[1] - first_hold_xy[1])
                                        if first_hold_xy is not None else None),
            'final_ground_speed_mps': (float(math.hypot(
                rows[-1]['x_m'] - rows[-2]['x_m'],
                rows[-1]['y_m'] - rows[-2]['y_m']) / .25)
                                         if len(rows) >= 2 else None),
            'post_hold_nonzero_rpm_ticks': sum(
                row['rpm'] != 0 for row in rows
                if first_hold_s is not None and row['time_s'] >= first_hold_s),
            'fault_ticks': fault_ticks,
            'navigation_fault_ticks': navigation_fault_ticks,
            'manual_cancel_ticks': cancel_ticks,
            'manual_cancel_zero_pid_ticks': cancel_ticks,
            'manual_cancel_zero_udp_ticks': cancel_ticks,
            'guard_telemetry_loss_ticks': guard_loss_ticks,
            'guard_telemetry_loss_zero_pid_ticks': guard_loss_ticks,
            'guard_telemetry_loss_zero_udp_ticks': guard_loss_ticks,
            'positive_rpm_ticks': positive_rpm_ticks,
            'max_rpm': max(row['rpm'] for row in rows),
            'final_xy_m': [rows[-1]['x_m'], rows[-1]['y_m']],
            'max_abs_y_m': max(abs(row['y_m']) for row in rows),
            'scan_sample_count': len(core._scan_x_m),
            'scan_lateral_range_m': [min(core._scan_x_m), max(core._scan_x_m)] if core._scan_x_m else None,
            'last_fwhm_reason_codes': list(core._last_fwhm.reason_codes) if core._last_fwhm is not None else None,
            'last_fwhm_center_m': float(core._last_fwhm.center_x_m) if core._last_fwhm is not None and core._last_fwhm.center_x_m is not None else None,
            'last_fwhm_crossings_m': [None if value is None else float(value) for value in (core._last_fwhm.left_crossing_x_m, core._last_fwhm.right_crossing_x_m)] if core._last_fwhm is not None else None,
            'last_lateral_reason_codes': list(core._last_lateral.reason_codes) if core._last_lateral is not None else None,
            'rejoin_runin_selected_m': core._fly_active_runin_m,
            'route_observed_lateral_mae_m': (core._fly_route_quality_sum_m / core._fly_route_quality_samples
                                             if core._fly_route_quality_samples else None),
            'route_observed_lateral_max_m': (core._fly_route_quality_max_m
                                             if core._fly_route_quality_samples else None),
            'route_observed_lateral_samples': core._fly_route_quality_samples,
            'route_quality_valid': rows[-1]['route_quality_valid'],
            'controller_feedforward_b': controller._pid_controller._pid.speed_ff_b,
            'current_speed_mps': current_speed_mps,
            'current_direction_deg': current_direction_deg,
            'cable_lateral_m': cable_lateral_m,
            'primary_cable_gain_nt': primary_cable_gain_nt,
            'secondary_cable_lateral_m': secondary_cable_lateral_m,
            'secondary_cable_gain_nt': secondary_cable_gain_nt,
            'sonar_identity_mode': sonar_identity_mode,
            'sonar_line_lateral_m': sonar_line_lateral_m,
            'sonar_track_fault': sonar_track_fault,
            'sonar_track_switch_offset_m': sonar_track_switch_offset_m,
            'sonar_track_position_variance_m2': sonar_track_position_variance_m2,
            'first_inspection_s': first_inspection_s,
            'inspection_current_step_mps': inspection_current_step_mps,
            'inspection_current_step_direction_deg': (
                inspection_current_step_direction_deg
                if inspection_current_step_mps is not None else None),
            'sonar_fixture_uses_true_plant_pose': sonar_identity_mode != 'off',
            'last_sonar_identity_reason': node._latest_identity_reason,
            'nav_position_noise_std_m': nav_position_noise_std_m,
            'nav_speed_bias_mps': nav_speed_bias_mps,
            'nav_heading_bias_deg': nav_heading_bias_deg,
            'ground_velocity_from_position': ground_velocity_from_position,
            'config_file': str(config),
            'source': f'{name}.csv',
            'native_pvs': True, 'ros_dds': True, 'protocol_encoded': True,
            'installed_v2_node_mode': INSTALLED_V2_NODE,
            'v2_node_loaded_path': str(Path(v2_node_module.__file__).resolve()),
            'bridge_and_guard_connected': with_bridge, 'hardware_connected': False,
            'fixture_source_wall_map_file': ('fixture_source_wall_map.csv'
                                             if record_source_wall_map else None),
        }
        return summary
    finally:
        telemetry_fixture_stop.set()
        if telemetry_fixture_thread is not None:
            telemetry_fixture_thread.join(timeout=1.)
        plant.close()
        for item in (node, controller, peer, bridge):
            if item is None:
                continue
            executor.remove_node(item)
            item.destroy_node()
        executor.shutdown()
        if rclpy.ok():
            rclpy.shutdown()
        if sink is not None:
            sink.close()
        if source_wall_stream is not None:
            source_wall_stream.close()
        if stage_wall_stream is not None:
            stage_wall_stream.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', default='wire', choices=[
        'wire', 'dipole', 'no_source', 'wire_magnetic_dropout',
        'wire_magnetic_persistent', 'wire_navigation_dropout',
        'wire_manual_cancel', 'wire_guard_telemetry_loss',
    ])
    parser.add_argument('--seed', type=int, default=101)
    parser.add_argument('--max-time-s', type=float, default=1600.)
    parser.add_argument('--current-speed-mps', type=float, default=0.)
    parser.add_argument('--current-direction-deg', type=float, default=0.)
    parser.add_argument('--cable-lateral-m', type=float, default=6.,
                        help='synthetic cable truth y coordinate; configured prior remains y=0')
    parser.add_argument('--primary-cable-gain-nt', type=float, default=20.,
                        help='target magnetic gain; zero makes the target magnetically absent')
    parser.add_argument('--secondary-cable-lateral-m', type=float,
                        help='independent synthetic interfering magnetic line y coordinate')
    parser.add_argument('--secondary-cable-gain-nt', type=float, default=0.,
                        help='synthetic interferer gain, zero disables it')
    parser.add_argument('--sonar-identity-mode', default='off',
                        choices=['off', 'target', 'missing', 'uncalibrated', 'wrong_line', 'fixed_line'],
                        help='synthetic DDS sonar/quality fixture; never physical evidence')
    parser.add_argument('--sonar-line-lateral-m', type=float,
                        help='fixed_line fixture: world lateral line, independent of target truth')
    parser.add_argument('--sonar-track-fault', default='none',
                        choices=['none', 'dropout', 'switch'],
                        help='inject loss or reassociation 8 s after first Track sample')
    parser.add_argument('--sonar-track-switch-offset-m', type=float, default=3.,
                        help='lateral sonar line change after Track switch; default preserves the original fault')
    parser.add_argument('--sonar-track-position-variance-m2', type=float,
                        help='optional reported position variance only after the Track fault')
    parser.add_argument('--inspection-current-step-mps', type=float,
                        help='native-PVS current step five seconds after finite inspection starts')
    parser.add_argument('--inspection-current-step-direction-deg', type=float, default=90.)
    parser.add_argument('--post-hold-coast-s', type=float, default=0.,
                        help='continue zero-command native-PVS motion after first Hold (diagnostic)')
    parser.add_argument('--retransmit-mission-on-hold', action='store_true',
                        help='re-send same and modified mission commands after first Hold')
    parser.add_argument('--config-file', type=Path,
                        help='alternative independent v2 YAML; default is the original flythrough profile')
    parser.add_argument('--with-bridge', action='store_true',
                        help='route PID commands through the real guard and local UDP bridge')
    parser.add_argument('--nav-position-noise-std-m', type=float, default=0.,
                        help='independent Gaussian navigation position noise (separate RNG from magnetic noise)')
    parser.add_argument('--nav-speed-bias-mps', type=float, default=0.,
                        help='constant along-heading bias added to reported world ground velocity')
    parser.add_argument('--nav-heading-bias-deg', type=float, default=0.,
                        help='constant error added to reported yaw')
    parser.add_argument('--ground-velocity-from-position', action='store_true',
                        help='derive world ground velocity from native-PVS position differences, including current')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'AUV-Master-Mag/results/v2/inspection_flythrough_ros_pvs_20260926')
    parser.add_argument('--record-source-wall-map', action='store_true',
                        help='write sim stamp to fixture publication monotonic time, for separate DDS receipt audit')
    args = parser.parse_args()
    result = run(args.case, args.seed, args.output_dir, args.max_time_s,
                 current_speed_mps=args.current_speed_mps,
                 current_direction_deg=args.current_direction_deg,
                 cable_lateral_m=args.cable_lateral_m,
                 primary_cable_gain_nt=args.primary_cable_gain_nt,
                 config_file=args.config_file,
                 with_bridge=args.with_bridge,
                 nav_position_noise_std_m=args.nav_position_noise_std_m,
                 nav_speed_bias_mps=args.nav_speed_bias_mps,
                 nav_heading_bias_deg=args.nav_heading_bias_deg,
                 ground_velocity_from_position=args.ground_velocity_from_position,
                 secondary_cable_lateral_m=args.secondary_cable_lateral_m,
                 secondary_cable_gain_nt=args.secondary_cable_gain_nt,
                 sonar_identity_mode=args.sonar_identity_mode,
                 sonar_line_lateral_m=args.sonar_line_lateral_m,
                 sonar_track_fault=args.sonar_track_fault,
                 sonar_track_switch_offset_m=args.sonar_track_switch_offset_m,
                 sonar_track_position_variance_m2=args.sonar_track_position_variance_m2,
                 inspection_current_step_mps=args.inspection_current_step_mps,
                 inspection_current_step_direction_deg=args.inspection_current_step_direction_deg,
                 post_hold_coast_s=args.post_hold_coast_s,
                 retransmit_mission_on_hold=args.retransmit_mission_on_hold,
                 record_source_wall_map=args.record_source_wall_map)
    summary_path = args.output_dir / f'{args.case}_seed_{args.seed}_summary.json'
    summary_path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
