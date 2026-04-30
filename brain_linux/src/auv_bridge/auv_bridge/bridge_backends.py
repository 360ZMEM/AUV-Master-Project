'''
本文件定义了 AUV 桥接节点的后端接口和两种实现：基于 Zenoh JSON 的主题后端和基于二进制协议的 UDP 后端。
'''
from __future__ import annotations

import json
import socket
import threading
from abc import ABC, abstractmethod
from typing import Any

from common.protocol import (
    KEY_CONTROL_MODE_BYTE,
    KEY_FRAME_NUMBER,
    KEY_MOCK_AMD_TIMESTAMP_US,
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
    """桥接后端抽象接口。

    该接口把不同传输实现统一成同一套生命周期和发送语义，便于桥接节点在
    Zenoh JSON 和协议 UDP 之间切换，而不需要改变上层决策逻辑。
    """

    backend_name = "base"
    requires_command_heartbeat = False

    def __init__(self, *, node, bridge_cfg: dict[str, Any]) -> None:
        self.node = node
        self.bridge_cfg = bridge_cfg

    @abstractmethod
    def open(self) -> None:
        """打开传输资源并准备收发通道。"""

    @abstractmethod
    def close(self) -> None:
        """释放传输资源并注销所有句柄。"""

    @abstractmethod
    def send_command(
        self,
        command_payload: dict[str, float],
        *,
        control_mode_byte: int,
        work_instruction: int,
        orientation_deg: float,
    ) -> None:
        """通过当前后端发送一条控制命令。"""

    def publish_bridge_telemetry(self, payload: dict[str, Any]) -> None:
        """向可选侧通道发布桥接遥测数据。"""
        _ = payload


class TopicBridgeBackend(BaseBridgeBackend):
    """兼容旧系统的 Zenoh JSON 后端。"""

    backend_name = "zenoh_json"

    def __init__(self, *, node, bridge_cfg: dict[str, Any]) -> None:
        """初始化 Zenoh 发布/订阅主题和运行时缓存。"""
        super().__init__(node=node, bridge_cfg=bridge_cfg)
        self.cmd_key = str(bridge_cfg.get('downlink_cmd_key', 'rt/auv/control/cmd_vel'))
        self.imu_key = str(bridge_cfg.get('imu_key', 'rt/auv/sensors/imu'))
        self.dvl_key = str(bridge_cfg.get('dvl_key', 'rt/auv/sensors/dvl'))
        self.depth_key = str(bridge_cfg.get('depth_key', 'rt/auv/sensors/depth'))
        self._session = None
        self._subscribers = []
        self._publishers: dict[str, Any] = {}

    def open(self) -> None:
        """建立 Zenoh 会话并订阅仿真传感器主题。"""
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
        """关闭所有 Zenoh 订阅、发布器和会话。"""
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
        """构造收到 Zenoh 消息后的 JSON 解码回调。"""
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
        """将控制命令写入 Zenoh 控制通道。"""
        _ = orientation_deg
        payload = dict(command_payload)
        payload['control_mode_byte'] = int(control_mode_byte)
        payload['work_instruction'] = int(work_instruction)
        self._publishers[self.cmd_key].put(json.dumps(payload, ensure_ascii=False))


class ProtocolBridgeBackend(BaseBridgeBackend):
    """兼容 $CKTH/$AUV 二进制协议的 UDP 后端。"""

    backend_name = "protocol_udp"
    requires_command_heartbeat = True

    def __init__(self, *, node, bridge_cfg: dict[str, Any]) -> None:
        """初始化 UDP 套接字参数、协议参数和可选 Zenoh 侧通道。"""
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
        """打开 UDP 套接字并启动接收线程。"""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((self.local_host, self.local_port))
        self._socket.settimeout(self.socket_timeout_s)
        self._stop_event.clear()
        self._recv_thread = threading.Thread(target=self._recv_loop, name='auv-protocol-udp-rx', daemon=True)
        self._recv_thread.start()
        if self.zenoh_side_channel_enabled:
            self._open_side_channel()

    def close(self) -> None:
        """停止接收线程并清理 UDP 和侧通道资源。"""
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
        """把控制命令编码为下行协议并通过 UDP 发出。"""
        if self._socket is None:
            raise RuntimeError('protocol udp backend is not open')

        payload = dict(command_payload)
        payload[KEY_FRAME_NUMBER] = self._frame_counter # 协议帧编号，0~255 循环，用于协议层检测丢包和重传
        payload.setdefault(KEY_OBJ_ADDRESS, self.obj_address) # 协议对象地址，默认为 1，表示主控 AUV 对象
        payload[KEY_CONTROL_MODE_BYTE] = int(control_mode_byte) # 协议控制模式字节，定义当前控制模式（如手动、自动、定深等），由上层决策逻辑设置
        payload[KEY_WORK_INSTRUCTION] = int(work_instruction) # 协议工作指令，定义当前具体动作指令（如前进、后退、转向等），由上层决策逻辑设置
        payload[KEY_ORIENTATION_DEG] = float(orientation_deg) # 协议航向角度，单位度，范围 0~360，由上层决策逻辑设置，表示当前期望的航向角度

        # 从 Para1 开始的参数字段，协议中预留了 12 个参数位置（Para1~Para12），供上层决策逻辑根据需要使用。这里我们把 Para1 用来携带一个 Mock AMD 时间戳（微秒级），以便协议侧的决策节点进行时钟同步和调试验证。其他参数位置暂时保留为 0。
        mock_amd_timestamp_us = int(time.time() * 1e6)
        # 确保 payload 中的 KEY_PARAMETERS 是一个长度至少为 1 的列表或元组，如果存在则更新第一个元素为 mock_amd_timestamp_us，否则创建一个新的列表并放入 payload 中。协议中 Para1~Para12 的位置由 KEY_PARAMETERS 定义，协议解析时会把它们映射到对应的参数字段。
        current_parameters = payload.get(KEY_PARAMETERS, [0] * 12)
        if isinstance(current_parameters, (list, tuple)) and len(current_parameters) >= 1:
            parameters_list = list(current_parameters)
            parameters_list[0] = mock_amd_timestamp_us
            payload[KEY_PARAMETERS] = tuple(parameters_list)
        else:
            payload[KEY_PARAMETERS] = [mock_amd_timestamp_us] + [0] * 11

        packet = build_downlink_packet_from_payload(payload, main_motor_rpm_scale=self.main_motor_rpm_scale) # 根据协议定义把 payload 字典编码成二进制下行数据包，main_motor_rpm_scale 用于把协议中的 RPM 值转换为实际推力百分比（仅供调试使用，实际控制算法中不应依赖此转换）
        self._socket.sendto(packet, (self.remote_host, self.remote_port))
        self._frame_counter = (self._frame_counter + 1) & 0xFF

    def publish_bridge_telemetry(self, payload: dict[str, Any]) -> None:
        """通过可选 Zenoh 侧通道发布桥接遥测。"""
        if not self._publishers:
            return
        encoded = json.dumps(payload, ensure_ascii=False)
        for key in (self.telemetry_key, self.viz_internal_key):
            publisher = self._publishers.get(key)
            if publisher is None:
                continue
            publisher.put(encoded)

    def _open_side_channel(self) -> None:
        """在 UDP 模式下额外打开 Zenoh 侧通道，用于调试与观测。"""
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
        """处理来自 PC 原始控制通道的输入并转发给桥接节点。"""
        payload_bytes = sample.payload.to_bytes() if hasattr(sample.payload, 'to_bytes') else bytes(sample.payload)
        data = self._decode_pc_raw_payload(payload_bytes)
        if data is None:
            self.node.get_logger().warning('[bridge] failed to decode rt/pc/cmd_raw side-channel payload')
            return
        self.node.handle_pc_raw_command(data)

        # Publish Mock AMD timestamp from Para1 for decision node clock synchronization
        mock_amd_timestamp_us = data.get(KEY_MOCK_AMD_TIMESTAMP_US, 0)
        if mock_amd_timestamp_us > 0:
            publisher = self._publishers.get(Z_PATH_MOCK_AMD_TIME)
            if publisher is not None:
                publisher.put(json.dumps({KEY_MOCK_AMD_TIMESTAMP_US: int(mock_amd_timestamp_us)}))

    def _decode_pc_raw_payload(self, payload_bytes: bytes) -> dict[str, Any] | None:
        """把原始 PC 控制负载解码为统一的字典格式。"""
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
        """后台 UDP 接收循环，解析上行遥测帧并交给节点处理。"""
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