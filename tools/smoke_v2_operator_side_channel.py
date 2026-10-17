#!/usr/bin/env python3
"""Loopback v2 bridge decision -> Zenoh -> PySide6 without AMD uplink."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'brain_linux/src/auv_cable_tracking_v2'),
                str(ROOT / 'console_soft/auv_console_pyside6')]

import rclpy
import yaml
from PySide6.QtWidgets import QApplication
from std_msgs.msg import String

from auv_cable_tracking_v2.inspection_bridge_node import InspectionBridgeNode
from common.protocol import KEY_CONFIDENCE, KEY_LEAK_LEVEL, KEY_TELEMETRY_FRESHNESS_MS, KEY_TOTAL_VOLTAGE_V
from src.ui.main_window import MainWindow


DEFAULT_OUT = ROOT / 'AUV-Master-Mag/results/v2/operator_chain/direct_status_no_uplink'


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return int(probe.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = args.output_dir
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        raise RuntimeError('use ROS_LOCALHOST_ONLY=1 and an isolated ROS_DOMAIN_ID')
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    out.mkdir(parents=True, exist_ok=True)
    os.environ['AUV_DATA_ROOT'] = str(out / 'bridge_data')
    (out / 'bridge_data').mkdir(exist_ok=True)
    zenoh_port = free_port()
    console_udp_port = free_port()
    udp_sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sink.bind(('127.0.0.1', 0))

    bridge_cfg = yaml.safe_load((ROOT / 'brain_linux/src/auv_cable_tracking_v2/config/inspection_bridge_passive.yaml').read_text())
    bridge_cfg['bridge']['passive_mode'] = False
    bridge_cfg['bridge']['protocol_udp']['remote_port'] = udp_sink.getsockname()[1]
    bridge_cfg['bridge']['protocol_udp']['zenoh_side_channel_enabled'] = True
    bridge_cfg['bridge']['protocol_udp']['zenoh_session_config'] = {
        'mode': 'peer', 'listen/endpoints': [f'tcp/127.0.0.1:{zenoh_port}']}
    bridge_cfg_path = out / 'bridge_params.yaml'
    bridge_cfg_path.write_text(yaml.safe_dump(bridge_cfg), encoding='utf-8')

    console_cfg = yaml.safe_load((ROOT / 'console_soft/auv_console_pyside6/console_config.defense.yaml').read_text())
    console_cfg['zenoh'].update({'router_ip': '127.0.0.1', 'router_port': zenoh_port,
                                 'mode': 'client', 'publish_cmd_raw': False,
                                 'subscribe_bridge_telemetry': True})
    console_cfg['udp']['local_port'] = console_udp_port
    console_cfg_path = out / 'console_loopback.yaml'
    console_cfg_path.write_text(yaml.safe_dump(console_cfg, allow_unicode=True), encoding='utf-8')

    app = QApplication([])
    rclpy.init(args=['--ros-args', '-p', f'auv_inspection_bridge_node:params_file:={bridge_cfg_path}',
                     '-p', 'auv_inspection_bridge_node:passive_mode:=false'])
    bridge = None
    window = None
    try:
        bridge = InspectionBridgeNode()
        window = MainWindow(config_file=str(console_cfg_path))
        assert window.comm_manager.side_channel.is_active
        bridge._on_localization_status(String(data='LOCALIZED_DEPTH_PENDING'))
        bridge._on_cable_tracking(String(data=json.dumps({
            'mode': 'track', 'industrial_ready': False, 'cross_track_m': 0.4,
            'burial_depth_m': None, 'confidence': .9, 'magnetic_snr_db': 18.,
            'diagnostics': {'burial_status': 'depth_not_calibrated'},
        })))
        guard = bridge.autonomy_guard.request_activation(
            sensor_status={KEY_CONFIDENCE: 1., KEY_LEAK_LEVEL: 0},
            telemetry_status={KEY_TOTAL_VOLTAGE_V: 52., KEY_TELEMETRY_FRESHNESS_MS: 1000.},
        )
        assert guard.deny_reason.value == 'AMD_UPLINK_STALE'
        bridge._publish_arbiter_status(guard_decision=guard)
        monitor = bridge.latest_cable_monitor_payload
        assert monitor['operational_status']['localization_status'] == 'LOCALIZED_DEPTH_PENDING'
        assert monitor['operational_status']['authority_reason'] == 'AMD_UPLINK_STALE'
        expected = '定位: 已定位（埋深未许可） | 自治许可: 禁止（上行失鲜）'
        deadline = time.monotonic() + 8.
        while time.monotonic() < deadline and window.lbl_inspection_authority.text() != expected:
            app.processEvents()
            time.sleep(.02)
        assert window.lbl_inspection_authority.text() == expected
        window.tab_widget.setCurrentIndex(3)
        window.show()
        app.processEvents()
        screenshot = out / 'console_inspection_authority.png'
        window.grab().save(str(screenshot))
        # A duplicate cached telemetry payload must not preserve green authority.
        window._inspection_operational_view._last_receive_monotonic_s -= 2.
        bridge.transport.publish_bridge_telemetry({
            'message_type': 'inspection_operational_status',
            'active_arbiter': monitor['operational_status']['arbiter_mode'],
            'auto_state': monitor['operational_status']['guard_state'],
            'deny_reason': monitor['operational_status']['guard_reason'],
            'cable_monitor': {'operational_status': monitor['operational_status']},
        })
        deadline = time.monotonic() + .5
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.02)
        window.refresh_inspection_authority_display()
        assert '状态失鲜' in window.lbl_inspection_authority.text()
        summary = {'role': 'synthetic_loopback_inspection_bridge_zenoh_pyside6',
                   'bridge_to_console_received': True,
                   'direct_status_without_amd_uplink': True,
                   'denied_label': expected,
                   'duplicate_stale_label': window.lbl_inspection_authority.text(),
                   'hardware_connected': False,
                   'screenshot': screenshot.name}
        (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(summary, ensure_ascii=False))
    finally:
        if window is not None:
            window.close()
        if bridge is not None:
            bridge.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        udp_sink.close()
        app.quit()


if __name__ == '__main__':
    main()
