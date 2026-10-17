#!/usr/bin/env python3
"""Independent ROS receipt recorder for an inspection timing evidence package.

The recorder never publishes control messages. Source timestamps are converted
to this host's monotonic axis only when they use the same system epoch clock;
the raw stamps and clock-pair trace are retained for later review.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import signal
import threading
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from auv_interfaces.msg import MpcCmd, Setpoint
from nav_msgs.msg import Odometry
from sensor_msgs.msg import MagneticField
from std_msgs.msg import String


COLUMNS = {
    'ros_setpoint': ('time_s', 'target_speed_mps', 'candidate_source_time_s',
                     'header_stamp_s', 'wall_received_s', 'source_age_at_receipt_s',
                     'clock_bracket_s', 'mode', 'note'),
    'pid': ('time_s', 'thrust_percent', 'producer_source_time_s', 'header_stamp_s',
            'wall_received_s', 'clock_bracket_s', 'valid', 'healthy', 'note'),
    'candidate': ('time_s', 'target_speed_mps', 'candidate_source_time_s',
                  'header_stamp_s', 'wall_received_s', 'source_age_at_receipt_s',
                  'clock_bracket_s', 'mode', 'note'),
    'navigation': ('time_s', 'source_time_s', 'header_stamp_s', 'wall_received_s',
                   'source_age_at_receipt_s', 'clock_bracket_s', 'x_m', 'y_m', 'z_m'),
    'magnetic': ('time_s', 'source_time_s', 'header_stamp_s', 'wall_received_s',
                 'source_age_at_receipt_s', 'clock_bracket_s', 'bx_t', 'by_t', 'bz_t'),
    'clock_alignment_trace': ('time_s', 'wall_s', 'wall_minus_monotonic_s',
                              'clock_bracket_s'),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clock_pair() -> tuple[float, float, float]:
    """Return monotonic midpoint, system epoch, and sampling half-span."""
    before = time.monotonic_ns()
    wall = time.time_ns()
    after = time.monotonic_ns()
    return (before + after) * .5e-9, wall * 1e-9, (after - before) * .5e-9


def stamp_seconds(stamp) -> float:
    return stamp.sec + stamp.nanosec * 1e-9


def aligned_source(stamp_s: float, monotonic_s: float, wall_s: float) -> float:
    return stamp_s - (wall_s - monotonic_s)


class InspectionRosTimingRecorder(Node):
    def __init__(self, *, event_queue: queue.Queue):
        super().__init__('inspection_ros_timing_recorder')
        self.event_queue = event_queue
        self.received = Counter()
        self.dropped = Counter()
        self.implausible_source_stamps = Counter()
        self.positive_setpoint_count = 0
        self.implausible_positive_setpoint_stamps = 0
        self.max_setpoint_publishers = 0
        self.create_subscription(Setpoint, '/auv/control/setpoint',
                                 lambda msg: self._setpoint('ros_setpoint', msg), 100)
        self.create_subscription(Setpoint, '/auv/control/setpoint_candidate',
                                 lambda msg: self._setpoint('candidate', msg), 100)
        self.create_subscription(MpcCmd, '/auv/control/mpc_cmd', self._pid, 100)
        self.create_subscription(Odometry, '/auv/state/filtered',
                                 self._navigation, qos_profile_sensor_data)
        self.create_subscription(MagneticField, '/auv/sensors/magnetic',
                                 self._magnetic, qos_profile_sensor_data)
        self.create_subscription(String, '/auv/cable/operational_status',
                                 self._status, 50)

    def _queue(self, role: str, row: dict) -> None:
        self.received[role] += 1
        try:
            self.event_queue.put_nowait((role, row))
        except queue.Full:
            self.dropped[role] += 1

    def _check_source_stamp(self, role: str, stamp: float, wall: float) -> None:
        # ROS simulation time or an unset header cannot be mapped to wall time.
        # Old but real messages remain visible to the downstream age audit.
        if not math.isfinite(stamp) or stamp < 1_000_000_000 or stamp > wall + 60.:
            self.implausible_source_stamps[role] += 1

    def _setpoint(self, role: str, msg: Setpoint) -> None:
        mono, wall, bracket = clock_pair()
        stamp = stamp_seconds(msg.header.stamp)
        self._check_source_stamp(role, stamp, wall)
        if role == 'ros_setpoint' and msg.target_speed_mps > 0:
            self.positive_setpoint_count += 1
            if not math.isfinite(stamp) or stamp < 1_000_000_000 or stamp > wall + 60.:
                self.implausible_positive_setpoint_stamps += 1
        self._queue(role, {'time_s': mono, 'target_speed_mps': float(msg.target_speed_mps),
                           'candidate_source_time_s': aligned_source(stamp, mono, wall),
                           'header_stamp_s': stamp, 'wall_received_s': wall,
                           'source_age_at_receipt_s': wall - stamp,
                           'clock_bracket_s': bracket,
                           'mode': msg.mode, 'note': msg.note})

    def _pid(self, msg: MpcCmd) -> None:
        mono, wall, bracket = clock_pair()
        stamp = stamp_seconds(msg.header.stamp)
        self._check_source_stamp('pid', stamp, wall)
        self._queue('pid', {'time_s': mono, 'thrust_percent': float(msg.thrust_percent),
                            'producer_source_time_s': aligned_source(stamp, mono, wall),
                            'header_stamp_s': stamp, 'wall_received_s': wall,
                            'clock_bracket_s': bracket, 'valid': int(msg.valid),
                            'healthy': int(msg.healthy), 'note': msg.note})

    def _navigation(self, msg: Odometry) -> None:
        mono, wall, bracket = clock_pair()
        stamp = stamp_seconds(msg.header.stamp)
        self._check_source_stamp('navigation', stamp, wall)
        p = msg.pose.pose.position
        self._queue('navigation', {'time_s': mono,
                                   'source_time_s': aligned_source(stamp, mono, wall),
                                   'header_stamp_s': stamp, 'wall_received_s': wall,
                                   'source_age_at_receipt_s': wall - stamp,
                                   'clock_bracket_s': bracket,
                                   'x_m': float(p.x), 'y_m': float(p.y), 'z_m': float(p.z)})

    def _magnetic(self, msg: MagneticField) -> None:
        mono, wall, bracket = clock_pair()
        stamp = stamp_seconds(msg.header.stamp)
        self._check_source_stamp('magnetic', stamp, wall)
        b = msg.magnetic_field
        self._queue('magnetic', {'time_s': mono,
                                 'source_time_s': aligned_source(stamp, mono, wall),
                                 'header_stamp_s': stamp, 'wall_received_s': wall,
                                 'source_age_at_receipt_s': wall - stamp,
                                 'clock_bracket_s': bracket,
                                 'bx_t': float(b.x), 'by_t': float(b.y), 'bz_t': float(b.z)})

    def _status(self, msg: String) -> None:
        mono, wall, bracket = clock_pair()
        self._queue('operational_status', {'time_s': mono, 'wall_received_s': wall,
                                           'clock_bracket_s': bracket,
                                           'raw_data': msg.data})

    def sample_clock(self) -> None:
        mono, wall, bracket = clock_pair()
        self._queue('clock_alignment_trace', {
            'time_s': mono, 'wall_s': wall,
            'wall_minus_monotonic_s': wall - mono,
            'clock_bracket_s': bracket,
        })
        self.max_setpoint_publishers = max(
            self.max_setpoint_publishers,
            len(self.get_publishers_info_by_topic('/auv/control/setpoint')))


def run(output_dir: Path, *, session_id: str, duration_s: float, queue_size: int) -> dict:
    if not session_id.strip():
        raise ValueError('nonempty session_id required')
    if not math.isfinite(duration_s) or duration_s < 0 or queue_size < 100:
        raise ValueError('duration must be finite and nonnegative; queue_size >= 100')
    output_dir.mkdir(parents=True, exist_ok=False)
    events: queue.Queue = queue.Queue(maxsize=queue_size)
    stop = threading.Event()
    writer_error: list[str] = []
    written = Counter()
    files = {role: (output_dir / f'{role}.csv').open('w', newline='', encoding='utf-8')
             for role in COLUMNS}
    files['operational_status'] = (output_dir / 'operational_status.jsonl').open(
        'w', encoding='utf-8')
    writers = {role: csv.DictWriter(files[role], fieldnames=columns)
               for role, columns in COLUMNS.items()}
    for writer in writers.values():
        writer.writeheader()

    def write_events() -> None:
        try:
            while True:
                role, row = events.get()
                if role is None:
                    return
                if role == 'operational_status':
                    files[role].write(json.dumps(row, ensure_ascii=False) + '\n')
                else:
                    writers[role].writerow(row)
                written[role] += 1
                if sum(written.values()) % 100 == 0:
                    for stream in files.values():
                        stream.flush()
        except Exception as exc:
            writer_error.append(f'{type(exc).__name__}: {exc}')

    worker = threading.Thread(target=write_events, name='inspection_timing_writer', daemon=True)
    worker.start()
    node = None
    executor = None
    started = time.monotonic()
    reason = 'duration' if duration_s else 'signal'
    old_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    received = {}
    dropped = {}
    implausible = {}
    positive_setpoints = 0
    implausible_positive_setpoints = 0
    max_publishers = 0
    try:
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        node = InspectionRosTimingRecorder(event_queue=events)
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        node.sample_clock()
        next_clock = started + 1.
        while not stop.is_set() and not writer_error:
            if duration_s and time.monotonic() - started >= duration_s:
                break
            executor.spin_once(timeout_sec=.05)
            if time.monotonic() >= next_clock:
                node.sample_clock()
                next_clock += 1.
    except KeyboardInterrupt:
        reason = 'keyboard_interrupt'
    except Exception as exc:
        writer_error.append(f'ROS recorder error: {type(exc).__name__}: {exc}')
        reason = 'recorder_error'
    finally:
        signal.signal(signal.SIGTERM, old_sigterm)
        if stop.is_set():
            reason = 'sigterm'
        if node is not None:
            try:
                node.sample_clock()
            except Exception as exc:
                writer_error.append(f'final clock sample: {type(exc).__name__}: {exc}')
            received = dict(node.received)
            dropped = dict(node.dropped)
            implausible = dict(node.implausible_source_stamps)
            positive_setpoints = node.positive_setpoint_count
            implausible_positive_setpoints = node.implausible_positive_setpoint_stamps
            max_publishers = node.max_setpoint_publishers
        if executor is not None:
            if node is not None:
                executor.remove_node(node)
            executor.shutdown()
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        try:
            events.put((None, None), timeout=2.)
        except queue.Full:
            # A failed writer can leave the bounded queue permanently full.
            events.get_nowait()
            dropped['recorder_shutdown'] = dropped.get('recorder_shutdown', 0) + 1
            events.put_nowait((None, None))
        worker.join(timeout=10.)
        if worker.is_alive():
            writer_error.append('writer did not drain within 10 s')
        else:
            for stream in files.values():
                stream.flush()
                stream.close()
    trace_path = output_dir / 'clock_alignment_trace.csv'
    with trace_path.open(newline='', encoding='utf-8') as stream:
        trace = list(csv.DictReader(stream))
    offsets = [float(row['wall_minus_monotonic_s']) for row in trace]
    brackets = [float(row['clock_bracket_s']) for row in trace]
    streams_present = written['ros_setpoint'] > 0 and written['pid'] > 0
    data_reviewable = (not writer_error and not dropped and not implausible
                       and streams_present and max_publishers == 1
                       and not worker.is_alive())
    positive_source_reviewable = (not writer_error and not dropped
                                  and positive_setpoints > 0
                                  and implausible_positive_setpoints == 0
                                  and max_publishers == 1 and not worker.is_alive())
    summary = {
        'role': 'inspection_ros_receipt_timing_capture',
        'session_id': session_id, 'ros_domain_id': os.environ.get('ROS_DOMAIN_ID'),
        'stop_reason': reason, 'elapsed_wall_s': time.monotonic() - started,
        'received': received, 'written': dict(written), 'dropped': dropped,
        'implausible_source_stamps': implausible,
        'positive_setpoint_count': positive_setpoints,
        'implausible_positive_setpoint_source_stamps': implausible_positive_setpoints,
        'positive_setpoint_source_reviewable': positive_source_reviewable,
        'required_ros_streams_present': streams_present,
        'data_reviewable': data_reviewable,
        'max_setpoint_publishers_seen': max_publishers,
        'max_local_clock_sample_bracket_s': max(brackets, default=None),
        'local_wall_monotonic_offset_span_s': max(offsets) - min(offsets) if offsets else None,
        'writer_errors': writer_error,
        'capture_complete': not writer_error and not dropped and not worker.is_alive(),
        'files_sha256': ({path.name: digest(path) for path in files_for_summary(output_dir)}
                         if not worker.is_alive() else {}),
        'recorder_sha256': digest(Path(__file__)),
        'physical_source_authenticated': False,
        'cross_device_clock_alignment_proven': False,
        'field_release_authorized': False,
    }
    (output_dir / 'capture_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return summary


def files_for_summary(output_dir: Path):
    return sorted(path for path in output_dir.iterdir()
                  if path.is_file() and path.name != 'capture_summary.json')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--duration-s', type=float, default=0.)
    parser.add_argument('--queue-size', type=int, default=10000)
    args = parser.parse_args()
    summary = run(args.output_dir, session_id=args.session_id,
                  duration_s=args.duration_s, queue_size=args.queue_size)
    print(json.dumps(summary, ensure_ascii=False))
    raise SystemExit(0 if summary['capture_complete'] else 2)


if __name__ == '__main__':
    main()
