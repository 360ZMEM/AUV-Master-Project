#!/usr/bin/env python3
"""Headless console emulator for benchmark scripts.

Sends a periodic JETSON_PROTOCOL (0xEE) command on the Zenoh side-channel topic
``rt/pc/cmd_raw`` so the bridge's AutonomyGuard transitions LOCKED -> ACTIVE,
allowing the behavior tree to leave StandbyCheck during automated experiments.

Without this emulator a benchmark run produces a 0-byte rosbag because no
"PC authorization" packet ever reaches the bridge.  See
``docs/experiment/terrain_benchmark_log.md`` for the full diagnosis.

The bridge opens its Zenoh session in *peer* mode with default scouting
(multicast).  We do the same here so the two peers discover each other on
loopback without needing a router/listener.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time

JETSON_PROTOCOL = 0xEE
PC_CMD_RAW_KEY = "rt/pc/cmd_raw"


def _build_payload(frame_number: int, *, target_depth_m: float | None = None) -> bytes:
    cmd = {
        "frame_number": frame_number & 0xFFFF,
        "obj_address": 1,
        "control_mode_byte": JETSON_PROTOCOL,
        "work_instruction": 0x00,
        "thrust": 0.0,
        "left": 0.0,
        "right": 0.0,
        "top": 0.0,
        "bottom": 0.0,
        "side_motor_rpm": 0,
        "orientation_deg": 0.0,
        "depth_protect_params": (0, 0),
        "bottom_protect_params": (0, 0),
        "preset_time_tenths_min": 0,
        "spare_params": (0, 0),
        "parameters": (0,) * 12,
        "ts": time.time(),
    }
    if target_depth_m is not None:
        cmd["target_depth_m"] = float(target_depth_m)
    return json.dumps(cmd, ensure_ascii=False).encode("utf-8")


def _open_session(timeout_s: float):
    import zenoh  # type: ignore

    zcfg = zenoh.Config()
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            session = zenoh.open(zcfg)
            return session
        except Exception as exc:
            last_err = exc
            logging.warning("zenoh.open peer-mode failed: %s; retrying...", exc)
            time.sleep(1.0)
    raise RuntimeError(f"zenoh peer session timeout after {timeout_s:.1f}s; last_err={last_err}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate-hz", type=float, default=10.0,
                        help="Heartbeat publish rate (default 10 Hz)")
    parser.add_argument("--connect-timeout", type=float, default=60.0,
                        help="Zenoh session bring-up timeout (s)")
    parser.add_argument("--key", default=PC_CMD_RAW_KEY,
                        help=f"Zenoh key to publish on (default {PC_CMD_RAW_KEY})")
    parser.add_argument(
        "--target-depth-m",
        type=float,
        default=None,
        help="Optional valid hold depth embedded in the 0xEE activation packet.",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    session = _open_session(args.connect_timeout)
    publisher = session.declare_publisher(args.key)
    logging.info("auto_activate_emu peer session up; publishing on %s at %.1f Hz",
                 args.key, args.rate_hz)

    stop = {"flag": False}

    def _bye(signum, _frame):
        logging.info("auto_activate_emu received signal %d, shutting down", signum)
        stop["flag"] = True

    signal.signal(signal.SIGINT, _bye)
    signal.signal(signal.SIGTERM, _bye)

    interval = 1.0 / max(args.rate_hz, 0.1)
    frame = 0
    try:
        while not stop["flag"]:
            try:
                publisher.put(_build_payload(frame, target_depth_m=args.target_depth_m))
            except Exception as exc:
                logging.warning("publish failed: %s", exc)
            frame += 1
            time.sleep(interval)
    finally:
        try:
            publisher.undeclare()
        except Exception:
            pass
        try:
            session.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
