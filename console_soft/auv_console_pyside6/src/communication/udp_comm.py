"""
WiFi UDP 通信处理模块
======================

本模块实现 AUV 与上位机之间的 WiFi UDP 通信。
UDP 是默认的通信方式，提供高速率、低延迟的数据传输。

C# 源码参考：Form1.cs UdpClient 使用 (lines 79-91, 399-434)

主要功能：
1. UDP socket 创建和绑定
2. 数据包发送（72字节控制指令）
3. 数据包接收（145字节遥测数据，非阻塞）
4. socket 生命周期管理

通信参数：
- 本地地址: 默认 192.168.0.11:21
- 目标地址: 默认 192.168.0.101:52364
- 缓冲区大小: 2048 字节
"""

import socket
from PySide6.QtCore import QObject, Signal


class UDPCommunicator(QObject):
    """
    WiFi UDP 通信器

    负责处理与 AUV 的 WiFi UDP 通信。
    继承自 QObject 以支持 Qt 信号/槽机制。

    C# 源码参考：Form1.cs lines 79-91, THREAD_REC (lines 399-434)

    Qt 信号：
        data_received (Signal): 数据接收信号
            - 参数: bytes (接收到的数据)
            - 用途: 通知有新数据到达

    属性：
        local_ip (str): 本地 IP 地址
        local_port (int): 本地 UDP 端口
        remote_ip (str): AUV IP 地址
        remote_port (int): AUV UDP 端口
        socket (socket.socket): UDP socket 对象
        is_running (bool): 通信状态标志

    使用示例：
        >>> udp = UDPCommunicator(
        ...     local_ip="192.168.0.11",
        ...     local_port=21,
        ...     remote_ip="192.168.0.101",
        ...     remote_port=52364
        ... )
        >>> udp.start()
        >>>
        >>> # 发送数据包
        >>> udp.send(packet_72bytes)
        >>>
        >>> # 接收数据包（非阻塞）
        >>> data = udp.receive()
        >>>
        >>> # 停止通信
        >>> udp.stop()
    """

    # 数据接收信号
    data_received = Signal(bytes)  # 参数: 接收到的数据

    def __init__(self, local_ip: str, local_port: int, remote_ip: str, remote_port: int):
        """
        初始化 UDP 通信器

        Args:
            local_ip (str): 本地 IP 地址 (如 "192.168.0.11")
            local_port (int): 本地 UDP 端口 (如 21)
            remote_ip (str): AUV IP 地址 (如 "192.168.0.101")
            remote_port (int): AUV UDP 端口 (如 52364)
        """
        super().__init__()
        self.local_ip = local_ip
        self.local_port = local_port
        self.remote_ip = remote_ip
        self.remote_port = remote_port
        self.socket = None
        self.is_running = False

    def start(self):
        """
        初始化 UDP socket 并绑定到本地地址

        创建 UDP socket，绑定到指定的本地 IP 和端口，
        并设置运行标志为 True。

        Returns:
            bool: 成功返回 True，失败返回 False

        Raises:
            无异常，错误会被捕获并打印

        注意事项：
            - 绑定失败可能是端口被占用
            - 确保本地 IP 地址正确配置
        """
        if self.is_running and self.socket is not None:
            return True

        try:
            if self.socket is not None:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None

            # 创建 UDP socket (AF_INET=IPv4, SOCK_DGRAM=UDP)
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            # 绑定到本地地址和端口
            self.socket.bind((self.local_ip, self.local_port))

            self.is_running = True
            print(f"UDP socket 已绑定到 {self.local_ip}:{self.local_port}")
            return True

        except Exception as e:
            print(f"UDP socket 绑定失败: {e}")
            return False

    def send(self, data: bytes):
        """
        通过 UDP 发送数据到 AUV

        向 AUV 发送 72 字节控制数据包。

        C# 源码参考：Form1.cs line 1478 udp_send_recv.Send()

        Args:
            data (bytes): 要发送的数据包（72字节）

        Returns:
            bool: 成功返回 True，失败返回 False

        注意事项：
            - 确保已调用 start() 且 socket 正常
            - 发送失败不会抛出异常，只返回 False
        """
        if self.socket and self.is_running:
            try:
                # 发送数据到目标地址
                self.socket.sendto(data, (self.remote_ip, self.remote_port))
                return True
            except Exception as e:
                print(f"UDP 发送错误: {e}")
                return False
        return False

    def receive(self) -> bytes:
        """
        非阻塞接收数据（从后台线程调用）

        尝试从 UDP socket 接收数据，如果没有数据到达则立即返回 None。
        由 UDP 接收线程定期调用此方法。

        C# 源码参考：Form1.cs lines 411 udp_send_recv.Receive()

        Returns:
            bytes or None: 接收到的数据，无数据则返回 None

        注意事项：
            - 非阻塞模式，无数据时立即返回
            - 缓冲区大小为 2048 字节
            - 应从后台线程调用，避免阻塞主线程
        """
        if self.socket and self.is_running:
            try:
                # 设置为非阻塞模式
                self.socket.setblocking(False)

                # 接收数据（最多 2048 字节）
                data, addr = self.socket.recvfrom(2048)
                return data

            except BlockingIOError:
                # 无数据到达（正常情况）
                return None

            except Exception as e:
                print(f"UDP 接收错误: {e}")
                return None
        return None

    def stop(self):
        """
        关闭 UDP socket

        关闭 socket 并释放资源。
        在应用程序关闭或切换通信模式时调用。

        注意事项：
            - 关闭后需要重新调用 start() 才能再次使用
            - 发送/接收操作在关闭后会自动失败
        """
        self.is_running = False
        if self.socket:
            try:
                self.socket.close()
                print("UDP socket 已关闭")
            except Exception as e:
                print(f"关闭 UDP socket 时出错: {e}")
            finally:
                self.socket = None
