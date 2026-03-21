#!/usr/bin/env python3
"""Zenoh JSON <-> ROS2 topic adapter for Linux side.

This node bridges current simulation JSON payloads to ROS2 topics and maps
`/cmd_vel` back to zenoh command payload expected by the simulation side.
"""

from __future__ import annotations

import json
import time
from typing import Any
from pathlib import Path

import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import Float32
import yaml


class ZenohJsonBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__('zenoh_json_bridge_node')

        default_params = str(Path(__file__).resolve().parents[4] / 'brain_linux' / 'config' / 'params.yaml')
        self.declare_parameter('params_file', default_params)
        self.declare_parameter('downlink_cmd_key', 'rt/auv/control/cmd_vel')
        self.declare_parameter('imu_key', 'rt/auv/sensors/imu')
        self.declare_parameter('dvl_key', 'rt/auv/sensors/dvl')
        self.declare_parameter('depth_key', 'rt/auv/sensors/depth')
        self.declare_parameter('cmd_timeout_s', 0.5)

        cfg = self._load_config(str(self.get_parameter('params_file').value)).get('bridge', {})

        self.cmd_key = str(cfg.get('downlink_cmd_key', self.get_parameter('downlink_cmd_key').value))
        self.imu_key = str(cfg.get('imu_key', self.get_parameter('imu_key').value))
        self.dvl_key = str(cfg.get('dvl_key', self.get_parameter('dvl_key').value))
        self.depth_key = str(cfg.get('depth_key', self.get_parameter('depth_key').value))

        self.imu_pub = self.create_publisher(Imu, '/auv/sensors/imu', 10)
        self.dvl_pub = self.create_publisher(TwistStamped, '/auv/sensors/dvl', 10)
        self.depth_pub = self.create_publisher(Float32, '/auv/sensors/depth', 10)

        self.cmd_sub = self.create_subscription(Twist, '/cmd_vel', self._on_cmd_vel, 10)

        self._session = None
        self._subscribers = []
        self._publishers = {}

        self._lat_count = 0
        self._lat_sum = 0.0

        self._open_zenoh()
        self.create_timer(2.0, self._on_stats_timer)

        self.get_logger().info('Zenoh JSON bridge node started')

    @staticmethod
    def _load_config(path: str) -> dict:
        p = Path(path)
        if not p.exists():
            return {}
        with p.open('r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}

    def _open_zenoh(self) -> None:
        try:
            import zenoh  # type: ignore
        except Exception as exc:
            raise RuntimeError('zenoh python package is required for auv_bridge') from exc

        zcfg = zenoh.Config()
        self._session = zenoh.open(zcfg)

        self._publishers[self.cmd_key] = self._session.declare_publisher(self.cmd_key)

        self._subscribers.append(self._session.declare_subscriber(self.imu_key, self._make_cb(self._on_imu_payload)))
        self._subscribers.append(self._session.declare_subscriber(self.dvl_key, self._make_cb(self._on_dvl_payload)))
        self._subscribers.append(self._session.declare_subscriber(self.depth_key, self._make_cb(self._on_depth_payload)))

    def _make_cb(self, fn):
        def _cb(sample):
            payload = sample.payload.to_bytes() if hasattr(sample.payload, 'to_bytes') else bytes(sample.payload)
            try:
                data = json.loads(payload.decode('utf-8'))
            except Exception:
                return
            fn(data)

        return _cb

    def _record_latency(self, data: dict[str, Any]) -> None:
        ts = data.get('ts')
        if isinstance(ts, (int, float)):
            dt = time.time() - float(ts)
            if dt >= 0.0:
                self._lat_count += 1
                self._lat_sum += dt

    def _on_imu_payload(self, data: dict[str, Any]) -> None:
        self._record_latency(data)

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

    def _on_dvl_payload(self, data: dict[str, Any]) -> None:
        self._record_latency(data)

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

    def _on_depth_payload(self, data: dict[str, Any]) -> None:
        self._record_latency(data)

        depth = data.get('depth_m')
        if not isinstance(depth, (int, float)):
            return

        msg = Float32()
        msg.data = float(depth)
        self.depth_pub.publish(msg)

    def _on_cmd_vel(self, msg: Twist) -> None:
        # Fixed mapping contract:
        # linear.x -> thrust, angular.x -> right, angular.y -> top,
        # angular.z -> left, linear.z -> bottom.
        command_payload = {
            'right': float(msg.angular.x),
            'top': float(msg.angular.y),
            'left': float(msg.angular.z),
            'bottom': float(msg.linear.z),
            'thrust': float(msg.linear.x),
            'ts': time.time(),
        }

        payload = json.dumps(command_payload, ensure_ascii=False)
        self._publishers[self.cmd_key].put(payload)

    def _on_stats_timer(self) -> None:
        if self._lat_count == 0:
            self.get_logger().info('[bridge] waiting for sensor payloads...')
            return
        mean_ms = (self._lat_sum / self._lat_count) * 1000.0
        self.get_logger().info(f'[bridge] mean sensor ingress latency: {mean_ms:.2f} ms over {self._lat_count} samples')

    def destroy_node(self):
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

        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ZenohJsonBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
