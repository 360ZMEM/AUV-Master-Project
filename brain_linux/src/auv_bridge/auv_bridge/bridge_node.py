#!/usr/bin/env python3
from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

import rclpy

from . import PROJECT_ROOT
from auv_interfaces.msg import Setpoint
from geometry_msgs.msg import Twist, TwistStamped
from rclpy.node import Node
from sensor_msgs.msg import Imu, MagneticField
from std_msgs.msg import Float32
import yaml

from common.enums import BridgeBackend
from common.protocol import (
    KEY_B_NED,
    KEY_BOTTOM,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_TOP,
    KEY_THRUST,
    ProtocolUplinkTelemetry,
)

from .bridge_backends import BaseBridgeBackend, ProtocolBridgeBackend, TopicBridgeBackend


def _rpy_deg_to_quaternion(roll_deg: float, pitch_deg: float, yaw_deg: float) -> tuple[float, float, float, float]:
    roll = math.radians(roll_deg)
    pitch = math.radians(pitch_deg)
    yaw = math.radians(yaw_deg)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    qw = cr * cp * cy + sr * sp * sy
    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy
    return qx, qy, qz, qw


class AUVBridgeNode(Node):
    """ROS2 bridge node with pluggable transport backend."""

    def __init__(self, *, node_name: str = 'auv_bridge_node', preferred_backend: str | None = None) -> None:
        super().__init__(node_name)

        default_params = str(PROJECT_ROOT / 'brain_linux' / 'config' / 'params.yaml')
        self.declare_parameter('params_file', default_params)
        self.declare_parameter('bridge_backend', preferred_backend or '')

        params_file = str(self.get_parameter('params_file').value)
        cfg = self._load_config(params_file)
        self.bridge_cfg = cfg.get('bridge', {})

        configured_backend = str(self.bridge_cfg.get('backend', '')).strip()
        requested_backend = str(self.get_parameter('bridge_backend').value).strip()
        backend_name = requested_backend or configured_backend or preferred_backend or BridgeBackend.ZENOH_JSON.value
        self.backend = BridgeBackend(backend_name)

        self.cmd_timeout_s = float(self.bridge_cfg.get('cmd_timeout_s', 0.5))
        self.command_publish_hz = float(self.bridge_cfg.get('command_publish_hz', 10.0))
        self.protocol_control_mode_byte = int(self.bridge_cfg.get('protocol_control_mode_byte', 0xEE))
        self.protocol_work_instruction = int(self.bridge_cfg.get('protocol_work_instruction', 0x00))
        self.protocol_send_zero_on_idle = bool(self.bridge_cfg.get('protocol_send_zero_on_idle', True))
        self.imu_key = str(self.bridge_cfg.get('imu_key', 'rt/auv/sensors/imu'))
        self.dvl_key = str(self.bridge_cfg.get('dvl_key', 'rt/auv/sensors/dvl'))
        self.depth_key = str(self.bridge_cfg.get('depth_key', 'rt/auv/sensors/depth'))
        self.magnetic_key = str(self.bridge_cfg.get('magnetic_key', 'rt/auv/sensors/magnetic'))

        self.imu_pub = self.create_publisher(Imu, '/auv/sensors/imu', 10)
        self.dvl_pub = self.create_publisher(TwistStamped, '/auv/sensors/dvl', 10)
        self.depth_pub = self.create_publisher(Float32, '/auv/sensors/depth', 10)
        self.magnetic_pub = self.create_publisher(MagneticField, '/auv/sensors/magnetic', 10)

        self.create_subscription(Twist, '/cmd_vel', self._on_cmd_vel, 10)
        self.create_subscription(Setpoint, '/auv/control/setpoint', self._on_setpoint, 10)

        self.latest_setpoint: Setpoint | None = None
        self.latest_command_payload: dict[str, float] | None = None
        self.latest_command_ts = 0.0
        self._rx_count = 0
        self._lat_count = 0
        self._lat_sum = 0.0

        self.transport = self._create_transport(self.backend)
        self.transport.open()

        if self.transport.requires_command_heartbeat:
            self.create_timer(1.0 / max(self.command_publish_hz, 1e-3), self._on_command_keepalive)
        self.create_timer(2.0, self._on_stats_timer)

        self.get_logger().info(f'bridge backend started: {self.backend.value}')

    @staticmethod
    def _load_config(path: str) -> dict[str, Any]:
        p = Path(path)
        if not p.exists():
            return {}
        with p.open('r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

    def _create_transport(self, backend: BridgeBackend) -> BaseBridgeBackend:
        if backend == BridgeBackend.ZENOH_JSON:
            return TopicBridgeBackend(node=self, bridge_cfg=self.bridge_cfg)
        if backend == BridgeBackend.PROTOCOL_UDP:
            return ProtocolBridgeBackend(node=self, bridge_cfg=self.bridge_cfg)
        raise RuntimeError(f'unsupported bridge backend: {backend.value}')

    def _on_setpoint(self, msg: Setpoint) -> None:
        self.latest_setpoint = msg

    def _on_cmd_vel(self, msg: Twist) -> None:
        self.latest_command_payload = {
            KEY_RIGHT: float(msg.angular.x),
            KEY_TOP: float(msg.angular.y),
            KEY_LEFT: float(msg.angular.z),
            KEY_BOTTOM: float(msg.linear.z),
            KEY_THRUST: float(msg.linear.x),
            'ts': time.time(),
        }
        self.latest_command_ts = time.time()
        self._publish_command(self.latest_command_payload)

    def _on_command_keepalive(self) -> None:
        if self.latest_command_payload is None:
            if not self.protocol_send_zero_on_idle:
                return
            payload = self._zero_command_payload()
        elif time.time() - self.latest_command_ts > self.cmd_timeout_s:
            payload = self._zero_command_payload()
        else:
            payload = dict(self.latest_command_payload)
            payload['ts'] = time.time()
        self._publish_command(payload)

    def _zero_command_payload(self) -> dict[str, float]:
        return {
            KEY_RIGHT: 0.0,
            KEY_TOP: 0.0,
            KEY_LEFT: 0.0,
            KEY_BOTTOM: 0.0,
            KEY_THRUST: 0.0,
            'ts': time.time(),
        }

    def _publish_command(self, payload: dict[str, float]) -> None:
        self.transport.send_command(
            payload,
            control_mode_byte=self._resolve_control_mode_byte(),
            work_instruction=self.protocol_work_instruction,
            orientation_deg=self._resolve_target_heading_deg(),
        )

    def _resolve_control_mode_byte(self) -> int:
        if self.latest_setpoint is not None and int(self.latest_setpoint.control_mode_byte) != 0:
            return int(self.latest_setpoint.control_mode_byte)
        return self.protocol_control_mode_byte if self.backend == BridgeBackend.PROTOCOL_UDP else 0x01

    def _resolve_target_heading_deg(self) -> float:
        if self.latest_setpoint is None:
            return 0.0
        return math.degrees(float(self.latest_setpoint.target_heading_rad))

    def _record_latency(self, payload: dict[str, Any]) -> None:
        ts = payload.get('ts')
        if isinstance(ts, (int, float)):
            dt = time.time() - float(ts)
            if dt >= 0.0:
                self._lat_count += 1
                self._lat_sum += dt

    def handle_json_sensor_payload(self, keyexpr: str, data: dict[str, Any]) -> None:
        self._rx_count += 1
        self._record_latency(data)

        if keyexpr == self.imu_key:
            accel = data.get('accel_ned', [0.0, 0.0, 0.0])
            gyro = data.get('gyro_ned', [0.0, 0.0, 0.0])
            if not (isinstance(accel, list) and len(accel) == 3 and isinstance(gyro, list) and len(gyro) == 3):
                return
            msg = Imu()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = 'auv/base_link'
            msg.linear_acceleration.x = float(accel[0])
            msg.linear_acceleration.y = float(accel[1])
            msg.linear_acceleration.z = float(accel[2])
            msg.angular_velocity.x = float(gyro[0])
            msg.angular_velocity.y = float(gyro[1])
            msg.angular_velocity.z = float(gyro[2])
            self.imu_pub.publish(msg)
            return

        if keyexpr == self.dvl_key:
            vel = data.get('vel_ned', [0.0, 0.0, 0.0])
            if not (isinstance(vel, list) and len(vel) == 3):
                return
            msg = TwistStamped()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = 'auv/base_link'
            msg.twist.linear.x = float(vel[0])
            msg.twist.linear.y = float(vel[1])
            msg.twist.linear.z = float(vel[2])
            self.dvl_pub.publish(msg)
            return

        if keyexpr == self.depth_key:
            depth = data.get('depth_m')
            if not isinstance(depth, (int, float)):
                return
            msg = Float32()
            msg.data = float(depth)
            self.depth_pub.publish(msg)
            return

        if keyexpr == self.magnetic_key:
            magnetic_vec = data.get(KEY_B_NED, [0.0, 0.0, 0.0])
            if not (isinstance(magnetic_vec, list) and len(magnetic_vec) == 3):
                return
            msg = MagneticField()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = 'auv/base_link'
            msg.magnetic_field.x = float(magnetic_vec[0])
            msg.magnetic_field.y = float(magnetic_vec[1])
            msg.magnetic_field.z = float(magnetic_vec[2])
            self.magnetic_pub.publish(msg)

    def handle_protocol_telemetry(self, telemetry: ProtocolUplinkTelemetry) -> None:
        self._rx_count += 1

        imu_msg = Imu()
        imu_msg.header.stamp = self.get_clock().now().to_msg()
        imu_msg.header.frame_id = 'auv/base_link'
        qx, qy, qz, qw = _rpy_deg_to_quaternion(telemetry.roll_deg, telemetry.pitch_deg, telemetry.heading_deg)
        imu_msg.orientation.x = qx
        imu_msg.orientation.y = qy
        imu_msg.orientation.z = qz
        imu_msg.orientation.w = qw
        imu_msg.angular_velocity.x = 0.0
        imu_msg.angular_velocity.y = 0.0
        imu_msg.angular_velocity.z = 0.0
        imu_msg.linear_acceleration.x = 0.0
        imu_msg.linear_acceleration.y = 0.0
        imu_msg.linear_acceleration.z = 0.0
        self.imu_pub.publish(imu_msg)

        dvl_msg = TwistStamped()
        dvl_msg.header.stamp = self.get_clock().now().to_msg()
        dvl_msg.header.frame_id = 'auv/base_link'
        dvl_msg.twist.linear.x = float(telemetry.dvl_speed_mps)
        dvl_msg.twist.linear.y = 0.0
        dvl_msg.twist.linear.z = 0.0
        self.dvl_pub.publish(dvl_msg)

        depth_msg = Float32()
        depth_msg.data = float(telemetry.depth_m)
        self.depth_pub.publish(depth_msg)

    def _on_stats_timer(self) -> None:
        if self._rx_count == 0:
            self.get_logger().info('[bridge] waiting for sensor payloads...')
            return
        if self._lat_count == 0:
            self.get_logger().info(f'[bridge] received {self._rx_count} sensor payloads via {self.backend.value}')
            return
        mean_ms = (self._lat_sum / self._lat_count) * 1000.0
        self.get_logger().info(f'[bridge] mean sensor ingress latency: {mean_ms:.2f} ms over {self._lat_count} samples')

    def destroy_node(self):
        self.transport.close()
        return super().destroy_node()


def main(args=None, *, preferred_backend: str | None = None, node_name: str = 'auv_bridge_node') -> None:
    rclpy.init(args=args)
    node = AUVBridgeNode(node_name=node_name, preferred_backend=preferred_backend)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()