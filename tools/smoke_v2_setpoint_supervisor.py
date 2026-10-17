#!/usr/bin/env python3
"""Installed-process ROS smoke for the opt-in candidate-to-Setpoint gate.

Only synthetic inputs and the supervisor are present; this is a timing and
fail-closed test, not an algorithm, bridge, plant, or vehicle acceptance test.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

import rclpy
from rclpy.node import Node
from auv_interfaces.msg import Setpoint
from nav_msgs.msg import Odometry
from sensor_msgs.msg import MagneticField
from std_msgs.msg import Bool, Float32MultiArray, String


ROOT = Path(__file__).resolve().parents[1]
EXECUTABLE = ROOT / 'brain_linux/install/auv_cable_tracking_v2/lib/auv_cable_tracking_v2/inspection_setpoint_supervisor_node'


def run(output: Path) -> dict:
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        raise RuntimeError('use ROS_LOCALHOST_ONLY=1 and an isolated ROS_DOMAIN_ID')
    rclpy.init()
    output.mkdir(parents=True, exist_ok=False)
    log = (output / 'supervisor.log').open('w', encoding='utf-8')
    proc = subprocess.Popen([str(EXECUTABLE)], cwd=ROOT, env=os.environ.copy(),
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    peer = Node('inspection_supervisor_smoke_fixture')
    candidate_pub = peer.create_publisher(Setpoint, '/auv/control/setpoint_candidate', 10)
    nav_pub = peer.create_publisher(Odometry, '/auv/state/filtered', 10)
    mag_pub = peer.create_publisher(MagneticField, '/auv/sensors/magnetic', 10)
    cov_pub = peer.create_publisher(Float32MultiArray, '/auv/state/covariance', 10)
    budget_pub = peer.create_publisher(Bool, '/auv/cable/recovery_required', 10)
    rows = []
    phase = 'startup'
    phase_start = time.monotonic()

    def on_setpoint(msg):
        rows.append({'time_s': time.monotonic(), 'phase': phase, 'topic': 'setpoint',
                     'speed_mps': float(msg.target_speed_mps), 'value': msg.note})

    def on_reason(msg):
        rows.append({'time_s': time.monotonic(), 'phase': phase, 'topic': 'reason',
                     'speed_mps': '', 'value': msg.data})

    peer.create_subscription(Setpoint, '/auv/control/setpoint', on_setpoint, 10)
    peer.create_subscription(String, '/auv/cable/setpoint_supervisor_reason', on_reason, 10)
    phase_starts = {}
    input_counts = {}
    phases = [('healthy', 3.), ('candidate_dropout', 1.), ('sensor_dropout', 1.),
              ('restored', 1.), ('budget_latch', 1.)]
    error = None
    try:
        deadline = time.monotonic() + 12.
        while candidate_pub.get_subscription_count() < 1:
            if proc.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('supervisor not discovered')
            rclpy.spin_once(peer, timeout_sec=.05)
        covariance = [0.] * 225
        covariance[0] = covariance[16] = covariance[48] = covariance[64] = covariance[128] = .01
        for phase, duration in phases:
            phase_start = time.monotonic()
            phase_starts[phase] = phase_start
            input_counts[phase] = 0
            next_publish = phase_start
            while time.monotonic() - phase_start < duration:
                if proc.poll() is not None:
                    raise RuntimeError(f'supervisor exited: {proc.returncode}')
                now = time.monotonic()
                if now >= next_publish:
                    input_counts[phase] += 1
                    if phase not in ('candidate_dropout',):
                        sp = Setpoint()
                        sp.header.stamp = peer.get_clock().now().to_msg()
                        sp.mode = 'CABLE_TRACKING'
                        sp.track_cable = True
                        sp.target_speed_mps = .3
                        sp.target_depth_m = 10.
                        candidate_pub.publish(sp)
                    if phase != 'sensor_dropout':
                        nav = Odometry()
                        nav.header.stamp = peer.get_clock().now().to_msg()
                        nav.pose.pose.orientation.w = 1.
                        nav.pose.pose.position.z = -10.
                        nav_pub.publish(nav)
                        mag = MagneticField()
                        mag.header.stamp = nav.header.stamp
                        mag_pub.publish(mag)
                        cov_pub.publish(Float32MultiArray(data=covariance))
                    budget_pub.publish(Bool(data=phase == 'budget_latch'))
                    next_publish = now + .1
                rclpy.spin_once(peer, timeout_sec=.02)
        for _ in range(10):
            rclpy.spin_once(peer, timeout_sec=.02)
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
    finally:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5.)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5.)
        peer.destroy_node()
        rclpy.shutdown()
        log.close()

    with (output / 'events.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=('time_s', 'phase', 'topic', 'speed_mps', 'value'))
        writer.writeheader()
        writer.writerows(rows)
    results = {}
    for name, _ in phases:
        selected = [row for row in rows if row['phase'] == name and row['topic'] == 'setpoint']
        positive = [row for row in selected if row['speed_mps'] > 0.]
        # 0.5 s input expiry + one 0.1 s output cycle + ROS delivery margin.
        settled = [row for row in selected if row['time_s'] >= phase_starts[name] + .75]
        results[name] = {'input_publish_count': input_counts.get(name, 0),
                         'count': len(selected), 'positive': len(positive),
                         'settled_zero': bool(settled) and all(row['speed_mps'] == 0. for row in settled)}
    times = [row['time_s'] for row in rows if row['topic'] == 'setpoint']
    max_gap = max((b-a for a,b in zip(times, times[1:])), default=float('inf'))
    passed = (error is None and proc.returncode == 0 and
              results['healthy']['input_publish_count'] >= 24 and
              results['healthy']['count'] >= 24 and
              results['healthy']['positive'] == results['healthy']['count'] and
              results['candidate_dropout']['settled_zero'] and
              results['sensor_dropout']['settled_zero'] and
              results['restored']['input_publish_count'] >= 8 and
              results['restored']['count'] >= 8 and
              results['restored']['positive'] >= 6 and
              results['budget_latch']['settled_zero'] and max_gap <= .3)
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    summary = {'role': 'isolated_supervisor_ros_smoke', 'passed': passed,
               'error': error, 'ros_domain_id': os.environ['ROS_DOMAIN_ID'],
               'max_output_gap_s': max_gap, 'phases': results,
               'probe_sha256': sha(Path(__file__)),
               'installed_supervisor_sha256': sha(ROOT / 'brain_linux/install/auv_cable_tracking_v2/lib/python3.10/site-packages/auv_cable_tracking_v2/inspection_setpoint_supervisor_node.py'),
               'algorithm_connected': False, 'controller_connected': False,
               'bridge_connected': False, 'hardware_connected': False}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    result = run(args.output_dir)
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 2)
