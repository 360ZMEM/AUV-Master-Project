"""Tests for preserving full-rate FK2301 magnetic blocks."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from auv_decision_ros.fangkong_adc_client import FangkongAdcMagneticClient
from auv_decision_ros.fangkong_adc_client import (
    DEFAULT_MAIN_REPO_CALIBRATION,
    DEFAULT_MAIN_REPO_DEVICE_HOST,
    build_fangkong_config,
    discover_project_root,
    load_fangkong_api,
    resolve_project_path,
)


class _Api:
    @staticmethod
    def voltage_to_magnetic_field(waveform, _sensitivity):
        return np.asarray(waveform, dtype=float)

    @staticmethod
    def apply_calibration(values, _profile, _enabled):
        return np.asarray(values, dtype=float)


def test_discover_project_root_finds_workspace():
    root = discover_project_root()
    assert (root / "hardware_wrappers" / "fangkong_adc" / "api.py").exists()


def test_build_fangkong_config_applies_main_repo_overrides():
    api = load_fangkong_api()
    config = build_fangkong_config(
        api,
        device_host=DEFAULT_MAIN_REPO_DEVICE_HOST,
        calibration_profile_path=DEFAULT_MAIN_REPO_CALIBRATION,
    )
    assert config.network.host == DEFAULT_MAIN_REPO_DEVICE_HOST
    assert config.calibration.enabled is True
    assert config.calibration.profile_path.endswith(
        "20260705T144937_magnetometer_9param.json"
    )
    assert config.storage.enabled is False


def test_resolve_project_path_converts_relative_path():
    resolved = resolve_project_path(DEFAULT_MAIN_REPO_CALIBRATION)
    assert resolved.exists()


def test_latest_block_preserves_samples_and_timestamps() -> None:
    snapshot = SimpleNamespace(
        waveform=np.array(
            [
                [1.0, 2.0, 3.0],
                [4.0, 5.0, 6.0],
                [7.0, 8.0, 9.0],
            ]
        ),
        timestamp=10.0,
        sample_rate_hz=2,
        status_message="acquiring",
        stats=SimpleNamespace(
            filled_sample_count=0,
            dropped_chunks=0,
            packet_loss_count=0,
        ),
    )
    controller = SimpleNamespace(
        get_latest_snapshot=lambda: snapshot,
        calibration_profile=SimpleNamespace(name="cal-v1"),
        config=SimpleNamespace(
            device=SimpleNamespace(
                sensor_sensitivity_mv_per_ut=[1.0, 1.0, 1.0]
            ),
            calibration=SimpleNamespace(enabled=True),
        ),
    )
    client = FangkongAdcMagneticClient()
    client.api = _Api()
    client.controller = controller

    block = client.latest_block()

    assert block is not None
    assert block.field_t.shape == (3, 3)
    assert np.allclose(block.sample_time_s, [9.0, 9.5, 10.0])
    assert block.calibration_valid is True
    assert block.calibration_id == "cal-v1"
    assert block.data_completeness == 1.0
