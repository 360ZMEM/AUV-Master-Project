#!/usr/bin/env python3
"""Diagnostic-only wrapper around the installed v2 ROS algorithm node.

Records callback wall times without changing the algorithm or its watchdog
thresholds. Use only in isolated probes; each JSONL row is one timer callback.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import os
import pstats
import time
from pathlib import Path

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor

from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node
from auv_decision_ros.cable_tracking_node import CableTrackingNode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-jsonl', required=True, type=Path)
    parser.add_argument('--diagnostics-every-n', type=int, default=1)
    parser.add_argument('--separate-timer-group', action='store_true')
    args, ros_args = parser.parse_known_args()
    if args.diagnostics_every_n < 1:
        raise ValueError('diagnostics-every-n must be at least 1')
    if args.output_jsonl.exists():
        raise FileExistsError(args.output_jsonl)
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    base_publish_profiler = (cProfile.Profile()
                             if os.environ.get('AUV_V2_PROFILE_BASE_PUBLISH') == '1' else None)
    with args.output_jsonl.open('w', encoding='utf-8', buffering=1) as stream:
        original_tick = CableTrackingV2Node._on_tick
        original_publish = CableTrackingV2Node._publish_tracking
        original_base_publish = CableTrackingNode._publish_tracking

        def cadence_base_publish(self, *call_args, **call_kwargs):
            self._trace_diagnostic_cycle = getattr(self, '_trace_diagnostic_cycle', 0) + 1
            if self._trace_diagnostic_cycle % args.diagnostics_every_n != 0:
                return None
            start = time.monotonic()
            start_cpu = time.thread_time()
            try:
                if base_publish_profiler is None:
                    return original_base_publish(self, *call_args, **call_kwargs)
                base_publish_profiler.enable()
                try:
                    return original_base_publish(self, *call_args, **call_kwargs)
                finally:
                    base_publish_profiler.disable()
            finally:
                self._trace_base_publish_s = time.monotonic() - start
                self._trace_base_publish_cpu_s = time.thread_time() - start_cpu

        def timed_publish(self, *call_args, **call_kwargs):
            start = time.monotonic()
            start_cpu = time.thread_time()
            try:
                return original_publish(self, *call_args, **call_kwargs)
            finally:
                self._trace_publish_s = time.monotonic() - start
                self._trace_publish_cpu_s = time.thread_time() - start_cpu

        def timed_tick(self):
            start = time.monotonic()
            start_cpu = time.thread_time()
            nav_before = (None if self.latest_odom is None else
                          start - self.latest_odom_wall_time_s)
            magnetic_before = (None if not self.latest_magnetic_wall_time_s else
                               start - self.latest_magnetic_wall_time_s)
            before_count = self._publish_count
            self._trace_step_s = None
            self._trace_step_cpu_s = None
            self._trace_publish_s = None
            self._trace_publish_cpu_s = None
            self._trace_base_publish_s = None
            self._trace_base_publish_cpu_s = None
            try:
                return original_tick(self)
            finally:
                end = time.monotonic()
                row = {
                    'tick_start_monotonic_s': start,
                    'tick_end_monotonic_s': end,
                    'tick_duration_s': end - start,
                    'tick_cpu_duration_s': time.thread_time() - start_cpu,
                    'navigation_age_before_s': nav_before,
                    'navigation_age_after_s': (None if self.latest_odom is None else
                                               end - self.latest_odom_wall_time_s),
                    'covariance_present': self._latest_nav_uncertainty is not None,
                    'covariance_age_before_s': (None if self._latest_nav_uncertainty is None else
                                                start - self._latest_nav_uncertainty_wall_time_s),
                    'magnetic_age_before_s': magnetic_before,
                    'step_duration_s': self._trace_step_s,
                    'step_cpu_duration_s': self._trace_step_cpu_s,
                    'publish_tracking_duration_s': self._trace_publish_s,
                    'publish_tracking_cpu_duration_s': self._trace_publish_cpu_s,
                    'base_publish_duration_s': self._trace_base_publish_s,
                    'base_publish_cpu_duration_s': self._trace_base_publish_cpu_s,
                    'published_setpoint_count_delta': self._publish_count - before_count,
                    'hold_recovery_required': self._hold_budget.recovery_required,
                    'sensor_gate_reason': self._last_sensor_gate_reason,
                }
                stream.write(json.dumps(row, allow_nan=False) + '\n')

        CableTrackingV2Node._publish_tracking = timed_publish
        CableTrackingV2Node._on_tick = timed_tick
        CableTrackingNode._publish_tracking = cadence_base_publish
        rclpy.init(args=ros_args)
        node = None
        executor = None
        try:
            node = CableTrackingV2Node()
            original_step = node.pipeline.step_with_guidance

            def timed_step(*call_args, **call_kwargs):
                start = time.monotonic()
                start_cpu = time.thread_time()
                try:
                    return original_step(*call_args, **call_kwargs)
                finally:
                    node._trace_step_s = time.monotonic() - start
                    node._trace_step_cpu_s = time.thread_time() - start_cpu

            node.pipeline.step_with_guidance = timed_step
            if args.separate_timer_group:
                node.destroy_timer(node.timer)
                node.timer = node.create_timer(
                    .1, node._on_tick, callback_group=MutuallyExclusiveCallbackGroup())
                executor = MultiThreadedExecutor(num_threads=2)
                executor.add_node(node)
                executor.spin()
            else:
                rclpy.spin(node)
        except (KeyboardInterrupt, ExternalShutdownException):
            pass
        finally:
            if base_publish_profiler is not None:
                base_publish_profiler.dump_stats(str(args.output_jsonl.with_suffix('.pstats')))
                profile_text = io.StringIO()
                pstats.Stats(base_publish_profiler, stream=profile_text).sort_stats(
                    'cumulative').print_stats(45)
                args.output_jsonl.with_suffix('.profile.txt').write_text(
                    profile_text.getvalue(), encoding='utf-8')
            if executor is not None:
                executor.shutdown(timeout_sec=1.)
            if node is not None:
                node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()


if __name__ == '__main__':
    main()
