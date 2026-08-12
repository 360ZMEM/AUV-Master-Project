"""Hysteretic, source-specific cable tracking authority logic."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


MODE_HOLD = 0
MODE_SEARCH = 1
MODE_TRACK = 2


@dataclass(frozen=True)
class QualitySignal:
    source: str
    validity: int
    p_detect: float
    p_track: float
    detection_calibrated: bool
    track_calibrated: bool
    age_s: float


@dataclass(frozen=True)
class AuthorityDecision:
    mode: int
    sensor_health_ok: bool
    detection_authorized: bool
    tracking_authorized: bool
    p_detect: float
    p_track: float
    contributing_sources: tuple[str, ...]
    reason_codes: tuple[str, ...]


class TrackingAuthorityMachine:
    """Separate sensor health, detection and tracking permission."""

    def __init__(
        self,
        *,
        maximum_age_s: float = 0.75,
        track_enter_probability: float = 0.75,
        track_exit_probability: float = 0.55,
        search_enter_probability: float = 0.55,
        search_exit_probability: float = 0.35,
        enter_debounce_count: int = 3,
        exit_debounce_count: int = 5,
    ) -> None:
        if track_exit_probability >= track_enter_probability:
            raise ValueError("track exit threshold must be below enter threshold")
        if search_exit_probability >= search_enter_probability:
            raise ValueError("search exit threshold must be below enter threshold")
        self.maximum_age_s = float(maximum_age_s)
        self.track_enter_probability = float(track_enter_probability)
        self.track_exit_probability = float(track_exit_probability)
        self.search_enter_probability = float(search_enter_probability)
        self.search_exit_probability = float(search_exit_probability)
        self.enter_debounce_count = max(int(enter_debounce_count), 1)
        self.exit_debounce_count = max(int(exit_debounce_count), 1)
        self.mode = MODE_HOLD
        self._candidate_mode = MODE_HOLD
        self._candidate_count = 0

    def update(
        self,
        signals: Sequence[QualitySignal],
        *,
        runtime_sensor_health_ok: bool,
    ) -> AuthorityDecision:
        fresh = [
            signal
            for signal in signals
            if signal.validity > 0
            and math.isfinite(signal.age_s)
            and signal.age_s <= self.maximum_age_s
        ]
        sensor_health_ok = bool(runtime_sensor_health_ok and fresh)
        detection = [
            signal
            for signal in fresh
            if signal.detection_calibrated
            and math.isfinite(signal.p_detect)
        ]
        tracking = [
            signal
            for signal in fresh
            if signal.track_calibrated and math.isfinite(signal.p_track)
        ]
        p_detect = max(
            (float(signal.p_detect) for signal in detection),
            default=float("nan"),
        )
        p_track = max(
            (float(signal.p_track) for signal in tracking),
            default=float("nan"),
        )

        reasons: list[str] = []
        if not runtime_sensor_health_ok:
            reasons.append("runtime_sensor_health_blocked")
        if not fresh:
            reasons.append("no_fresh_quality_source")
        if not detection:
            reasons.append("calibrated_detection_unavailable")
        if not tracking:
            reasons.append("calibrated_tracking_unavailable")

        target_mode = self._target_mode(
            sensor_health_ok=sensor_health_ok,
            p_detect=p_detect,
            p_track=p_track,
        )
        if not sensor_health_ok:
            self.mode = MODE_HOLD
            self._candidate_mode = MODE_HOLD
            self._candidate_count = 0
        elif target_mode == self.mode:
            self._candidate_mode = target_mode
            self._candidate_count = 0
        else:
            if target_mode != self._candidate_mode:
                self._candidate_mode = target_mode
                self._candidate_count = 1
            else:
                self._candidate_count += 1
            required = (
                self.enter_debounce_count
                if target_mode > self.mode
                else self.exit_debounce_count
            )
            if self._candidate_count >= required:
                self.mode = target_mode
                self._candidate_count = 0

        contributing = tuple(
            sorted(
                {
                    signal.source
                    for signal in (*detection, *tracking)
                }
            )
        )
        return AuthorityDecision(
            mode=self.mode,
            sensor_health_ok=sensor_health_ok,
            detection_authorized=bool(
                self.mode in (MODE_SEARCH, MODE_TRACK)
                and math.isfinite(p_detect)
            ),
            tracking_authorized=bool(
                self.mode == MODE_TRACK and math.isfinite(p_track)
            ),
            p_detect=p_detect,
            p_track=p_track,
            contributing_sources=contributing,
            reason_codes=tuple(reasons),
        )

    def _target_mode(
        self,
        *,
        sensor_health_ok: bool,
        p_detect: float,
        p_track: float,
    ) -> int:
        if not sensor_health_ok:
            return MODE_HOLD
        track_threshold = (
            self.track_exit_probability
            if self.mode == MODE_TRACK
            else self.track_enter_probability
        )
        if math.isfinite(p_track) and p_track >= track_threshold:
            return MODE_TRACK
        search_threshold = (
            self.search_exit_probability
            if self.mode == MODE_SEARCH
            else self.search_enter_probability
        )
        if math.isfinite(p_detect) and p_detect >= search_threshold:
            return MODE_SEARCH
        return MODE_HOLD
