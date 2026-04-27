from __future__ import annotations

import json
import socket
import threading
from abc import ABC, abstractmethod
from typing import Any

from common.protocol import (
    KEY_CONTROL_MODE_BYTE,
    KEY_FRAME_NUMBER,
    KEY_MOCK_AMD_TIMESTAMP,
    KEY_OBJ_ADDRESS,
    KEY_ORIENTATION_DEG,
    KEY_PARAMETERS,
    KEY_WORK_INSTRUCTION,
    PROTOCOL_DOWNLINK_SIZE,
    PROTOCOL_UPLINK_SIZE,
    Z_PATH_MOCK_AMD_TIME,
    build_downlink_packet_from_payload,
    parse_downlink_packet_to_payload,
    parse_uplink_packet,
)

import time


class BaseBridgeBackend(ABC):
    """Transport backend interface used by the ROS2 bridge node."""

    backend_name = "base"
    requires_command_heartbeat = False

    def __init__(self, *, node, bridge_cfg: dict[str, Any]) -> None:
        self.node = node
        self.bridge_cfg = bridge_cfg

    @abstractmethod
    def open(self) -> None:
        """Open transport resources."""

    @abstractmethod
    def close(self) -> None:
        """Release transport resources."""

    @abstractmethod
    def send_command(
        self,
        command_payload: dict[str, float],
        *,
        control_mode_byte: int,
        work_instruction: int,
        orientation_deg: float,
    ) -> None:
        """Send one control command through the backend."""

    def publish_bridge_telemetry(self, payload: dict[str, Any]) -> None:
        """Publish bridge telemetry to any optional side channel."""
        _ = payload


class TopicBridgeBackend(BaseBridgeBackend):
    """Legacy Zenoh JSON backend preserved for compatibility."""

    backend_name = "zenoh_json"

    def __init__(self, *, node, bridge_cfg: dict[str, Any]) -> None:
        super().__init__(node=node, bridge_cfg=bridge_cfg)
        self.cmd_key = str(bridge_cfg.get('downlink_cmd_key', 'rt/auv/control/cmd_vel'))
        self.imu_key = str(bridge_cfg.get('imu_key', 'rt/auv/sensors/imu'))
        self.dvl_key = str(bridge_cfg.get('dvl_key', 'rt/auv/sensors/dvl'))
        self.depth_key = str(bridge_cfg.get('depth_key', 'rt/auv/sensors/depth'))
        self._session = None
        self._subscribers = []
        self._publishers: dict[str, Any] = {}

    def open(self) -> None:
        try:
            import zenoh  # type: ignore
        except Exception as exc:
            raise RuntimeError('zenoh python package is required for auv_bridge') from exc

        zcfg = zenoh.Config()
        self._session = zenoh.open(zcfg)
        self._publishers[self.cmd_key] = self._session.declare_publisher(self.cmd_key)
        self._subscribers.append(self._session.declare_subscriber(self.imu_key, self._make_cb(self.imu_key)))
        self._subscribers.append(self._session.declare_subscriber(self.dvl_key, self._make_cb(self.dvl_key)))
        self._subscribers.append(self._session.declare_subscriber(self.depth_key, self._make_cb(self.depth_key)))
        magnetic_key = str(self.bridge_cfg.get('magnetic_key', 'rt/auv/sensors/magnetic'))
        self._subscribers.append(self._session.declare_subscriber(magnetic_key, self._make_cb(magnetic_key)))

    def close(self) -> None:
        for sub in self._subscribers:
            try:
                sub.undeclare()
            except Exception:
                pass
        self._subscribers = []

        for pub in self._publishers.values():
            try:
                pub.undeclare()
            except Exception:
                pass
        self._publishers = {}

        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    def _make_cb(self, keyexpr: str):
        def _cb(sample) -> None:
            payload = sample.payload.to_bytes() if hasattr(sample.payload, 'to_bytes') else bytes(sample.payload)
            try:
                data = json.loads(payload.decode('utf-8'))
            except Exception:
                return
            self.node.handle_json_sensor_payload(keyexpr, data)

        return _cb

    def send_command(
        self,
        command_payload: dict[str, float],
        *,
        control_mode_byte: int,
        work_instruction: int,
        orientation_deg: float,
    ) -> None:
        _ = orientation_deg
        payload = dict(command_payload)
        payload['control_mode_byte'] = int(control_mode_byte)
        payload['work_instruction'] = int(work_instruction)
        self._publishers[self.cmd_key].put(json.dumps(payload, ensure_ascii=False))


