#!/usr/bin/env python3
"""Diagnostic wrapper for independent inspection Setpoint supervisor timing."""
import argparse
import csv
import json
import math
from pathlib import Path
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from auv_cable_tracking_v2.inspection_setpoint_supervisor_node import InspectionSetpointSupervisorNode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-jsonl', required=True, type=Path)
    parser.add_argument('--gate-csv', type=Path,
                        help='Optional synchronized supervisor tick export for timing audit')
    args, ros_args = parser.parse_known_args()
    if args.output_jsonl.exists():
        raise FileExistsError(args.output_jsonl)
    if args.gate_csv and args.gate_csv.exists():
        raise FileExistsError(args.gate_csv)
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    if args.gate_csv:
        args.gate_csv.parent.mkdir(parents=True, exist_ok=True)
    gate_stream = args.gate_csv.open('w', newline='', encoding='utf-8', buffering=1) if args.gate_csv else None
    gate_columns = ('time_s', 'end_s', 'decision_speed_mps',
                    'navigation_receipt_age_s', 'navigation_source_age_s',
                    'magnetic_receipt_age_s', 'magnetic_source_age_s',
                    'covariance_receipt_age_s', 'candidate_receipt_age_s',
                    'candidate_source_age_s', 'budget_receipt_age_s', 'budget_latched')
    gate_writer = csv.DictWriter(gate_stream, fieldnames=gate_columns) if gate_stream else None
    if gate_writer:
        gate_writer.writeheader()
    with args.output_jsonl.open('w', encoding='utf-8', buffering=1) as stream:
        original = InspectionSetpointSupervisorNode._on_tick

        def traced(self):
            start = time.monotonic()
            cpu = time.thread_time()
            clock_now = self.get_clock().now().nanoseconds * 1e-9
            with self._authority_lock:
                reason_before_stamp_check = self.authority.problem(start)
                candidate = self.authority.candidate
                stamp = candidate.header.stamp if candidate is not None else None
                stamp_s = stamp.sec + stamp.nanosec * 1e-9 if stamp else 0.
                candidate_age = clock_now - stamp_s if clock_now > 0 and stamp_s > 0 else float('nan')
                reason = self.authority.problem(
                    start, candidate_sim_age_s=candidate_age, source_clock_now_s=clock_now)
                authority = self.authority
                def age(last):
                    value = start - last
                    return value if math.isfinite(value) else None
                def source_age(stamp_s):
                    value = clock_now - stamp_s
                    return value if stamp_s > 0 and math.isfinite(value) else None
                gate_row = {
                    'time_s': start,
                    'decision_speed_mps': float(candidate.target_speed_mps) if reason is None else 0.,
                    'navigation_receipt_age_s': age(authority.nav_at),
                    'navigation_source_age_s': source_age(authority.nav_source_stamp_s),
                    'magnetic_receipt_age_s': age(authority.mag_at),
                    'magnetic_source_age_s': source_age(authority.mag_source_stamp_s),
                    'covariance_receipt_age_s': age(authority.cov_at),
                    'candidate_receipt_age_s': age(authority.candidate_at),
                    'candidate_source_age_s': candidate_age if math.isfinite(candidate_age) else None,
                    'budget_receipt_age_s': age(authority.budget_at),
                    'budget_latched': int(authority.budget_latched),
                }
            try:
                return original(self)
            finally:
                gate_row['end_s'] = time.monotonic()
                if gate_writer:
                    gate_writer.writerow(gate_row)
                stream.write(json.dumps({
                    'tick_start_monotonic_s': start,
                    'tick_end_monotonic_s': gate_row['end_s'],
                    'tick_cpu_s': time.thread_time() - cpu,
                    'reason_before_stamp_check': reason_before_stamp_check,
                    'effective_reason': reason,
                    'candidate_receipt_age_s': gate_row['candidate_receipt_age_s'],
                    'navigation_receipt_age_s': gate_row['navigation_receipt_age_s'],
                    'budget_receipt_age_s': gate_row['budget_receipt_age_s'],
                }, allow_nan=False) + '\n')

        InspectionSetpointSupervisorNode._on_tick = traced
        rclpy.init(args=ros_args)
        node = InspectionSetpointSupervisorNode()
        try:
            rclpy.spin(node)
        except (KeyboardInterrupt, ExternalShutdownException):
            pass
        except Exception:
            if rclpy.ok():
                raise
        finally:
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
            if gate_stream:
                gate_stream.close()


if __name__ == '__main__':
    main()
