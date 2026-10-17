#!/usr/bin/env python3
"""Check that the passive inspection launch does not invent scene truth."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from visualization_msgs.msg import Marker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (ROOT / 'AUV-Master-Mag/results/v2/'
                  'inspection_shadow_stack_20260927/scene_fallback_audit.json')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observe-s', type=float, default=8.)
    parser.add_argument('--publish-sim-clock', action='store_true',
                        help='drive synthetic-only launch clock during the observation')
    parser.add_argument('--expect-synthetic-fallback', action='store_true',
                        help='counterexample audit of the legacy demo display behavior')
    parser.add_argument('--output-json', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or not os.environ.get('ROS_DOMAIN_ID'):
        raise RuntimeError('run in the live launch ROS_LOCALHOST_ONLY=1 domain')
    if not 3. <= args.observe_s <= 30.:
        raise ValueError('observe-s must be in [3, 30]')

    rclpy.init()
    node = Node('inspection_shadow_scene_audit')
    observed = {'mock_scene': 0, 'cable_add': 0, 'truth_add': 0,
                'sim_ground_truth': 0,
                'cable_deleteall': 0, 'mission_state': 0}
    mission_states: set[str] = set()
    def mock_cb(_msg: String) -> None:
        observed['mock_scene'] += 1
    def cable_cb(msg: Marker) -> None:
        if msg.action == Marker.ADD:
            observed['cable_add'] += 1
        elif msg.action == Marker.DELETEALL:
            observed['cable_deleteall'] += 1
    def truth_cb(msg: Marker) -> None:
        if msg.action == Marker.ADD:
            observed['truth_add'] += 1
    def mission_cb(msg: String) -> None:
        observed['mission_state'] += 1
        mission_states.add(msg.data)
    node.create_subscription(String, '/auv/mock/scene', mock_cb, 10)
    node.create_subscription(Marker, '/auv/visual/cable_marker', cable_cb, 10)
    node.create_subscription(Marker, '/auv/visual/truth_marker', truth_cb, 10)
    node.create_subscription(PoseStamped, '/auv/sensors/ground_truth',
                             lambda _msg: observed.__setitem__(
                                 'sim_ground_truth', observed['sim_ground_truth'] + 1), 10)
    node.create_subscription(String, '/auv/visual/mission_state', mission_cb, 10)
    clock_pub = node.create_publisher(Clock, '/clock', 10) if args.publish_sim_clock else None
    deadline = time.monotonic() + args.observe_s
    started = time.monotonic()
    try:
        while time.monotonic() < deadline:
            if clock_pub is not None:
                clock = Clock()
                elapsed = 1. + time.monotonic() - started
                clock.clock.sec = int(elapsed)
                clock.clock.nanosec = int((elapsed - int(elapsed)) * 1e9)
                clock_pub.publish(clock)
            rclpy.spin_once(node, timeout_sec=.1)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    param = subprocess.run(
        ['ros2', 'param', 'get', '/zenoh_viz_bridge_node',
         'allow_synthetic_scene_fallback'],
        capture_output=True, text=True, timeout=8, check=False,
    )
    gt_param = subprocess.run(
        ['ros2', 'param', 'get', '/zenoh_viz_bridge_node',
         'publish_sim_ground_truth'],
        capture_output=True, text=True, timeout=8, check=False,
    )
    disabled = param.returncode == 0 and param.stdout.strip() == 'Boolean value is: False'
    enabled = param.returncode == 0 and param.stdout.strip() == 'Boolean value is: True'
    gt_disabled = (gt_param.returncode == 0
                   and gt_param.stdout.strip() == 'Boolean value is: False')
    if args.expect_synthetic_fallback:
        checks_passed = (enabled and observed['mission_state'] > 0
                         and observed['mock_scene'] > 0
                         and observed['cable_add'] > 0
                         and observed['truth_add'] > 0)
    else:
        checks_passed = (disabled and gt_disabled and observed['mission_state'] > 0
                         and observed['mock_scene'] == 0
                         and observed['cable_add'] == 0
                         and observed['truth_add'] == 0
                         and observed['sim_ground_truth'] == 0)
    result = {
        'role': ('legacy_demo_synthetic_scene_counterexample' if args.expect_synthetic_fallback
                 else 'live_passive_inspection_no_synthetic_scene_audit'),
        'ros_domain_id': os.environ['ROS_DOMAIN_ID'],
        'observe_s': args.observe_s,
        'synthetic_clock_published': args.publish_sim_clock,
        'observed': observed,
        'mission_states_seen': sorted(mission_states),
        'viz_parameter': param.stdout.strip() or param.stderr.strip(),
        'ground_truth_parameter': gt_param.stdout.strip() or gt_param.stderr.strip(),
        'fallback_disabled': disabled,
        'expect_synthetic_fallback': args.expect_synthetic_fallback,
        'checks_passed': checks_passed,
        'interpretation': ('No live Zenoh scene was injected. A bounded DDS observation '
                           'compares demo fallback with the passive inspection setting. '
                           'It does not test actual mission execution or authenticate '
                           'future Zenoh inputs.'),
        'field_release_authorized': False,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                                encoding='utf-8')
    print(json.dumps({'checks_passed': checks_passed, 'observed': observed,
                      'fallback_disabled': disabled}))
    raise SystemExit(0 if checks_passed else 2)


if __name__ == '__main__':
    main()
