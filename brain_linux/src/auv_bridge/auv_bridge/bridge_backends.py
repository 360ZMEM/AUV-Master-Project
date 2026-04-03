from __future__ import annotations

import json
import socket
import threading
from abc import ABC, abstractmethod
from typing import Any

from common.protocol import PROTOCOL_UPLINK_SIZE, build_downlink_packet, parse_uplink_packet


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
        self._frame_counter = 0
        self._socket: socket.socket | None = None
        self._recv_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def open(self) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((self.local_host, self.local_port))
        self._socket.settimeout(self.socket_timeout_s)
        self._stop_event.clear()
        self._recv_thread = threading.Thread(target=self._recv_loop, name='auv-protocol-udp-rx', daemon=True)
        self._recv_thread.start()

    def close(self) -> None:
        self._stop_event.set()
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

        packet = build_downlink_packet(
            command_payload,
            frame_counter=self._frame_counter,
            obj_address=self.obj_address,
            control_mode_byte=control_mode_byte,
            work_instruction=work_instruction,
            orientation_deg=orientation_deg,
            main_motor_rpm_scale=self.main_motor_rpm_scale,
            side_motor_rpm=self.side_motor_rpm,
        )
        self._socket.sendto(packet, (self.remote_host, self.remote_port))
        self._frame_counter = (self._frame_counter + 1) & 0xFF

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