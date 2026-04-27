"""Unit tests for SensorSampleCache and SensorSnapshot.

Each test is isolated — no dependency on protocol.py or mock_amd_server.
"""

from __future__ import annotations

from sim_holoocean.interfaces.mock_amd_sensor_cache import SensorSampleCache, SensorSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(
    heading: float = 90.0,
    pitch: float = 5.0,
    roll: float = -3.0,
    dvl_speed: float = 1.5,
    depth_m: float = 10.0,
    b_ned: list[float] | None = None,
    b_norm: float = 50000.0,
) -> dict:
    """Build a minimal raw_state dict accepted by SensorSampleCache."""
    return {
        "imu": {"heading_deg": heading, "pitch_deg": pitch, "roll_deg": roll},
        "dvl": {"speed_mps": dvl_speed},
        "depth": {"depth_m": depth_m},
        "mag": {
            "B_ned": b_ned or [1000.0, 2000.0, 3000.0],
            "B_norm": b_norm,
        },
    }


# ---------------------------------------------------------------------------
# SensorSnapshot
# ---------------------------------------------------------------------------

class TestSensorSnapshot:
    def test_default_fields_are_none(self) -> None:
        snap = SensorSnapshot()
        assert snap.imu is None
        assert snap.dvl is None
        assert snap.depth is None
        assert snap.mag is None
        assert snap.ts == 0.0

    def test_copy_is_deep(self) -> None:
        snap = SensorSnapshot(
            imu={"heading_deg": 90.0},
            dvl={"speed_mps": 1.0},
            depth={"depth_m": 5.0},
            mag={"B_ned": [1.0, 2.0, 3.0], "B_norm": 100.0},
            ts=1.0,
        )
        copy = snap.copy()

        # Mutating copy must not affect original
        copy.imu["heading_deg"] = 180.0
        copy.dvl["speed_mps"] = 99.0
        copy.depth["depth_m"] = 99.0
        copy.mag["B_ned"][0] = 999.0

        assert snap.imu["heading_deg"] == 90.0
        assert snap.dvl["speed_mps"] == 1.0
        assert snap.depth["depth_m"] == 5.0
        assert snap.mag["B_ned"][0] == 1.0


# ---------------------------------------------------------------------------
# SensorSampleCache construction
# ---------------------------------------------------------------------------

class TestSensorSampleCacheConstruct:
    def test_default_rates(self) -> None:
        cache = SensorSampleCache()
        assert cache.snapshot().imu is None

    def test_zero_rate_disables_cache(self) -> None:
        """With hz=0, period=0 means always re-sample."""
        cache = SensorSampleCache(imu_hz=0.0, dvl_hz=0.0, depth_hz=0.0, mag_hz=0.0)
        state = _make_state()
        snap1 = cache.update(state, now=0.0)
        state["imu"]["heading_deg"] = 270.0  # change
        snap2 = cache.update(state, now=0.0001)  # almost same time
        # With hz=0, should re-sample immediately
        assert snap2.imu["heading_deg"] == 270.0


# ---------------------------------------------------------------------------
# Independent clock sampling
# ---------------------------------------------------------------------------

class TestSensorSampleCacheClocks:
    def test_imu_cached_between_ticks(self) -> None:
        """IMU at 10 Hz = 0.1s period. Must cache between ticks."""
        cache = SensorSampleCache(imu_hz=10.0, dvl_hz=0.0, depth_hz=0.0, mag_hz=0.0)
        state = _make_state(heading=90.0)

        # t=0: first sample
        snap0 = cache.update(state, now=0.0)
        assert snap0.imu["heading_deg"] == 90.0

        # t=0.05 (half period): change raw state, but cache should return old value
        state["imu"]["heading_deg"] = 180.0
        snap1 = cache.update(state, now=0.05)
        assert snap1.imu["heading_deg"] == 90.0  # cached!

        # t=0.1 (full period): should refresh
        snap2 = cache.update(state, now=0.1)
        assert snap2.imu["heading_deg"] == 180.0  # refreshed!

    def test_dvl_cached_between_ticks(self) -> None:
        """DVL at 6 Hz ≈ 0.1667s period."""
        cache = SensorSampleCache(imu_hz=0.0, dvl_hz=6.0, depth_hz=0.0, mag_hz=0.0)
        state = _make_state(dvl_speed=1.5)

        snap0 = cache.update(state, now=0.0)
        assert snap0.dvl["speed_mps"] == 1.5

        state["dvl"]["speed_mps"] = 2.0
        snap1 = cache.update(state, now=0.1)  # < 1/6 ≈ 0.1667
        assert snap1.dvl["speed_mps"] == 1.5  # cached

        snap2 = cache.update(state, now=0.17)  # >= 0.1667
        assert snap2.dvl["speed_mps"] == 2.0  # refreshed

    def test_depth_cached_between_ticks(self) -> None:
        cache = SensorSampleCache(imu_hz=0.0, dvl_hz=0.0, depth_hz=50.0, mag_hz=0.0)
        state = _make_state(depth_m=10.0)

        snap0 = cache.update(state, now=0.0)
        assert snap0.depth["depth_m"] == 10.0

        state["depth"]["depth_m"] = 15.0
        snap1 = cache.update(state, now=0.009)  # < 1/50 = 0.02
        assert snap1.depth["depth_m"] == 10.0

        snap2 = cache.update(state, now=0.02)
        assert snap2.depth["depth_m"] == 15.0

    def test_mag_cached_between_ticks(self) -> None:
        cache = SensorSampleCache(imu_hz=0.0, dvl_hz=0.0, depth_hz=0.0, mag_hz=20.0)
        state = _make_state(b_norm=50000.0)

        snap0 = cache.update(state, now=0.0)
        assert snap0.mag["B_norm"] == 50000.0

        state["mag"]["B_norm"] = 60000.0
        snap1 = cache.update(state, now=0.03)  # < 1/20 = 0.05
        assert snap1.mag["B_norm"] == 50000.0

        snap2 = cache.update(state, now=0.05)
        assert snap2.mag["B_norm"] == 60000.0


