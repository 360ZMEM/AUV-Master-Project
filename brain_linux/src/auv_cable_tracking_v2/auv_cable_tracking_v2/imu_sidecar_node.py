"""Passive loopback-only ROS receiver for the uninstalled IMV1 candidate.

The normal output is a separate review topic. Publication to the navigation
IMU topic is available only for an explicitly identified synthetic fixture.
"""

from __future__ import annotations

import math
import socket
from copy import deepcopy

import rclpy
from geometry_msgs.msg import TwistStamped
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import String

from common.imu_provenance_sidecar import decode_imu_provenance
from .dvl_sidecar_join import BodyDvlSample, join_body_dvl_to_sidecar, parse_body_dvl_json
from .imu_sidecar_gate import ImuSidecarGate


def _quaternion(roll: float, pitch: float, yaw: float) -> tuple[float, float, float, float]:
    cr, sr = math.cos(roll / 2.), math.sin(roll / 2.)
    cp, sp = math.cos(pitch / 2.), math.sin(pitch / 2.)
    cy, sy = math.cos(yaw / 2.), math.sin(yaw / 2.)
    return (sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy,
            cr * cp * cy + sr * sp * sy)


class ImuSidecarNode(Node):
    def __init__(self, *, parameter_overrides=None):
        super().__init__('auv_inspection_imu_sidecar_node',
                         parameter_overrides=parameter_overrides)
        self.declare_parameter('local_host', '127.0.0.1')
        self.declare_parameter('local_port', 53667)
        self.declare_parameter('source_host', '127.0.0.1')
        self.declare_parameter('publish_navigation_imu', False)
        self.declare_parameter('synthetic_fixture_only', False)
        self.declare_parameter('yaw_alignment_deg', 9999.0)
        self.declare_parameter('synthetic_orientation_variance_rad2', 0.0)
        host = str(self.get_parameter('local_host').value)
        source_host = str(self.get_parameter('source_host').value)
        port = int(self.get_parameter('local_port').value)
        self.publish_navigation_imu = bool(self.get_parameter('publish_navigation_imu').value)
        fixture = bool(self.get_parameter('synthetic_fixture_only').value)
        if host != '127.0.0.1' or source_host != '127.0.0.1' or not 1024 <= port <= 65535:
            raise ValueError('candidate sidecar receiver requires explicit localhost UDP port')
        if self.publish_navigation_imu and not fixture:
            raise ValueError('navigation IMU publication is restricted to synthetic fixtures')
        self.yaw_alignment_deg = float(self.get_parameter('yaw_alignment_deg').value)
        self.fixture_orientation_variance = float(
            self.get_parameter('synthetic_orientation_variance_rad2').value)
        self.alignment_known = (math.isfinite(self.yaw_alignment_deg)
                                and abs(self.yaw_alignment_deg) <= 360.)
        if self.publish_navigation_imu and (
                not self.alignment_known
                or not math.isfinite(self.fixture_orientation_variance)
                or self.fixture_orientation_variance <= 0.):
            raise ValueError('synthetic navigation fixture requires alignment and variance')
        self.gate = ImuSidecarGate()
        self._latest_dvl: BodyDvlSample | None = None
        self._latest_imu = None
        self._latest_imu_quaternion = None
        self._latest_imu_stamp_s = None
        self._last_published_dvl_uptime_ms = None
        self.candidate_pub = self.create_publisher(Imu, '/auv/sensors/imu_provenance_candidate', 10)
        self.navigation_pub = (self.create_publisher(Imu, '/auv/sensors/imu', 10)
                               if self.publish_navigation_imu else None)
        self.dvl_candidate_pub = self.create_publisher(
            TwistStamped, '/auv/sensors/dvl_provenance_candidate', 10)
        self.dvl_navigation_pub = (self.create_publisher(TwistStamped, '/auv/sensors/dvl', 10)
                                   if self.publish_navigation_imu else None)
        self.create_subscription(String, '/auv/sensors/dvl_body_pc104_candidate',
                                 self._on_body_dvl, 10)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.socket.bind((host, port))
            self.socket.setblocking(False)
        except Exception:
            self.socket.close()
            raise
        self.create_timer(0.01, self._poll)
        self.get_logger().warning('IMV1 candidate on loopback; no physical IMU source certified')

    def _on_body_dvl(self, message: String):
        try:
            self._latest_dvl = parse_body_dvl_json(message.data)
        except ValueError:
            return
        self._try_join_dvl()

    def _revoke_join_authority(self):
        self._latest_imu = None
        self._latest_imu_quaternion = None
        self._latest_imu_stamp_s = None

    def _try_join_dvl(self):
        if (not self.alignment_known or self._latest_dvl is None
                or self._latest_imu is None):
            return
        dvl = self._latest_dvl
        previous_ms = self._last_published_dvl_uptime_ms
        if previous_ms is not None:
            advance = (dvl.pc104_dvl_uptime_ms - previous_ms) & 0xffffffff
            if advance == 0 or advance >= 0x80000000:
                return
        now_s = self.get_clock().now().nanoseconds * 1e-9
        joined = join_body_dvl_to_sidecar(
            dvl, self._latest_imu, self._latest_imu_quaternion,
            self._latest_imu_stamp_s, now_s)
        if not joined.accepted:
            return
        msg = TwistStamped()
        stamp_sec = math.floor(joined.stamp_s)
        msg.header.stamp.sec = stamp_sec
        msg.header.stamp.nanosec = int(round((joined.stamp_s - stamp_sec) * 1e9))
        if msg.header.stamp.nanosec == 1_000_000_000:
            msg.header.stamp.sec += 1
            msg.header.stamp.nanosec = 0
        msg.header.frame_id = 'auv/world'
        msg.twist.linear.x, msg.twist.linear.y, msg.twist.linear.z = joined.world_xyz_mps
        self._last_published_dvl_uptime_ms = dvl.pc104_dvl_uptime_ms
        self.dvl_candidate_pub.publish(msg)
        if self.dvl_navigation_pub is not None:
            self.dvl_navigation_pub.publish(msg)

    def _poll(self):
        for _ in range(32):
            try:
                packet, source = self.socket.recvfrom(2048)
            except BlockingIOError:
                return
            if source[0] != '127.0.0.1':
                continue
            try:
                record = decode_imu_provenance(packet)
            except ValueError:
                continue
            now_s = self.get_clock().now().nanoseconds * 1e-9
            admission = self.gate.admit(record, receive_ros_s=now_s)
            if not admission.accepted:
                if admission.reason != 'warming_up':
                    self._revoke_join_authority()
                continue
            message = Imu()
            stamp_sec = math.floor(admission.stamp_s)
            message.header.stamp.sec = stamp_sec
            message.header.stamp.nanosec = int(round((admission.stamp_s - stamp_sec) * 1e9))
            if message.header.stamp.nanosec == 1_000_000_000:
                message.header.stamp.sec += 1
                message.header.stamp.nanosec = 0
            message.header.frame_id = ('auv/base_link' if self.alignment_known
                                       else 'imu/gx3_unaligned')
            yaw = record.yaw_rad + (math.radians(self.yaw_alignment_deg)
                                    if self.alignment_known else 0.)
            quaternion = _quaternion(
                 record.roll_rad, record.pitch_rad, yaw)
            (message.orientation.x, message.orientation.y,
             message.orientation.z, message.orientation.w) = quaternion
            message.angular_velocity.x = record.angular_rate_x_rps
            message.angular_velocity.y = record.angular_rate_y_rps
            message.angular_velocity.z = record.angular_rate_z_rps
            # The sidecar carries no acceleration or physical covariance.
            message.linear_acceleration_covariance[0] = -1.
            message.orientation_covariance[0] = -1.
            self.candidate_pub.publish(message)
            if self.navigation_pub is not None:
                nav_message = deepcopy(message)
                nav_message.orientation_covariance[0] = self.fixture_orientation_variance
                nav_message.orientation_covariance[4] = self.fixture_orientation_variance
                nav_message.orientation_covariance[8] = self.fixture_orientation_variance
                self.navigation_pub.publish(nav_message)
            self._latest_imu = record
            self._latest_imu_quaternion = quaternion
            self._latest_imu_stamp_s = admission.stamp_s
            self._try_join_dvl()

    def destroy_node(self):
        self.socket.close()
        return super().destroy_node()


def main():
    rclpy.init()
    node = ImuSidecarNode()
    try:
        rclpy.spin(node)
    except ExternalShutdownException:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
