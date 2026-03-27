"""Main control entry for AUV_Software_Stack.

设计目标：保持与原 `auv_project/main_sim.py` 相同行为，
同时将仿真相关代码限制在 3_interfaces 与少量主循环调度中。
"""

import argparse
import os
import signal
import sys
from pathlib import Path

import yaml


SIM_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for folder_path in [
    PROJECT_ROOT,
    PROJECT_ROOT / "common",
    PROJECT_ROOT / "algorithm",
    SIM_ROOT / "behavior",
    SIM_ROOT / "interfaces",
    SIM_ROOT / "apps",
    SIM_ROOT / "experiments",
]:
    folder_path = str(folder_path)
    if folder_path not in sys.path:
        sys.path.insert(0, folder_path)

from main_loop import run_main


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_merged_config(sim_config_path, real_config_path=None):
    cfg = load_config(sim_config_path)
    if real_config_path and os.path.exists(real_config_path):
        real_cfg = load_config(real_config_path)
        for key, value in real_cfg.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                cfg[key] = {**cfg[key], **value}
            else:
                cfg[key] = value
    return cfg


def parse_args():
    parser = argparse.ArgumentParser(description="Main simulation loop for underactuated AUV")
    parser.add_argument("--config", type=str, default=str(PROJECT_ROOT / "config" / "sim_params.yaml"), help="Path to sim yaml config")
    parser.add_argument("--real-config", type=str, default=str(PROJECT_ROOT / "config" / "real_params.yaml"), help="Path to real yaml config (optional override)")
    parser.add_argument("--enable-plot", action="store_true", help="Enable matplotlib plot output")
    parser.add_argument("--interactive", action="store_true", help="Use interactive matplotlib mode and update during run")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    config = load_merged_config(args.config, args.real_config)
    interrupted = {"sigint": False}

    def _mark_interrupted(signum, frame):
        interrupted["sigint"] = True

    signal.signal(signal.SIGINT, _mark_interrupted)
    signal.signal(signal.SIGTERM, _mark_interrupted)

    if os.environ.get("AUV_HOLOOCEAN_UUID"):
        print(f"[AUV] using HoloOcean UUID={os.environ['AUV_HOLOOCEAN_UUID']}")
    try:
        run_main(config, args.config, args.enable_plot, args.interactive)
    except KeyboardInterrupt:
        interrupted["sigint"] = True
        print("[AUV] simulation terminated by user (SIGINT)")
    except Exception:
        if interrupted["sigint"]:
            print("[AUV] simulation terminated by user (SIGINT)")
        else:
            raise
