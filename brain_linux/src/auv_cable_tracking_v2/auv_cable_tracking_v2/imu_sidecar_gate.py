"""Conservative admission of the isolated IMV1 IMU provenance stream.

The first packet only establishes a PC104-to-host clock anchor. A second,
consistent source sample is required before any ROS message can be emitted.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from common.imu_provenance_sidecar import ImuProvenanceV1


@dataclass(frozen=True)
class Admission:
    accepted: bool
    reason: str
    stamp_s: float | None = None


class ImuSidecarGate:
    def __init__(self, *, maximum_gap_s: float = 0.75,
                 maximum_clock_skew_s: float = 0.10,
                 maximum_receive_age_s: float = 0.25):
        limits = (maximum_gap_s, maximum_clock_skew_s, maximum_receive_age_s)
        if not all(math.isfinite(x) and x > 0. for x in limits):
            raise ValueError('sidecar gate limits must be finite and positive')
        self.maximum_gap_s = maximum_gap_s
        self.maximum_clock_skew_s = maximum_clock_skew_s
        self.maximum_receive_age_s = maximum_receive_age_s
        self._last: ImuProvenanceV1 | None = None
        self._last_receive_s: float | None = None
        self._anchor_uptime_ms: int | None = None
        self._anchor_ros_s: float | None = None

    def reset(self) -> None:
        self._last = None
        self._last_receive_s = None
        self._anchor_uptime_ms = None
        self._anchor_ros_s = None

    def admit(self, record: ImuProvenanceV1, *, receive_ros_s: float) -> Admission:
        if not math.isfinite(receive_ros_s) or receive_ros_s <= 0.:
            return Admission(False, 'invalid_receive_clock')
        if self._last is None:
            self._last = record
            self._last_receive_s = receive_ros_s
            self._anchor_uptime_ms = record.pc104_receive_uptime_ms
            self._anchor_ros_s = receive_ros_s
            return Admission(False, 'warming_up')

        previous = self._last
        sequence_delta = (record.sample_sequence - previous.sample_sequence) & 0xffffffff
        if sequence_delta == 0 or sequence_delta > 100:
            return Admission(False, 'sample_sequence_replay_or_reset')
        timer_delta_s = ((record.sensor_timer_ticks - previous.sensor_timer_ticks)
                         & 0xffffffff) / 62500.
        board_delta_s = ((record.pc104_receive_uptime_ms
                          - previous.pc104_receive_uptime_ms) & 0xffffffff) / 1000.
        if board_delta_s <= 0. or board_delta_s > self.maximum_gap_s:
            self.reset()
            return Admission(False, 'pc104_time_gap_requires_readmission')
        if (timer_delta_s <= 0. or timer_delta_s > self.maximum_gap_s
                or abs(timer_delta_s - board_delta_s) > self.maximum_clock_skew_s):
            return Admission(False, 'sensor_timer_inconsistent')
        host_delta_s = receive_ros_s - self._last_receive_s
        if (host_delta_s < 0. or host_delta_s > self.maximum_gap_s
                or abs(host_delta_s - board_delta_s) > self.maximum_clock_skew_s):
            self.reset()
            return Admission(False, 'receive_clock_inconsistent')

        board_since_anchor_s = ((record.pc104_receive_uptime_ms
                                 - self._anchor_uptime_ms) & 0xffffffff) / 1000.
        stamp_s = self._anchor_ros_s + board_since_anchor_s
        age_s = receive_ros_s - stamp_s
        if age_s < -self.maximum_clock_skew_s or age_s > self.maximum_receive_age_s:
            self.reset()
            return Admission(False, 'pc104_receive_age_out_of_range')
        self._last = record
        self._last_receive_s = receive_ros_s
        return Admission(True, 'source_sample_advanced', min(stamp_s, receive_ros_s))
