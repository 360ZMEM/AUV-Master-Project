#!/usr/bin/env python3
"""Run one synthetic PVS guard-loss mission through the real Zenoh console.

The bridge's AMD uplink is a synthetic freshness fixture and PC104 is absent.
The decision-path operational status must still reach the console when that
uplink becomes stale. Existing pinned PVS and UI results are not overwritten.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'brain_linux/src/auv_cable_tracking_v2'),
                str(ROOT / 'console_soft/auv_console_pyside6')]

import yaml
from PySide6.QtWidgets import QApplication

import auv_cable_tracking_v2.inspection_bridge_node as bridge_module
from src.ui.main_window import MainWindow
import smoke_v2_flythrough_ros_pvs as flythrough


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return int(probe.getsockname()[1])


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'AUV-Master-Mag/results/v2/operator_chain/same_run_guard_loss')
    parser.add_argument('--seed', type=int, default=101)
    args = parser.parse_args()
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        raise RuntimeError('set ROS_LOCALHOST_ONLY=1 and an isolated ROS_DOMAIN_ID')
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    zenoh_port, console_udp_port = free_port(), free_port()
    console_config = yaml.safe_load((ROOT / 'console_soft/auv_console_pyside6/console_config.defense.yaml').read_text())
    console_config['zenoh'].update({
        'router_ip': '127.0.0.1', 'router_port': zenoh_port, 'mode': 'client',
        'publish_cmd_raw': False, 'subscribe_bridge_telemetry': True,
    })
    console_config['udp']['local_port'] = console_udp_port
    console_config_path = out / 'console_same_run.yaml'
    console_config_path.write_text(yaml.safe_dump(console_config, allow_unicode=True), encoding='utf-8')
    app = QApplication([])
    observed: list[dict] = []
    bridge_statuses: dict[tuple[int, float], dict] = {}
    holder: dict[str, MainWindow] = {}

    def on_telemetry(payload: object) -> None:
        if not isinstance(payload, dict) or payload.get('message_type') != 'inspection_operational_status':
            return
        status = (payload.get('cable_monitor') or {}).get('operational_status')
        if not isinstance(status, dict):
            return
        observed.append({
            'command_sequence': status.get('command_sequence'),
            'timestamp_s': status.get('timestamp_s'),
            'autonomous_execution_authorized': status.get('autonomous_execution_authorized'),
            'authority_reason': status.get('authority_reason'),
            'localization_status': status.get('localization_status'),
            'console_label': holder['window'].lbl_inspection_authority.text(),
        })

    original_bridge = bridge_module.InspectionBridgeNode

    class ObservedBridge(original_bridge):
        def __init__(self):
            super().__init__()
            window = MainWindow(config_file=str(console_config_path))
            holder['window'] = window
            window.comm_manager.bridge_telemetry_received.connect(on_telemetry)
            assert window.comm_manager.side_channel.is_active
            window.tab_widget.setCurrentIndex(3)
            window.show()
            app.processEvents()

        def _publish_arbiter_status(self, *, guard_decision=None):
            super()._publish_arbiter_status(guard_decision=guard_decision)
            status = getattr(self, '_latest_operational_status', None)
            if isinstance(status, dict):
                bridge_statuses[(status['command_sequence'], status['timestamp_s'])] = dict(status)

    original_executor = flythrough.SingleThreadedExecutor

    class GuiExecutor(original_executor):
        def spin_once(self, *args, **kwargs):
            result = super().spin_once(*args, **kwargs)
            app.processEvents()
            return result

    original_safe_load = yaml.safe_load

    def bridge_config_with_zenoh(stream):
        config = original_safe_load(stream)
        if isinstance(config, dict) and isinstance(config.get('bridge'), dict):
            protocol = config['bridge'].get('protocol_udp')
            if isinstance(protocol, dict):
                protocol['zenoh_side_channel_enabled'] = True
                protocol['zenoh_session_config'] = {
                    'mode': 'peer', 'listen/endpoints': [f'tcp/127.0.0.1:{zenoh_port}']}
        return config

    try:
        with patch.object(bridge_module, 'InspectionBridgeNode', ObservedBridge), \
                patch.object(flythrough, 'SingleThreadedExecutor', GuiExecutor), \
                patch.object(yaml, 'safe_load', bridge_config_with_zenoh):
            summary = flythrough.run(
                'wire_guard_telemetry_loss', args.seed, out, max_time_s=700.,
                with_bridge=True, sonar_identity_mode='target',
                config_file=ROOT / 'brain_linux/src/auv_cable_tracking_v2/config/cable_tracking_v2_flythrough_sonar_identity_corridor_budget_sim.yaml',
            )
        deadline = time.monotonic() + 3.
        while time.monotonic() < deadline and not any(
            item['authority_reason'] == 'AMD_UPLINK_STALE' for item in observed
        ):
            app.processEvents()
            time.sleep(.02)
        app.processEvents()
        assert observed, 'console received no direct operational status'
        for item in observed:
            key = (item['command_sequence'], item['timestamp_s'])
            counterpart = bridge_statuses.get(key)
            assert counterpart is not None, f"unknown bridge status {key}"
            assert item['autonomous_execution_authorized'] == counterpart['autonomous_execution_authorized']
            assert item['authority_reason'] == counterpart['authority_reason']
        assert any(item['autonomous_execution_authorized'] is True for item in observed)
        denied = [item for item in observed if item['authority_reason'] == 'AMD_UPLINK_STALE']
        assert denied and all(item['autonomous_execution_authorized'] is False for item in denied)
        assert summary['guard_telemetry_loss_ticks'] > 0
        assert summary['guard_telemetry_loss_zero_udp_ticks'] == summary['guard_telemetry_loss_ticks']
        assert summary['final_operational_status']['authority_reason'] == 'AMD_UPLINK_STALE'
        window = holder['window']
        window.refresh_inspection_authority_display()
        assert '自治许可: 禁止（上行失鲜）' in window.lbl_inspection_authority.text()
        screenshot = out / 'console_same_run_guard_loss.png'
        window.grab().save(str(screenshot))
        trace_path = out / 'console_operational_status.json'
        trace_path.write_text(json.dumps(observed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        bridge_trace_path = out / 'bridge_operational_status.json'
        bridge_trace_path.write_text(json.dumps(list(bridge_statuses.values()), ensure_ascii=False,
                                                indent=2) + '\n', encoding='utf-8')
        csv_path = out / f'wire_guard_telemetry_loss_seed_{args.seed}.csv'
        with csv_path.open(newline='', encoding='utf-8') as stream:
            rows = list(csv.DictReader(stream))
        assert any(row['authority_reason'] == 'AMD_UPLINK_STALE' and float(row['rpm']) == 0. for row in rows)
        result = {
            'role': 'single_synthetic_ros_pid_guard_udp_pvs_zenoh_pyside6_run',
            'same_run': True, 'hardware_connected': False, 'physical_amd_uplink': False,
            'bridge_status_count': len(bridge_statuses), 'console_status_count': len(observed),
            'console_authorized_seen': True, 'console_guard_revocation_seen': True,
            'guard_loss_zero_udp_ticks': summary['guard_telemetry_loss_zero_udp_ticks'],
            'final_console_label': window.lbl_inspection_authority.text(),
            'evidence_sha256': {
                csv_path.name: sha(csv_path), trace_path.name: sha(trace_path),
                bridge_trace_path.name: sha(bridge_trace_path), screenshot.name: sha(screenshot),
            },
            'source_sha256': {
                'decision_node': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/cable_tracking_v2_node.py'),
                'static_prior': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/static_target_prior.py'),
                'bridge': sha(ROOT / 'brain_linux/src/auv_cable_tracking_v2/auv_cable_tracking_v2/inspection_bridge_node.py'),
                'console': sha(ROOT / 'console_soft/auv_console_pyside6/src/ui/main_window.py'),
                'pvs_harness': sha(ROOT / 'tools/smoke_v2_flythrough_ros_pvs.py'),
                'same_run_harness': sha(Path(__file__)),
            },
        }
        (out / 'same_run_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        if 'window' in holder:
            holder['window'].close()
        if flythrough.rclpy.ok():
            flythrough.rclpy.shutdown()
        app.quit()


if __name__ == '__main__':
    main()
