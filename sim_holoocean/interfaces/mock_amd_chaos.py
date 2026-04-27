"""Chaos injection layer for Mock AMD realism enhancement.

Applies sensor-level and transport-level faults to sensor snapshots and
uplink frames based on a :class:`ChaosProfile` configuration.

Pure-stdlib, no external dependencies.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from common.physics import clamp

try:
    from .mock_amd_sensor_cache import SensorSnapshot
except ImportError:
    from mock_amd_sensor_cache import SensorSnapshot


@dataclass
class ChaosProfile:
    """Configuration for all chaos injection behaviours.

    Each behaviour has an independent ``*_enabled`` flag.  The top-level
    ``enabled`` flag acts as a master switch — when ``False`` no injection
    occurs regardless of individual flags.
    """

    # Master switch
    enabled: bool = False

    # ── Transport layer ──
    packet_loss_pct: float = 0.0              # [0.0, 1.0]
    reorder_enabled: bool = False
    reorder_buffer_ms: float = 50.0

    # ── Sensor layer ──
    dvl_freeze_enabled: bool = False
    dvl_freeze_after_s: float = 30.0

    imu_drift_enabled: bool = False
    imu_drift_rate_deg_per_s: float = 0.5

    depth_spike_enabled: bool = False
    depth_spike_m: float = 5.0
    depth_spike_after_s: float = 60.0

    mag_saturation_enabled: bool = False
    mag_saturation_threshold_t: float = 50000.0

    # ── Uplink layer ──
    uplink_dropout_enabled: bool = False
    uplink_dropout_on_pct: float = 0.8
    uplink_dropout_period_s: float = 10.0


class ChaosInjector:
    """Stateful chaos injector driven by a :class:`ChaosProfile`.

    Parameters
    ----------
    profile : ChaosProfile
        Injection configuration.
    start_time : float
        Wall-clock epoch for elapsed-time calculations (typically ``time.time()``
        at server start).
    """

    def __init__(
        self,
        profile: ChaosProfile,
        start_time: float = 0.0,
        *,
        _rng: random.Random | None = None,
    ) -> None:
        self._profile = profile
        self._start_time = start_time
        self._rng = _rng or random.Random()

        # Accumulated state
        self._dvl_frozen: dict | None = None
        self._imu_drift_accum: float = 0.0
        self._depth_spike_applied: bool = False
        self._depth_spike_offset: float = 0.0
        self._depth_spike_reset_elapsed: float | None = None

    # ------------------------------------------------------------------
    # Sensor-level injection
    # ------------------------------------------------------------------

    def apply_to_sensors(
        self,
        snapshot: SensorSnapshot,
        elapsed_s: float,
    ) -> SensorSnapshot:
        """Return a *new* snapshot with chaos applied.

        The original *snapshot* is never mutated.  Processing order:

        1. DVL freeze
        2. IMU drift
        3. Depth spike
        4. Magnetometer saturation
        """
        if not self._profile.enabled:
            return snapshot

        result = snapshot.copy()

        result = self._apply_dvl_freeze(result, elapsed_s)
        result = self._apply_imu_drift(result, elapsed_s)
        result = self._apply_depth_spike(result, elapsed_s)
        result = self._apply_mag_saturation(result)

        return result

    # ------------------------------------------------------------------
    # Uplink-level decisions
    # ------------------------------------------------------------------

    def should_drop_uplink(self, elapsed_s: float) -> bool:
        """Return ``True`` if the current uplink frame should be dropped."""
        if not self._profile.enabled:
            return False
        p = self._profile
        if not p.uplink_dropout_enabled:
            return False
        if p.uplink_dropout_period_s <= 0:
            return False
        phase = (elapsed_s % p.uplink_dropout_period_s) / p.uplink_dropout_period_s
        return phase < p.uplink_dropout_on_pct

    def should_lose_packet(self) -> bool:
        """Return ``True`` with probability ``packet_loss_pct``."""
        if not self._profile.enabled:
            return False
        pct = clamp(self._profile.packet_loss_pct, 0.0, 1.0)
        return self._rng.random() < pct

    def should_reorder(self, elapsed_s: float) -> bool:
        """Return ``True`` if the current uplink frame should be delayed (reordered)."""
        if not self._profile.enabled:
            return False
        if not self._profile.reorder_enabled:
            return False
        # ~5 % chance per frame when enabled
        return self._rng.random() < 0.05

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self, elapsed_s: float | None = None) -> None:
        """Clear all accumulated injector state.

        Parameters
        ----------
        elapsed_s : float or None
            Current elapsed time (same basis as used in apply_to_sensors).
            If provided, the depth spike will not re-trigger until
            ``depth_spike_after_s`` seconds have elapsed after this reset.
        """
        self._dvl_frozen = None
        self._imu_drift_accum = 0.0
        self._depth_spike_applied = False
        self._depth_spike_offset = 0.0
        self._depth_spike_reset_elapsed = elapsed_s

    # ------------------------------------------------------------------
    # Private: individual injectors
    # ------------------------------------------------------------------

    def _apply_dvl_freeze(self, snap: SensorSnapshot, elapsed_s: float) -> SensorSnapshot:
        p = self._profile
        if not p.dvl_freeze_enabled:
            return snap
        if elapsed_s < p.dvl_freeze_after_s:
            return snap
        # Freeze: capture first value after trigger time
        if self._dvl_frozen is None and snap.dvl is not None:
            self._dvl_frozen = dict(snap.dvl)  # shallow copy is fine
        if self._dvl_frozen is not None and snap.dvl is not None:
            snap.dvl = dict(self._dvl_frozen)
        return snap

    def _apply_imu_drift(self, snap: SensorSnapshot, elapsed_s: float) -> SensorSnapshot:
        p = self._profile
        if not p.imu_drift_enabled:
            return snap
        if snap.imu is None:
            return snap
        drift = elapsed_s * p.imu_drift_rate_deg_per_s
        snap.imu = dict(snap.imu)  # copy to avoid mutating input
        snap.imu["heading_deg"] = (snap.imu.get("heading_deg", 0.0) + drift) % 360.0
        return snap

    def _apply_depth_spike(self, snap: SensorSnapshot, elapsed_s: float) -> SensorSnapshot:
        p = self._profile
        if not p.depth_spike_enabled:
            return snap
        # After reset, require depth_spike_after_s of new elapsed time before re-triggering.
        # Use a small epsilon (1e-6s) so that even with after_s=0, one tick must elapse.
        if self._depth_spike_reset_elapsed is not None:
            reset_at = self._depth_spike_reset_elapsed
            self._depth_spike_reset_elapsed = None
            if elapsed_s - reset_at < max(p.depth_spike_after_s, 1e-6):
                return snap
        if elapsed_s < p.depth_spike_after_s:
            return snap
        if not self._depth_spike_applied:
            self._depth_spike_offset = p.depth_spike_m
            self._depth_spike_applied = True
        if snap.depth is not None:
            snap.depth = dict(snap.depth)  # copy
            snap.depth["depth_m"] = snap.depth.get("depth_m", 0.0) + self._depth_spike_offset
        return snap

    def _apply_mag_saturation(self, snap: SensorSnapshot) -> SensorSnapshot:
        p = self._profile
        if not p.mag_saturation_enabled:
            return snap
        if snap.mag is None:
            return snap
        threshold = p.mag_saturation_threshold_t
        snap.mag = dict(snap.mag)  # copy top-level
        b_ned = list(snap.mag.get("B_ned", [0.0, 0.0, 0.0]))
        snap.mag["B_ned"] = [clamp(v, -threshold, threshold) for v in b_ned]
        return snap
