#!/usr/bin/env python3
"""DDS check of the opt-in inspection PID's received Setpoint source-age gate."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from nav_msgs.msg import Odometry
from auv_interfaces.msg import ArbiterStatus, MpcCmd, Setpoint
from auv_cable_tracking_v2.inspection_controller_node import InspectionControllerNode


def stamp_at(seconds, stamp):
    stamp.sec = int(seconds)
    stamp.nanosec = int((seconds - int(seconds)) * 1e9)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        parser.error('isolated localhost ROS domain required')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    rclpy.init(args=['--ros-args', '-p', 'use_sim_time:=false',
                     '-p', 'inspection_setpoint_source_timeout_s:=0.35',
                     '-p', 'inspection_speed_feedforward_b:=40.0',
                     '-p', 'publish_arbiter_command:=true'])
    controller = InspectionControllerNode()
    controller._control_timer.cancel()
    peer = Node('inspection_controller_source_probe')
    executor = SingleThreadedExecutor()
    executor.add_node(controller)
    executor.add_node(peer)
    setpoint_pub = peer.create_publisher(Setpoint, '/auv/control/setpoint', 10)
    navigation_pub = peer.create_publisher(Odometry, '/auv/state/filtered', 10)
    arbiter_pub = peer.create_publisher(ArbiterStatus, '/auv/arbiter/status', 10)
    efforts = []
    peer.create_subscription(MpcCmd, '/auv/control/mpc_cmd', efforts.append, 10)

    def wait_for(predicate, label):
        deadline = time.monotonic() + 6.
        while not predicate():
            if time.monotonic() > deadline:
                raise TimeoutError(f'DDS timeout: {label}')
            executor.spin_once(timeout_sec=.02)

    result = {'role': 'inspection_controller_received_source_age_dds_probe',
              'ros_domain_id': os.environ['ROS_DOMAIN_ID'], 'source_timeout_s': .35,
              'use_sim_time': False, 'algorithm_connected': False,
              'bridge_connected': False, 'hardware_connected': False}
    result['controller_source_sha256'] = digest(
        Path(__file__).resolve().parents[1] /
        'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_controller_node.py')
    result['controller_installed_sha256'] = digest(
        Path(__file__).resolve().parents[1] /
        'brain_linux/install/auv_cable_tracking_v2/lib/python3.10/site-packages/auv_cable_tracking_v2/inspection_controller_node.py')
    result['controller_source_matches_installed'] = (
        result['controller_source_sha256'] == result['controller_installed_sha256'])
    try:
        wait_for(lambda: setpoint_pub.get_subscription_count() >= 1
                 and navigation_pub.get_subscription_count() >= 1
                 and arbiter_pub.get_subscription_count() >= 1, 'subscriptions')
        nav = Odometry()
        stamp_at(time.time(), nav.header.stamp)
        nav.pose.pose.position.z = -10.
        nav.pose.pose.orientation.w = 1.
        status = ArbiterStatus(active_arbiter='AUTONOMOUS', autonomy_allowed=True)
        navigation_pub.publish(nav)
        arbiter_pub.publish(status)
        wait_for(lambda: controller.latest_filtered_state is not None
                 and controller.latest_arbiter_status is not None, 'navigation and arbiter')

        stale = Setpoint()
        stamp_at(time.time() - 1., stale.header.stamp)
        stale.mode = 'CABLE_TRACKING'
        stale.track_cable = True
        stale.target_depth_m = 10.
        stale.target_speed_mps = .3
        stale.target_heading_rad = 0.
        setpoint_pub.publish(stale)
        wait_for(lambda: controller.latest_setpoint is not None
                 and controller.latest_setpoint.header.stamp == stale.header.stamp,
                 'stale Setpoint')
        result['stale_source_age_at_controller_s'] = time.time() - (
            stale.header.stamp.sec + stale.header.stamp.nanosec * 1e-9)
        count = len(efforts)
        controller._on_timer()
        wait_for(lambda: len(efforts) > count, 'stale output')
        result['stale_effort_percent'] = float(efforts[-1].thrust_percent)
        result['stale_effort_note'] = efforts[-1].note

        fresh = Setpoint()
        stamp_at(time.time(), fresh.header.stamp)
        fresh.mode = stale.mode
        fresh.track_cable = True
        fresh.target_depth_m = 10.
        fresh.target_speed_mps = .3
        fresh.target_heading_rad = 0.
        setpoint_pub.publish(fresh)
        wait_for(lambda: controller.latest_setpoint.header.stamp == fresh.header.stamp,
                 'fresh Setpoint')
        result['fresh_source_age_at_controller_s'] = time.time() - (
            fresh.header.stamp.sec + fresh.header.stamp.nanosec * 1e-9)
        count = len(efforts)
        controller._on_timer()
        wait_for(lambda: len(efforts) > count, 'fresh output')
        result['fresh_effort_percent'] = float(efforts[-1].thrust_percent)
        result['fresh_effort_note'] = efforts[-1].note
        result['passed'] = (result['controller_source_matches_installed']
                            and result['stale_effort_percent'] == 0.
                            and result['stale_effort_note'] == 'inspection_setpoint_source_stale'
                            and result['fresh_effort_percent'] > 0.)
    except Exception as exc:
        result['passed'] = False
        result['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        executor.remove_node(controller)
        executor.remove_node(peer)
        controller.destroy_node()
        peer.destroy_node()
        executor.shutdown()
        rclpy.shutdown()
    (args.output_dir / 'summary.json').write_text(json.dumps(result, indent=2) + '\n',
                                                   encoding='utf-8')
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 2)


if __name__ == '__main__':
    main()
