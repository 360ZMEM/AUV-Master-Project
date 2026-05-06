"""Pure-Python console backend for headless integration testing.

This module provides a Zenoh-based console backend that has zero dependency on
PySide6 / Qt.  It is designed to be used in automated integration tests where
the GUI cannot run.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


class HeadlessConsoleBackend:
    """Zenoh-side-channel implementation that works without any Qt dependency."""

    def __init__(
        self,
        zenoh_ip: str = "127.0.0.1",
        zenoh_port: int = 7447,
        pc_cmd_raw_key: str = "rt/pc/cmd_raw",
        telemetry_key: str = "rt/auv/telemetry",
        viz_internal_key: str = "rt/auv/viz/internal",
    ) -> None:
        self._zenoh_ip = zenoh_ip
        self._zenoh_port = zenoh_port
        self._pc_cmd_raw_key = pc_cmd_raw_key
        self._telemetry_key = telemetry_key
        self._viz_internal_key = viz_internal_key

        self._session: Any = None
        self._publisher: Any = None
        self._subscribers: list[Any] = []

        # Telemetry storage (thread-safe)
        self._telemetry_lock = threading.Lock()
        self._telemetry_queue: deque[dict] = deque(maxlen=200)
        self._viz_queue: deque[dict] = deque(maxlen=200)

        # Heartbeat
        self._heartbeat_running = False
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_interval = 0.1  # 10 Hz default

        # Arbiter state tracking
        self._arbiter_state_lock = threading.Lock()
        self._latest_arbiter: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    def connect(self, timeout_s: float = 5.0) -> bool:
        """Open a Zenoh session in client mode."""
        if self._session is not None:
            return True

        try:
            import zenoh  # type: ignore
        except Exception as exc:
            logger.error("zenoh Python package is not available: %s", exc)
            return False

        connect_str = f"tcp/{self._zenoh_ip}:{self._zenoh_port}"
        zcfg = zenoh.Config()
        zcfg.insert_json5("connect/endpoints", json.dumps([connect_str]))
        zcfg.insert_json5("mode", '"client"')

        try:
            self._session = zenoh.open(zcfg)
            logger.info("Zenoh connected to %s (client mode)", connect_str)
        except Exception as exc:
            logger.error("Zenoh connection failed: %s", exc)
            self._session = None
            return False

        # Declare publisher
        self._publisher = self._session.declare_publisher(self._pc_cmd_raw_key)

        # Declare subscribers
        self._subscribers.append(
            self._session.declare_subscriber(self._telemetry_key, self._telemetry_cb)
        )
        self._subscribers.append(
            self._session.declare_subscriber(self._viz_internal_key, self._viz_cb)
        )

        return True

    def close(self) -> None:
        """Shut down the Zenoh session and release all resources."""
        self.stop_heartbeat()

        for sub in self._subscribers:
            try:
                sub.undeclare()
            except Exception:
                pass
        self._subscribers.clear()

        if self._publisher is not None:
            try:
                self._publisher.undeclare()
            except Exception:
                pass
            self._publisher = None

        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    # ------------------------------------------------------------------
    # Command publishing
    # ------------------------------------------------------------------
    def send_json_command(self, cmd_dict: dict[str, Any]) -> bool:
        """Publish a JSON-encoded command to the PC raw command topic."""
        if self._session is None or self._publisher is None:
            logger.error("Cannot publish: not connected")
            return False
        try:
            payload = json.dumps(cmd_dict, ensure_ascii=False).encode("utf-8")
            self._publisher.put(payload)
            return True
        except Exception as exc:
            logger.error("Publish failed: %s", exc)
            return False

    def send_control_command(
        self,
        control_mode_byte: int,
        thrust: float = 0.0,
        work_instruction: int = 0x00,
        frame_number: int = 0,
        obj_address: int = 1,
        left: float = 0.0,
        right: float = 0.0,
        top: float = 0.0,
        bottom: float = 0.0,
        side_motor_rpm: int = 0,
        orientation_deg: float = 0.0,
        parameters: tuple = (0,) * 12,
    ) -> bool:
        """Send a control command matching the bridge's expected schema."""
        cmd = {
            "frame_number": frame_number,
            "obj_address": obj_address,
            "control_mode_byte": control_mode_byte,
            "work_instruction": work_instruction,
            "thrust": float(thrust),
            "left": float(left),
            "right": float(right),
            "top": float(top),
            "bottom": float(bottom),
            "side_motor_rpm": int(side_motor_rpm),
            "orientation_deg": float(orientation_deg),
            "depth_protect_params": (0, 0),
            "bottom_protect_params": (0, 0),
            "preset_time_tenths_min": 0,
            "spare_params": (0, 0),
            "parameters": parameters,
            "ts": time.time(),
        }
        return self.send_json_command(cmd)

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------
    def start_heartbeat(self, hz: float = 10.0) -> None:
        """Start a background thread that sends heartbeat commands."""
        if self._heartbeat_running:
            return
        self._heartbeat_running = True
        self._heartbeat_interval = 1.0 / max(hz, 1e-3)
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, name="heartbeat", daemon=True
        )
        self._heartbeat_thread.start()
        logger.info("Heartbeat started at %.1f Hz", hz)

    def stop_heartbeat(self) -> None:
        """Stop the heartbeat thread."""
        self._heartbeat_running = False
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2.0)
            self._heartbeat_thread = None
        logger.info("Heartbeat stopped")

    def _heartbeat_loop(self) -> None:
        """Internal loop that periodically sends REMOTE-mode heartbeat."""
        while self._heartbeat_running:
            try:
                self.send_control_command(
                    control_mode_byte=0x01,  # REMOTE_CONTROL
                    thrust=0.0,
                    work_instruction=0x00,
                )
            except Exception as exc:
                logger.warning("Heartbeat send failed: %s", exc)
            time.sleep(self._heartbeat_interval)

    # ------------------------------------------------------------------
    # Telemetry consumption
    # ------------------------------------------------------------------
    def get_latest_telemetry(self, timeout: float = 2.0) -> dict | None:
        """Wait up to *timeout* seconds for a fresh telemetry sample."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._telemetry_lock:
                if self._telemetry_queue:
                    return self._telemetry_queue[-1]
            time.sleep(0.05)
        return None

    def get_all_telemetry(self) -> list[dict]:
        """Return a copy of the entire telemetry buffer."""
        with self._telemetry_lock:
            return list(self._telemetry_queue)

    def get_latest_arbiter_state(self, timeout: float = 2.0) -> dict | None:
        """Wait for arbiter state (from telemetry or viz)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._arbiter_state_lock:
                if self._latest_arbiter:
                    return dict(self._latest_arbiter)
            time.sleep(0.05)
        return None

    def clear_telemetry(self) -> None:
        """Clear the telemetry buffer."""
        with self._telemetry_lock:
            self._telemetry_queue.clear()
        with self._arbiter_state_lock:
            self._latest_arbiter.clear()

    # ------------------------------------------------------------------
    # Callbacks (invoked by Zenoh on background threads)
    # ------------------------------------------------------------------
    def _telemetry_cb(self, sample) -> None:
        """Handle incoming telemetry sample."""
        try:
            payload = sample.payload.to_bytes() if hasattr(sample.payload, "to_bytes") else bytes(sample.payload)
            data = json.loads(payload.decode("utf-8"))
            if not isinstance(data, dict):
                return
            with self._telemetry_lock:
                self._telemetry_queue.append(data)
            self._update_arbiter_state(data)
        except Exception as exc:
            logger.warning("Telemetry decode error: %s", exc)

    def _viz_cb(self, sample) -> None:
        """Handle incoming viz-internal sample."""
        try:
            payload = sample.payload.to_bytes() if hasattr(sample.payload, "to_bytes") else bytes(sample.payload)
            data = json.loads(payload.decode("utf-8"))
            if not isinstance(data, dict):
                return
            with self._telemetry_lock:
                self._viz_queue.append(data)
            self._update_arbiter_state(data)
        except Exception as exc:
            logger.warning("Viz decode error: %s", exc)

    def _update_arbiter_state(self, data: dict) -> None:
        """Extract arbiter-related fields from any incoming dict."""
        arb = {}
        for key in ("active_arbiter", "auto_state", "deny_reason", "arbiter_source",
                     "main_motor_rpm", "work_instruction", "control_mode_byte",
                     "telemetry_freshness_ms", "bt_status_markdown"):
            if key in data:
                arb[key] = data[key]
        if arb:
            arb["_ts"] = time.time()
            with self._arbiter_state_lock:
                self._latest_arbiter.update(arb)
