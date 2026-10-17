#!/usr/bin/env python3
"""Local UDP proof that fresh PID commands cannot outlive an inspection Setpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import Bool
from auv_interfaces.msg import MpcCmd, Setpoint
import yaml

from auv_cable_tracking_v2.inspection_bridge_node import InspectionBridgeNode
from common.enums import ArbiterMode, ControlModeByte
from common.protocol import (KEY_BOTTOM, KEY_CONTROL_MODE_BYTE, KEY_LEFT, KEY_RIGHT,
                             KEY_THRUST, KEY_TOP, KEY_TOTAL_VOLTAGE_V,
                             parse_downlink_packet_to_payload)


ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def zero(payload: dict) -> bool:
    return all(abs(float(payload[key])) <= .1 for key in
               (KEY_THRUST, KEY_LEFT, KEY_RIGHT, KEY_TOP, KEY_BOTTOM))


def run(output_dir: Path) -> dict:
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        raise RuntimeError('use localhost-only and a dedicated ROS domain')
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    template = ROOT / 'brain_linux/src/auv_cable_tracking_v2/config/inspection_bridge_passive.yaml'
    config = yaml.safe_load(template.read_text(encoding='utf-8'))
    sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sink.bind(('127.0.0.1', 0))
    sink.settimeout(3.)
    config['bridge']['protocol_udp']['remote_port'] = sink.getsockname()[1]
    config_path = output_dir / 'bridge_loopback.yaml'
    config_path.write_text(yaml.safe_dump(config), encoding='utf-8')

    rclpy.init(args=['--ros-args', '-p', f'params_file:={config_path}',
                     '-p', 'passive_mode:=false', '-p', 'bridge_backend:=protocol_udp',
                     '-p', 'inspection_setpoint_timeout_s:=0.5'])
    bridge = InspectionBridgeNode()
    bridge._command_keepalive_timer.cancel()
    peer = Node('inspection_setpoint_gate_probe')
    setpoint_pub = peer.create_publisher(Setpoint, '/auv/control/setpoint', 10)
    budget_pub = peer.create_publisher(Bool, '/auv/cable/recovery_required', 10)
    cmd_pub = peer.create_publisher(MpcCmd, '/auv/control/mpc_cmd', 10)
    executor = SingleThreadedExecutor()
    executor.add_node(bridge)
    executor.add_node(peer)
    packets = []

    def receive(stage: str) -> dict:
        raw, _ = sink.recvfrom(2048)
        payload = parse_downlink_packet_to_payload(raw)
        packets.append({'stage': stage, 'elapsed_s': time.monotonic() - started,
                        'packet_hex': raw.hex(), 'payload': payload,
                        'bridge_stop_reason': bridge._inspection_authority_problem(),
                        'arbiter_source': bridge.last_arbiter_decision.arbiter_source.value})
        return payload

    def spin_until(predicate, deadline_s: float = 4.) -> None:
        deadline = time.monotonic() + deadline_s
        while not predicate():
            if time.monotonic() >= deadline:
                raise TimeoutError('DDS input did not reach bridge')
            executor.spin_once(timeout_sec=.02)

    def send_setpoint(*, hold: bool) -> None:
        before = bridge._setpoint_seen_wall_time_s
        msg = Setpoint()
        msg.mode = 'CABLE_TRACKING_DEGRADED_HOLD' if hold else 'CABLE_TRACKING'
        msg.track_cable = not hold
        msg.target_depth_m = 10.
        msg.target_heading_rad = 0.
        msg.target_speed_mps = 0. if hold else .3
        setpoint_pub.publish(msg)
        spin_until(lambda: bridge._setpoint_seen_wall_time_s > before)

    def send_cmd(stage: str) -> dict:
        bridge.latest_protocol_telemetry_ts = time.time()
        before_budget = bridge._budget_seen_wall_time_s
        budget_pub.publish(Bool(data=False))
        spin_until(lambda: bridge._budget_seen_wall_time_s > before_budget)
        msg = MpcCmd()
        msg.header.stamp = bridge.get_clock().now().to_msg()
        msg.source, msg.valid, msg.healthy = 'INSPECTION_GATE_PROBE', True, True
        msg.thrust_percent = 25.
        msg.target_depth_m = 10.
        cmd_pub.publish(msg)
        before_count = bridge._operational_command_sequence
        spin_until(lambda: bridge._operational_command_sequence > before_count)
        return receive(stage)

    started = time.monotonic()
    try:
        bridge.latest_sensor_status_payload.update(confidence=1., leak_level=0)
        bridge.latest_bridge_telemetry_payload = {KEY_TOTAL_VOLTAGE_V: 50.}
        bridge.latest_protocol_telemetry_ts = time.time()
        pc = {KEY_CONTROL_MODE_BYTE: int(ControlModeByte.JETSON_PROTOCOL),
              'work_instruction': 0, KEY_THRUST: 0., KEY_RIGHT: 0.,
              KEY_TOP: 0., KEY_LEFT: 0., KEY_BOTTOM: 0.}
        bridge.handle_pc_raw_command(pc)
        assert zero(receive('autonomy_request'))
        assert bridge.command_arbiter.active_mode == ArbiterMode.AUTONOMOUS
        spin_until(lambda: all(pub.get_subscription_count() >= 1 for pub in
                               (setpoint_pub, budget_pub, cmd_pub)))

        send_setpoint(hold=False)
        active = send_cmd('fresh_setpoint_fresh_pid')
        assert active[KEY_THRUST] > 0 and bridge._inspection_authority_problem() is None

        # Keep sending *fresh* PID commands and budget heartbeats, but do not
        # refresh the upstream algorithm Setpoint.
        while time.monotonic() - bridge._setpoint_seen_wall_time_s <= .55:
            time.sleep(.05)
        stale = send_cmd('stale_setpoint_fresh_pid')
        assert zero(stale)
        assert bridge.last_arbiter_decision.arbiter_source.value == 'SAFETY_FALLBACK'
        assert packets[-1]['bridge_stop_reason'] == 'inspection_setpoint_stale'

        # The periodic command keepalive must reapply the same independent
        # Setpoint gate even while the just-received PID command remains fresh.
        assert bridge.command_arbiter.decide(now=time.time()).mpc_command_valid
        bridge._on_command_keepalive()
        kept_zero = receive('stale_setpoint_keepalive')
        assert zero(kept_zero) and packets[-1]['bridge_stop_reason'] == 'inspection_setpoint_stale'

        send_setpoint(hold=True)
        held = send_cmd('explicit_hold_fresh_pid')
        assert zero(held) and packets[-1]['bridge_stop_reason'] == 'inspection_setpoint_hold'

        summary = {
            'role': 'installed_inspection_bridge_setpoint_provenance_gate_loopback',
            'stages': [item['stage'] for item in packets],
            'fresh_setpoint_fresh_pid_thrust_percent': active[KEY_THRUST],
            'stale_setpoint_fresh_pid_zero': zero(stale),
            'stale_setpoint_keepalive_zero': zero(kept_zero),
            'explicit_hold_fresh_pid_zero': zero(held),
            'source_bridge_sha256': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_bridge_node.py'),
            'probe_sha256': sha(Path(__file__)),
            'config_sha256': sha(config_path),
            'local_udp_only': True, 'pc104_connected': False, 'vehicle_connected': False,
        }
        installed = ROOT / 'brain_linux/install/auv_cable_tracking_v2/lib/python3.10/site-packages/auv_cable_tracking_v2/inspection_bridge_node.py'
        summary['installed_bridge_sha256'] = sha(installed)
        assert summary['installed_bridge_sha256'] == summary['source_bridge_sha256']
        (output_dir / 'packets.json').write_text(json.dumps(packets, indent=2) + '\n', encoding='utf-8')
        (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        return summary
    finally:
        executor.remove_node(bridge)
        executor.remove_node(peer)
        bridge.destroy_node()
        peer.destroy_node()
        executor.shutdown()
        if rclpy.ok():
            rclpy.shutdown()
        sink.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir)))


if __name__ == '__main__':
    main()
