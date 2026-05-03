"""
AUV 通信管理器
================

本模块实现了 AUV 操控台的通信管理功能，支持三种通信模式的切换：
1. WiFi UDP 通信（默认，高速率）
2. 无线电串口通信（备用，中等距离）
3. 北斗卫星串口通信（远距离，低带宽）

C# 源码参考：Form1.cs ComMode 变量和菜单处理程序

设计模式：
- 策略模式：不同通信模式使用不同的通信策略
- 单例模式：全局唯一的通信管理器
- 观察者模式：使用 Qt 信号通知模式变更

主要功能：
1. 通信模式切换（WiFi ↔ 无线电 ↔ 北斗）
2. 数据包路由（根据当前模式选择通信方式）
3. 北斗数据包压缩（72字节 → 34字节）
4. 资源生命周期管理
"""

from PySide6.QtCore import QObject, Signal
from .udp_comm import UDPCommunicator
from .serial_comm import SerialCommunicator
from .zenoh_side_channel import ZenohSideChannel
from ..protocol.beidou_protocol import BeidouProtocol
from ..protocol.constants import *


class CommunicationMode:
    """
    通信模式枚举类

    定义了三种支持的通信模式：
    - RADIO: 无线电串口通信（备用，中等距离）
    - WIFI: WiFi UDP 通信（默认，高速率）
    - BEIDOU: 北斗卫星通信（远距离，低带宽）
    """
    RADIO = 1   # 无线电模式
    WIFI = 2    # WiFi模式（默认）
    BEIDOU = 3  # 北斗模式


