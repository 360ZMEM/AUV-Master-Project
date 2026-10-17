#!/usr/bin/env python3
"""Save one isolated synthetic $AUV + IMV1 -> ROS -> ES-EKF observation.

Requires the ROS Humble workspace environment. It never sends actuator
commands: the bridge profile is passive and binds only to loopback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'brain_linux/src/auv_cable_tracking_v2'),
                str(ROOT / 'brain_linux/src/auv_bridge')]

import rclpy  # noqa: E402
from geometry_msgs.msg import TwistStamped  # noqa: E402
from nav_msgs.msg import Odometry  # noqa: E402
from rclpy.parameter import Parameter  # noqa: E402
from sensor_msgs.msg import Imu  # noqa: E402
from std_msgs.msg import Float32  # noqa: E402
import yaml  # noqa: E402

from common.imu_provenance_sidecar import ImuProvenanceV1, encode_imu_provenance  # noqa: E402
from common.protocol import build_uplink_packet  # noqa: E402
from auv_cable_tracking_v2.imu_sidecar_node import ImuSidecarNode  # noqa: E402
from auv_cable_tracking_v2.inspection_bridge_node import InspectionBridgeNode  # noqa: E402
from auv_localization.auv_localization_node import AUVLocalizationNode  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reserve:
        reserve.bind(('127.0.0.1', 0))
        return reserve.getsockname()[1]


def spin(nodes, duration_s: float) -> None:
    end = time.monotonic() + duration_s
    while time.monotonic() < end:
        for node in nodes:
            rclpy.spin_once(node, timeout_sec=.002)


def sidecar_frame(sequence: int, uptime: int) -> bytes:
    return encode_imu_provenance(ImuProvenanceV1(
        frame_checksum_u16=0x1234, sample_sequence=sequence,
        sensor_timer_ticks=100000 + (uptime - 1000) * 62500 // 1000,
        pc104_receive_uptime_ms=uptime,
        roll_rad=0., pitch_rad=0., yaw_rad=0.,
        angular_rate_x_rps=0., angular_rate_y_rps=0., angular_rate_z_rps=0.))


def run(output: Path) -> dict:
    bridge_port, sidecar_port = free_port(), free_port()
    config_path = (ROOT / 'brain_linux/src/auv_cable_tracking_v2/config'
                   / 'inspection_bridge_sidecar_candidate.yaml')
    profile = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    profile['bridge']['protocol_udp']['local_port'] = bridge_port
    profile['ekf'] = {'imu_acc_is_linear': True}
    profile['localization'] = {'use_imu_orientation_measurement': True}
    with tempfile.TemporaryDirectory(prefix='auv_sidecar_dvl_') as temporary:
        params_path = Path(temporary) / 'params.yaml'
        params_path.write_text(yaml.safe_dump(profile), encoding='utf-8')
        rclpy.init(args=['--ros-args', '-p', f'params_file:={params_path}',
                         '-p', 'passive_mode:=true',
                         '-p', 'navigation_imu_max_age_s:=0.75'])
        bridge = sidecar = localization = observer = None
        try:
            bridge = InspectionBridgeNode()
            sidecar = ImuSidecarNode(parameter_overrides=[
                Parameter('local_port', value=sidecar_port),
                Parameter('publish_navigation_imu', value=True),
                Parameter('synthetic_fixture_only', value=True),
                Parameter('yaw_alignment_deg', value=90.0),
                Parameter('synthetic_orientation_variance_rad2', value=.01),
            ])
            localization = AUVLocalizationNode()
            observer = rclpy.create_node('sidecar_dvl_evidence_observer')
            received = {name: [] for name in ('imu', 'dvl', 'depth', 'odom')}
            observer.create_subscription(Imu, '/auv/sensors/imu', received['imu'].append, 10)
            observer.create_subscription(TwistStamped, '/auv/sensors/dvl', received['dvl'].append, 10)
            observer.create_subscription(Float32, '/auv/sensors/depth', received['depth'].append, 10)
            observer.create_subscription(Odometry, '/auv/state/filtered', received['odom'].append, 10)
            nodes = (sidecar, localization, observer)
            spin(nodes, .3)
            parameters = [0, 0, 0, 0, 300, 0, 0, 0, 0, 0, 0, 0]
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                sender.sendto(build_uplink_packet(
                    frame_counter=0, heading_deg=0., depth_m=3.,
                    parameter_values=parameters, pc104_uptime_ms=1000),
                    ('127.0.0.1', bridge_port))
                spin(nodes, .1)
                old_only = {name: len(received[name]) for name in ('imu', 'dvl', 'depth')}
                assert old_only == {'imu': 0, 'dvl': 0, 'depth': 1}
                sender.sendto(sidecar_frame(10, 1000), ('127.0.0.1', sidecar_port))
                spin(nodes, .1)
                for step in range(1, 8):
                    uptime = 1000 + step * 100
                    sender.sendto(build_uplink_packet(
                        frame_counter=step, heading_deg=0., depth_m=3.,
                        parameter_values=parameters,
                        pc104_uptime_ms=uptime, dvl_bi_uptime_ms=uptime),
                        ('127.0.0.1', bridge_port))
                    spin(nodes, .02)
                    sender.sendto(sidecar_frame(10 + step, uptime),
                                  ('127.0.0.1', sidecar_port))
                    spin(nodes, .08)
            good_counts = {name: len(items) for name, items in received.items()}
            assert good_counts['imu'] == 7 and good_counts['dvl'] == 7
            assert good_counts['odom'] > 0
            dvl_values = [[msg.twist.linear.x, msg.twist.linear.y,
                           msg.twist.linear.z] for msg in received['dvl']]
            odom_velocity = [received['odom'][-1].twist.twist.linear.x,
                             received['odom'][-1].twist.twist.linear.y,
                             received['odom'][-1].twist.twist.linear.z]
            assert all(abs(x) < 1e-6 and abs(y-.3) < 1e-6
                       for x, y, _ in dvl_values)
            assert abs(odom_velocity[0]) < .1 and abs(odom_velocity[1]-.3) < .1
            spin(nodes, 1.)
            after_grace = len(received['odom'])
            spin(nodes, .3)
            stale_window_new_odom = len(received['odom']) - after_grace
            assert stale_window_new_odom == 0
        finally:
            if observer is not None:
                observer.destroy_node()
            if localization is not None:
                localization.destroy_node()
            if sidecar is not None:
                sidecar.destroy_node()
            if bridge is not None:
                bridge.destroy_node()
            rclpy.shutdown()
    result = {
        'role': 'synthetic_passive_loopback_sidecar_dvl_to_existing_eskf',
        'checks_passed': True,
        'old_uplink_only_counts': old_only,
        'matched_sample_counts': good_counts,
        'world_dvl_velocity_xyz_mps': dvl_values,
        'last_filtered_velocity_xyz_mps': odom_velocity,
        'stale_window_new_odom_count': stale_window_new_odom,
        'fixture': {'legacy_heading_deg': 0., 'sidecar_yaw_alignment_deg': 90.,
                    'body_dvl_forward_mps': .3, 'sample_count': 7,
                    'navigation_imu_max_age_s': .75,
                    'synthetic_orientation_variance_rad2': .01},
        'source_sha256': {
            'probe': sha(Path(__file__)),
            'bridge': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_bridge_node.py'),
            'sidecar_node': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/imu_sidecar_node.py'),
            'dvl_join': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/dvl_sidecar_join.py'),
            'localization': sha(ROOT / 'brain_linux/src/auv_localization/auv_localization/auv_localization_node.py'),
            'profile': sha(config_path),
        },
        'physical_imu_or_dvl_tested': False,
        'field_release_authorized': False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=(
        ROOT / 'AUV-Master-Mag/results/v2/inspection_imu_sidecar_dvl_join_20260927/fixture.json'))
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({'output': str(args.output),
                      'counts': result['matched_sample_counts'],
                      'velocity_mps': result['last_filtered_velocity_xyz_mps']},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
