from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    config.validate()
    return config


@dataclass
class FangkongLatestField:
    x_t: float
    y_t: float
    z_t: float
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
        self.axis_order = list(axis_order) if axis_order is not None else [0, 1, 2]
        self.axis_signs = [float(item) for item in (axis_signs if axis_signs is not None else [1.0, 1.0, 1.0])]
        self.api = None
        self.controller = None

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
        if self.controller is None or self.api is None:
            return None
        snapshot = self.controller.get_latest_snapshot()
        if snapshot.waveform.size == 0:
            return None
        latest_voltage = snapshot.waveform[-1:, :]
        magnetic_ut = self.api.voltage_to_magnetic_field(
            latest_voltage,
            self.controller.config.device.sensor_sensitivity_mv_per_ut,
        )
        magnetic_ut = self.api.apply_calibration(
            magnetic_ut,
            self.controller.calibration_profile,
            self.controller.config.calibration.enabled,
        )
        vector = magnetic_ut[0]
        ordered = [vector[index] for index in self.axis_order]
        signed = [value * sign for value, sign in zip(ordered, self.axis_signs)]
        return FangkongLatestField(
            x_t=signed[0] * 1.0e-6,
            y_t=signed[1] * 1.0e-6,
            z_t=signed[2] * 1.0e-6,
            status_message=snapshot.status_message,
        )
