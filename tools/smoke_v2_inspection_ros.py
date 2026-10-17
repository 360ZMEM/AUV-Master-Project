#!/usr/bin/env python3
"""Isolated DDS inspection loop; simulated clock and explicit tick scheduling.

Run with ROS_LOCALHOST_ONLY=1 and a dedicated ROS_DOMAIN_ID. No controller,
bridge, hardware or actuator node is started. The plant has bounded yaw/speed.
"""
from pathlib import Path
import json
import math
import os
import time
import argparse

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from nav_msgs.msg import Odometry
from sensor_msgs.msg import MagneticField
from std_msgs.msg import String, Bool
from rosgraph_msgs.msg import Clock
from auv_interfaces.msg import Setpoint, ArbiterStatus, MpcCmd
from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-controller', action='store_true', help='Also audit actual guarded PID command messages; plant still follows setpoints.')
    parser.add_argument('--output-dir', type=Path, help='Use a new directory to preserve previous run evidence.')
    args = parser.parse_args()
    if os.environ.get("ROS_LOCALHOST_ONLY") != "1" or not os.environ.get("ROS_DOMAIN_ID"):
        raise SystemExit("Set ROS_LOCALHOST_ONLY=1 and an isolated ROS_DOMAIN_ID")
    config = ROOT / "brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_inspection.yaml"
    rclpy.init(args=["--ros-args", "-p", f"config_file:={config}", "-p", "use_sim_time:=true",
                    "-p", "publish_arbiter_command:=true"])
    node = CableTrackingV2Node()
    node.timer.cancel()  # Explicit ticks make DDS scheduling repeatable.
    peer = Node("inspection_audit_peer")
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    executor.add_node(peer)
    controller = None
    efforts = []
    if args.with_controller:
        from auv_cable_tracking_v2.inspection_controller_node import InspectionControllerNode
        controller = InspectionControllerNode()
        controller._control_timer.cancel()
        executor.add_node(controller)
        peer.create_subscription(MpcCmd, '/auv/control/mpc_cmd', efforts.append, 10)
    arbiter_pub = peer.create_publisher(ArbiterStatus, '/auv/arbiter/status', 10)
    commands, tracking, depths = [], [], []
    peer.create_subscription(Setpoint, "/auv/control/setpoint", commands.append, 10)
    peer.create_subscription(String, "/auv/cable/tracking", lambda msg: tracking.append(json.loads(msg.data)), 10)
    peer.create_subscription(Bool, "/auv/cable/depth_valid", lambda msg: depths.append(msg.data), 10)
    odom_pub = peer.create_publisher(Odometry, "/auv/state/filtered", 10)
    mag_pub = peer.create_publisher(MagneticField, "/auv/sensors/magnetic", 10)
    mission_pub = peer.create_publisher(String, "/auv/cable/mission_command", 10)
    clock_pub = peer.create_publisher(Clock, "/clock", 10)

    def wait_for(predicate, timeout=5.0):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                raise AssertionError("DDS delivery timeout")
            executor.spin_once(timeout_sec=0.005)

    rows = []
    first_track = None
    completed = False
    fault_holds = 0
    positive_effort_ticks = 0
    rng = np.random.default_rng(100)
    position = np.array([0., -10.])
    heading, speed, dt = 0., 0., .25
    try:
        wait_for(lambda: mission_pub.get_subscription_count() > 0 and clock_pub.get_subscription_count() >= 2)
        mission_pub.publish(String(data=json.dumps({"mission_type": "CABLE_INSPECTION", "target_depth": 10., "target_speed_mps": .8})))
        wait_for(lambda: node.latest_mission is not None)
        # Malformed requests must preserve the last accepted mission.
        for value in ("[]", '{"mission_type":"CABLE_INSPECTION","target_depth":"bad"}'):
            node._on_mission_command(String(data=value))
        assert node.latest_mission["target_depth"] == 10.
        if controller is not None:
            wait_for(lambda: arbiter_pub.get_subscription_count() >= 2)
            arbiter = ArbiterStatus()
            arbiter.active_arbiter, arbiter.autonomy_allowed = 'AUTONOMOUS', True
            arbiter_pub.publish(arbiter)
            wait_for(lambda: controller.latest_arbiter_status is not None)
        for index in range(4000):
            t = 1. + index * dt
            clock = Clock()
            clock.clock.sec = int(t)
            clock.clock.nanosec = int(round((t - int(t)) * 1e9))
            clock_pub.publish(clock)
            wait_for(lambda: node.get_clock().now().nanoseconds >= round(t * 1e9))
            odom = Odometry()
            odom.header.stamp = clock.clock
            odom.pose.pose.position.x, odom.pose.pose.position.y = map(float, position)
            odom.pose.pose.position.z = -10.
            odom.pose.pose.orientation.z = math.sin(math.radians(heading) / 2)
            odom.pose.pose.orientation.w = math.cos(math.radians(heading) / 2)
            odom.twist.twist.linear.x = speed
            mag = MagneticField()
            value = 1 + 20 / np.sqrt(1 + ((position[1] - 6) / 3) ** 2) + rng.normal(0, .03)
            fault = first_track is not None and first_track + 8 <= t < first_track + 23
            mag.magnetic_field.x = float("nan") if fault else float(value * 1e-9)
            previous_odom, previous_mag = node.latest_odom_wall_time_s, node.latest_magnetic_wall_time_s
            odom_pub.publish(odom)
            mag_pub.publish(mag)
            wait_for(lambda: node.latest_odom_wall_time_s > previous_odom and node.latest_magnetic_wall_time_s > previous_mag)
            count, track_count, depth_count = len(commands), len(tracking), len(depths)
            node._on_tick()
            wait_for(lambda: len(commands) > count and len(tracking) > track_count and len(depths) > depth_count)
            command, result = commands[-1], tracking[-1]
            if controller is not None:
                wait_for(lambda: controller.latest_setpoint is not None and
                         controller.latest_setpoint.header.stamp == command.header.stamp and
                         controller.latest_filtered_state is not None and
                         controller.latest_filtered_state.header.stamp == odom.header.stamp)
                count_effort = len(efforts)
                controller._on_timer()
                wait_for(lambda: len(efforts) > count_effort)
                effort = efforts[-1]
                actuator_values = [effort.thrust_percent,effort.right_fin_deg,effort.left_fin_deg,
                                   effort.top_fin_deg,effort.bottom_fin_deg]
                assert np.isfinite(actuator_values).all()
                positive_effort_ticks += int(effort.thrust_percent > 0)
                if fault or command.target_speed_mps == 0:
                    assert actuator_values == [0.,0.,0.,0.,0.]
            assert np.isfinite([command.target_speed_mps, command.target_depth_m, command.target_heading_rad]).all()
            assert 0 <= command.target_speed_mps <= .800001
            assert result.get("burial_depth_m") is None and not depths[-1]
            if fault:
                assert command.target_speed_mps == 0 and not command.track_cable
                assert command.target_depth_m == 10.
                fault_holds += 1
            if result["mode"] == "track" and first_track is None:
                first_track = t
            rows.append({"time_s": t, "mode": result["mode"], "x_m": float(position[0]),
                         "y_m": float(position[1]), "speed_mps": command.target_speed_mps})
            if controller is not None:
                rows[-1].update(thrust_percent=actuator_values[0], right_fin_deg=actuator_values[1],
                                left_fin_deg=actuator_values[2], top_fin_deg=actuator_values[3],
                                bottom_fin_deg=actuator_values[4], controller_note=effort.note)
            if result["diagnostics"].get("endpoint_complete"):
                assert command.target_speed_mps == 0 and not command.track_cable
                completed = True
                break
            heading_error = (math.degrees(command.target_heading_rad) - heading + 180) % 360 - 180
            heading += float(np.clip(heading_error, -12 * dt, 12 * dt))
            speed += float(np.clip(command.target_speed_mps - speed, -.25 * dt, .20 * dt))
            position += dt * speed * np.array([math.cos(math.radians(heading)), math.sin(math.radians(heading))])
        assert completed and fault_holds == 60
        # The stale-input path is outside the core: verify its actual DDS command.
        node.latest_magnetic_wall_time_s = time.monotonic() - 5
        count = len(commands)
        node._on_tick()
        wait_for(lambda: len(commands) > count)
        assert commands[-1].target_speed_mps == 0 and not commands[-1].track_cable
        if controller is not None:
            assert positive_effort_ticks > 0, 'controller never produced forward thrust'
            controller._inspection_setpoint_received = time.monotonic() - 5
            count_effort = len(efforts)
            controller._on_timer()
            wait_for(lambda: len(efforts) > count_effort)
            assert efforts[-1].thrust_percent == 0 and efforts[-1].note == 'inspection_setpoint_stale'
        out = ROOT / ('AUV-Master-Mag/results/v2/inspection_ros_controller_20260926' if controller else
                      'AUV-Master-Mag/results/v2/inspection_ros_dds_20260926')
        if args.output_dir is not None:
            out = args.output_dir
        out.mkdir(parents=True, exist_ok=True)
        summary = {"completed": completed, "first_track_s": first_track, "duration_s": rows[-1]["time_s"],
                   "ticks": len(rows), "fault_hold_ticks": fault_holds, "stale_gate_hold": True,
                   "uncalibrated_depth_publications": 0, "finite_commands": True,
                   "scheduler": "explicit tick; DDS input/output; simulated clock; kinematic plant",
                   "hardware_connected": False}
        summary.update(controller_audited=controller is not None, controller_messages=len(efforts),
                       positive_effort_ticks=positive_effort_ticks,
                       plant_driven_by='setpoint kinematics, not controller forces')
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        (out / "trajectory.json").write_text(json.dumps(rows) + "\n")
        print(json.dumps(summary))
    finally:
        executor.remove_node(node)
        executor.remove_node(peer)
        if controller is not None:
            executor.remove_node(controller)
            controller.destroy_node()
        node.destroy_node()
        peer.destroy_node()
        executor.shutdown()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
