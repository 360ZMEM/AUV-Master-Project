#!/usr/bin/env python3
"""
ROS2 AUV数据发布节点
发布模拟的AUV传感器数据供Foxglove可视化
"""

import random
import math
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from std_msgs.msg import Header, String, Float32
from geometry_msgs.msg import Point, Quaternion, PoseStamped, TwistStamped, TransformStamped
from sensor_msgs.msg import NavSatFix, Imu, FluidPressure, Temperature
from tf2_ros import TransformBroadcaster, StaticTransformBroadcaster
from tf2_msgs.msg import TFMessage


class AUVDataPublisher(Node):
    """AUV数据发布器类"""

    def __init__(self):
        super().__init__('auv_data_publisher')

        # 配置QoS策略以确保可靠的通信
        qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL
        )

        # 仿真参数
        self.dt = 0.1
        self.tau_depth = 5.0
        self.tau_speed = 4.0
        self.tau_turn_rate = 3.0

        # 地图参考点（用于局部ENU近似到经纬度）
        self.ref_lat = 31.0300
        self.ref_lon = 110.1230

        # 平滑状态（连续变化）
        self.x = 0.0
        self.y = 0.0
        self.depth = 5.0
        self.heading = 0.0
        self.speed = 1.2
        self.turn_rate = 0.0

        # 一阶驱动目标（慢变）
        self.depth_target = self.depth
        self.speed_target = self.speed
        self.turn_rate_target = self.turn_rate

        # 创建发布器
        self.pose_pub = self.create_publisher(PoseStamped, '/auv/pose', qos)
        self.twist_pub = self.create_publisher(TwistStamped, '/auv/twist', qos)
        self.gps_pub = self.create_publisher(NavSatFix, '/auv/gps', qos)
        self.imu_pub = self.create_publisher(Imu, '/auv/imu', qos)
        self.pressure_pub = self.create_publisher(FluidPressure, '/auv/pressure', 10)
        self.temp_pub = self.create_publisher(Temperature, '/auv/temperature', 10)
        self.status_pub = self.create_publisher(String, '/auv/status', 10)
        self.depth_pub = self.create_publisher(Float32, '/auv/depth', 10)
        self.tf_pub = self.create_publisher(TFMessage, '/tf', 10)

        # TF广播器
        self.tf_broadcaster = TransformBroadcaster(self)
        self.static_tf_broadcaster = StaticTransformBroadcaster(self)

        # 发布静态TF
        self._publish_static_transforms()

        # 创建定时器，10Hz发布频率
        self.timer = self.create_timer(0.1, self.timer_callback)

        self.get_logger().info('AUV数据发布节点已启动')
        self.get_logger().info('发布话题列表:')
        self.get_logger().info('  - /auv/pose (位姿)')
        self.get_logger().info('  - /auv/twist (速度)')
        self.get_logger().info('  - /auv/gps (GPS位置)')
        self.get_logger().info('  - /auv/imu (IMU数据)')
        self.get_logger().info('  - /auv/pressure (压力)')
        self.get_logger().info('  - /auv/temperature (温度)')
        self.get_logger().info('  - /auv/depth (深度)')
        self.get_logger().info('  - /auv/status (状态)')
        self.get_logger().info('  - /tf (TF坐标变换)')

    @staticmethod
    def _quat_from_yaw(yaw: float) -> Quaternion:
        """由偏航角生成四元数。"""
        return Quaternion(
            x=0.0,
            y=0.0,
            z=math.sin(yaw * 0.5),
            w=math.cos(yaw * 0.5),
        )

    def _publish_static_transforms(self):
        """发布AUV本体相关静态TF。"""
        static_tfs: list[TransformStamped] = []

        def _make_static(parent: str, child: str, xyz: tuple[float, float, float]) -> TransformStamped:
            tf = TransformStamped()
            tf.header.stamp = self.get_clock().now().to_msg()
            tf.header.frame_id = parent
            tf.child_frame_id = child
            tf.transform.translation.x = xyz[0]
            tf.transform.translation.y = xyz[1]
            tf.transform.translation.z = xyz[2]
            tf.transform.rotation.w = 1.0
            return tf

        static_tfs.append(_make_static('auv_base_link', 'imu_link', (0.0, 0.0, 0.0)))
        static_tfs.append(_make_static('auv_base_link', 'gps', (0.2, 0.0, 0.1)))
        static_tfs.append(_make_static('auv_base_link', 'pressure_sensor', (0.0, 0.0, -0.1)))
        static_tfs.append(_make_static('auv_base_link', 'temp_sensor', (0.0, 0.0, -0.1)))

        self.static_tf_broadcaster.sendTransform(static_tfs)

    def timer_callback(self):
        """定时回调函数，发布所有传感器数据"""
        time_stamp = self.get_clock().now().to_msg()

        # 更新模拟状态
        self._update_simulation()

        # 发布动态TF(map -> auv_base_link)
        tf_msg = TransformStamped()
        tf_msg.header = Header(stamp=time_stamp, frame_id='map')
        tf_msg.child_frame_id = 'auv_base_link'
        tf_msg.transform.translation.x = self.x
        tf_msg.transform.translation.y = self.y
        tf_msg.transform.translation.z = -self.depth
        tf_msg.transform.rotation = self._quat_from_yaw(self.heading)
        self.tf_broadcaster.sendTransform(tf_msg)
        self.tf_pub.publish(TFMessage(transforms=[tf_msg]))

        # 基于局部平面位移估算经纬度
        latitude = self.ref_lat + self.y / 111111.0
        longitude = self.ref_lon + self.x / (111111.0 * math.cos(math.radians(self.ref_lat)))

        # 发布位姿
        pose_msg = PoseStamped()
        pose_msg.header = Header(stamp=time_stamp, frame_id='map')
        pose_msg.pose.position = Point(
            x=self.x,
            y=self.y,
            z=-self.depth
        )
        pose_msg.pose.orientation = self._quat_from_yaw(self.heading)
        self.pose_pub.publish(pose_msg)

        # 发布速度
        twist_msg = TwistStamped()
        twist_msg.header = Header(stamp=time_stamp, frame_id='auv_base_link')
        twist_msg.twist.linear.x = self.speed
        twist_msg.twist.linear.y = 0.0
        twist_msg.twist.linear.z = 0.0
        twist_msg.twist.angular.x = 0.0
        twist_msg.twist.angular.y = 0.0
        twist_msg.twist.angular.z = self.turn_rate
        self.twist_pub.publish(twist_msg)

        # 发布GPS
        gps_msg = NavSatFix()
        gps_msg.header = Header(stamp=time_stamp, frame_id='gps')
        gps_msg.latitude = latitude
        gps_msg.longitude = longitude
        gps_msg.altitude = -self.depth
        gps_msg.position_covariance = [0.0] * 9
        gps_msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_APPROXIMATED
        self.gps_pub.publish(gps_msg)

        # 发布IMU
        imu_msg = Imu()
        imu_msg.header = Header(stamp=time_stamp, frame_id='imu_link')
        imu_msg.orientation = self._quat_from_yaw(self.heading)
        imu_msg.angular_velocity.x = 0.0
        imu_msg.angular_velocity.y = 0.0
        imu_msg.angular_velocity.z = self.turn_rate
        imu_msg.linear_acceleration.x = 0.0
        imu_msg.linear_acceleration.y = 0.0
        imu_msg.linear_acceleration.z = 9.8
        self.imu_pub.publish(imu_msg)

        # 发布压力
        pressure_msg = FluidPressure()
        pressure_msg.header = Header(stamp=time_stamp, frame_id='pressure_sensor')
        pressure_msg.fluid_pressure = 101325.0 + self.depth * 10000.0  # 帕斯卡
        pressure_msg.variance = 0.0
        self.pressure_pub.publish(pressure_msg)

        # 发布温度
        temp_msg = Temperature()
        temp_msg.header = Header(stamp=time_stamp, frame_id='temp_sensor')
        temp_msg.temperature = 20.0 - 0.015 * self.depth + 0.3 * math.sin(self.heading)
        temp_msg.variance = 0.1
        self.temp_pub.publish(temp_msg)

        # 发布深度
        depth_msg = Float32()
        depth_msg.data = self.depth
        self.depth_pub.publish(depth_msg)

        # 发布状态
        status_msg = String()
        status_msg.data = (
            f'AUV运行正常 | 深度: {self.depth:.2f}m | 航向: {math.degrees(self.heading):.1f}° '
            f'| 航速: {self.speed:.2f}m/s | 位置: ({self.x:.1f}, {self.y:.1f})m'
        )
        self.status_pub.publish(status_msg)

    def _update_simulation(self):
        """使用一阶平滑积分模型更新模拟状态，避免白噪声跳变。"""
        # 目标值缓慢随机游走（低频输入）
        self.depth_target = max(0.0, min(100.0, self.depth_target + random.uniform(-0.25, 0.25)))
        self.speed_target = max(0.2, min(4.0, self.speed_target + random.uniform(-0.06, 0.06)))
        self.turn_rate_target = max(-0.12, min(0.12, self.turn_rate_target + random.uniform(-0.01, 0.01)))

        # 一阶惯性环节：x += (u-x)/tau * dt
        self.depth += (self.depth_target - self.depth) * (self.dt / self.tau_depth)
        self.speed += (self.speed_target - self.speed) * (self.dt / self.tau_speed)
        self.turn_rate += (self.turn_rate_target - self.turn_rate) * (self.dt / self.tau_turn_rate)

        # 积分更新位姿
        self.heading = (self.heading + self.turn_rate * self.dt) % (2 * math.pi)
        self.x += self.speed * math.cos(self.heading) * self.dt
        self.y += self.speed * math.sin(self.heading) * self.dt


def main(args=None):
    """主函数"""
    import rclpy

    rclpy.init(args=args)

    auv_publisher = AUVDataPublisher()

    try:
        rclpy.spin(auv_publisher)
    except KeyboardInterrupt:
        pass
    finally:
        auv_publisher.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
