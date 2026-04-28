"""
Mock AMD (AUV 管理设备) UDP 服务器——将 HoloOcean 仿真数据转换为真实 AUV 水下通信协议。

本模块模拟一个真实的 AMD（AUV Management Device）设备，通过 UDP 双向通信与上位机进行交互：
  - 接收下行控制命令（方向舵、推力等）
  - 发送上行遥测数据（深度、航向、速度、体态等）
  - 支持可注入的延迟、抖动、丢包、传感器故障等网络和物理层故障

核心职责：
  1. 管理 HoloOcean 物理仿真（步态、位姿、速度等）
  2. 将 UE4 坐标系转换为 NED（北东地）坐标系
  3. 模拟多速率传感器采样（IMU、DVL、深度、磁力计）
  4. 编码/解码二进制协议数据包
  5. 引入现实故障效果（丢包、延迟、传感器漂移等）
"""

import socket
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for folder in [PROJECT_ROOT, PROJECT_ROOT / 'common']:
    folder_str = str(folder)
    if folder_str not in sys.path:
        sys.path.insert(0, folder_str)

from common.protocol import build_uplink_packet, parse_downlink_packet
from common.protocol_debug import format_protocol_packet, format_protocol_packet_ascii, format_protocol_packet_raw

from mock_amd_chaos import ChaosInjector, ChaosProfile
from mock_amd_delay import TransportDelayQueue
from mock_amd_sensor_cache import SensorSampleCache, SensorSnapshot
from frame_transform import body_vector_ue_to_ned, pose_matrix_ue_to_ned
from sim_wrapper import create_sim_wrapper, build_scenario, extract_body_velocity, extract_depth, get_agent_state