class CommunicationManager(QObject):
    """
    AUV 通信管理器

    本类负责管理三种通信模式的切换和数据包的路由分发。
    继承自 QObject 以支持 Qt 信号/槽机制。

    C# 源码参考：Form1.cs ComMode 变量和菜单处理程序

    职责：
    - 管理三种通信模式的切换
    - 根据当前模式路由数据包
    - 处理北斗数据包的压缩和CCTXA编码
    - 发射模式变更信号供UI响应

    Qt 信号：
        telemetry_received (Signal): 遥测数据接收信号
            - 参数: TelemetryData 对象
            - 用途: 通知主窗口更新遥测显示

        mode_changed (Signal): 通信模式变更信号
            - 参数: int (新模式，CommunicationMode枚举值)
            - 用途: 通知UI更新模式显示

    属性：
        comm_mode (int): 当前通信模式
            - 默认: CommunicationMode.WIFI
            - 值域: 1(无线电), 2(WiFi), 3(北斗)

        udp_comm (UDPCommunicator): WiFi UDP通信器
            - 用于高速本地通信
            - 默认端口: 操控台 21, AUV 52364

        radio_serial (SerialCommunicator): 无线电串口通信器
            - 用于中等距离备用通信
            - 串口配置: 9600 baud, 8N1

        beidou_serial (SerialCommunicator): 北斗串口通信器
            - 用于远距离卫星通信
            - 串口配置: 9600 baud, 8N1

        beidou_protocol (BeidouProtocol): 北斗协议处理器
            - 处理CCTXA格式的编码/解码
            - 压缩数据包格式

    使用示例：
        >>> comm_mgr = CommunicationManager()
        >>>
        >>> # 初始化配置
        >>> config = {
        ...     'radio_port': 'COM3',
        ...     'beidou_port': 'COM4',
        ...     'console_ip': '192.168.0.11',
        ...     'console_port': 21,
        ...     'auv_ip': '192.168.0.101',
        ...     'auv_port': 52364
        ... }
        >>> comm_mgr.initialize(config)
        >>>
        >>> # 连接信号
        >>> comm_mgr.mode_changed.connect(lambda mode: print(f"模式切换: {mode}"))
        >>>
        >>> # 切换到无线电模式
        >>> comm_mgr.switch_mode(CommunicationMode.RADIO)
        >>>
        >>> # 发送数据包
        >>> comm_mgr.send_packet(packet_72bytes)
        >>>
        >>> # 清理资源
        >>> comm_mgr.cleanup()
    """

    # ========== Qt 信号定义 ==========
    telemetry_received = Signal(object)  # 参数: TelemetryData
    mode_changed = Signal(int)            # 参数: 新模式 (CommunicationMode枚举值)
    bridge_telemetry_received = Signal(object)
    arbiter_state_received = Signal(object)
    side_channel_status_changed = Signal(str)

    def __init__(self):
        """
        初始化通信管理器

        创建通信管理器实例，初始化所有通信接口为 None，
        并设置默认通信模式为 WiFi。
        """
        super().__init__()

        # 当前通信模式，默认WiFi
        self.comm_mode = CommunicationMode.WIFI

        # 通信接口（在 initialize() 中创建）
        self.udp_comm = None          # WiFi UDP通信器
        self.radio_serial = None      # 无线电串口通信器
        self.beidou_serial = None     # 北斗串口通信器

        # 北斗协议处理器
        self.beidou_protocol = BeidouProtocol()
        self.side_channel = None

        # 配置字典（在 initialize() 中填充）
        self.config = {}

    def initialize(self, port_config: dict):
        """
        初始化所有通信接口

        本方法创建并配置所有通信接口，但不建立连接。
        连接将在 switch_mode() 时建立。

        C# 源码参考：Form1.cs Form1_Load() lines 266-287

        Args:
            port_config (dict): 端口配置字典，包含以下键：
                - radio_port (str): 无线电串口名
                    示例: "COM3" 或 "/dev/ttyUSB0"

                - beidou_port (str): 北斗串口名
                    示例: "COM4" 或 "/dev/ttyUSB1"

                - console_ip (str): 操控台IP地址
                    示例: "192.168.0.11"

                - console_port (int): 操控台UDP端口
                    示例: 21

                - auv_ip (str): AUV IP地址
                    示例: "192.168.0.101"

                - auv_port (int): AUV UDP端口
                    示例: 52364

        注意事项：
            - 串口名格式：
              * Windows: "COM3", "COM4"
              * Linux: "/dev/ttyUSB0", "/dev/ttyS0"
              * macOS: "/dev/cu.usbserial-*"
            - 串口在 switch_mode() 时才会打开
            - UDP通信器在初始化后自动启动
        """
        # 保存配置
        self.config = port_config

        # ========== 创建 WiFi UDP 通信器 ==========
        # 用于高速本地网络通信
        self.udp_comm = UDPCommunicator(
            local_ip=port_config['console_ip'],      # 本地IP
            local_port=port_config['console_port'],  # 本地端口
            remote_ip=port_config['auv_ip'],         # 目标IP
            remote_port=port_config['auv_port']      # 目标端口
        )

        # ========== 创建串口通信器 ==========
        # 无线电串口（备用通信）
        self.radio_serial = SerialCommunicator(
            port_name=port_config['radio_port'],
            baudrate=9600
        )

        # 北斗串口（卫星通信）
        self.beidou_serial = SerialCommunicator(
            port_name=port_config['beidou_port'],
            baudrate=9600
        )

        # ========== 启动默认模式（WiFi）==========
        self.udp_comm.start()

        side_channel_cfg = port_config.get('zenoh_side_channel', {})
        self.side_channel = ZenohSideChannel(side_channel_cfg)
        self.side_channel.bridge_telemetry_received.connect(self.bridge_telemetry_received.emit)
        self.side_channel.arbiter_state_received.connect(self.arbiter_state_received.emit)
        self.side_channel.status_changed.connect(self.side_channel_status_changed.emit)
        self.side_channel.start()
        print(f"通信管理器初始化完成: 当前模式=WiFi (默认)")

    def switch_mode(self, mode: int):
        """
        切换通信模式

        本方法处理通信模式的切换，包括：
        1. 停止当前模式的通信接口
        2. 启动新模式的通信接口
        3. 发射模式变更信号

        C# 源码参考：Form1.cs 菜单事件处理程序 (lines 1611-1634)

        Args:
            mode (int): 目标通信模式
                - CommunicationMode.RADIO (1): 无线电模式
                - CommunicationMode.WIFI (2): WiFi模式
                - CommunicationMode.BEIDOU (3): 北斗模式

        注意事项：
            - 如果目标模式与当前模式相同，直接返回
            - 切换模式会短暂中断通信（约100-500ms）
            - 北斗模式仅支持基本指令（0x00, 0x01, 0x02, 0x91, 0x92）
            - 模式切换后会发射 mode_changed 信号

        示例：
            >>> # 切换到无线电模式
            >>> comm_mgr.switch_mode(CommunicationMode.RADIO)
            通信模式切换到: Radio
            >>>
            >>> # 切换到北斗模式
            >>> comm_mgr.switch_mode(CommunicationMode.BEIDOU)
            通信模式切换到: Beidou
        """
        # 如果目标模式与当前模式相同，直接返回
        if mode == self.comm_mode:
            return

        # ========== 停止当前模式的通信接口 ==========

        if self.comm_mode == CommunicationMode.WIFI:
            # 停止 WiFi UDP 通信
            self.udp_comm.stop()

        elif self.comm_mode == CommunicationMode.RADIO:
            # 关闭无线电串口
            self.radio_serial.close()

        elif self.comm_mode == CommunicationMode.BEIDOU:
            # 关闭北斗串口
            self.beidou_serial.close()

        # ========== 启动新模式的通信接口 ==========

        self.comm_mode = mode  # 更新当前模式

        if mode == CommunicationMode.WIFI:
            # 启动 WiFi UDP 通信
            self.udp_comm.start()

        elif mode == CommunicationMode.RADIO:
            # 打开无线电串口
            self.radio_serial.open()

        elif mode == CommunicationMode.BEIDOU:
            # 打开北斗串口
            self.beidou_serial.open()

        # ========== 输出日志并发射信号 ==========

        mode_names = {
            CommunicationMode.RADIO: "Radio",
            CommunicationMode.WIFI: "WiFi",
            CommunicationMode.BEIDOU: "Beidou"
        }
        print(f"通信模式切换到: {mode_names.get(mode, 'Unknown')}")
        self.mode_changed.emit(mode)  # 通知UI模式已变更

    def send_packet(self, packet: bytes, preferences=None, work_instruct=0x00):
        """
        通过当前通信模式发送数据包

        本方法根据当前通信模式，将数据包路由到相应的通信接口。
        对于北斗模式，会自动进行数据包压缩和CCTXA编码。

        C# 源码参考：Form1.cs timer1_Tick lines 1476-1483

        Args:
            packet (bytes): 要发送的数据包
                - WiFi/无线电: 72字节完整数据包
                - 北斗: 此参数被忽略，使用 preferences 重新构建

            preferences (Preferences, optional): 任务首选项
                - 用于北斗模式构建压缩数据包
                - WiFi/无线电模式可省略

            work_instruct (int): 工作指令字节 (默认: 0x00)
                - 用于北斗模式判断指令是否允许
                - 北斗仅允许: 0x00, 0x01, 0x02, 0x91, 0x92

        注意事项：
            - WiFi模式: 直接发送72字节UDP数据包
            - 无线电模式: 直接发送72字节串口数据包
            - 北斗模式:
              * 检查指令是否允许
              * 构建34字节压缩数据包
              * CCTXA编码
              * 发送串口数据
            - 北斗指令不在允许列表时会警告并放弃发送

        示例：
            >>> # WiFi/无线电模式：直接发送
            >>> comm_mgr.send_packet(packet_72bytes)
            >>>
            >>> # 北斗模式：需要提供 preferences
            >>> comm_mgr.send_packet(
            ...     packet=None,
            ...     preferences=prefs,
            ...     work_instruct=0x01  # 任务开启
            ... )
        """
        if self.comm_mode == CommunicationMode.WIFI:
            # ========== WiFi 模式：直接发送 UDP 数据包 ==========
            sent = self.udp_comm.send(packet)
            if self.side_channel is not None:
                self.side_channel.publish_pc_cmd_raw(packet)
            return sent

        elif self.comm_mode == CommunicationMode.RADIO:
            # ========== 无线电模式：直接发送串口数据包 ==========
            return self.radio_serial.write(packet)

        elif self.comm_mode == CommunicationMode.BEIDOU:
            # ========== 北斗模式：压缩并编码数据包 ==========

            if not preferences:
                print("警告: 北斗模式需要提供 preferences")
                return

            # 导入数据包构建器
            from ..protocol.packet_builder import PacketBuilder
            builder = PacketBuilder()

            # 检查指令是否被北斗允许
            # 北斗带宽有限，仅支持基本控制指令
            allowed_commands = [0x00, 0x01, 0x02, 0x91, 0x92]
            if work_instruct not in allowed_commands:
                print(
                    f"警告: 指令 {work_instruct:#04x} 不被北斗支持，"
                    f"北斗仅支持: {[f'{c:#04x}' for c in allowed_commands]}"
                )
                return

            # 构建34字节北斗压缩数据包
            beidou_packet = builder.build_beidou_packet(preferences, work_instruct)

            # 编码为 CCTXA 格式（北斗卫星通信的ASCII十六进制格式）
            cctxa_packet = self.beidou_protocol.build_cctxa_packet(beidou_packet)

            # 通过北斗串口发送
            return self.beidou_serial.write(cctxa_packet)

        return False

    def get_udp_communicator(self) -> UDPCommunicator:
        """
        获取 WiFi UDP 通信器

        供 UDP 接收线程使用，用于接收 AUV 发回的遥测数据。

        Returns:
            UDPCommunicator: UDP 通信器实例

        使用示例：
            >>> udp = comm_mgr.get_udp_communicator()
            >>> receiver_thread = UDPReceiverThread(udp)
            >>> receiver_thread.start()
        """
        return self.udp_comm

    def get_radio_serial(self) -> SerialCommunicator:
        """
        获取无线电串口通信器

        Returns:
            SerialCommunicator: 无线电串口通信器实例

        使用示例：
            >>> serial = comm_mgr.get_radio_serial()
            >>> if serial.is_open():
            ...     print("无线电串口已打开")
        """
        return self.radio_serial

    def get_beidou_serial(self) -> SerialCommunicator:
        """
        获取北斗串口通信器

        Returns:
            SerialCommunicator: 北斗串口通信器实例

        使用示例：
            >>> serial = comm_mgr.get_beidou_serial()
            >>> if serial.is_open():
            ...     print("北斗串口已打开")
        """
        return self.beidou_serial

    def cleanup(self):
        """
        清理所有通信资源

        本方法在应用程序关闭时调用，用于：
        1. 停止 UDP 通信器
        2. 关闭所有串口
        3. 释放系统资源

        使用示例：
            >>> # 应用程序关闭前
            >>> comm_mgr.cleanup()
            通信管理器资源已清理
        """
        if self.udp_comm:
            self.udp_comm.stop()
        if self.radio_serial:
            self.radio_serial.close()
        if self.beidou_serial:
            self.beidou_serial.close()
        if self.side_channel:
            self.side_channel.stop()
        print("通信管理器资源已清理")

    def set_side_channel_active(self, active: bool):
        """Enable or disable the optional Zenoh side channel with mode switches."""
        if self.side_channel is None:
            return
        if active:
            self.side_channel.start()
            return
        self.side_channel.stop()

    def is_side_channel_active(self) -> bool:
        """Report whether the optional Zenoh side channel is currently active."""
        return bool(self.side_channel is not None and self.side_channel.is_active)
