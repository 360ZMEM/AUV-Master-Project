from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_FANGKONG_ROOT = "hardware_wrappers/fangkong_adc"
DEFAULT_FANGKONG_CONFIG = "hardware_wrappers/fangkong_adc/config/default_config.yaml"
DEFAULT_MAIN_REPO_DEVICE_HOST = "192.168.0.12"
DEFAULT_MAIN_REPO_DEVICE_PORT = 1600
DEFAULT_MAIN_REPO_CALIBRATION = (
    "hardware_wrappers/fangkong_adc/calibration_profiles/20260705T144937_magnetometer_9param.json"
)


def discover_project_root() -> Path:
    env_root = os.environ.get("AUV_PROJECT_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / DEFAULT_FANGKONG_ROOT / "api.py").exists():
            return candidate

    search_roots = [Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents]
    seen: set[Path] = set()
    for root in search_roots:
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / DEFAULT_FANGKONG_ROOT / "api.py").exists():
            return resolved
    raise FileNotFoundError("无法定位项目根目录；需要找到 hardware_wrappers/fangkong_adc/api.py")


def resolve_project_path(path: str | Path, *, project_root: Path | None = None) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    root = project_root or discover_project_root()
    return (root / candidate).resolve()


def load_fangkong_api(*, fangkong_root: str | Path = DEFAULT_FANGKONG_ROOT) -> Any:
    root = resolve_project_path(fangkong_root)
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    return importlib.import_module("api")


def build_fangkong_config(
    api: Any,
    *,
    fangkong_default_config: str | Path = DEFAULT_FANGKONG_CONFIG,
    fangkong_user_config: str | Path | None = None,
    use_fangkong_user_config: bool = False,
    device_host: str = DEFAULT_MAIN_REPO_DEVICE_HOST,
    device_port: int = DEFAULT_MAIN_REPO_DEVICE_PORT,
    connect_timeout_sec: float | None = None,
    recv_timeout_sec: float | None = None,
    reconnect_interval_sec: float | None = None,
    sample_rate_hz: int | None = None,
    active_channels: list[int] | None = None,
    read_bytes_per_request: int | None = None,
    sensor_sensitivity_mv_per_ut: list[float] | None = None,
    transport_mode: str | None = None,
    waveform_y_unit: str | None = None,
    calibration_enabled: bool = True,
    calibration_profile_path: str | Path = DEFAULT_MAIN_REPO_CALIBRATION,
    storage_enabled: bool = False,
    storage_root_dir: str | Path | None = None,
) -> Any:
    project_root = discover_project_root()
    default_path = resolve_project_path(fangkong_default_config, project_root=project_root)
    user_path = None
    if use_fangkong_user_config and fangkong_user_config:
        user_path = resolve_project_path(fangkong_user_config, project_root=project_root)

    config = api.load_merged_config(default_path, user_path)
    config.network.host = str(device_host)
    config.network.port = int(device_port)

    if connect_timeout_sec is not None:
        config.network.connect_timeout_sec = float(connect_timeout_sec)
    if recv_timeout_sec is not None:
        config.network.recv_timeout_sec = float(recv_timeout_sec)
    if reconnect_interval_sec is not None:
        config.network.reconnect_interval_sec = float(reconnect_interval_sec)

    if sample_rate_hz is not None:
        config.device.sample_rate_hz = int(sample_rate_hz)
    if active_channels is not None:
        config.device.active_channels = [int(item) for item in active_channels]
    if read_bytes_per_request is not None:
        config.device.read_bytes_per_request = int(read_bytes_per_request)
    if sensor_sensitivity_mv_per_ut is not None:
        config.device.sensor_sensitivity_mv_per_ut = [float(item) for item in sensor_sensitivity_mv_per_ut]

    if transport_mode is not None:
        config.runtime.transport_mode = str(transport_mode)
    if waveform_y_unit is not None:
        config.runtime.waveform_y_unit = str(waveform_y_unit)

    config.calibration.enabled = bool(calibration_enabled)
    config.calibration.profile_path = str(
        resolve_project_path(calibration_profile_path, project_root=project_root)
    )
    config.storage.enabled = bool(storage_enabled)
    if storage_root_dir:
        config.storage.root_dir = str(resolve_project_path(storage_root_dir, project_root=project_root))
    config.validate()
    return config


