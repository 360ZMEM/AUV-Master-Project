"""Synthetic ROS DDS display smoke; no Zenoh, actuators or mission execution."""
import argparse
import json
from pathlib import Path
import time
from unittest.mock import patch

import rclpy
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import String
from auv_viz_bridge.zenoh_viz_bridge_node import ZenohVizBridgeNode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    rclpy.init(args=['--ros-args', '-p', 'allow_synthetic_scene_fallback:=false',
                    '-p', 'publish_sim_ground_truth:=false'])
    # Isolate the real installed ROS rendering node from hardware transports.
    with patch.object(ZenohVizBridgeNode, '_open_zenoh', lambda self: None):
        viz = ZenohVizBridgeNode()
    probe = rclpy.create_node('inspection_visualization_smoke')
    phase, text = [], []
    probe.create_subscription(String, '/auv/visual/mission_state', lambda msg: phase.append(msg.data), 10)
    probe.create_subscription(String, '/auv/visual/perception_text', lambda msg: text.append(msg.data), 10)
    tracking = probe.create_publisher(String, '/auv/cable/tracking', 10)
    authority = probe.create_publisher(String, '/auv/cable/operational_status', 10)
    executor = SingleThreadedExecutor()
    executor.add_node(viz)
    executor.add_node(probe)
    def spin(duration):
        end = time.monotonic() + duration
        while time.monotonic() < end:
            executor.spin_once(timeout_sec=.02)
    try:
        spin(.8)
        track = dict(mode='TRACK', estimated_cable_xy_m=[4., 6.], burial_depth_m=2.,
                     diagnostics=dict(inspection_enabled=True, lateral_valid=True,
                                      depth_valid=False, fwhm_width_m=8.))
        status = dict(command_sequence=1, timestamp_s=time.time(),
                      task_status='SOFTWARE_ROUTE_COMPLETE', task_status_fresh=True,
                      autonomous_execution_authorized=False, authority_reason='endpoint_hold',
                      arbiter_mode='AUTONOMOUS', arbiter_source='NONE', guard_state='ACTIVE')
        tracking.publish(String(data=json.dumps(track)))
        authority.publish(String(data=json.dumps(status)))
        spin(.5)
        fresh_text = text[-1] if text else ''
        checks = {'completion_received': 'SOFTWARE_ROUTE_COMPLETE' in phase,
                  'unqualified_depth_hidden': '埋深：UNAVAILABLE' in fresh_text,
                  'bridge_revocation_visible': 'DENIED / endpoint_hold' in fresh_text,
                  'width_received': '8.00 m' in fresh_text}
        spin(1.7)
        checks.update(stale_phase=bool(phase) and phase[-1] == 'STATUS_STALE',
                      stale_permission=bool(text) and 'UNKNOWN / 未证实' in text[-1],
                      stale_position=bool(text) and '横向估计：--' in text[-1])
        report = dict(scope='synthetic DDS presentation smoke, Zenoh disabled; no task or hardware claim',
                      passed=all(checks.values()), checks=checks,
                      fresh_text=fresh_text, final_text=text[-1] if text else '', phases=phase)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps(checks, ensure_ascii=False))
        return 0 if report['passed'] else 1
    finally:
        executor.shutdown()
        viz.destroy_node()
        probe.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