class MockAmdUdpServer:
    """
    Mock AMD UDP 服务器 - 仿真侧与决策侧的通信网关。

    负责：
      1. 启动和管理 HoloOcean 仿真实例（physics bridge）
      2. 接收下行数据包（UDP 从 ROS2 bridge 端发来的控制命令）
      3. 解析控制命令并应用到仿真的 AUV 模型
      4. 读取仿真的传感器数据（位姿、速度、深度、磁场等）
      5. 注入现实的网络故障（延迟、丢包、重排序）和传感器故障（漂移、冻结、饱和等）
      6. 编码成上行数据包并发送回 ROS2 bridge 端

    通信流程（每个仿真周期 dt=1/rate_hz 秒）：
      1. _poll_command_packet()：接收客户端的下行命令包（含控制指令）
      2. command_guard.sanitize()：应用安全护栏（推力限幅等）
      3. wrapper.step(cmd)：推进仿真一步
      4. _build_uplink_packet()：构造上行遥测包
      5. 通过 UDP 发送到 last_client_addr
    """

    def __init__(self, config, command_guard):
        """
        初始化 Mock AMD UDP 服务器。

        参数：
          config: 字典，包含所有配置项，结构如下：
            - simulation: 仿真配置（agent_name、show_viewport 等）
            - bridge: 桥接配置（rate_hz、protocol_udp 等）
            - mock_amd: Mock AMD 特有配置（延迟、故障注入等）
            - digital_twin: 数字孪生配置（如海底深度）
          command_guard: CommandGuard 对象，用于校验和清理控制命令
        """
        self.config = config
        self.command_guard = command_guard
        self.agent_name = config['simulation']['agent_name']

        # ────────────────────────────────────────
        # 仿真主循环参数
        # ────────────────────────────────────────
        self.rate_hz = float(config['bridge']['rate_hz'])
        self.dt = 1.0 / max(1e-6, self.rate_hz)  # 单帧时间，秒

        protocol_cfg = config['bridge'].get('protocol_udp', {})

        # ────────────────────────────────────────
        # UDP 网络配置
        # ────────────────────────────────────────
        self.bind_host = str(protocol_cfg.get('bind_host', '0.0.0.0'))  # 此服务器的绑定地址
        self.bind_port = int(protocol_cfg.get('bind_port', 52364))      # 此服务器的绑定端口
        self.default_remote_host = str(protocol_cfg.get('remote_host', '127.0.0.1'))  # 客户端默认地址
        self.default_remote_port = int(protocol_cfg.get('remote_port', 52365))        # 客户端默认端口
        self.socket_timeout_s = float(protocol_cfg.get('socket_timeout_s', 0.01))     # UDP 接收超时
        self.recv_buffer_size = int(protocol_cfg.get('recv_buffer_size', 2048))       # UDP 接收缓冲大小

        # ────────────────────────────────────────
        # 协议和设备参数
        # ────────────────────────────────────────
        self.main_motor_rpm_scale = float(protocol_cfg.get('main_motor_rpm_scale', 15.0))  # 推力百分比 → RPM 的缩放系数
        self.side_motor_rpm = int(protocol_cfg.get('side_motor_rpm', 0))                    # 侧推电机 RPM（通常为 0）
        self.auv_address = int(protocol_cfg.get('auv_address', 1))                          # AUV 在网络中的地址/ID
        self.default_control_mode_byte = int(protocol_cfg.get('default_control_mode_byte', 0xEE))  # 默认控制模式

        # ────────────────────────────────────────
        # 遥测参数（模拟电池状态等）
        # ────────────────────────────────────────
        self.telemetry_total_voltage_v = float(protocol_cfg.get('telemetry_total_voltage_v', 48.0))  # 总电压
        self.telemetry_total_current_a = float(protocol_cfg.get('telemetry_total_current_a', 0.0))   # 总电流
        self.telemetry_soc = int(protocol_cfg.get('telemetry_soc', 100))                             # 电池 SOC（%）
        self.telemetry_soh = int(protocol_cfg.get('telemetry_soh', 100))                             # 电池 SOH（%）

        # ────────────────────────────────────────
        # 协议包镜像和日志配置
        # ────────────────────────────────────────
        # 用于监控工具（Wireshark、自定义 sniffer）的数据包镜像
        self.sniffer_mirror_host = str(protocol_cfg.get('sniffer_mirror_host', '127.0.0.1'))
        self.sniffer_mirror_port = int(protocol_cfg.get('sniffer_mirror_port', 0))

        # 日志输出模式
        self.log_packets = bool(protocol_cfg.get('log_packets', True))           # 是否打印协议包
        self.log_raw_format = bool(protocol_cfg.get('log_raw_format', False))    # 原始紧凑格式
        self.log_ascii_format = bool(protocol_cfg.get('log_ascii_format', False)) # 详细 ASCII 格式
        self.log_packet_hex = bool(protocol_cfg.get('log_packet_hex', False))    # 是否包含十六进制数据
        self.log_hex_bytes = int(protocol_cfg.get('log_hex_bytes', 48))          # 十六进制显示的字节数
        self.log_every_n = max(1, int(protocol_cfg.get('log_every_n', 1)))       # 每 N 帧打印一次

        mock_cfg = dict(config.get('mock_amd', {}) or {})

        # ────────────────────────────────────────
        # 传输层故障模拟（延迟和抖动）
        # ────────────────────────────────────────
        # 模拟水下通信的固有延迟和变动
        delay_ms = float(mock_cfg.get('transport_delay_ms', 0.0))      # 基础延迟（毫秒）
        jitter_ms = float(mock_cfg.get('transport_jitter_ms', 0.0))    # 抖动范围（毫秒）
        max_queue_depth = int(mock_cfg.get('transport_max_queue', 64)) # 最大队列深度
        self._delay_queue = None
        if delay_ms > 0.0 or jitter_ms > 0.0:
            self._delay_queue = TransportDelayQueue(
                base_delay_ms=delay_ms,
                jitter_ms=jitter_ms,
                max_queue_depth=max_queue_depth,
            )

        # ────────────────────────────────────────
        # 传感器多速率采样缓存
        # ────────────────────────────────────────
        # 模拟真实 AUV 的多速率传感器架构：
        #   - IMU: ~100 Hz（高频，提供即时姿态）
        #   - DVL: ~6 Hz（低频，经过实际处理）
        #   - 深度传感器: ~50 Hz
        #   - 磁力计: ~20 Hz
        sensor_cfg = dict(mock_cfg.get('sensor_clocks', {}) or {})
        self._sensor_cache = None
        if any(float(sensor_cfg.get(name, 0.0) or 0.0) > 0.0 for name in ('imu_hz', 'dvl_hz', 'depth_hz', 'mag_hz')):
            self._sensor_cache = SensorSampleCache(
                imu_hz=float(sensor_cfg.get('imu_hz', 0.0) or 0.0),
                dvl_hz=float(sensor_cfg.get('dvl_hz', 0.0) or 0.0),
                depth_hz=float(sensor_cfg.get('depth_hz', 0.0) or 0.0),
                mag_hz=float(sensor_cfg.get('mag_hz', 0.0) or 0.0),
            )

        # ────────────────────────────────────────
        # 故障注入层（Chaos Engineering）
        # ────────────────────────────────────────
        # 用于测试控制系统对各类故障的鲁棒性：传感器故障、通信中断、数据异常等
        chaos_cfg = dict(mock_cfg.get('chaos', {}) or {})
        self._chaos = None
        if bool(chaos_cfg.get('enabled', False)):
            self._chaos = ChaosInjector(
                ChaosProfile(
                    enabled=True,
                    # 传输层
                    packet_loss_pct=float(chaos_cfg.get('packet_loss_pct', 0.0)),
                    reorder_enabled=bool(chaos_cfg.get('reorder_enabled', False)),
                    reorder_buffer_ms=float(chaos_cfg.get('reorder_buffer_ms', 50.0)),
                    # 传感器层
                    dvl_freeze_enabled=bool(chaos_cfg.get('dvl_freeze_enabled', False)),
                    dvl_freeze_after_s=float(chaos_cfg.get('dvl_freeze_after_s', 30.0)),
                    imu_drift_enabled=bool(chaos_cfg.get('imu_drift_enabled', False)),
                    imu_drift_rate_deg_per_s=float(chaos_cfg.get('imu_drift_rate_deg_per_s', 0.5)),
                    depth_spike_enabled=bool(chaos_cfg.get('depth_spike_enabled', False)),
                    depth_spike_m=float(chaos_cfg.get('depth_spike_m', 5.0)),
                    depth_spike_after_s=float(chaos_cfg.get('depth_spike_after_s', 60.0)),
                    mag_saturation_enabled=bool(chaos_cfg.get('mag_saturation_enabled', False)),
                    mag_saturation_threshold_t=float(chaos_cfg.get('mag_saturation_threshold_t', 50000.0)),
                    # 上行链路
                    uplink_dropout_enabled=bool(chaos_cfg.get('uplink_dropout_enabled', False)),
                    uplink_dropout_on_pct=float(chaos_cfg.get('uplink_dropout_on_pct', 0.8)),
                    uplink_dropout_period_s=float(chaos_cfg.get('uplink_dropout_period_s', 10.0)),
                )
            )

        # ────────────────────────────────────────
        # 运行时状态
        # ────────────────────────────────────────
        self._start_time = 0.0

        # HoloOcean 仿真包装器
        self.wrapper = None
        # UDP socket
        self.sock = None

        # ────────────────────────────────────────
        # 最后接收的命令状态
        # ────────────────────────────────────────
        self.last_cmd = np.array(config['bridge'].get('default_command', [0, 0, 0, 0, 0]), dtype=float)
        self.last_cmd_msg = None        # 最后接收的命令字典 {right, top, left, bottom, thrust}
        self.last_cmd_ts = 0.0          # 最后接收命令的时间戳
        self.last_client_addr = (self.default_remote_host, self.default_remote_port)  # 上一个客户端地址

        # ────────────────────────────────────────
        # 传输层协议状态
        # ────────────────────────────────────────
        self.last_work_instruction = 0           # 上次接收到的工作指令字节
        self.last_control_mode_byte = self.default_control_mode_byte  # 控制模式
        self.last_mock_amd_timestamp_us = 0      # 上次接收的 AMD 时间戳（微秒）

    # ========================================================================
    # 公共 API：生命周期管理
    # ========================================================================

    def open(self):
        """
        启动 Mock AMD 服务器。

        初始化 HoloOcean 物理仿真环境和 UDP socket，准备接收控制命令和发送遥测数据。

        返回值：
            self，支持链式调用
        """
        scenario = build_scenario(self.config)
        sim_cfg = self.config['simulation']
        self.wrapper = create_sim_wrapper(
            self.config,
            scenario_cfg=scenario,
            agent_name=self.agent_name,
            show_viewport=bool(sim_cfg.get('show_viewport', False)),
            verbose=bool(sim_cfg.get('verbose', False)),
        ).open()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.bind_host, self.bind_port))
        self.sock.settimeout(self.socket_timeout_s)
        return self

    def close(self):
        """关闭 Mock AMD 服务器，释放 socket 和仿真资源。"""
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        if self.wrapper is not None:
            self.wrapper.close()
            self.wrapper = None

    # ========================================================================
    # 私有 API：数据包操作
    # ========================================================================

    def _mirror_packet(self, packet: bytes):
        """
        将数据包镜像发送到监控工具（如 Wireshark）。

        用于调试，允许外部工具（协议分析器）同步观察往来于 AUV 的通信。
        如果 sniffer_mirror_port == 0 或 socket 未初始化，此操作被跳过。

        参数：
            packet: 要镜像的 UDP 数据包字节
        """
        if self.sock is None or self.sniffer_mirror_port <= 0:
            return
        try:
            self.sock.sendto(packet, (self.sniffer_mirror_host, self.sniffer_mirror_port))
        except OSError:
            return

    @staticmethod
    def _build_sensor_raw_state(
        heading_deg: float,
        pitch_deg: float,
        roll_deg: float,
        dvl_speed_mps: float,
        depth_m: float,
        mag_payload: dict | None,
    ) -> dict:
        """
        从原始传感器值构造内部原始状态字典。

        参数：
            heading_deg: 航向（度，0-360）
            pitch_deg: 俯仰角（度）
            roll_deg: 横滚角（度）
            dvl_speed_mps: DVL 前向速度（m/s）
            depth_m: 深度（米）
            mag_payload: 磁力计负载字典，包含 B_ned 和 B_norm，或 None

        返回值：
            格式化的传感器状态字典，用于 _sensor_cache.update()
        """
        raw_state = {
            'imu': {
                'heading_deg': float(heading_deg),
                'pitch_deg': float(pitch_deg),
                'roll_deg': float(roll_deg),
            },
            'dvl': {
                'speed_mps': float(dvl_speed_mps),
            },
            'depth': {
                'depth_m': float(depth_m),
            },
        }
        if mag_payload is not None:
            raw_state['mag'] = mag_payload
        return raw_state

    # ========================================================================
    # 私有 API：命令接收和处理
    # ========================================================================

    def _poll_command_packet(self):
        """
        从 UDP socket 接收并处理下行控制命令包。

        流程：
          1. 若启用了延迟队列，从队列中取出已就绪的包（release_ts <= now）
          2. 尝试从 socket 接收新包（非阻塞，超时可忽略）
          3. 若接收到新包，将其入队（若启用延迟）或直接处理
          4. 对所有就绪的包，解析协议、更新内部状态、记录日志

        状态更新：
          - self.last_cmd_msg: 从包中提取的舵面和推力指令
          - self.last_cmd_ts: 命令接收时间
          - self.last_client_addr: 发送命令的客户端地址（用于回复）
          - self.last_work_instruction, last_control_mode_byte: 协议控制字
          - self.last_mock_amd_timestamp_us: 时间同步戳
        """
        if self.sock is None:
            return

        now = time.time()
        ready_packets = []
        # 从延迟队列取出已就绪的包
        if self._delay_queue is not None:
            ready_packets = self._delay_queue.dequeue(now)

        # 非阻塞接收新包
        try:
            packet, addr = self.sock.recvfrom(self.recv_buffer_size)
        except socket.timeout:
            packet = None
            addr = None
        except OSError:
            packet = None
            addr = None

        # 若有新包，入队或直接加入就绪列表
        if packet is not None and addr is not None:
            if self._delay_queue is not None:
                self._delay_queue.enqueue((packet, addr), now)
                ready_packets.extend(self._delay_queue.dequeue(now))
            else:
                ready_packets.append((packet, addr))

        # 处理所有就绪的包
        for ready_item, ready_recv_ts in ready_packets:
            if isinstance(ready_item, tuple) and len(ready_item) == 2 and isinstance(ready_item[1], tuple):
                ready_packet, ready_addr = ready_item
            else:
                ready_packet = ready_item
                ready_addr = self.last_client_addr
            try:
                downlink = parse_downlink_packet(ready_packet, main_motor_rpm_scale=self.main_motor_rpm_scale)
            except Exception as exc:
                print(f'[mock-amd][warn] invalid downlink packet: {exc}')
                continue

            # 日志输出
            if self.log_packets:
                if self.log_raw_format:
                    # 紧凑原始格式（单行，方便脚本解析）
                    print(
                        format_protocol_packet_raw(
                            ready_packet,
                            label='mock-amd RX',
                            source=f'{ready_addr[0]}:{ready_addr[1]}',
                        )
                    )
                elif self.log_ascii_format:
                    # 详细 ASCII 格式（多行，便于人工阅读）
                    print(
                        format_protocol_packet_ascii(
                            ready_packet,
                            label='mock-amd RX',
                            source=f'{ready_addr[0]}:{ready_addr[1]}',
                            include_timestamp=True,
                        )
                    )
                    print()  # 空行分隔
                else:
                    # 单行摘要格式（默认，包含关键信息和可选十六进制）
                    print(
                        format_protocol_packet(
                            ready_packet,
                            label='mock-amd RX',
                            source=f'{ready_addr[0]}:{ready_addr[1]}',
                            color=True,
                            include_hex=self.log_packet_hex,
                            max_hex_bytes=self.log_hex_bytes,
                            main_motor_rpm_scale=self.main_motor_rpm_scale,
                        )
                    )

            # 镜像到监控工具
            self._mirror_packet(ready_packet)

            # 更新内部状态
            self.last_client_addr = ready_addr
            self.last_work_instruction = downlink.work_instruction
            self.last_control_mode_byte = downlink.control_mode_byte
            self.last_mock_amd_timestamp_us = downlink.mock_amd_timestamp_us
            self.last_cmd_msg = {
                'right': float(downlink.right_fin_deg),
                'top': float(downlink.top_fin_deg),
                'left': float(downlink.left_fin_deg),
                'bottom': float(downlink.bottom_fin_deg),
                'thrust': float(downlink.thrust_percent),
            }
            self.last_cmd_ts = time.time()

    # ========================================================================
    # 私有 API：遥测数据包构造
    # ========================================================================

    def _build_uplink_packet(self, raw_state, step, command_vector):
        """
        构造并返回上行遥测数据包。

        编码流程：
          1. 从仿真 state 提取位姿和传感器数据
          2. 进行坐标系转换（UE4 → NED）
          3. 应用传感器多速率采样缓存和故障注入
          4. 编码为二进制协议包（遵循 common.protocol 规范）

        参数：
            raw_state: HoloOcean 返回的原始仿真状态（位姿、速度、传感器）
            step: 仿真步数（0-255 循环）
            command_vector: 当前应用的控制向量 [right_fin, top_fin, left_fin, bottom_fin, thrust]

        返回值：
            bytes: 编码后的上行数据包（60 字节左右）
            None: 若故障注入导致此帧应被丢弃（上行中断）
        """
        now = time.time()
        elapsed = now - self._start_time  # 仿真从启动至今的经过时间

        # ────────────────────────────────────────
        # 步骤 1：从仿真状态提取位姿和传感器基准值
        # ────────────────────────────────────────
        state = get_agent_state(raw_state, self.agent_name)
        pose = state['PoseSensor']  # 4x4 变换矩阵
        tf = pose_matrix_ue_to_ned(pose)  # 变换到 NED 坐标系

        # DVL（多普勒速度测头）：身体坐标系前向速度
        dvl_ue = extract_body_velocity(state.get('DVLSensor', np.zeros(3)))
        dvl_ned = body_vector_ue_to_ned(dvl_ue)  # 转换到 NED

        # 深度：从位置 Z 坐标（负值 = 深度）
        depth_raw = extract_depth(state.get('DepthSensor', np.array([-pose[2, 3]])), pose[2, 3])
        depth_ned = float(-depth_raw if depth_raw < 0.0 else depth_raw)

        # 欧拉角（滚转、俯仰、偏航） / NED 坐标系
        rpy_deg = np.degrees(tf['rpy_ned'])
        seabed_depth_m = float(self.config.get('digital_twin', {}).get('seabed_z_m', 15.0))

        # 提取各分量（基准值，将被故障注入覆盖）
        base_heading_deg = float((rpy_deg[2] + 360.0) % 360.0)  # 航向：偏航角 [0, 360)
        base_pitch_deg = float(rpy_deg[1])                        # 俯仰角
        base_roll_deg = float(rpy_deg[0])                         # 横滚角
        base_dvl_speed_mps = float(dvl_ned[0])                   # 前向速度

        # 磁力计数据（可选）
        mag_state = state.get('magnetic') or state.get('MagneticSensor') or state.get('mag')
        mag_payload = None
        if isinstance(mag_state, dict):
            mag_payload = {
                'B_ned': list(mag_state.get('B_ned', [0.0, 0.0, 0.0])),
                'B_norm': float(mag_state.get('B_norm', 0.0)),
            }

        # ────────────────────────────────────────
        # 步骤 2：构造原始传感器状态
        # ────────────────────────────────────────
        sensor_raw_state = self._build_sensor_raw_state(
            heading_deg=base_heading_deg,
            pitch_deg=base_pitch_deg,
            roll_deg=base_roll_deg,
            dvl_speed_mps=base_dvl_speed_mps,
            depth_m=depth_ned,
            mag_payload=mag_payload,
        )

        # ────────────────────────────────────────
        # 步骤 3：应用多速率采样缓存（若启用）
        # ────────────────────────────────────────
        if self._sensor_cache is not None:
            # 每个传感器独立采样时钟
            sensor_snapshot = self._sensor_cache.update(sensor_raw_state, now)
        else:
            # 无缓存：每帧采用最新值
            sensor_snapshot = SensorSnapshot(
                imu=dict(sensor_raw_state['imu']),
                dvl=dict(sensor_raw_state['dvl']),
                depth=dict(sensor_raw_state['depth']),
                mag=dict(sensor_raw_state['mag']) if sensor_raw_state.get('mag') is not None else None,
                ts=now,
            )

        # ────────────────────────────────────────
        # 步骤 4：应用故障注入（Chaos Injection）
        # ────────────────────────────────────────
        if self._chaos is not None:
            # 应用传感器级故障：漂移、冻结、饱和等
            sensor_snapshot = self._chaos.apply_to_sensors(sensor_snapshot, elapsed)
            # 检查上行链路是否应被中断（模拟通信故障）
            if self._chaos.should_drop_uplink(elapsed):
                return None

        # ────────────────────────────────────────
        # 步骤 5：从快照中提取最终的传感器值
        # ────────────────────────────────────────
        imu_snapshot = sensor_snapshot.imu or {}
        dvl_snapshot = sensor_snapshot.dvl or {}
        depth_snapshot = sensor_snapshot.depth or {}

        heading_deg = float(imu_snapshot.get('heading_deg', base_heading_deg))
        pitch_deg = float(imu_snapshot.get('pitch_deg', base_pitch_deg))
        roll_deg = float(imu_snapshot.get('roll_deg', base_roll_deg))
        dvl_speed_mps = float(dvl_snapshot.get('speed_mps', base_dvl_speed_mps))
        depth_ned = float(depth_snapshot.get('depth_m', depth_ned))
        altitude_m = max(0.0, seabed_depth_m - depth_ned)  # 离海底距离

        # ────────────────────────────────────────
        # 步骤 6：准备遥测参数并编码上行包
        # ────────────────────────────────────────
        # Parameter values[0] 回显 AMD 时间戳用于时间同步
        parameter_values = [0] * 12
        parameter_values[0] = int(self.last_mock_amd_timestamp_us)

        return build_uplink_packet(
            frame_counter=int(step) & 0xFF,
            auv_address=self.auv_address,
            control_mode_byte=self.last_control_mode_byte,
            work_instruction=self.last_work_instruction,
            main_motor_rpm=int(round(float(command_vector[4]) * self.main_motor_rpm_scale)),
            side_motor_rpm=self.side_motor_rpm,
            left_fin_deg=float(command_vector[2]),
            right_fin_deg=float(command_vector[0]),
            top_fin_deg=float(command_vector[1]),
            bottom_fin_deg=float(command_vector[3]),
            depth_m=depth_ned,
            heading_deg=heading_deg,
            pitch_deg=pitch_deg,
            roll_deg=roll_deg,
            gps_heading_deg=heading_deg,
            gps_speed_mps=max(0.0, float(dvl_speed_mps)),
            dvl_speed_mps=dvl_speed_mps,
            altitude_m=altitude_m,
            parameter_values=parameter_values,
            total_voltage_v=self.telemetry_total_voltage_v,
            total_current_a=self.telemetry_total_current_a,
            soc=self.telemetry_soc,
            soh=self.telemetry_soh,
        )

    # ========================================================================
    # 公共 API：主运行循环
    # ========================================================================

    def run_forever(self):
        """
        启动 Mock AMD 服务器的主运行循环 - 持续仿真、通信、故障注入。

        核心流程（每个 dt 秒一次迭代）：
          1. _poll_command_packet()：从网络接收下行命令（非阻塞）
          2. command_guard.sanitize()：应用安全护栏（推力限幅等）
          3. wrapper.step(cmd)：推进 HoloOcean 物理仿真一步
          4. _build_uplink_packet()：从仿真状态构造上行遥测包
                  ├─ 坐标系转换（UE4 → NED）
                  ├─ 多速率传感器采样
                  ├─ 故障注入（丢包、漂移、中断）
                  └─ 协议编码
          5. 通过 UDP 发送到 last_client_addr（若包非 None）
          6. 日志输出（可配置格式）
          7. 自适应睡眠以维持目标速率（rate_hz）

        循环条件：
          - 无限循环，直到 max_steps 达到阈值或强制中断

        性能：
          - 使用自适应延迟控制："忙-等待" 到精确时刻不超过 4ms，然后睡眠
          - 若单帧耗时已超过 dt，则不睡眠（允许帧率落后但继续前进）
        """
        self._start_time = time.time()
        state = self.wrapper.reset_and_tick()
        step = 0
        start_wall = time.time()

        while True:
            loop_start = time.time()

            # ────────────────────────────────────────
            # 接收命令和安全护栏
            # ────────────────────────────────────────
            self._poll_command_packet()
            cmd = self.command_guard.sanitize(self.last_cmd_msg, self.last_cmd, self.last_cmd_ts)
            self.last_cmd = cmd

            # ────────────────────────────────────────
            # 推进仿真并构造遥测包
            # ────────────────────────────────────────
            state = self.wrapper.step(cmd)
            packet = self._build_uplink_packet(state, step, cmd)

            # ────────────────────────────────────────
            # 发送上行遥测（若包有效）
            # ────────────────────────────────────────
            if packet is not None and self.sock is not None:
                self.sock.sendto(packet, self.last_client_addr)
                self._mirror_packet(packet)

            # ────────────────────────────────────────
            # 日志输出（每 log_every_n 帧）
            # ────────────────────────────────────────
            if step % self.log_every_n == 0:
                if self.log_packets:
                    if self.log_raw_format:
                        # 紧凑原始格式
                        print(
                            format_protocol_packet_raw(
                                packet,
                                label='mock-amd TX',
                                source=f'{self.last_client_addr[0]}:{self.last_client_addr[1]}',
                            )
                        )
                    elif self.log_ascii_format:
                        # 详细 ASCII 格式
                        print(
                            format_protocol_packet_ascii(
                                packet,
                                label='mock-amd TX',
                                source=f'{self.last_client_addr[0]}:{self.last_client_addr[1]}',
                                include_timestamp=True,
                            )
                        )
                        print(f'step={step:06d}')
                        print()  # 空行分隔
                    else:
                        # 单行摘要格式
                        uplink_log = format_protocol_packet(
                            packet,
                            label='mock-amd TX',
                            source=f'{self.last_client_addr[0]}:{self.last_client_addr[1]}',
                            color=True,
                            include_hex=self.log_packet_hex,
                            max_hex_bytes=self.log_hex_bytes,
                            main_motor_rpm_scale=self.main_motor_rpm_scale,
                        )
                        print(f'{uplink_log} step={step:06d}')
                else:
                    # 简化模式：只打印关键数值（深度和控制向量）
                    depth_m = int.from_bytes(packet[38:40], byteorder='big', signed=False) * 0.1
                    print(
                        f'step={step:06d} depth={depth_m:.2f}m '
                        f'cmd=({cmd[0]:.1f},{cmd[1]:.1f},{cmd[2]:.1f},{cmd[3]:.1f},{cmd[4]:.1f})'
                    )

            # ────────────────────────────────────────
            # 速率控制：维持 rate_hz
            # ────────────────────────────────────────
            step += 1
            elapsed = time.time() - loop_start
            sleep_t = self.dt - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

            # ────────────────────────────────────────
            # 终止条件
            # ────────────────────────────────────────
            if self.config['bridge'].get('max_steps', 0) > 0 and step >= int(self.config['bridge']['max_steps']):
                break

        print(f'mock amd done, wall_time={time.time() - start_wall:.2f}s')