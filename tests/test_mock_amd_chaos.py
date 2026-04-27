"""Unit tests for ChaosInjector and ChaosProfile.

Each injector is tested independently.  No dependency on mock_amd_server.
"""

from __future__ import annotations

import random

from sim_holoocean.interfaces.mock_amd_chaos import ChaosInjector, ChaosProfile
from sim_holoocean.interfaces.mock_amd_sensor_cache import SensorSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(**overrides: Any) -> ChaosProfile:
    defaults = {"enabled": True}
    defaults.update(overrides)
    return ChaosProfile(**defaults)


def _make_snapshot(
    heading: float = 90.0,
    pitch: float = 5.0,
    roll: float = -3.0,
    dvl_speed: float = 1.5,
    depth_m: float = 10.0,
    b_ned: list[float] | None = None,
    b_norm: float = 50000.0,
) -> SensorSnapshot:
    return SensorSnapshot(
        imu={"heading_deg": heading, "pitch_deg": pitch, "roll_deg": roll},
        dvl={"speed_mps": dvl_speed},
        depth={"depth_m": depth_m},
        mag={"B_ned": b_ned or [1000.0, 2000.0, 3000.0], "B_norm": b_norm},
        ts=0.0,
    )


def _make_injector(profile: ChaosProfile, seed: int = 42) -> ChaosInjector:
    return ChaosInjector(profile, start_time=0.0, _rng=random.Random(seed))


# ---------------------------------------------------------------------------
# Master switch
# ---------------------------------------------------------------------------

class TestChaosMasterSwitch:
    def test_disabled_profile_passes_through(self) -> None:
        """When enabled=False, apply_to_sensors returns snapshot unchanged."""
        profile = ChaosProfile(enabled=False, dvl_freeze_enabled=True)
        injector = _make_injector(profile)
        snap = _make_snapshot()
        result = injector.apply_to_sensors(snap, elapsed_s=999.0)
        assert result.dvl["speed_mps"] == 1.5  # not frozen

    def test_disabled_should_not_drop(self) -> None:
        profile = ChaosProfile(enabled=False, uplink_dropout_enabled=True)
        injector = _make_injector(profile)
        assert injector.should_drop_uplink(999.0) is False

    def test_disabled_should_not_lose(self) -> None:
        profile = ChaosProfile(enabled=False, packet_loss_pct=1.0)
        injector = _make_injector(profile)
        assert injector.should_lose_packet() is False


# ---------------------------------------------------------------------------
# DVL freeze
# ---------------------------------------------------------------------------

class TestDvlFreeze:
    def test_no_freeze_before_trigger_time(self) -> None:
        profile = _make_profile(dvl_freeze_enabled=True, dvl_freeze_after_s=10.0)
        injector = _make_injector(profile)
        snap = _make_snapshot(dvl_speed=1.5)
        result = injector.apply_to_sensors(snap, elapsed_s=5.0)
        assert result.dvl["speed_mps"] == 1.5  # not frozen yet

    def test_freeze_after_trigger(self) -> None:
        profile = _make_profile(dvl_freeze_enabled=True, dvl_freeze_after_s=1.0)
        injector = _make_injector(profile)

        # At t=0.5, not yet frozen
        snap0 = _make_snapshot(dvl_speed=1.5)
        result0 = injector.apply_to_sensors(snap0, elapsed_s=0.5)
        assert result0.dvl["speed_mps"] == 1.5

        # At t=1.0, freeze triggers — captures speed=2.0
        snap1 = _make_snapshot(dvl_speed=2.0)
        result1 = injector.apply_to_sensors(snap1, elapsed_s=1.0)
        assert result1.dvl["speed_mps"] == 2.0

        # At t=5.0, even though speed changed to 3.0, frozen at 2.0
        snap2 = _make_snapshot(dvl_speed=3.0)
        result2 = injector.apply_to_sensors(snap2, elapsed_s=5.0)
        assert result2.dvl["speed_mps"] == 2.0

    def test_does_not_mutate_input_snapshot(self) -> None:
        profile = _make_profile(dvl_freeze_enabled=True, dvl_freeze_after_s=0.0)
        injector = _make_injector(profile)
        snap = _make_snapshot(dvl_speed=1.5)
        injector.apply_to_sensors(snap, elapsed_s=1.0)
        assert snap.dvl["speed_mps"] == 1.5  # original unchanged


# ---------------------------------------------------------------------------
# IMU drift
# ---------------------------------------------------------------------------

