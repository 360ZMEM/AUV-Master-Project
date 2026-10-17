#!/usr/bin/env python3
"""Independent 10 Hz stationary synthetic ROS feeder for inspection timing probes."""
import argparse
import json
import math
import os
from pathlib import Path
import time

import numpy as np
import rclpy
from rclpy.node import Node
from auv_interfaces.msg import ArbiterStatus
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import MagneticField
from std_msgs.msg import Float32MultiArray, String


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', required=True, type=Path)
    parser.add_argument('--prewarm-s', type=float, default=5.)
    parser.add_argument('--healthy-s', type=float, default=5.)
    parser.add_argument('--dropout-s', type=float, default=3.)
    parser.add_argument('--recovery-s', type=float, default=4.)
    parser.add_argument('--startup-timeout-s', type=float, default=60.)
    parser.add_argument('--mission-speed-mps', type=float, default=.3)
    parser.add_argument('--wall-time-stamps', action='store_true',
                        help='stamp sensors with the system clock for use_sim_time=false probes')
    args = parser.parse_args()
    if not math.isfinite(args.mission_speed_mps) or args.mission_speed_mps <= 0.:
        parser.error('mission-speed-mps must be finite and positive')
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        raise RuntimeError('isolated ROS domain and localhost only required')
    rclpy.init()
    node = Node('inspection_fixed_sensor_feeder')
    mission_pub = node.create_publisher(String, '/auv/cable/mission_command', 10)
    clock_pub = node.create_publisher(Clock, '/clock', 10)
    nav_pub = node.create_publisher(Odometry, '/auv/state/filtered', 10)
    mag_pub = node.create_publisher(MagneticField, '/auv/sensors/magnetic', 10)
    cov_pub = node.create_publisher(Float32MultiArray, '/auv/state/covariance', 10)
    arbiter_pub = node.create_publisher(ArbiterStatus, '/auv/arbiter/status', 10)
    start = time.monotonic()
    events = []
    try:
        while True:
            ready = (mission_pub.get_subscription_count() >= 1
                     and (args.wall_time_stamps or clock_pub.get_subscription_count() >= 2)
                     and nav_pub.get_subscription_count() >= 2
                     and mag_pub.get_subscription_count() >= 2
                     and cov_pub.get_subscription_count() >= 2
                     and arbiter_pub.get_subscription_count() >= 1)
            if ready:
                break
            if time.monotonic() - start > args.startup_timeout_s:
                raise TimeoutError('fixed feeder could not discover required subscriptions')
            time.sleep(.05)
        schedule = time.monotonic()
        next_tick = schedule
        mission_sent = False
        total = args.prewarm_s + args.healthy_s + args.dropout_s + args.recovery_s
        covariance = np.eye(15) * .0004
        covariance[0, 0] = covariance[1, 1] = .01
        covariance[8, 8] = math.radians(1.) ** 2
        while True:
            now = time.monotonic()
            elapsed = now - schedule
            if elapsed >= total:
                break
            if now < next_tick:
                time.sleep(min(.01, next_tick-now))
                continue
            phase = ('prewarm' if elapsed < args.prewarm_s else
                     'healthy' if elapsed < args.prewarm_s + args.healthy_s else
                     'dropout' if elapsed < args.prewarm_s + args.healthy_s + args.dropout_s else
                     'restored')
            stamp_s = time.time() if args.wall_time_stamps else 1. + elapsed
            stamp = Clock()
            stamp.clock.sec = int(stamp_s)
            stamp.clock.nanosec = int((stamp_s - int(stamp_s)) * 1e9)
            clock_pub.publish(stamp)
            arbiter_pub.publish(ArbiterStatus(active_arbiter='AUTONOMOUS', autonomy_allowed=True))
            if phase != 'dropout':
                nav = Odometry()
                nav.header.stamp = stamp.clock
                nav.header.frame_id = 'world'
                nav.pose.pose.position.x = -250.
                nav.pose.pose.position.y = -15.
                nav.pose.pose.position.z = -10.
                yaw = math.radians(10.)
                nav.pose.pose.orientation.z = math.sin(yaw / 2.)
                nav.pose.pose.orientation.w = math.cos(yaw / 2.)
                mag = MagneticField()
                mag.header.stamp = stamp.clock
                mag.magnetic_field.x = (1. + 20. / math.sqrt(1. + ((-15. - 6.) / 3.) ** 2)) * 1e-9
                nav_pub.publish(nav)
                mag_pub.publish(mag)
                cov_pub.publish(Float32MultiArray(data=covariance.reshape(-1).tolist()))
            if phase != 'prewarm' and not mission_sent:
                mission_pub.publish(String(data=json.dumps({
                    'mission_type': 'CABLE_INSPECTION', 'target_depth': 10.,
                    'target_speed_mps': args.mission_speed_mps,
                })))
                mission_sent = True
                events.append({'monotonic_s': now, 'phase': phase, 'event': 'mission'})
            events.append({'monotonic_s': now, 'phase': phase,
                           'event': 'sensor_tick' if phase != 'dropout' else 'clock_only_tick'})
            next_tick += .1
            if next_tick < now:
                next_tick = now + .1
        result = {'start_monotonic_s': schedule, 'completed': True,
                  'prewarm_s': args.prewarm_s, 'healthy_s': args.healthy_s,
                  'dropout_s': args.dropout_s, 'recovery_s': args.recovery_s,
                  'mission_speed_mps': args.mission_speed_mps,
                  'wall_time_stamps': args.wall_time_stamps,
                  'events': events}
        args.events.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
