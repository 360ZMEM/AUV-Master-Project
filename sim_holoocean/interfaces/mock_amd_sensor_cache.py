"""Asynchronous sensor sample cache with independent clocks.

Simulates realistic multi-rate sensor sampling: IMU at ~100 Hz, DVL at ~6 Hz,
depth at ~50 Hz, magnetometer at ~20 Hz.  Each sensor only refreshes when its
own clock ticks, otherwise the last sampled value is returned.

Pure-stdlib, no external dependencies.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field


@dataclass
class SensorSnapshot:
    """Immutable-ish snapshot of all sensor values at one instant."""

    imu: dict | None = None       # heading_deg, pitch_deg, roll_deg
    dvl: dict | None = None       # speed_mps (forward)
    depth: dict | None = None     # depth_m
    mag: dict | None = None       # B_ned[3], B_norm
    ts: float = 0.0

    def copy(self) -> SensorSnapshot:
        """Return a deep copy so callers can mutate without affecting cache."""
        return SensorSnapshot(
            imu=deepcopy(self.imu) if self.imu else None,
            dvl=deepcopy(self.dvl) if self.dvl else None,
            depth=deepcopy(self.depth) if self.depth else None,
            mag=deepcopy(self.mag) if self.mag else None,
            ts=self.ts,
        )


class SensorSampleCache:
    """Independent-clock sensor sampling cache.

    Each sensor channel has its own period.  :meth:`update` is called at the
    simulation loop rate (e.g. 60 Hz).  A sensor is only re-sampled from
    *raw_state* when its local clock has elapsed; otherwise the cached value
    is reused.

    Parameters
    ----------
    imu_hz, dvl_hz, depth_hz, mag_hz :
        Sampling rate for each sensor.  ``0`` disables the cache for that
        channel (always re-samples).
    """

    def __init__(
        self,
        imu_hz: float = 100.0,
        dvl_hz: float = 6.0,
        depth_hz: float = 50.0,
        mag_hz: float = 20.0,
    ) -> None:
        def _period(hz: float) -> float:
            return 1.0 / max(0.1, hz) if hz > 0 else 0.0

        self._imu_period = _period(imu_hz)
        self._dvl_period = _period(dvl_hz)
        self._depth_period = _period(depth_hz)
        self._mag_period = _period(mag_hz)

        # Track last sample time per channel
        self._last_imu_ts = -999.0
        self._last_dvl_ts = -999.0
        self._last_depth_ts = -999.0
        self._last_mag_ts = -999.0

        # Cached snapshot
        self._snapshot = SensorSnapshot()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        raw_state: dict,
        now: float,
    ) -> SensorSnapshot:
        """Sample sensors from *raw_state* according to independent clocks.

        Parameters
        ----------
        raw_state : dict
            Must contain keys matching the extractors below.  Missing keys
            are silently skipped (sensor stays at last cached value).
        now : float
            Current wall-clock or sim time in seconds.

        Returns
        -------
        SensorSnapshot
            Merged snapshot with each channel refreshed or cached.
        """
        # ── IMU ──
        imu_data = self._extract_imu(raw_state)
        if imu_data is not None:
            if self._imu_period <= 0 or (now - self._last_imu_ts) >= self._imu_period:
                self._snapshot.imu = imu_data
                self._last_imu_ts = now

        # ── DVL ──
        dvl_data = self._extract_dvl(raw_state)
        if dvl_data is not None:
            if self._dvl_period <= 0 or (now - self._last_dvl_ts) >= self._dvl_period:
                self._snapshot.dvl = dvl_data
                self._last_dvl_ts = now

        # ── Depth ──
        depth_data = self._extract_depth(raw_state)
        if depth_data is not None:
            if self._depth_period <= 0 or (now - self._last_depth_ts) >= self._depth_period:
                self._snapshot.depth = depth_data
                self._last_depth_ts = now

        # ── Mag ──
        mag_data = self._extract_mag(raw_state)
        if mag_data is not None:
            if self._mag_period <= 0 or (now - self._last_mag_ts) >= self._mag_period:
                self._snapshot.mag = mag_data
                self._last_mag_ts = now

        self._snapshot.ts = now
        return self._snapshot.copy()

    def snapshot(self) -> SensorSnapshot:
        """Return the current cached snapshot (last update values)."""
        return self._snapshot.copy()

    def reset(self) -> None:
        """Clear all cached values and reset clocks."""
        self._last_imu_ts = -999.0
        self._last_dvl_ts = -999.0
        self._last_depth_ts = -999.0
        self._last_mag_ts = -999.0
        self._snapshot = SensorSnapshot()

    # ------------------------------------------------------------------
    # Extraction helpers (overridable in tests)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_imu(raw_state: dict) -> dict | None:
        """Extract IMU data from raw state dict."""
        imu = raw_state.get("imu")
        if imu is None:
            return None
        return {
            "heading_deg": float(imu.get("heading_deg", 0.0)),
            "pitch_deg": float(imu.get("pitch_deg", 0.0)),
            "roll_deg": float(imu.get("roll_deg", 0.0)),
        }

    @staticmethod
    def _extract_dvl(raw_state: dict) -> dict | None:
        """Extract DVL data from raw state dict."""
        dvl = raw_state.get("dvl")
        if dvl is None:
            return None
        return {"speed_mps": float(dvl.get("speed_mps", 0.0))}

    @staticmethod
    def _extract_depth(raw_state: dict) -> dict | None:
        """Extract depth data from raw state dict."""
        depth = raw_state.get("depth")
        if depth is None:
            return None
        return {"depth_m": float(depth.get("depth_m", 0.0))}

    @staticmethod
    def _extract_mag(raw_state: dict) -> dict | None:
        """Extract magnetometer data from raw state dict."""
        mag = raw_state.get("mag")
        if mag is None:
            return None
        return {
            "B_ned": list(mag.get("B_ned", [0.0, 0.0, 0.0])),
            "B_norm": float(mag.get("B_norm", 0.0)),
        }