class TestImuDrift:
    def test_no_drift_when_disabled(self) -> None:
        profile = _make_profile(imu_drift_enabled=False)
        injector = _make_injector(profile)
        snap = _make_snapshot(heading=90.0)
        result = injector.apply_to_sensors(snap, elapsed_s=10.0)
        assert result.imu["heading_deg"] == 90.0

    def test_drift_accumulates_linearly(self) -> None:
        profile = _make_profile(imu_drift_enabled=True, imu_drift_rate_deg_per_s=1.0)
        injector = _make_injector(profile)

        snap = _make_snapshot(heading=0.0)
        result = injector.apply_to_sensors(snap, elapsed_s=5.0)
        # heading = (0 + 5*1.0) % 360 = 5.0
        assert abs(result.imu["heading_deg"] - 5.0) < 0.01

        # At t=360s, full rotation
        snap2 = _make_snapshot(heading=0.0)
        result2 = injector.apply_to_sensors(snap2, elapsed_s=360.0)
        assert abs(result2.imu["heading_deg"] - 0.0) < 0.01  # wraps around

    def test_negative_drift_rate(self) -> None:
        profile = _make_profile(imu_drift_enabled=True, imu_drift_rate_deg_per_s=-2.0)
        injector = _make_injector(profile)
        snap = _make_snapshot(heading=10.0)
        result = injector.apply_to_sensors(snap, elapsed_s=5.0)
        # heading = (10 + 5*(-2)) % 360 = 0.0
        assert abs(result.imu["heading_deg"] - 0.0) < 0.01

    def test_preserves_pitch_and_roll(self) -> None:
        profile = _make_profile(imu_drift_enabled=True, imu_drift_rate_deg_per_s=1.0)
        injector = _make_injector(profile)
        snap = _make_snapshot(heading=0.0, pitch=5.0, roll=-3.0)
        result = injector.apply_to_sensors(snap, elapsed_s=10.0)
        assert result.imu["pitch_deg"] == 5.0
        assert result.imu["roll_deg"] == -3.0


# ---------------------------------------------------------------------------
# Depth spike
# ---------------------------------------------------------------------------

class TestDepthSpike:
    def test_no_spike_before_trigger(self) -> None:
        profile = _make_profile(depth_spike_enabled=True, depth_spike_m=5.0, depth_spike_after_s=30.0)
        injector = _make_injector(profile)
        snap = _make_snapshot(depth_m=10.0)
        result = injector.apply_to_sensors(snap, elapsed_s=20.0)
        assert result.depth["depth_m"] == 10.0

    def test_spike_applied_once(self) -> None:
        profile = _make_profile(depth_spike_enabled=True, depth_spike_m=5.0, depth_spike_after_s=1.0)
        injector = _make_injector(profile)

        snap0 = _make_snapshot(depth_m=10.0)
        result0 = injector.apply_to_sensors(snap0, elapsed_s=1.0)
        assert result0.depth["depth_m"] == 15.0  # 10 + 5

        # Subsequent updates still have the offset
        snap1 = _make_snapshot(depth_m=12.0)
        result1 = injector.apply_to_sensors(snap1, elapsed_s=2.0)
        assert result1.depth["depth_m"] == 17.0  # 12 + 5 (offset persists)

    def test_does_not_mutate_input(self) -> None:
        profile = _make_profile(depth_spike_enabled=True, depth_spike_m=5.0, depth_spike_after_s=0.0)
        injector = _make_injector(profile)
        snap = _make_snapshot(depth_m=10.0)
        injector.apply_to_sensors(snap, elapsed_s=1.0)
        assert snap.depth["depth_m"] == 10.0


# ---------------------------------------------------------------------------
# Magnetometer saturation
# ---------------------------------------------------------------------------

class TestMagSaturation:
    def test_no_saturation_when_disabled(self) -> None:
        profile = _make_profile(mag_saturation_enabled=False)
        injector = _make_injector(profile)
        snap = _make_snapshot(b_ned=[60000.0, 70000.0, 80000.0])
        result = injector.apply_to_sensors(snap, elapsed_s=0.0)
        assert result.mag["B_ned"] == [60000.0, 70000.0, 80000.0]

    def test_clamps_above_threshold(self) -> None:
        profile = _make_profile(mag_saturation_enabled=True, mag_saturation_threshold_t=50000.0)
        injector = _make_injector(profile)
        snap = _make_snapshot(b_ned=[60000.0, 70000.0, 40000.0])
        result = injector.apply_to_sensors(snap, elapsed_s=0.0)
        assert result.mag["B_ned"] == [50000.0, 50000.0, 40000.0]

    def test_clamps_below_negative_threshold(self) -> None:
        profile = _make_profile(mag_saturation_enabled=True, mag_saturation_threshold_t=50000.0)
        injector = _make_injector(profile)
        snap = _make_snapshot(b_ned=[-60000.0, -40000.0, 0.0])
        result = injector.apply_to_sensors(snap, elapsed_s=0.0)
        assert result.mag["B_ned"] == [-50000.0, -40000.0, 0.0]

    def test_does_not_mutate_input(self) -> None:
        profile = _make_profile(mag_saturation_enabled=True, mag_saturation_threshold_t=1000.0)
        injector = _make_injector(profile)
        snap = _make_snapshot(b_ned=[5000.0, 0.0, 0.0])
        injector.apply_to_sensors(snap, elapsed_s=0.0)
        assert snap.mag["B_ned"][0] == 5000.0  # original unchanged


# ---------------------------------------------------------------------------
# Uplink dropout
# ---------------------------------------------------------------------------

