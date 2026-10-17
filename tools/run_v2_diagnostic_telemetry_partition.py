#!/usr/bin/env python3
"""Diagnostic-only full-telemetry partition with every-tick Hold status.

This wrapper patches an installed v2 node only in its own process. It cannot
be used by the normal launch or silently change the product configuration.
"""

import argparse
import json
from pathlib import Path

import rclpy
from rclpy.executors import ExternalShutdownException
from std_msgs.msg import Bool, String

from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
from auv_decision_ros.cable_tracking_node import CableTrackingNode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--every-n', type=int, required=True)
    parser.add_argument('--suppress-full-monitor', action='store_true',
                        help='diagnostic upper bound: keep Hold budget but omit all full monitor frames')
    parser.add_argument('--stats-path', type=Path, required=True)
    args, ros_args = parser.parse_known_args()
    if args.every_n < 2:
        parser.error('--every-n must be at least 2')
    original = CableTrackingNode._publish_tracking
    stats = {'cycles': 0, 'full': 0, 'skipped': 0,
             'full_on_change': 0, 'every_n': args.every_n,
             'suppress_full_monitor': args.suppress_full_monitor}

    def partition(self, tracking, guidance, limited):
        if not self._inspection_enabled():
            raise RuntimeError('telemetry partition requires v2 inspection')
        if self.pub_setpoint.topic_name != '/auv/control/setpoint_candidate':
            raise RuntimeError('telemetry partition requires candidate-only Setpoint remap')
        budget = tracking.diagnostics.get('hold_budget')
        if not isinstance(budget, dict) or 'recovery_required' not in budget:
            raise RuntimeError('telemetry partition refuses missing Hold budget')
        signature = (str(tracking.mode), bool(guidance.safe_lock_active),
                     str(budget.get('state')), str(budget.get('reason')),
                     bool(tracking.diagnostics.get('lateral_valid')),
                     bool(tracking.diagnostics.get('depth_valid')),
                     tuple(self._acceptance_flags(tracking)))
        cycle = getattr(self, '_diagnostic_partition_cycle', 0) + 1
        self._diagnostic_partition_cycle = cycle
        changed = signature != getattr(self, '_diagnostic_partition_signature', None)
        stats['cycles'] += 1
        if not args.suppress_full_monitor and (cycle == 1 or cycle % args.every_n == 0 or changed):
            stats['full'] += 1
            stats['full_on_change'] += int(changed)
            result = original(self, tracking, guidance, limited)
        else:
            stats['skipped'] += 1
            # The independent final Setpoint gate consumes this status. It
            # must remain at decision cadence even when long JSON and derived
            # operator topics are omitted for this diagnostic cycle.
            self.pub_recovery_required.publish(Bool(data=bool(budget['recovery_required'])))
            self.pub_hold_budget.publish(String(data=json.dumps(budget, allow_nan=False)))
            result = None
        self._diagnostic_partition_signature = signature
        return result

    CableTrackingNode._publish_tracking = partition
    rclpy.init(args=ros_args)
    node = None
    try:
        node = CableTrackingV2Node()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except Exception:
        if rclpy.ok():
            raise
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        args.stats_path.write_text(json.dumps(stats, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
