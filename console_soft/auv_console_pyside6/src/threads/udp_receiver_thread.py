"""
UDP 接收线程模块
================

本模块实现后台 UDP 数据包接收线程，用于持续接收 AUV 发回的遥测数据。

C# 源码参考：Form1.cs THREAD_REC() 方法, lines 399-434

设计模式：
- 线程模式：后台线程持续轮询
- 观察者模式：使用 Qt 信号通知数据到达
- 互斥锁：保证线程安全的启停控制

主要功能：
1. 后台轮询接收 UDP 数据包（300ms 周期）
2. 验证数据包格式（帧头、帧尾、校验和）
3. 发射 Qt 信号通知主窗口

数据包验证：
- 帧头: 0x24 0x41 0x55 0x56 0x91 ($AUV▒)
- 长度: 145 字节
- 帧尾: 0xFF 0xFF
- 校验和: 字节 0-142 之和应等于字节 142
"""

from PySide6.QtCore import QThread, QMutex, QMutexLocker, Signal
from ..communication.udp_comm import UDPCommunicator
from ..communication.comm_manager import CommunicationMode
from ..protocol.constants import *


class UDPReceiverThread(QThread):
    """
    UDP 接收后台线程

    本类在后台线程中持续轮询 UDP socket，接收 AUV 发送的145字节
    遥测数据包，验证后通过 Qt 信号发送给主窗口。

    C# 源码参考：Form1.cs lines 399-434 THREAD_REC()

    职责：
    - 持续轮询 UDP socket（300ms 周期）
    - 验证接收到的数据包
    - 通过信号通知主窗口更新显示

    Qt 信号：
        data_received (Signal): 有效数据包接收信号
            - 参数: bytes (145字节接收数据包)
            - 用途: 通知主窗口解析并更新遥测显示

        comm_mode_detected (Signal): WiFi 模式检测信号
            - 参数: int (CommunicationMode.WIFI = 2)
            - 用途: 通信管理器确认当前使用 WiFi 模式

    属性：
        udp_comm (UDPCommunicator): UDP 通信器实例
            - 用于接收数据包
            - 非阻塞模式

        running (bool): 线程运行标志
            - True: 线程持续运行
            - False: 线程退出循环

        mutex (QMutex): 互斥锁
            - 保护 running 标志的线程安全访问
            - 防止竞态条件

    使用示例：
        >>> # 创建 UDP 通信器
        >>> udp_comm = UDPCommunicator(
        ...     local_ip="192.168.0.11",
        ...     local_port=21,
        ...     remote_ip="192.168.0.101",
        ...     remote_port=52364
        ... )
        >>> udp_comm.start()
        >>>
        >>> # 创建并启动接收线程
        >>> receiver_thread = UDPReceiverThread(udp_comm)
        >>> receiver_thread.data_received.connect(lambda data: print(f"收到 {len(data)} 字节"))
        >>> receiver_thread.start()
        >>>
        >>> # 停止线程
        >>> receiver_thread.stop()
        >>> receiver_thread.wait()  # 等待线程退出

    注意事项：
        - 线程以 300ms 周期轮询（与 C# 版本一致）
        - 仅接收完整有效的 145 字节数据包
        - 无效数据包会被静默丢弃
        - 必须调用 stop() 才能安全退出线程
    """

    # ========== Qt 信号定义 ==========
    data_received = Signal(bytes)  # 参数: 145字节接收数据包
    comm_mode_detected = Signal(int)  # 参数: 通信模式 (CommunicationMode.WIFI)

    def __init__(self, udp_communicator: UDPCommunicator):
        """
        初始化 UDP 接收线程

        Args:
            udp_communicator (UDPCommunicator): UDP 通信器实例
                - 必须已调用 start() 绑定 socket
                - 用于非阻塞接收数据

        注意事项：
            - 线程创建后不会自动启动，需调用 start()
            - 确保传入的 udp_comm 已正确初始化
        """
        super().__init__()

        # 保存 UDP 通信器引用
        self.udp_comm = udp_communicator

        # 线程运行标志（通过互斥锁保护）
        self.running = True

        # 互斥锁（保护 running 标志）
        self.mutex = QMutex()

    def run(self):
        """
        线程主循环 - 每 300ms 轮询一次

        持续接收 UDP 数据包，验证后发射信号通知主窗口。
        循环周期为 300ms，与 C# 源码保持一致。

        C# 源码参考：Form1.cs Thread.Sleep(300) at line 432

        工作流程：
        1. 调用 udp_comm.receive() 尝试接收数据
        2. 检查数据长度是否为 145 字节
        3. 验证帧头 (0x24 0x41 0x55 0x56 0x91)
        4. 验证帧尾 (0xFF 0xFF)
        5. 验证校验和 (字节 0-142 之和)
        6. 发射 data_received 信号
        7. 休眠 300ms

        数据包格式验证：
        - [字节 0-4]:   帧头 = 0x24 0x41 0x55 0x56 0x91 ($AUV▒)
        - [字节 5-141]: 数据载荷
        - [字节 142]:   校验和 (字节 0-141 之和，取低8位)
        - [字节 143-144]: 帧尾 = 0xFF 0xFF

        注意事项：
            - 接收到的数据包必须是完整的 145 字节
            - 数据包必须通过所有验证（帧头、帧尾、校验和）
            - 无效数据包会被静默丢弃，不发射信号
            - 休眠 300ms 避免占用过多 CPU
        """
        print("UDP接收线程已启动")

        # ========== 主循环 ==========
        while self.running:
            # ========== 1. 尝试接收数据 ==========
            # udp_comm.receive() 是非阻塞的，无数据时立即返回 None
            data = self.udp_comm.receive()

            # ========== 2. 验证数据长度 ==========
            # 完整的接收数据包应为 145 字节
            if data and len(data) >= 145:

                # ========== 3. 验证帧头 ==========
                # 帧头: 0x24 0x41 0x55 0x56 0x91
                # ASCII: "$AUV▒" (AUV Telemetry Header)
                if (data[0] == 0x24 and      # 0x24 = '$'
                    data[1] == 0x41 and      # 0x41 = 'A'
                    data[2] == 0x55 and      # 0x55 = 'U'
                    data[3] == 0x56 and      # 0x56 = 'V'
                    data[4] == 0x91):        # 0x91 = '▒'

                    # ========== 4. 验证帧尾 ==========
                    # 帧尾: 0xFF 0xFF
                    if data[143] == 0xFF and data[144] == 0xFF:

                        # ========== 5. 验证校验和 ==========
                        # 导入校验和计算函数
                        from ..protocol.checksums import calculate_byte_sum_checksum

                        # 计算字节 0-142 的和
                        checksum = calculate_byte_sum_checksum(data[0:142])

                        # 校验字节 142 是否等于计算值
                        if data[142] == (checksum & 0xFF):
                            # ========== 6. 有效数据包！==========
                            # 发射信号通知主窗口
                            self.data_received.emit(data)

                            # 发射信号确认 WiFi 模式
                            self.comm_mode_detected.emit(CommunicationMode.WIFI)

            # ========== 7. 休眠 300ms ==========
            # C# 源码 line 432: Thread.Sleep(300)
            # 避免占用过多 CPU，同时保持及时的响应
            self.msleep(300)

        print("UDP接收线程已停止")

    def stop(self):
        """
        停止线程（优雅退出）

        设置 running 标志为 False，等待线程自然退出循环。
        使用互斥锁保证线程安全。

        调用流程：
        1. 加锁
        2. 设置 running = False
        3. 解锁
        4. 等待线程退出（wait()）

        注意事项：
            - 必须调用 stop() 才能安全退出线程
            - stop() 后应调用 wait() 等待线程完全退出
            - 不要使用 terminate() 强制终止（不安全）

        示例：
            >>> receiver_thread.stop()  # 请求停止
            >>> receiver_thread.wait()   # 等待退出
            >>> print("线程已安全退出")
        """
        # 使用互斥锁保护 running 标志
        with QMutexLocker(self.mutex):
            self.running = False

        # 等待线程自然退出
        # wait() 会阻塞直到线程的 run() 方法返回
        self.wait()
