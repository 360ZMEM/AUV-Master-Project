#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brain_linux" / "src" / "auv_control"))

from auv_decision_ros.fangkong_adc_client import (  # noqa: E402
    DEFAULT_MAIN_REPO_DEVICE_HOST,
    FangkongAdcMagneticClient,
    resolve_project_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="探测 FK2301/TMR8637 链路是否可达")
    parser.add_argument(
        "--params-file",
        default="brain_linux/config/magnetic_wrapper_fangkong.yaml",
        help="真实 magnetic wrapper 参数文件",
    )
    parser.add_argument("--host", default="", help="临时覆盖 ADC IP")
    parser.add_argument("--port", type=int, default=0, help="临时覆盖 ADC 端口")
    parser.add_argument("--print-config-only", action="store_true", help="仅打印解析后的配置，不连接设备")
    return parser.parse_args()


def load_ros_params(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("参数文件顶层必须是字典")
    for section in data.values():
        if isinstance(section, dict) and isinstance(section.get("ros__parameters"), dict):
            return dict(section["ros__parameters"])
    raise ValueError("参数文件中缺少 ros__parameters")


def main() -> int:
    args = parse_args()
    params_path = resolve_project_path(args.params_file)
    params = load_ros_params(params_path)
    params["device_host"] = args.host or params.get("device_host", DEFAULT_MAIN_REPO_DEVICE_HOST)
    if args.port:
        params["device_port"] = args.port

    print("[probe] params_file =", params_path)
    print("[probe] device_host =", params["device_host"])
    print("[probe] calibration_profile_path =", params.get("calibration_profile_path", ""))

    if args.print_config_only:
        return 0

    client = FangkongAdcMagneticClient(
        fangkong_root=params["fangkong_root"],
        fangkong_default_config=params["fangkong_default_config"],
        fangkong_user_config=params.get("fangkong_user_config") or None,
        use_fangkong_user_config=bool(params.get("use_fangkong_user_config", False)),
        device_host=params["device_host"],
        device_port=int(params["device_port"]),
        connect_timeout_sec=float(params.get("connect_timeout_sec", 3.0)),
        recv_timeout_sec=float(params.get("recv_timeout_sec", 1.0)),
        reconnect_interval_sec=float(params.get("reconnect_interval_sec", 2.0)),
        sample_rate_hz=int(params.get("sample_rate_hz", 2000)),
        active_channels=[int(item) for item in params.get("active_channels", [0, 1, 2])],
        read_bytes_per_request=int(params.get("read_bytes_per_request", 1404)),
        sensor_sensitivity_mv_per_ut=[float(item) for item in params.get("sensor_sensitivity_mv_per_ut", [20.02, 19.98, 19.96])],
        transport_mode=str(params.get("transport_mode", "poll")),
        waveform_y_unit=str(params.get("waveform_y_unit", "magnetic_field")),
        calibration_enabled=bool(params.get("calibration_enabled", True)),
        calibration_profile_path=params.get("calibration_profile_path", ""),
        axis_order=[int(item) for item in params.get("axis_order", [0, 1, 2])],
        axis_signs=[float(item) for item in params.get("axis_signs", [1.0, 1.0, 1.0])],
    )
    try:
        client.start()
    except Exception as exc:
        print(f"[probe][ERROR] ADC 未就绪或链路错误: {exc}")
        return 2
    finally:
        client.stop()

    print("[probe] ADC 连接/设参/启动成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