# ---------------------------------------------------------------------------
# Mixed channels: independent clocks don't interfere
# ---------------------------------------------------------------------------

class TestSensorSampleCacheMixed:
    def test_channels_independent(self) -> None:
        """Changing one channel doesn't affect cached values of another."""
        cache = SensorSampleCache(imu_hz=10.0, dvl_hz=6.0, depth_hz=0.0, mag_hz=0.0)
        state = _make_state(heading=90.0, dvl_speed=1.5)

        snap0 = cache.update(state, now=0.0)

        # Change both
        state["imu"]["heading_deg"] = 180.0
        state["dvl"]["speed_mps"] = 2.0

        # At t=0.05: IMU cached (< 0.1), DVL cached (< 0.1667)
        snap1 = cache.update(state, now=0.05)
        assert snap1.imu["heading_deg"] == 90.0
        assert snap1.dvl["speed_mps"] == 1.5

        # At t=0.1: IMU refreshes, DVL still cached
        snap2 = cache.update(state, now=0.1)
        assert snap2.imu["heading_deg"] == 180.0
        assert snap2.dvl["speed_mps"] == 1.5


# ---------------------------------------------------------------------------
# Missing sensor keys
# ---------------------------------------------------------------------------

class TestSensorSampleCacheMissingKeys:
    def test_missing_imu_keeps_none(self) -> None:
        cache = SensorSampleCache(imu_hz=0.0, dvl_hz=0.0, depth_hz=0.0, mag_hz=0.0)
        state = {"dvl": {"speed_mps": 1.0}}  # no imu key
        snap = cache.update(state, now=0.0)
        assert snap.imu is None

    def test_partial_state_ok(self) -> None:
        """Only some sensors present — rest stay None."""
        cache = SensorSampleCache()
        state = {"imu": {"heading_deg": 45.0, "pitch_deg": 0.0, "roll_deg": 0.0}}
        snap = cache.update(state, now=0.0)
        assert snap.imu is not None
        assert snap.dvl is None
        assert snap.depth is None
        assert snap.mag is None


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestSensorSampleCacheReset:
    def test_reset_clears_all(self) -> None:
        cache = SensorSampleCache()
        state = _make_state()
        cache.update(state, now=0.0)
        assert cache.snapshot().imu is not None

        cache.reset()
        assert cache.snapshot().imu is None
        assert cache.snapshot().ts == 0.0

    def test_update_after_reset_resamples(self) -> None:
        cache = SensorSampleCache()
        state = _make_state(heading=90.0)
        cache.update(state, now=0.0)

        cache.reset()
        state["imu"]["heading_deg"] = 270.0
        snap = cache.update(state, now=0.0)
        assert snap.imu["heading_deg"] == 270.0


# ---------------------------------------------------------------------------
# snapshot() returns cached copy
# ---------------------------------------------------------------------------

class TestSensorSampleCacheSnapshot:
    def test_snapshot_returns_cached_copy(self) -> None:
        cache = SensorSampleCache()
        state = _make_state()
        cache.update(state, now=0.0)

        snap = cache.snapshot()
        # snapshot is a copy — mutating it should not affect cache
        snap.imu["heading_deg"] = 999.0
        snap2 = cache.snapshot()
        assert snap2.imu["heading_deg"] == 90.0  # unchanged
