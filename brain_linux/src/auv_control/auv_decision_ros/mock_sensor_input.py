#!/usr/bin/env python3
"""海试日志回放 -> SensorStatus 发布节点。

功能目标：
  1) 读取海试文本日志（默认读取仓库内示例 txt）
  2) 提取 `$AUV` 行并解析数字字段
  3) 转换为 `auv_interfaces/SensorStatus` 后发布到 `/auv/sensors/status`
  4) `confidence` 按当前需求默认随机生成，便于快速联调
  5) 发布辅助显示话题（置信度文本、电压警告等）

设计模式：
  - 多候选日志路径自动探测，支持不同工作目录启动
  - 文本日志数字恢复为近似145字节二进制帧进行协议级解析
  - 漏水等级、电压、深度等关键字段通过协议字节位读取
  - confidence 仍为随机值，后续可替换为算法结果
  
说明：
  - 当前版本优先"可运行与可回放"，字段映射采用启发式方案
  - 后续若提供精确协议字段说明，可在 `_map_tokens_to_sensor_status()` 中替换
"""

from __future__ import annotations

import random
import re
import struct
from pathlib import Path
from typing import List

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, String

from auv_interfaces.msg import SensorStatus, Setpoint


def _format_confidence_markdown(confidence: float) -> str:
    return f'## {confidence:.2f}'


def _format_power_markdown(voltage_v: float, threshold_v: float) -> str:
    if voltage_v < threshold_v:
        return f'## LOW POWER: {voltage_v:.2f}V'
    return f'## POWER: {voltage_v:.2f}V'


