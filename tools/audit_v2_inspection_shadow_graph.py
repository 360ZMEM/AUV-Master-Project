#!/usr/bin/env python3
"""Snapshot the live ROS graph of the passive inspection shadow launch.

Run this while inspection_shadow_stack.launch.py is still alive in the same
ROS_DOMAIN_ID. A saved launch log alone cannot prove live graph composition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import rclpy
from rclpy.node import Node


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    'auv_cable_tracking_v2_node',
    'auv_inspection_bridge_node',
    'auv_inspection_controller_node',
    'auv_localization_node',
    'auv_sensor_supervisor_node',
    'zenoh_viz_bridge_node',
}
FORBIDDEN = {
    'auv_bridge_node',
    'auv_controller_node',
    'auv_decision_node',
    'auv_cable_mission_autostart_node',
}
DEFAULT_OUTPUT = (ROOT / 'AUV-Master-Mag/results/v2/'
                  'inspection_shadow_stack_20260927/graph_audit.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-json', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--discovery-s', type=float, default=3.)
    parser.add_argument('--expect-sim-time', action='store_true',
                        help='also require the three base nodes to consume /clock')
    args = parser.parse_args()
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        raise RuntimeError('use ROS_LOCALHOST_ONLY=1 and the live isolated ROS_DOMAIN_ID')
    if not 0.5 <= args.discovery_s <= 15.:
        raise ValueError('discovery-s must be between 0.5 and 15')

    rclpy.init()
    node = Node('inspection_shadow_graph_audit')
    try:
        steps = round(args.discovery_s / .1)
        for _ in range(steps):
            rclpy.spin_once(node, timeout_sec=.1)
        seen = set(node.get_node_names()) - {'inspection_shadow_graph_audit'}
    finally:
        node.destroy_node()
        rclpy.shutdown()
    try:
        param = subprocess.run(
            ['ros2', 'param', 'get', '/auv_inspection_bridge_node', 'passive_mode'],
            capture_output=True, text=True, timeout=8, check=False,
        )
        passive = param.returncode == 0 and param.stdout.strip() == 'Boolean value is: True'
        param_output = param.stdout.strip() or param.stderr.strip()
    except subprocess.TimeoutExpired:
        passive, param_output = False, 'parameter query timeout'

    base_clock_parameters = {}
    for name in ('auv_localization_node', 'auv_sensor_supervisor_node',
                 'zenoh_viz_bridge_node'):
        try:
            clock_param = subprocess.run(
                ['ros2', 'param', 'get', f'/{name}', 'use_sim_time'],
                capture_output=True, text=True, timeout=8, check=False,
            )
            base_clock_parameters[name] = (clock_param.stdout.strip()
                                           if clock_param.returncode == 0
                                           else clock_param.stderr.strip())
        except subprocess.TimeoutExpired:
            base_clock_parameters[name] = 'parameter query timeout'
    base_sim_time_verified = all(
        value == 'Boolean value is: True'
        for value in base_clock_parameters.values()
    )

    source = ROOT / 'brain_linux/src/auv_cable_tracking_v2/launch/inspection_shadow_stack.launch.py'
    installed = (ROOT / 'brain_linux/install/auv_cable_tracking_v2/share/'
                 'auv_cable_tracking_v2/launch/inspection_shadow_stack.launch.py')
    installed_equal = installed.is_file() and sha(source) == sha(installed)
    result = {
        'role': 'live_passive_inspection_shadow_graph_audit',
        'ros_domain_id': os.environ['ROS_DOMAIN_ID'],
        'nodes': sorted(seen),
        'missing_expected_nodes': sorted(EXPECTED - seen),
        'unexpected_general_nodes': sorted(FORBIDDEN & seen),
        'bridge_passive_parameter': param_output,
        'bridge_passive_verified': passive,
        'base_clock_parameters': base_clock_parameters,
        'base_sim_time_verified': base_sim_time_verified,
        'expected_sim_time': args.expect_sim_time,
        'source_sha256': sha(source),
        'installed_source_equal': installed_equal,
        'physical_actuation_tested': False,
        'field_release_authorized': False,
        'interpretation': ('Live graph and bridge parameter in a local isolated ROS domain. '
                           'No injected mission, real sonar, physical PC104, or vehicle motion '
                           'was tested; absence of a mission injector does not authenticate '
                           'other publishers.'),
    }
    result['checks_passed'] = (not result['missing_expected_nodes']
                               and not result['unexpected_general_nodes']
                               and passive and installed_equal
                               and (not args.expect_sim_time or base_sim_time_verified))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                                encoding='utf-8')
    print(json.dumps({'checks_passed': result['checks_passed'],
                      'nodes': result['nodes'], 'bridge_passive_verified': passive}))
    raise SystemExit(0 if result['checks_passed'] else 2)


if __name__ == '__main__':
    main()