class ProtocolBridgeBackend(BaseBridgeBackend):
    """Binary UDP backend compatible with the $CKTH/$AUV protocol."""

    backend_name = "protocol_udp"
    requires_command_heartbeat = True

    def __init__(self, *, node, bridge_cfg: dict[str, Any]) -> None:
        super().__init__(node=node, bridge_cfg=bridge_cfg)
        protocol_cfg = bridge_cfg.get('protocol_udp', {})
        self.local_host = str(protocol_cfg.get('local_host', '0.0.0.0'))
        self.local_port = int(protocol_cfg.get('local_port', 52365))
        self.remote_host = str(protocol_cfg.get('remote_host', '127.0.0.1'))
        self.remote_port = int(protocol_cfg.get('remote_port', 52364))
        self.socket_timeout_s = float(protocol_cfg.get('socket_timeout_s', 0.1))
        self.recv_buffer_size = int(protocol_cfg.get('recv_buffer_size', 2048))
        self.obj_address = int(protocol_cfg.get('obj_address', 1))
        self.main_motor_rpm_scale = float(protocol_cfg.get('main_motor_rpm_scale', 15.0))
        self.side_motor_rpm = int(protocol_cfg.get('side_motor_rpm', 0))
        arbiter_cfg = bridge_cfg.get('arbiter', {})
        self.zenoh_side_channel_enabled = bool(protocol_cfg.get('zenoh_side_channel_enabled', False))
        self.pc_cmd_raw_key = str(arbiter_cfg.get('pc_cmd_raw_key', 'rt/pc/cmd_raw'))
        self.telemetry_key = str(arbiter_cfg.get('telemetry_key', 'rt/auv/telemetry'))
        self.viz_internal_key = str(arbiter_cfg.get('viz_internal_key', 'rt/auv/viz/internal'))
        self._frame_counter = 0
        self._socket: socket.socket | None = None
        self._recv_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._session = None
        self._subscribers = []
        self._publishers: dict[str, Any] = {}

    def open(self) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((self.local_host, self.local_port))
        self._socket.settimeout(self.socket_timeout_s)
        self._stop_event.clear()
        self._recv_thread = threading.Thread(target=self._recv_loop, name='auv-protocol-udp-rx', daemon=True)
        self._recv_thread.start()
        if self.zenoh_side_channel_enabled:
            self._open_side_channel()

    def close(self) -> None:
        self._stop_event.set()
        for sub in self._subscribers:
            try:
                sub.undeclare()
            except Exception:
                pass
        self._subscribers = []

        for pub in self._publishers.values():
            try:
                pub.undeclare()
            except Exception:
                pass
        self._publishers = {}

        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        if self._recv_thread is not None:
            self._recv_thread.join(timeout=1.0)
            self._recv_thread = None

    def send_command(
        self,
        command_payload: dict[str, float],
        *,
        control_mode_byte: int,
        work_instruction: int,
        orientation_deg: float,
    ) -> None:
        if self._socket is None:
            raise RuntimeError('protocol udp backend is not open')

        payload = dict(command_payload)
        payload[KEY_FRAME_NUMBER] = self._frame_counter
        payload.setdefault(KEY_OBJ_ADDRESS, self.obj_address)
        payload[KEY_CONTROL_MODE_BYTE] = int(control_mode_byte)
        payload[KEY_WORK_INSTRUCTION] = int(work_instruction)
        payload[KEY_ORIENTATION_DEG] = float(orientation_deg)

        # Embed current Unix microseconds in Para1 for Mock AMD clock synchronization
        mock_amd_timestamp_us = int(time.time() * 1e6)
        # Para1 is the first element of parameters tuple
        current_parameters = payload.get(KEY_PARAMETERS, [0] * 12)
        if isinstance(current_parameters, (list, tuple)) and len(current_parameters) >= 1:
            parameters_list = list(current_parameters)
            parameters_list[0] = mock_amd_timestamp_us
            payload[KEY_PARAMETERS] = tuple(parameters_list)
        else:
            payload[KEY_PARAMETERS] = [mock_amd_timestamp_us] + [0] * 11

        packet = build_downlink_packet_from_payload(payload, main_motor_rpm_scale=self.main_motor_rpm_scale)
        self._socket.sendto(packet, (self.remote_host, self.remote_port))
        self._frame_counter = (self._frame_counter + 1) & 0xFF

    def publish_bridge_telemetry(self, payload: dict[str, Any]) -> None:
        if not self._publishers:
            return
        encoded = json.dumps(payload, ensure_ascii=False)
        for key in (self.telemetry_key, self.viz_internal_key):
            publisher = self._publishers.get(key)
            if publisher is None:
                continue
            publisher.put(encoded)

    def _open_side_channel(self) -> None:
        try:
            import zenoh  # type: ignore
        except Exception as exc:
            self.node.get_logger().warning(
                f'[bridge] zenoh python package unavailable, disable protocol_udp side channel: {exc}'
            )
            self.zenoh_side_channel_enabled = False
            return

        zcfg = zenoh.Config()
        self._session = zenoh.open(zcfg)
        self._subscribers.append(self._session.declare_subscriber(self.pc_cmd_raw_key, self._on_pc_raw_sample))
        self._publishers[self.telemetry_key] = self._session.declare_publisher(self.telemetry_key)
        self._publishers[self.viz_internal_key] = self._session.declare_publisher(self.viz_internal_key)
        self._publishers[Z_PATH_MOCK_AMD_TIME] = self._session.declare_publisher(Z_PATH_MOCK_AMD_TIME)

    def _on_pc_raw_sample(self, sample) -> None:
        payload_bytes = sample.payload.to_bytes() if hasattr(sample.payload, 'to_bytes') else bytes(sample.payload)
        data = self._decode_pc_raw_payload(payload_bytes)
        if data is None:
            self.node.get_logger().warning('[bridge] failed to decode rt/pc/cmd_raw side-channel payload')
            return
        self.node.handle_pc_raw_command(data)

        # Publish Mock AMD timestamp from Para1 for decision node clock synchronization
        mock_amd_timestamp_us = data.get(KEY_MOCK_AMD_TIMESTAMP, 0)
        if mock_amd_timestamp_us != 0:
            publisher = self._publishers.get(Z_PATH_MOCK_AMD_TIME)
            if publisher is not None:
                publisher.put(json.dumps({KEY_MOCK_AMD_TIMESTAMP: int(mock_amd_timestamp_us)}))

    def _decode_pc_raw_payload(self, payload_bytes: bytes) -> dict[str, Any] | None:
        if len(payload_bytes) == PROTOCOL_DOWNLINK_SIZE:
            try:
                return parse_downlink_packet_to_payload(payload_bytes, main_motor_rpm_scale=self.main_motor_rpm_scale)
            except Exception:
                return None

        try:
            decoded = json.loads(payload_bytes.decode('utf-8'))
        except Exception:
            return None
        return decoded if isinstance(decoded, dict) else None

    def _recv_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._socket is None:
                return
            try:
                packet, _addr = self._socket.recvfrom(self.recv_buffer_size)
            except socket.timeout:
                continue
            except OSError:
                return

            if len(packet) != PROTOCOL_UPLINK_SIZE:
                self.node.get_logger().warning(f'[bridge] ignore uplink with unexpected size: {len(packet)}')
                continue

            try:
                telemetry = parse_uplink_packet(packet)
            except Exception as exc:
                self.node.get_logger().warning(f'[bridge] failed to parse uplink packet: {exc}')
                continue

            self.node.handle_protocol_telemetry(telemetry)