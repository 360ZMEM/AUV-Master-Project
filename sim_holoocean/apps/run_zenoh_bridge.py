import argparse
import os
import signal
import sys
from pathlib import Path

import yaml

SIM_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
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
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_args():
    parser = argparse.ArgumentParser(description="Windows-side HoloOcean-Zenoh bridge")
    parser.add_argument("--config", type=str, default=str(PROJECT_ROOT / "config" / "bridge_params.yaml"))
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = load_config(args.config)
    interrupted = {"sigint": False}

    def _mark_interrupted(signum, frame):
        interrupted["sigint"] = True

    signal.signal(signal.SIGINT, _mark_interrupted)
    signal.signal(signal.SIGTERM, _mark_interrupted)

    if os.environ.get("AUV_HOLOOCEAN_UUID"):
        print(f"[AUV] using HoloOcean UUID={os.environ['AUV_HOLOOCEAN_UUID']}")

    guard = CommandGuard(cfg["bridge"])
    backend = str(cfg.get("bridge", {}).get("backend", "zenoh_json"))
    if backend == "protocol_udp":
        bridge = MockAmdUdpServer(cfg, guard)
    else:
        bridge = HoloOceanPhysicsZenohBridge(cfg, guard)

    try:
        bridge.open()
        bridge.run_forever()
    except KeyboardInterrupt:
        interrupted["sigint"] = True
        print("[AUV] bridge terminated by user (SIGINT)")
    except Exception as exc:
        if interrupted["sigint"] and exc.__class__.__name__ == "BusyError" and "Semaphore is busy" in str(exc):
            print("[AUV] bridge terminated by user (SIGINT)")
        else:
            raise
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
