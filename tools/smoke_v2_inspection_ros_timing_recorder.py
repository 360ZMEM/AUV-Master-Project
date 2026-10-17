#!/usr/bin/env python3
"""Isolated DDS smoke for the read-only inspection timing recorder."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import rclpy
from rclpy.node import Node
from auv_interfaces.msg import MpcCmd, Setpoint
from nav_msgs.msg import Odometry
from sensor_msgs.msg import MagneticField
from std_msgs.msg import String


TOPICS = {
    'setpoint': ('/auv/control/setpoint', Setpoint),
    'candidate': ('/auv/control/setpoint_candidate', Setpoint),
    'pid': ('/auv/control/mpc_cmd', MpcCmd),
    'navigation': ('/auv/state/filtered', Odometry),
    'magnetic': ('/auv/sensors/magnetic', MagneticField),
    'status': ('/auv/cable/operational_status', String),
}


def stamp(msg, *, valid: bool) -> None:
    ns = time.time_ns() - 30_000_000 if valid else 0
    msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(ns, 1_000_000_000)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def run_case(root: Path, name: str, *, valid_epoch: bool) -> dict:
    output = root / name
    command = [sys.executable, str(Path(__file__).with_name(
        'record_v2_inspection_ros_timing.py')), '--output-dir', str(output),
        '--session-id', name, '--duration-s', '30']
    capture = subprocess.Popen(command, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    node = Node(f'inspection_timing_smoke_{name}')
    pubs = {name: node.create_publisher(msg_type, topic, 100)
            for name, (topic, msg_type) in TOPICS.items()}
    try:
        deadline = time.monotonic() + 20.
        while time.monotonic() < deadline:
            if all(pub.get_subscription_count() >= 1 for pub in pubs.values()):
                break
            if capture.poll() is not None:
                stdout, stderr = capture.communicate()
                raise RuntimeError(f'recorder exited before DDS match: {stderr}')
            time.sleep(.05)
        else:
            counts = {name: pub.get_subscription_count() for name, pub in pubs.items()}
            raise RuntimeError(f'DDS recorder subscribers did not all match: {counts}; '
                               f'child_exit={capture.poll()}')
        for i in range(12):
            candidate = Setpoint()
            stamp(candidate, valid=valid_epoch)
            candidate.target_speed_mps = .2
            candidate.mode = 'SMOKE'
            candidate.note = f'candidate-{i}'
            pubs['candidate'].publish(candidate)

            final = Setpoint()
            stamp(final, valid=valid_epoch)
            if valid_epoch and i == 11:
                # A well-formed system-epoch header can still be stale at DDS receipt.
                stale_ns = time.time_ns() - 1_030_000_000
                final.header.stamp.sec, final.header.stamp.nanosec = divmod(
                    stale_ns, 1_000_000_000)
            final.target_speed_mps = .2
            final.mode = 'SMOKE'
            final.note = f'final-{i}'
            pubs['setpoint'].publish(final)

            pid = MpcCmd()
            stamp(pid, valid=valid_epoch)
            pid.thrust_percent = 10.
            pid.valid = True
            pid.healthy = True
            pid.note = f'pid-{i}'
            pubs['pid'].publish(pid)

            nav = Odometry()
            stamp(nav, valid=valid_epoch)
            nav.pose.pose.position.x = float(i)
            pubs['navigation'].publish(nav)

            magnetic = MagneticField()
            stamp(magnetic, valid=valid_epoch)
            magnetic.magnetic_field.x = 1e-9 * i
            pubs['magnetic'].publish(magnetic)

            status = String()
            status.data = json.dumps({'smoke_index': i})
            pubs['status'].publish(status)
            time.sleep(.06)
        time.sleep(.4)
        capture.send_signal(signal.SIGTERM)
        stdout, stderr = capture.communicate(timeout=12.)
    finally:
        node.destroy_node()
        if capture.poll() is None:
            capture.terminate()
            try:
                capture.communicate(timeout=5.)
            except subprocess.TimeoutExpired:
                capture.kill()
                capture.communicate(timeout=5.)
    if capture.returncode != 0:
        raise RuntimeError(f'recorder exited {capture.returncode}: {stderr}')
    summary = json.loads((output / 'capture_summary.json').read_text())
    final_rows = read_csv(output / 'ros_setpoint.csv')
    pid_rows = read_csv(output / 'pid.csv')
    assert len(final_rows) == len(pid_rows) == 12
    assert summary['capture_complete'] is True
    assert summary['dropped'] == {}
    assert summary['max_setpoint_publishers_seen'] == 1
    assert len(summary['files_sha256']) == 7
    if valid_epoch:
        assert summary['data_reviewable'] is True
        assert summary['positive_setpoint_source_reviewable'] is True
        assert summary['implausible_source_stamps'] == {}
        ages = [float(row['time_s']) - float(row['candidate_source_time_s'])
                for row in final_rows]
        raw_ages = [float(row['wall_received_s']) - float(row['header_stamp_s'])
                    for row in final_rows]
        assert all(0.01 <= age < 30. for age in ages), ages
        assert all(abs(age - raw) < .001 for age, raw in zip(ages, raw_ages))
        assert max(ages) >= 1., ages
    else:
        assert summary['data_reviewable'] is False
        assert summary['positive_setpoint_source_reviewable'] is False
        assert summary['implausible_source_stamps'].get('ros_setpoint') == 12
    return {'case': name, 'summary': str(output / 'capture_summary.json'),
            'capture_complete': summary['capture_complete'],
            'data_reviewable': summary['data_reviewable'],
            'setpoint_rows': len(final_rows), 'pid_rows': len(pid_rows),
            'implausible_source_stamps': summary['implausible_source_stamps'],
            'maximum_positive_setpoint_source_age_s':
                max((float(row['source_age_at_receipt_s']) for row in final_rows),
                    default=None)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', required=True, type=Path)
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=False)
    os.environ['ROS_LOCALHOST_ONLY'] = '1'
    os.environ.setdefault('ROS_DOMAIN_ID', str(200 + os.getpid() % 20))
    rclpy.init()
    try:
        cases = [run_case(args.output_root, 'valid_epoch', valid_epoch=True),
                 run_case(args.output_root, 'invalid_epoch', valid_epoch=False)]
    finally:
        rclpy.shutdown()
    result = {'synthetic_dds_only': True, 'ros_domain_id': os.environ['ROS_DOMAIN_ID'],
              'cases': cases, 'passed': True, 'field_release_authorized': False}
    (args.output_root / 'smoke_summary.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