class MockSensorInputNode(Node):
    """海试日志回放发布器。
    
    该节点模拟真实传感数据流，通过回放历史海试日志为决策引擎
    提供一致的输入序列。常用于联调、验证与回归测试。
    
    订阅话题：
      - /auv/control/setpoint: 控制目标（用于计算深度误差）
      
    发布话题：
      - /auv/sensors/status: 传感器状态（主要输出）
      - /auv/metrics/depth_error: 深度误差标量
      - /auv/metrics/lateral_error: 横向误差标量
      - /auv/display/confidence_text: 置信度Markdown文本
      - /auv/display/power_text: 电压警告Markdown文本
    """

    def __init__(self) -> None:
        super().__init__('mock_sensor_input')

        # 默认日志文件指向仓库中的历史样例；可通过参数覆盖。
        # 说明：安装到 ROS2 install 后，__file__ 位于 site-packages，
        # 不能再假设固定父目录层级，因此采用“多候选路径”自动探测。
        default_log = self._guess_default_log_file()

        self.declare_parameter('log_file', str(default_log))
        self.declare_parameter('publish_hz', 10.0)
        self.declare_parameter('battery_low_voltage_threshold', 44.8)
        self.declare_parameter('seabed_depth_m', 15.0)
        self.declare_parameter('seabed_proximity_margin_m', 1.5)
        self.declare_parameter('status_log_period', 2.0)

        self.log_file = Path(self.get_parameter('log_file').get_parameter_value().string_value)
        self.publish_hz = float(
            self.get_parameter('publish_hz').get_parameter_value().double_value
        )
        self.battery_low_voltage_threshold = float(
            self.get_parameter('battery_low_voltage_threshold').get_parameter_value().double_value
        )
        self.seabed_depth_m = float(self.get_parameter('seabed_depth_m').get_parameter_value().double_value)
        self.seabed_proximity_margin_m = float(
            self.get_parameter('seabed_proximity_margin_m').get_parameter_value().double_value
        )
        self.status_log_period = float(
            self.get_parameter('status_log_period').get_parameter_value().double_value
        )

        # 发布器：将解析后的传感状态发布到行为树输入话题。
        self.publisher = self.create_publisher(SensorStatus, '/auv/sensors/status', 10)
        self.depth_error_pub = self.create_publisher(Float32, '/auv/metrics/depth_error', 10)
        self.lateral_error_pub = self.create_publisher(Float32, '/auv/metrics/lateral_error', 10)
        self.confidence_text_pub = self.create_publisher(String, '/auv/display/confidence_text', 10)
        self.power_text_pub = self.create_publisher(String, '/auv/display/power_text', 10)
        self.latest_setpoint_depth_m: float | None = None
        self.create_subscription(Setpoint, '/auv/control/setpoint', self._on_setpoint, 10)

        # 读取日志并预解析：仅缓存每条 $AUV 行的数字序列。
        self.parsed_lines: List[List[int]] = self._load_auv_numeric_lines(self.log_file)
        self.current_index = 0
        self.last_status_log_ns = 0

        timer_period = 1.0 / max(self.publish_hz, 1e-6)
        self.timer = self.create_timer(timer_period, self._on_timer)

        self.get_logger().info(f'已加载日志: {self.log_file}')
        self.get_logger().info(f'可回放数据行数: {len(self.parsed_lines)}')
        self.get_logger().info(
            f'低电压阈值: {self.battery_low_voltage_threshold:.1f}V '
            '(total_voltage 低于该值视作 battery_low=True)'
        )
        self.get_logger().info(
            f'海底参考深度: {self.seabed_depth_m:.1f}m, '
            f'近底告警余量: {self.seabed_proximity_margin_m:.1f}m'
        )
        self.get_logger().info(f'状态摘要周期: {self.status_log_period:.1f}s')
        self.get_logger().info('发布话题: /auv/sensors/status')

    def _on_setpoint(self, msg: Setpoint) -> None:
        """订阅控制目标消息，记录当前设定深度用于误差计算。
        
        Args:
            msg: 控制器发布的设定点消息
        """
        self.latest_setpoint_depth_m = float(msg.target_depth_m)

    def _guess_default_log_file(self) -> Path:
        """自动猜测默认日志文件路径。

        搜索优先级：
          1) 当前工作目录相对路径（适合在 ros2_ws 下运行）
          2) 安装脚本路径反推仓库根目录
          3) 用户主目录下常见项目路径
          
        Returns:
            Path: 默认日志文件的完整路径
            
        说明：
            若所有候选路径都不存在，仍返回第一候选以便日志
            中显示期望的文件位置，便于用户调试。
        """
        # 仓库实际结构: AUV_Master_Project/ 与 Console上位机软件/ 并列
        workspace = Path(__file__).resolve()
        # 尝试从当前文件反推仓库根目录
        for i in range(2, 10):
            candidate_root = workspace.parents[i] if i < len(workspace.parents) else workspace.parent
            if (candidate_root / 'AUV_Master_Project').exists():
                workspace_root = candidate_root
                break
        else:
            workspace_root = Path.cwd()

        candidates = [
            # 1) 仓库根目录下的 Console上位机软件 样例日志
            workspace_root / 'Console上位机软件' / 'auv_console_python' / '20020101103632.txt',
            # 2) 当前工作目录同级（常见开发布局）
            Path.cwd().parent / 'Console上位机软件' / 'auv_console_python' / '20020101103632.txt',
            # 3) 用户主目录下常见位置
            Path.home() / 'master_work-tmp' / 'Console上位机软件' / 'auv_console_python' / '20020101103632.txt',
        ]

        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.exists():
                return resolved

        # 若都未命中，返回第一候选，便于日志中直观看到期望路径。
        return candidates[0].resolve()

    def _load_auv_numeric_lines(self, file_path: Path) -> List[List[int]]:
        """读取日志文件并提取 `$AUV` 行中的数字序列。
        
        Args:
            file_path: 日志文件路径
            
        Returns:
            List[List[int]]: 每行的整数序列列表
            
        说明：
            - 忽略非 $AUV 行
            - 使用正则表达式提取所有整数（包括负数）
            - 若文件不存在，返回空列表并记录错误日志
        """
        if not file_path.exists():
            self.get_logger().error(f'日志文件不存在: {file_path}')
            return []

        result: List[List[int]] = []
        pattern = re.compile(r'-?\d+')

        with file_path.open('r', encoding='utf-8', errors='ignore') as f:
            for raw_line in f:
                if '$AUV' not in raw_line:
                    continue

                # 截断到 $AUV 之后，提取全部整数。
                segment = raw_line[raw_line.find('$AUV') + 4 :]
                tokens = [int(x) for x in pattern.findall(segment)]
                if tokens:
                    result.append(tokens)

        return result

    def _map_tokens_to_sensor_status(self, tokens: List[int]) -> SensorStatus:
        """将数字字段映射为 SensorStatus。

        映射策略（本版）：
          1) 先把文本数字序列恢复为"近似145字节二进制帧"
          2) 再按协议字节位读取关键字段，减少启发式误判：
             - leak_level: 来自 system_alarm（byte 127）bit0/bit1
             - battery_low: 来自 total_voltage（bytes 102-103）阈值判断
             - depth_m: 来自 depth（bytes 38-39）
             - speed_mps: 来自 gps_speed（bytes 80-81）并从节转换为 m/s
             - seabed_proximity: 由当前深度与配置海底深度计算
             - anomaly_detected: 来自 depth_alarm/bottom_alarm，辅以小概率扰动

        Args:
            tokens: 从日志 $AUV 行解析的整数序列
            
        Returns:
            SensorStatus: 完整的传感器状态消息
            
        注意：
          - confidence 仍按默认要求使用随机值，后续可替换为算法输出
          - 文本日志有零值压缩，本恢复算法是"最小可用"版本，聚焦决策所需字段
        """
        msg = SensorStatus()
        packet = self._tokens_to_binary_packet(tokens)

        # 1) 置信度：按当前要求默认随机输出，后续可改为算法结果。
        msg.confidence = random.uniform(0.35, 0.95)

        # 2) 漏水等级（协议位级映射）：
        # system_alarm = byte 127，bit0=内部漏水，bit1=外部漏水。
        system_alarm = packet[127]
        internal_leak = bool(system_alarm & 0x01)
        external_leak = bool(system_alarm & 0x02)
        if internal_leak and external_leak:
            msg.leak_level = SensorStatus.LEAK_BOTH
        elif internal_leak:
            msg.leak_level = SensorStatus.LEAK_INTERNAL
        elif external_leak:
            msg.leak_level = SensorStatus.LEAK_EXTERNAL
        else:
            msg.leak_level = SensorStatus.LEAK_NONE

        # 3) battery_low：从总电压字段读取（bytes 102-103，×0.1V）。
        total_voltage_v = struct.unpack('>H', packet[102:104])[0] * 0.1
        msg.total_voltage_v = float(total_voltage_v)
        msg.battery_low = total_voltage_v < self.battery_low_voltage_threshold

        # 4) depth_m：从深度字段读取（bytes 38-39）。
        # 与现有 packet_builder 对齐：u16 × 0.1。
        msg.depth_m = struct.unpack('>H', packet[38:40])[0] * 0.1

        # 5) speed_mps：优先使用 GPS 速度（bytes 80-81，单位节×0.1）。
        gps_speed_knots = struct.unpack('>H', packet[80:82])[0] * 0.1
        msg.speed_mps = gps_speed_knots * 0.514444

        # 6) seabed warning：由当前深度与配置化海底深度计算。
        msg.seabed_depth_m = self.seabed_depth_m
        msg.seabed_clearance_m = self.seabed_depth_m - msg.depth_m
        msg.seabed_proximity_warning = msg.seabed_clearance_m <= self.seabed_proximity_margin_m
        msg.seabed_penetration_warning = msg.seabed_clearance_m < 0.0

        # 7) anomaly_detected：优先依据报警字节，辅以小概率扰动便于演示装饰器生效。
        # depth_alarm(byte128) / bottom_alarm(byte129) 任一非零即视为异常。
        depth_alarm = packet[128]
        bottom_alarm = packet[129]
        msg.anomaly_detected = bool(depth_alarm != 0 or bottom_alarm != 0 or random.random() < 0.05)

        return msg

    def _publish_display_topics(self, msg: SensorStatus) -> None:
        """发布用于显示的辅助话题（Markdown文本）。
        
        Args:
            msg: 当前传感器状态消息
            
        说明：
            - 置信度显示为H2标题
            - 电压低于阈值时显示低电压告警
            - 深度误差基于当前设定点计算
            - 横向误差当前为占位值（后续集成磁力计）
        """
        target_depth = self.latest_setpoint_depth_m if self.latest_setpoint_depth_m is not None else float(msg.depth_m)
        self.depth_error_pub.publish(Float32(data=float(msg.depth_m) - float(target_depth)))
        self.lateral_error_pub.publish(Float32(data=0.0))
        self.confidence_text_pub.publish(String(data=_format_confidence_markdown(float(msg.confidence))))
        self.power_text_pub.publish(
            String(
                data=_format_power_markdown(
                    float(msg.total_voltage_v),
                    float(self.battery_low_voltage_threshold),
                )
            )
        )

    def _tokens_to_binary_packet(self, tokens: List[int]) -> bytes:
        """将文本数字序列恢复为近似145字节二进制帧。

        恢复策略：
          - 文本日志并非逐字节直出，存在"零值压缩 + 关键字段保留"
          - 通过值域扫描定位 GPS/深度/压力/舵角等关键字段并写入固定偏移
          - 优先级：固定位置覆盖 > 值域扫描（提高稳定性）
          
        Args:
            tokens: 从日志提取的整数序列
            
        Returns:
            bytes: 145字节的接近真实格式的二进制帧
            
        说明：
          - 目标是稳定提取 leak/depth/voltage/speed，不是完整重建所有语义
          - 帧头 5 字节固定为 $AUV\x91
          - 关键字段的字节偏移参考项目协议文档
        """
        packet = bytearray(145)
        packet[0:5] = b'\x24\x41\x55\x56\x91'

        # 前几个字段通常稳定：长度、帧号、地址、模式。
        if len(tokens) > 0:
            packet[5] = tokens[0] & 0xFF
        if len(tokens) > 1:
            packet[6] = tokens[1] & 0xFF
        if len(tokens) > 2:
            packet[7] = tokens[2] & 0xFF
        if len(tokens) > 3:
            packet[8] = tokens[3] & 0xFF

        # 扫描剩余值并填充关键字段。
        for value in tokens:
            # GPS经度（×1e6）
            if 70000000 < value < 140000000:
                packet[94:98] = int(value).to_bytes(4, byteorder='big', signed=True)
            # GPS纬度（×1e6）
            elif 10000000 < value < 55000000:
                packet[98:102] = int(value).to_bytes(4, byteorder='big', signed=True)
            # 深度原始值（bytes 38-39）
            elif 0 <= value <= 50000 and packet[38:40] == b'\x00\x00':
                packet[38:40] = int(value).to_bytes(2, byteorder='big', signed=False)
            # 压力（bytes 35-36）
            elif 0 <= value <= 100000 and packet[35:37] == b'\x00\x00':
                packet[35:37] = int(value).to_bytes(2, byteorder='big', signed=False)
            # 舵角（bytes 27-34）
            elif -1800 <= value <= 1800:
                if packet[27:29] == b'\x00\x00':
                    packet[27:29] = int(value).to_bytes(2, byteorder='big', signed=True)
                elif packet[29:31] == b'\x00\x00':
                    packet[29:31] = int(value).to_bytes(2, byteorder='big', signed=True)
                elif packet[31:33] == b'\x00\x00':
                    packet[31:33] = int(value).to_bytes(2, byteorder='big', signed=True)
                elif packet[33:35] == b'\x00\x00':
                    packet[33:35] = int(value).to_bytes(2, byteorder='big', signed=True)

        # 尽可能用“固定位置”覆盖关键字段（当文本长度足够时），提高稳定性。
        # 位置来源：项目文档《协议映射详解》中的关键字段映射表。
        # tokens[18]~[21] 通常对应压力/温度/深度等。
        if len(tokens) > 21:
            packet[35:37] = int(tokens[19]).to_bytes(2, byteorder='big', signed=False)
            packet[37] = int(tokens[20]) & 0xFF
            packet[38:40] = int(tokens[21]).to_bytes(2, byteorder='big', signed=False)

        # GPS 位置常见在 tokens[27], tokens[28]。
        if len(tokens) > 28:
            lon = int(tokens[27])
            lat = int(tokens[28])
            if 70000000 < lon < 140000000:
                packet[94:98] = lon.to_bytes(4, byteorder='big', signed=True)
            if 10000000 < lat < 55000000:
                packet[98:102] = lat.to_bytes(4, byteorder='big', signed=True)

        # 尾部字段尝试映射：system/depth/bottom alarm（若可用）。
        # 由于文本存在压缩，这里仅在有足够长度时按“近似固定偏移”写入。
        if len(tokens) > 42:
            packet[127] = int(tokens[42]) & 0xFF
        if len(tokens) > 43:
            packet[128] = int(tokens[43]) & 0xFF
        if len(tokens) > 44:
            packet[129] = int(tokens[44]) & 0xFF

        # 校验和与帧尾。
        packet[142] = sum(packet[0:142]) & 0xFF
        packet[143:145] = b'\xFF\xFF'

        return bytes(packet)

    def _on_timer(self) -> None:
        """定时发布一条回放状态。"""
        if not self.parsed_lines:
            return

        tokens = self.parsed_lines[self.current_index]
        msg = self._map_tokens_to_sensor_status(tokens)
        self.publisher.publish(msg)
        self._publish_display_topics(msg)

        self._log_readable_progress(msg)

        self.current_index = (self.current_index + 1) % len(self.parsed_lines)

    def _log_readable_progress(self, msg: SensorStatus) -> None:
        """低频输出一行回放进度摘要，避免刷屏。"""
        now_ns = self.get_clock().now().nanoseconds
        if now_ns - self.last_status_log_ns < int(self.status_log_period * 1e9):
            return

        self.last_status_log_ns = now_ns
        self.get_logger().info(
            '[回放摘要] '
            f'index={self.current_index + 1}/{len(self.parsed_lines)} | '
            f'confidence={msg.confidence:.2f} | leak_level={msg.leak_level} | '
            f'battery_low={msg.battery_low} | anomaly={msg.anomaly_detected} | '
            f'depth={msg.depth_m:.2f}m | speed={msg.speed_mps:.2f}m/s | '
            f'seabed_clearance={msg.seabed_clearance_m:.2f}m | '
            f'seabed_warn={msg.seabed_proximity_warning} | '
            f'seabed_penetration={msg.seabed_penetration_warning}'
        )


def main(args=None) -> None:
    """节点入口。"""
    rclpy.init(args=args)
    node = MockSensorInputNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        # 说明：避免 Ctrl+C 场景下重复 shutdown 引发 RCLError。
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
