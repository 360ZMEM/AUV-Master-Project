#!/usr/bin/env python3
"""Strict ROS 2 monitor for the ESTOP-to-surface defense demonstration."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class Monitor(Node):
    def __init__(self) -> None:
        super().__init__("emergency_surface_monitor")
        self.started = time.monotonic()
        self.events: list[dict] = []
        self.initial_depth_m: float | None = None
        self.minimum_depth_m: float | None = None
        self.maximum_active_speed_mps = 0.0
        self.saw_active = False
        self.saw_surfaced = False
        self.latest: dict = {}
        self.create_subscription(String, "/auv/emergency/status", self._on_status, 20)

    def _on_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        self.latest = payload
        depth = float(payload.get("current_depth_m", float("nan")))
        active = bool(payload.get("active", False))
        state = str(payload.get("state", "UNKNOWN"))
        if active and not self.saw_active:
            self.saw_active = True
            self.initial_depth_m = depth
            self.events.append({"elapsed_s": round(time.monotonic() - self.started, 3), "state": state, "depth_m": depth})
        if active:
            self.minimum_depth_m = depth if self.minimum_depth_m is None else min(self.minimum_depth_m, depth)
            self.maximum_active_speed_mps = max(
                self.maximum_active_speed_mps,
                abs(float(payload.get("horizontal_speed_mps", 0.0))),
            )
        if state == "SURFACED" and not self.saw_surfaced:
            self.saw_surfaced = True
            self.events.append({"elapsed_s": round(time.monotonic() - self.started, 3), "state": state, "depth_m": depth})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--output", required=True)
    parser.add_argument("--surface-threshold-m", type=float, default=0.8)
    parser.add_argument("--minimum-ascent-m", type=float, default=8.0)
    args = parser.parse_args()
    rclpy.init()
    node = Monitor()
    deadline = time.monotonic() + args.duration
    try:
        while rclpy.ok() and time.monotonic() < deadline and not node.saw_surfaced:
            rclpy.spin_once(node, timeout_sec=0.1)
        initial = node.initial_depth_m
        final = node.minimum_depth_m
        ascent = None if initial is None or final is None else initial - final
        passed = bool(
            node.saw_active
            and node.saw_surfaced
            and final is not None
            and final <= args.surface_threshold_m
            and ascent is not None
            and ascent >= args.minimum_ascent_m
            and node.maximum_active_speed_mps <= 0.05
        )
        report = {
            "schema": "auv.emergency_surface_assurance.v1",
            "passed": passed,
            "saw_estop": node.saw_active,
            "saw_surfaced": node.saw_surfaced,
            "initial_depth_m": initial,
            "minimum_depth_m": final,
            "ascent_m": ascent,
            "maximum_active_horizontal_speed_mps": node.maximum_active_speed_mps,
            "events": node.events,
            "latest": node.latest,
        }
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        raise SystemExit(0 if passed else 3)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
