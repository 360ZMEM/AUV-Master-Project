"""
Windows 侧 HoloOcean-Zenoh 桥接启动脚本。

该脚本在 Windows 环境下运行，作为 HoloOcean 仿真与 Linux ROS2 决策侧之间的通信桥梁。

架构：
  HoloOcean 仿真 ←→ 本桥接脚本 ←→ Zenoh 网络 ←→ Linux ROS2 决策侧

支持的桥接后端：
  1. zenoh_json：默认，通过 Zenoh 发布 JSON 格式的传感器数据
  2. protocol_udp：二进制 UDP 协议，用于实物 AUV 通信测试

使用方式：
  # 在 Windows 下启动（默认 zenoh_json 后端）
  python sim_holoocean/apps/run_zenoh_bridge.py

  # 指定配置文件
  python sim_holoocean/apps/run_zenoh_bridge.py --config path/to/bridge_params.yaml

环境变量：
  AUV_HOLOOCEAN_UUID：HoloOcean 实例的 UUID（可选）
"""

import argparse
import os
import signal
import sys
from pathlib import Path

import yaml

SIM_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# ────────────────────────────────────────────────
# Python 路径设置：确保所有模块可导入
# ────────────────────────────────────────────────
for p in [
    PROJECT_ROOT,
    PROJECT_ROOT / "common",
    PROJECT_ROOT / "algorithm",
    SIM_ROOT / "behavior",
    SIM_ROOT / "interfaces",
    SIM_ROOT / "apps",
    SIM_ROOT / "experiments",
]:
    p = str(p)
    if p not in sys.path:
        sys.path.insert(0, p)

from command_guard import CommandGuard
from holoocean_physics_bridge import HoloOceanPhysicsZenohBridge
from mock_amd_server import MockAmdUdpServer


def load_config(path):
    """从 YAML 文件加载配置。"""
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return apply_scenario_overrides(cfg)


def _deep_merge(base, override):
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def apply_scenario_overrides(cfg):
    scenario_file = os.environ.get("AUV_SCENARIO_FILE")
    if not scenario_file:
        return cfg
    path = Path(scenario_file)
    if not path.exists():
        print(f"[scenario][WARN] file not found: {path}")
        return cfg
    with path.open("r", encoding="utf-8") as handle:
        scenario = yaml.safe_load(handle) or {}

    if scenario.get("sim_backend"):
        cfg.setdefault("simulation", {})["backend"] = scenario["sim_backend"]
    if "perception" in scenario:
        _deep_merge(cfg.setdefault("perception", {}), scenario.get("perception", {}) or {})
    if "sensor_extrinsics_truth" in scenario:
        cfg["sensor_extrinsics_truth"] = scenario.get("sensor_extrinsics_truth", {}) or {}
    if "flow" in scenario:
        speed = float((scenario.get("flow", {}) or {}).get("current_speed_mps", 0.0))
        current_cfg = cfg.setdefault("environment", {}).setdefault("current", {})
        current_cfg["enabled"] = abs(speed) > 0.0
        current_cfg["vector_ned"] = [speed, 0.0, 0.0]
    if "chaos" in scenario:
        chaos = scenario.get("chaos", {}) or {}
        mock_chaos = cfg.setdefault("mock_amd", {}).setdefault("chaos", {})
        mock_chaos["enabled"] = bool(chaos.get("enabled", False))
        mock_chaos["packet_loss_pct"] = 100.0 * float(chaos.get("packet_loss_prob", 0.0) or 0.0)
        dvl_freeze = chaos.get("dvl_freeze", {}) or {}
        mock_chaos["dvl_freeze_enabled"] = bool(dvl_freeze.get("enabled", False))
        window = dvl_freeze.get("freeze_window_s", [30.0, 60.0])
        mock_chaos["dvl_freeze_after_s"] = float(window[0] if isinstance(window, list) and window else 30.0)
        imu_drift = chaos.get("imu_drift", {}) or {}
        mock_chaos["imu_drift_enabled"] = bool(imu_drift.get("enabled", False))
        mock_chaos["imu_drift_rate_deg_per_s"] = float(imu_drift.get("bias_rate", 0.0) or 0.0)
        depth_spike = chaos.get("depth_spike", {}) or {}
        mock_chaos["depth_spike_enabled"] = bool(depth_spike.get("rate_hz", 0.0) or depth_spike.get("enabled", False))
        mock_chaos["depth_spike_m"] = float(depth_spike.get("amplitude_m", 0.0) or 0.0)
        if chaos.get("mag_saturation_threshold_t") is not None:
            mock_chaos["mag_saturation_enabled"] = True
            mock_chaos["mag_saturation_threshold_t"] = float(chaos["mag_saturation_threshold_t"])
    print(f"[scenario] applied {path}")
    return cfg


def parse_args():
    """
    解析命令行参数。

    返回：
        argparse.Namespace：包含 config 字段
    """
    parser = argparse.ArgumentParser(description="Windows-side HoloOcean-Zenoh bridge")
    parser.add_argument("--config", type=str, default=str(PROJECT_ROOT / "config" / "bridge_params.yaml"))
    return parser.parse_args()


def main():
    """
    主入口：初始化并运行桥接服务。

    流程：
      1. 加载配置文件
      2. 设置信号处理（SIGINT/SIGTERM）
      3. 根据后端类型创建桥接实例
         - protocol_udp → MockAmdUdpServer（二进制协议）
         - zenoh_json → HoloOceanPhysicsZenohBridge（JSON Zenoh）
      4. 启动桥接：open() → run_forever()
      5. 优雅关闭：finally 块中调用 close()
    """
    args = parse_args()
    cfg = load_config(args.config)
    interrupted = {"sigint": False}

    # ────────────────────────────────────────────────
    # 信号处理：支持 Ctrl+C 优雅退出
    # ────────────────────────────────────────────────
    def _mark_interrupted(signum, frame):
        interrupted["sigint"] = True

    signal.signal(signal.SIGINT, _mark_interrupted)
    signal.signal(signal.SIGTERM, _mark_interrupted)

    if os.environ.get("AUV_HOLOOCEAN_UUID"):
        print(f"[AUV] using HoloOcean UUID={os.environ['AUV_HOLOOCEAN_UUID']}")

    # ────────────────────────────────────────────────
    # 创建控制命令护栏和桥接实例
    # ────────────────────────────────────────────────
    guard = CommandGuard(cfg["bridge"])
    backend = str(cfg.get("bridge", {}).get("backend", "zenoh_json"))
    if backend == "protocol_udp":
        # 二进制 UDP 协议后端（用于实物通信测试）
        bridge = MockAmdUdpServer(cfg, guard)
    else:
        # 默认 Zenoh JSON 后端（用于仿真联调）
        bridge = HoloOceanPhysicsZenohBridge(cfg, guard)

    try:
        bridge.open()
        bridge.run_forever()
    except KeyboardInterrupt:
        interrupted["sigint"] = True
        print("[AUV] bridge terminated by user (SIGINT)")
    except Exception as exc:
        # ────────────────────────────────────────────────
        # 容错：SIGINT 时 Zenoh 可能抛出 BusyError
        # ────────────────────────────────────────────────
        if interrupted["sigint"] and exc.__class__.__name__ == "BusyError" and "Semaphore is busy" in str(exc):
            print("[AUV] bridge terminated by user (SIGINT)")
        else:
            raise
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
