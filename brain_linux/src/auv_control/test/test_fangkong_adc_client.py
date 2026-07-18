from __future__ import annotations

from auv_decision_ros.fangkong_adc_client import (
    DEFAULT_MAIN_REPO_CALIBRATION,
    DEFAULT_MAIN_REPO_DEVICE_HOST,
    build_fangkong_config,
    discover_project_root,
    load_fangkong_api,
    resolve_project_path,
)


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
    assert config.calibration.profile_path.endswith("20260705T144937_magnetometer_9param.json")
    assert config.storage.enabled is False


def test_resolve_project_path_converts_relative_path():
    resolved = resolve_project_path(DEFAULT_MAIN_REPO_CALIBRATION)
    assert resolved.exists()