@dataclass
class FangkongLatestField:
    x_t: float
    y_t: float
    z_t: float
    sample_time_s: float
    status_message: str


@dataclass
class FangkongLatestBlock:
    field_t: Any
    sample_time_s: Any
    sample_rate_hz: float
    clipping_ratio: float
    data_completeness: float
    dropped_sample_count: int
    calibration_valid: bool
    calibration_id: str
    sample_clock_verified: bool
    status_message: str


class FangkongAdcMagneticClient:
    def __init__(
        self,
        *,
        fangkong_root: str | Path = DEFAULT_FANGKONG_ROOT,
        fangkong_default_config: str | Path = DEFAULT_FANGKONG_CONFIG,
        fangkong_user_config: str | Path | None = None,
        use_fangkong_user_config: bool = False,
        device_host: str = DEFAULT_MAIN_REPO_DEVICE_HOST,
        device_port: int = DEFAULT_MAIN_REPO_DEVICE_PORT,
        connect_timeout_sec: float | None = None,
        recv_timeout_sec: float | None = None,
        reconnect_interval_sec: float | None = None,
        sample_rate_hz: int | None = None,
        active_channels: list[int] | None = None,
        read_bytes_per_request: int | None = None,
        sensor_sensitivity_mv_per_ut: list[float] | None = None,
        transport_mode: str = "poll",
        waveform_y_unit: str = "magnetic_field",
        calibration_enabled: bool = True,
        calibration_profile_path: str | Path = DEFAULT_MAIN_REPO_CALIBRATION,
        storage_enabled: bool = False,
        storage_root_dir: str | Path | None = None,
        axis_order: list[int] | None = None,
        axis_signs: list[float] | None = None,
    ) -> None:
        self.fangkong_root = fangkong_root
        self.fangkong_default_config = fangkong_default_config
        self.fangkong_user_config = fangkong_user_config
        self.use_fangkong_user_config = use_fangkong_user_config
        self.device_host = device_host
        self.device_port = device_port
        self.connect_timeout_sec = connect_timeout_sec
        self.recv_timeout_sec = recv_timeout_sec
        self.reconnect_interval_sec = reconnect_interval_sec
        self.sample_rate_hz = sample_rate_hz
        self.active_channels = list(active_channels) if active_channels is not None else None
        self.read_bytes_per_request = read_bytes_per_request
        self.sensor_sensitivity_mv_per_ut = (
            [float(item) for item in sensor_sensitivity_mv_per_ut]
            if sensor_sensitivity_mv_per_ut is not None
            else None
        )
        self.transport_mode = transport_mode
        self.waveform_y_unit = waveform_y_unit
        self.calibration_enabled = calibration_enabled
        self.calibration_profile_path = calibration_profile_path
        self.storage_enabled = storage_enabled
        self.storage_root_dir = storage_root_dir
        self.axis_order = list(axis_order) if axis_order is not None else [0, 1, 2]
        self.axis_signs = [float(item) for item in (axis_signs if axis_signs is not None else [1.0, 1.0, 1.0])]
        self.api = None
        self.controller = None
        self._last_filled_sample_count = 0

    def start(self) -> None:
        self.api = load_fangkong_api(fangkong_root=self.fangkong_root)
        config = build_fangkong_config(
            self.api,
            fangkong_default_config=self.fangkong_default_config,
            fangkong_user_config=self.fangkong_user_config,
            use_fangkong_user_config=self.use_fangkong_user_config,
            device_host=self.device_host,
            device_port=self.device_port,
            connect_timeout_sec=self.connect_timeout_sec,
            recv_timeout_sec=self.recv_timeout_sec,
            reconnect_interval_sec=self.reconnect_interval_sec,
            sample_rate_hz=self.sample_rate_hz,
            active_channels=self.active_channels,
            read_bytes_per_request=self.read_bytes_per_request,
            sensor_sensitivity_mv_per_ut=self.sensor_sensitivity_mv_per_ut,
            transport_mode=self.transport_mode,
            waveform_y_unit=self.waveform_y_unit,
            calibration_enabled=self.calibration_enabled,
            calibration_profile_path=self.calibration_profile_path,
            storage_enabled=self.storage_enabled,
            storage_root_dir=self.storage_root_dir,
        )
        self.controller = self.api.AcquisitionController(config)
        self.controller._connect_impl()
        self.controller._configure_impl()
        self.controller._start_impl()

    def stop(self) -> None:
        if self.controller is None:
            return
        self.controller._stop_impl()
        self.controller = None

    def latest_field(self) -> FangkongLatestField | None:
        block = self.latest_block()
        if block is None or block.field_t.size == 0:
            return None
        vector = block.field_t[-1]
        return FangkongLatestField(
            x_t=float(vector[0]),
            y_t=float(vector[1]),
            z_t=float(vector[2]),
            sample_time_s=float(block.sample_time_s[-1]),
            status_message=block.status_message,
        )

    def latest_block(self) -> FangkongLatestBlock | None:
        if self.controller is None or self.api is None:
            return None
        snapshot = self.controller.get_latest_snapshot()
        if snapshot.waveform.size == 0:
            return None
        waveform = np.asarray(snapshot.waveform, dtype=float)
        magnetic_ut = self.api.voltage_to_magnetic_field(
            waveform,
            self.controller.config.device.sensor_sensitivity_mv_per_ut,
        )
        magnetic_ut = self.api.apply_calibration(
            magnetic_ut,
            self.controller.calibration_profile,
            self.controller.config.calibration.enabled,
        )
        ordered = magnetic_ut[:, self.axis_order]
        signed_t = ordered * np.asarray(self.axis_signs, dtype=float)[None, :] * 1.0e-6
        sample_rate_hz = max(float(snapshot.sample_rate_hz), 1e-6)
        sample_count = int(signed_t.shape[0])
        sample_time_s = (
            float(snapshot.timestamp)
            - np.arange(sample_count - 1, -1, -1, dtype=float) / sample_rate_hz
        )
        voltage_limit = 10.0
        clipping_ratio = float(np.mean(np.abs(waveform) >= 0.995 * voltage_limit))
        filled_total = int(getattr(snapshot.stats, "filled_sample_count", 0))
        newly_filled = max(filled_total - self._last_filled_sample_count, 0)
        self._last_filled_sample_count = filled_total
        data_completeness = 1.0 - min(newly_filled / max(sample_count, 1), 1.0)
        profile = self.controller.calibration_profile
        calibration_enabled = bool(self.controller.config.calibration.enabled)
        calibration_valid = not calibration_enabled or profile is not None
        calibration_id = ""
        if profile is not None:
            calibration_id = str(getattr(profile, "name", ""))
        dropped_count = (
            int(getattr(snapshot.stats, "dropped_chunks", 0))
            + int(getattr(snapshot.stats, "packet_loss_count", 0))
        )
        return FangkongLatestBlock(
            field_t=signed_t,
            sample_time_s=sample_time_s,
            sample_rate_hz=sample_rate_hz,
            clipping_ratio=clipping_ratio,
            data_completeness=data_completeness,
            dropped_sample_count=dropped_count,
            calibration_valid=calibration_valid,
            calibration_id=calibration_id,
            sample_clock_verified=False,
            status_message=snapshot.status_message,
        )
