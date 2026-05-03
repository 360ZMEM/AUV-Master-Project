"""Optional Zenoh side channel for arbiter-aware console integration."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QObject, Signal


class ZenohSideChannel(QObject):
    """Publish raw CKTH packets and receive bridge telemetry over Zenoh."""

    bridge_telemetry_received = Signal(object)
    viz_internal_received = Signal(object)
    arbiter_state_received = Signal(object)
    status_changed = Signal(str)

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__()
        cfg = config or {}
        self.enabled = bool(cfg.get('enabled', False))
        self.session_config = cfg.get('session', {})
        self.pc_cmd_raw_key = str(cfg.get('pc_cmd_raw_key', 'rt/pc/cmd_raw'))
        self.telemetry_key = str(cfg.get('telemetry_key', 'rt/auv/telemetry'))
        self.viz_internal_key = str(cfg.get('viz_internal_key', 'rt/auv/viz/internal'))
        self.publish_cmd_raw = bool(cfg.get('publish_cmd_raw', True))
        self.subscribe_bridge_telemetry = bool(cfg.get('subscribe_bridge_telemetry', True))
        self.subscribe_viz_internal = bool(cfg.get('subscribe_viz_internal', False))

        self._session = None
        self._publisher = None
        self._subscribers: list[Any] = []
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active and self._session is not None

    def start(self) -> bool:
        if not self.enabled:
            self.status_changed.emit('Zenoh side channel disabled by config')
            return False
        if self.is_active:
            return True

        try:
            import zenoh  # type: ignore
        except Exception as exc:
            self.status_changed.emit(f'Zenoh side channel unavailable: {exc}')
            return False

        zcfg = zenoh.Config()
        if isinstance(self.session_config, dict):
            for key, value in self.session_config.items():
                try:
                    zcfg.insert_json5(str(key), json.dumps(value, ensure_ascii=False))
                except Exception:
                    continue

        self._session = zenoh.open(zcfg)
        if self.publish_cmd_raw:
            self._publisher = self._session.declare_publisher(self.pc_cmd_raw_key)
        if self.subscribe_bridge_telemetry:
            self._subscribers.append(self._session.declare_subscriber(self.telemetry_key, self._make_cb('telemetry')))
        if self.subscribe_viz_internal:
            self._subscribers.append(self._session.declare_subscriber(self.viz_internal_key, self._make_cb('viz')))

        self._active = True
        self.status_changed.emit('Zenoh side channel started')
        return True

    def stop(self) -> None:
        self._active = False
        for sub in self._subscribers:
            try:
                sub.undeclare()
            except Exception:
                pass
        self._subscribers = []

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

        self.status_changed.emit('Zenoh side channel stopped')

    def publish_pc_cmd_raw(self, packet: bytes) -> bool:
        if not self.is_active or self._publisher is None:
            return False
        try:
            self._publisher.put(packet)
            return True
        except Exception as exc:
            self.status_changed.emit(f'Zenoh raw publish failed: {exc}')
            return False

    def _make_cb(self, stream_name: str):
        def _cb(sample) -> None:
            payload = sample.payload.to_bytes() if hasattr(sample.payload, 'to_bytes') else bytes(sample.payload)
            try:
                decoded = json.loads(payload.decode('utf-8'))
            except Exception as exc:
                self.status_changed.emit(f'Zenoh {stream_name} decode failed: {exc}')
                return
            if not isinstance(decoded, dict):
                self.status_changed.emit(f'Zenoh {stream_name} payload is not a dict')
                return

            if stream_name == 'telemetry':
                self.bridge_telemetry_received.emit(decoded)
                arbiter_view = {
                    'active_arbiter': decoded.get('active_arbiter', '--'),
                    'auto_state': decoded.get('auto_state', '--'),
                    'deny_reason': decoded.get('deny_reason', '--'),
                    'telemetry_freshness_ms': decoded.get('telemetry_freshness_ms', None),
                }
                self.arbiter_state_received.emit(arbiter_view)
                return

            self.viz_internal_received.emit(decoded)

        return _cb