class TestUplinkDropout:
    def test_no_dropout_when_disabled(self) -> None:
        profile = _make_profile(uplink_dropout_enabled=False)
        injector = _make_injector(profile)
        assert injector.should_drop_uplink(999.0) is False

    def test_dropout_pattern(self) -> None:
        """With on_pct=0.5, period=1.0: first 0.5s drop, next 0.5s pass."""
        profile = _make_profile(uplink_dropout_enabled=True, uplink_dropout_on_pct=0.5, uplink_dropout_period_s=1.0)
        injector = _make_injector(profile)

        # t=0.0: phase=0.0 < 0.5 → drop
        assert injector.should_drop_uplink(0.0) is True
        # t=0.4: phase=0.4 < 0.5 → drop
        assert injector.should_drop_uplink(0.4) is True
        # t=0.5: phase=0.5 >= 0.5 → pass
        assert injector.should_drop_uplink(0.5) is False
        # t=0.9: phase=0.9 >= 0.5 → pass
        assert injector.should_drop_uplink(0.9) is False
        # t=1.0: phase=0.0 < 0.5 → drop (new cycle)
        assert injector.should_drop_uplink(1.0) is True

    def test_full_on_dropout(self) -> None:
        """on_pct=1.0 means always drop."""
        profile = _make_profile(uplink_dropout_enabled=True, uplink_dropout_on_pct=1.0, uplink_dropout_period_s=10.0)
        injector = _make_injector(profile)
        assert injector.should_drop_uplink(5.0) is True


# ---------------------------------------------------------------------------
# Packet loss
# ---------------------------------------------------------------------------

class TestPacketLoss:
    def test_zero_loss_never_drops(self) -> None:
        profile = _make_profile(packet_loss_pct=0.0)
        injector = _make_injector(profile)
        for _ in range(100):
            assert injector.should_lose_packet() is False

    def test_full_loss_always_drops(self) -> None:
        profile = _make_profile(packet_loss_pct=1.0)
        injector = _make_injector(profile)
        for _ in range(100):
            assert injector.should_lose_packet() is True


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------

class TestReorder:
    def test_disabled_never_reorders(self) -> None:
        profile = _make_profile(reorder_enabled=False)
        injector = _make_injector(profile)
        for _ in range(100):
            assert injector.should_reorder(0.0) is False

    def test_enabled_occasionally_reorders(self) -> None:
        profile = _make_profile(reorder_enabled=True)
        injector = _make_injector(profile)
        # With ~5% chance, over 200 tries we should see at least one True
        results = [injector.should_reorder(0.0) for _ in range(200)]
        assert any(results)


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestChaosReset:
    def test_reset_clears_dvl_freeze(self) -> None:
        profile = _make_profile(dvl_freeze_enabled=True, dvl_freeze_after_s=0.0)
        injector = _make_injector(profile)
        snap = _make_snapshot(dvl_speed=1.5)
        injector.apply_to_sensors(snap, elapsed_s=1.0)

        injector.reset()

        # After reset, new speed should be used (not frozen)
        snap2 = _make_snapshot(dvl_speed=3.0)
        result = injector.apply_to_sensors(snap2, elapsed_s=1.0)
        assert result.dvl["speed_mps"] == 3.0

    def test_reset_clears_depth_spike(self) -> None:
        profile = _make_profile(depth_spike_enabled=True, depth_spike_m=5.0, depth_spike_after_s=1.0)
        injector = _make_injector(profile)

        # At t=2s (> after_s=1.0), spike applied
        snap = _make_snapshot(depth_m=10.0)
        result = injector.apply_to_sensors(snap, elapsed_s=2.0)
        assert result.depth["depth_m"] == 15.0  # 10 + 5 spike

        # Reset at elapsed=2s
        injector.reset(elapsed_s=2.0)

        # Immediately after reset, spike should NOT re-apply
        snap2 = _make_snapshot(depth_m=10.0)
        result2 = injector.apply_to_sensors(snap2, elapsed_s=2.0001)
        assert result2.depth["depth_m"] == 10.0  # no spike

        # But after another 1s, spike triggers again
        snap3 = _make_snapshot(depth_m=10.0)
        result3 = injector.apply_to_sensors(snap3, elapsed_s=3.1)
        assert result3.depth["depth_m"] == 15.0  # spike re-triggered


# ---------------------------------------------------------------------------
# Combined injection
# ---------------------------------------------------------------------------

class TestCombinedInjection:
    def test_multiple_injectors_apply_together(self) -> None:
        profile = _make_profile(
            imu_drift_enabled=True,
            imu_drift_rate_deg_per_s=1.0,
            depth_spike_enabled=True,
            depth_spike_m=3.0,
            depth_spike_after_s=0.0,
        )
        injector = _make_injector(profile)
        snap = _make_snapshot(heading=0.0, depth_m=10.0)
        result = injector.apply_to_sensors(snap, elapsed_s=5.0)
        assert abs(result.imu["heading_deg"] - 5.0) < 0.01
        assert result.depth["depth_m"] == 13.0
