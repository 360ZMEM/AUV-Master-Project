"""
AUV 通信协议数据包构建器
=====================================

本模块实现了 AUV 与上位机之间的通信协议数据包构建和解析功能。

C# 源码参考：
- Form1.cs timer1_Tick (行 1388-1487) - 发送数据包构建
- Form1.cs display() (行 603-840) - 接收数据包解析

主要功能：
1. 构建发送数据包 (72字节 $CKTH) - 用于向 AUV 发送控制指令
2. 构建北斗数据包 (34字节) - 北斗卫星通信的压缩格式
3. 解析接收数据包 (145字节 $AUV) - 解析 AUV 发回的遥测数据

数据包格式：
- 发送包: 72字节，帧头 0x24 0x43 0x4B 0x54 0x48 ($CKTH)
- 接收包: 145字节，帧头 0x24 0x41 0x55 0x56 0x91 ($AUV▒)
- 北斗包: 34字节，帧头 0x24 0x43 0x4B 0x54 0x48 ($CKTH)

字节序：所有多字节字段使用大端序 (big-endian)
校验和：字节和校验（取低8位）
"""

from .constants import *
from .checksums import calculate_byte_sum_checksum
from ..data_structures import Preferences, TelemetryData
import struct


class PacketBuilder:
    """
    AUV 通信协议数据包构建器

    职责：
    - 构建72字节发送数据包（WiFi/无线电）
    - 构建34字节北斗数据包（卫星通信）
    - 解析145字节接收数据包（AUV遥测数据）
    - 管理帧序号计数器

    使用示例：
        builder = PacketBuilder()

        # 构建发送数据包
        packet = builder.build_send_packet(
            preferences=prefs,
            work_instruct=0x01,
            motor_speeds=(1000, 2000),
            rudder_angles=(10, -10, 5, -5),
            orientation=90,
            parameters=(0,)*12
        )

        # 解析接收数据包
        telemetry = builder.parse_recv_packet(recv_data)
        print(f"深度: {telemetry.depth}m")
        print(f"GPS: {telemetry.gps_lon}, {telemetry.gps_lat}")
    """

    def __init__(self):
        """
        初始化数据包构建器

        属性：
            frame_counter (int): 帧序号计数器 (0-255循环)
                               用于跟踪数据包顺序，检测丢包
        """
        self.frame_counter = 0  # 帧序号，每次发送后递增，0-255循环

    def build_send_packet(self,
                          preferences: Preferences,
                          work_instruct: int,
                          motor_speeds: tuple,
                          rudder_angles: tuple,
                          orientation: int,
                          parameters: tuple,
                          control_mode_byte=None) -> bytes:
        """
        构建72字节发送数据包 ($CKTH)

        本方法将所有控制参数打包成72字节的二进制数据包，通过WiFi或无线电发送给AUV。

        C# 源码参考：Form1.cs lines 1388-1480

        数据包结构：
        [字节0-4]   帧头: 0x24 0x43 0x4B 0x54 0x48 ($CKTH)
        [字节5]     帧序号 (frame_counter)
        [字节6]     目标地址 (1-3)
        [字节7]     工作模式 (0-4)
        [字节8-9]   深度保护参数1 (UInt16, 单位m)
        [字节10-11] 深度保护参数2 (UInt16, 单位m)
        [字节12-13] 离底保护参数1 (UInt16, 单位m)
        [字节14-15] 离底保护参数2 (UInt16, 单位m)
        [字节16-17] 预设时间 (UInt16, ×0.1分钟)
        [字节18-19] 备用参数1 (Int16)
        [字节20-21] 备用参数2 (Int16)
        [字节22]    工作指令 (work_instruct, 位掩码)
        [字节23-24] 主推进器转速 (Int16, RPM)
        [字节25-26] 侧推进器转速 (Int16, RPM)
        [字节27-28] 左水平舵角 (Int16, ×0.1°)
        [字节29-30] 右水平舵角 (Int16, ×0.1°)
        [字节31-32] 上垂直舵角 (Int16, ×0.1°)
        [字节33-34] 下垂直舵角 (Int16, ×0.1°)
        [字节35-36] 航向角 (UInt16, ×0.1°)
        [字节37-40] 参数1 (Int32, ×1,000,000 - GPS经度)
        [字节41-44] 参数2 (Int32, ×1,000,000 - GPS纬度)
        [字节45-48] 参数3 (Int32, ×1,000,000)
        [字节49-52] 参数4 (Int32, ×1,000,000)
        [字节53-54] 参数5 (Int16, ×10,000)
        [字节55-56] 参数6 (Int16, ×10,000)
        [字节57-58] 参数7 (Int16, ×10,000)
        [字节59-60] 参数8 (Int16, ×10,000)
        [字节61-62] 参数9 (Int16, ×1,000)
        [字节63-64] 参数10 (Int16, ×1,000)
        [字节65-66] 参数11 (Int16, ×1,000)
        [字节67-68] 参数12 (Int16, ×1,000)
        [字节69]    校验和 (字节0-68之和，取低8位)
        [字节70-71] 帧尾: 0xFF 0xFF

        Args:
            preferences (Preferences): 任务首选项结构体
                - obj_address: 目标AUV地址 (1-3)
                - work_mode: 工作模式 (0=仅发送, 1=遥控, 2=定点, 3=定向, 4=回航)
                - depth_proprotect_param1/2: 深度保护参数
                - bottom_proprotect_param1/2: 离底保护参数
                - preset_time: 预设时间 (×0.1分钟)
                - spare_param1/2: 备用参数
                - return_longitude/latitude: 回航航路点

            work_instruct (int): 工作指令字节 (位掩码)
                - 0x11: 主推上电, 0x12: 主推断电
                - 0x13: 侧推上电, 0x14: 侧推断电
                - 0x15-0x18: 舵机上电/断电
                - 0x21-0x24: DVL/罗经上电/断电
                - 0x51-0x54: 参数调整
                - 0x71-0x74: 航行控制

            motor_speeds (tuple): (主推进器转速, 侧推进器转速)
                - 主推: -1500 ~ 1500 RPM
                - 侧推: -4000 ~ 4000 RPM

            rudder_angles (tuple): (左水平舵, 右水平舵, 上垂直舵, 下垂直舵)
                - 单位: ×0.1°, 范围: -300 ~ 300 (±30°)

            orientation (int): 航向角 (0-359°, ×0.1)

            parameters (tuple): 12个可调参数
                - 参数1-4: Int32 (×1,000,000) - 用于GPS坐标
                - 参数5-8: Int16 (×10,000)
                - 参数9-12: Int16 (×1,000)

        Returns:
            bytes: 72字节完整数据包，可直接发送

        Raises:
            无异常，所有输入通过参数对象和类型约束保证有效性

        注意事项：
            - 所有多字节字段使用大端序 (network byte order)
            - 工作指令使用位掩码，多个指令可按位或运算组合
            - GPS坐标缩放 ×1,000,000 (如 115.368621° → 115368621)
        """
        # 创建72字节空数据包
        packet = bytearray(SEND_PACKET_SIZE)

        # ========== 帧头 (字节 0-4) ==========
        # 固定值: 0x24 0x43 0x4B 0x54 0x48
        # ASCII: "$CKTH" (Console to AUV Header)
        packet[0:5] = FRAME_HEADER_SEND

        # ========== 帧序号 (字节 5) ==========
        # 范围: 0-255, 循环递增
        # 用途: 跟踪数据包顺序，检测丢包
        packet[5] = self.frame_counter & 0xFF

        # ========== 首选项数据 (字节 6-21) ==========

        # 字节6: 目标地址
        # 1 = AUV #1, 2 = AUV #2, 3 = AUV #3
        packet[6] = preferences.obj_address & 0xFF

        # 字节7: 工作模式
        # 0 = 仅发送 (不执行任务)
        # 1 = 遥控模式 (远程控制)
        # 2 = 自主定点 (按航点航行)
        # 3 = 自主定向 (按定航向航行)
        # 4 = 自主回航 (返回起始点)
        effective_control_mode = preferences.work_mode if control_mode_byte is None else control_mode_byte
        packet[7] = effective_control_mode & 0xFF

        # 字节8-9: 深度保护参数1 (UInt16, 大端序)
        # 单位: 米 (m)
        # 含义: 超过此深度触发保护（如紧急上浮）
        struct.pack_into('>H', packet, 8, preferences.depth_proprotect_param1)

        # 字节10-11: 深度保护参数2 (UInt16, 大端序)
        # 单位: 米 (m)
        # 含义: 第二级深度保护阈值
        struct.pack_into('>H', packet, 10, preferences.depth_proprotect_param2)

        # 字节12-13: 离底保护参数1 (UInt16, 大端序)
        # 单位: 米 (m)
        # 含义: 离底距离小于此值触发保护
        struct.pack_into('>H', packet, 12, preferences.bottom_proprotect_param1)

        # 字节14-15: 离底保护参数2 (UInt16, 大端序)
        # 单位: 米 (m)
        # 含义: 第二级离底保护阈值
        struct.pack_into('>H', packet, 14, preferences.bottom_proprotect_param2)

        # 字节16-17: 预设时间 (UInt16, 大端序)
        # 单位: ×0.1 分钟
        # 示例: 600 = 60分钟
        struct.pack_into('>H', packet, 16, preferences.preset_time)

        # 字节18-19: 备用参数1 (Int16, 大端序)
        # 保留用于未来扩展
        struct.pack_into('>h', packet, 18, preferences.spare_param1)

        # 字节20-21: 备用参数2 (Int16, 大端序)
        # 保留用于未来扩展
        struct.pack_into('>h', packet, 20, preferences.spare_param2)

        # ========== 工作指令 (字节 22) ==========
        # 位掩码格式的控制指令
        # 可组合多个指令: work_instruct |= 0x11 | 0x21
        packet[22] = work_instruct & 0xFF

        # ========== 电机转速控制 (字节 23-26) ==========

        # 字节23-24: 主推进器转速 (Int16, 大端序)
        # 范围: -1500 ~ 1500 RPM
        # 负值 = 反转, 正值 = 正转
        struct.pack_into('>h', packet, 23, motor_speeds[0])

        # 字节25-26: 侧推进器转速 (Int16, 大端序)
        # 范围: -4000 ~ 4000 RPM
        # 用于横向推进和转向
        struct.pack_into('>h', packet, 25, motor_speeds[1])

        # ========== 舵角控制 (字节 27-34) ==========
        # 所有舵角单位: ×0.1°, 范围: -300 ~ 300 (±30°)

        # 字节27-28: 左水平舵角 (Int16, 大端序)
        struct.pack_into('>h', packet, 27, rudder_angles[0])

        # 字节29-30: 右水平舵角 (Int16, 大端序)
        struct.pack_into('>h', packet, 29, rudder_angles[1])

        # 字节31-32: 上垂直舵角 (Int16, 大端序)
        struct.pack_into('>h', packet, 31, rudder_angles[2])

        # 字节33-34: 下垂直舵角 (Int16, 大端序)
        struct.pack_into('>h', packet, 33, rudder_angles[3])

        # ========== 航向角 (字节 35-36) ==========
        # 目标航向 (UInt16, 大端序)
        # 单位: ×0.1°, 范围: 0-3599 (0-359.9°)
        struct.pack_into('>H', packet, 35, orientation)

        # ========== 12个可调参数 (字节 37-68) ==========

        # 参数1-4: GPS坐标或其他 (Int32, ×1,000,000)
        # 常用于存储GPS坐标: 经纬度 × 1,000,000
        # 示例: 115.368621°E → 115368621
        struct.pack_into('>i', packet, 37, parameters[0])  # 字节37-40
        struct.pack_into('>i', packet, 41, parameters[1])  # 字节41-44
        struct.pack_into('>i', packet, 45, parameters[2])  # 字节45-48
        struct.pack_into('>i', packet, 49, parameters[3])  # 字节49-52

        # 参数5-8: 中等精度参数 (Int16, ×10,000)
        struct.pack_into('>h', packet, 53, parameters[4])  # 字节53-54
        struct.pack_into('>h', packet, 55, parameters[5])  # 字节55-56
        struct.pack_into('>h', packet, 57, parameters[6])  # 字节57-58
        struct.pack_into('>h', packet, 59, parameters[7])  # 字节59-60

        # 参数9-12: 低精度参数 (Int16, ×1,000)
        struct.pack_into('>h', packet, 61, parameters[8])  # 字节61-62
        struct.pack_into('>h', packet, 63, parameters[9])  # 字节63-64
        struct.pack_into('>h', packet, 65, parameters[10]) # 字节65-66
        struct.pack_into('>h', packet, 67, parameters[11]) # 字节67-68

        # ========== 校验和 (字节 69) ==========
        # 计算字节0-68的和，取低8位
        checksum = calculate_byte_sum_checksum(packet[0:69])
        packet[69] = checksum

        # ========== 帧尾 (字节 70-71) ==========
        # 固定值: 0xFF 0xFF
        # 用于数据包结束标识
        packet[70:72] = FRAME_TRAILER

        return bytes(packet)

    def build_beidou_packet(self,
                           preferences: Preferences,
                           work_instruct: int) -> bytes:
        """
        构建34字节北斗卫星数据包 (压缩格式)

        北斗卫星通信带宽有限，使用压缩数据包格式。
        仅包含必要的控制参数，不含电机和舵角控制。

        C# 源码参考：Form1.cs Timer2_Tick 北斗部分

        数据包结构：
        [字节0-4]   帧头: 0x24 0x43 0x4B 0x54 0x48 ($CKTH)
        [字节5]     帧序号
        [字节6]     目标地址
        [字节7]     工作模式
        [字节8-21] 保护参数和备用参数 (同发送包)
        [字节22]    工作指令 (仅限: 0x00, 0x01, 0x02, 0x91, 0x92)
        [字节23-30] 回航航路点 (经度、纬度)
        [字节31]    校验和
        [字节32-33] 帧尾: 0xFF 0xFF

        Args:
            preferences (Preferences): 任务首选项
            work_instruct (int): 工作指令
                仅支持基本指令:
                - 0x00: 无操作
                - 0x01: 任务开启
                - 0x02: 任务取消
                - 0x91: 清除故障
                - 0x92: 初始化

        Returns:
            bytes: 34字节压缩数据包

        注意事项：
            - 北斗带宽有限，仅用于基本任务控制
            - 不支持实时电机和舵角控制
            - 使用频率应控制在每分钟1-2次
        """
        # 创建34字节压缩数据包
        packet = bytearray(BEIDOU_PACKET_SIZE)

        # 帧头 (与发送包相同)
        packet[0:5] = FRAME_HEADER_BEIDOU

        # 帧序号
        packet[5] = self.frame_counter & 0xFF

        # ========== 首选项数据 (与发送包相同) ==========
        packet[6] = preferences.obj_address & 0xFF
        packet[7] = preferences.work_mode & 0xFF

        # 深度保护参数
        struct.pack_into('>H', packet, 8, preferences.depth_proprotect_param1)
        struct.pack_into('>H', packet, 10, preferences.depth_proprotect_param2)

        # 离底保护参数
        struct.pack_into('>H', packet, 12, preferences.bottom_proprotect_param1)
        struct.pack_into('>H', packet, 14, preferences.bottom_proprotect_param2)

        # 预设时间和备用参数
        struct.pack_into('>H', packet, 16, preferences.preset_time)
        struct.pack_into('>h', packet, 18, preferences.spare_param1)
        struct.pack_into('>h', packet, 20, preferences.spare_param2)

        # ========== 工作指令 (字节 22) ==========
        # 北斗仅支持基本指令
        packet[22] = work_instruct & 0xFF

        # ========== 回航航路点 (字节 23-30) ==========
        # 用于自主回航模式
        # 经度: Int32, ×1,000,000
        struct.pack_into('>i', packet, 23, preferences.return_longitude)

        # 纬度: Int32, ×1,000,000
        struct.pack_into('>i', packet, 27, preferences.return_latitude)

        # ========== 校验和 (字节 31) ==========
        checksum = calculate_byte_sum_checksum(packet[0:31])
        packet[31] = checksum

        # 帧尾
        packet[32:34] = FRAME_TRAILER

        return bytes(packet)

    def parse_recv_packet(self, data: bytes) -> TelemetryData:
        """
        解析145字节接收数据包 ($AUV)

        本方法解析从AUV接收的145字节遥测数据包，提取所有传感器数据
        和状态信息。

        C# 源码参考：Form1.cs display() method, lines 603-840

        数据包结构：
        [字节0-4]   帧头: 0x24 0x41 0x55 0x56 0x91 ($AUV▒)
        [字节5]     帧序号
        [字节6]     AUV地址
        [字节7]     工作模式
        [字节8-21] 首选项回显
        [字节22]    工作指令反馈
        [字节23-26] 电机转速反馈
        [字节27-34] 舵角反馈
        [字节35-36] 航向角
        [字节37-68] 12个参数反馈
        [字节69-85] 传感器数据
        [字节86-101] 位置数据
        [字节102-113] 电源数据
        [字节114-141] 系统状态
        [字节142]   校验和
        [字节143-144] 帧尾: 0xFF 0xFF

        Args:
            data (bytes): 145字节接收数据包

        Returns:
            TelemetryData: 解析后的遥测数据对象，包含：
                - 基本信息帧序号、地址、工作模式
                - 首选项回显保护参数等
                - 电机状态转速、舵角
                - 传感器数据深度、温度、罗经、DVL、GPS
                - 位置数据GPS坐标、推算航位
                - 电源数据电压、电流、SOC、电池详情
                - 系统状态设备状态、任务状态、报警

        Raises:
            ValueError: 当数据包校验失败时
                - 长度不等于145字节
                - 帧头不匹配
                - 帧尾不匹配
                - 校验和不匹配

        示例：
            >>> telemetry = builder.parse_recv_packet(recv_data)
            >>> print(f"深度: {telemetry.depth:.2f}m")
            >>> print(f"航向: {telemetry.compass_heading:.1f}°")
            >>> print(f"GPS: {telemetry.gps_lat:.6f}°N, {telemetry.gps_lon:.6f}°E")
            >>> print(f"电池: {telemetry.soc}%")
        """
        # ========== 数据包验证 ==========

        # 检查数据包长度
        if len(data) < RECV_PACKET_SIZE:
            raise ValueError(f"数据包长度错误: 收到 {len(data)} 字节, 应为 {RECV_PACKET_SIZE} 字节")

        # 验证帧头: $AUV▒ (0x24 0x41 0x55 0x56 0x91)
        if data[0:5] != FRAME_HEADER_RECV:
            raise ValueError(f"帧头错误: {data[0:5].hex()} != {FRAME_HEADER_RECV.hex()}")

        # 验证帧尾: 0xFF 0xFF
        if data[143:145] != FRAME_TRAILER:
            raise ValueError(f"帧尾错误: {data[143:145].hex()} != {FRAME_TRAILER.hex()}")

        # 验证校验和 (字节 0-141 之和应等于 字节 142)
        checksum = calculate_byte_sum_checksum(data[0:142])
        if data[142] != checksum:
            raise ValueError(
                f"校验和错误: 计算 {checksum:#04x}, 收到 {data[142]:#04x}"
            )

        # ========== 开始解析数据包 ==========
        telemetry = TelemetryData()

        # ========== 基本信息 (字节 5-7) ==========

        # 字节5: 帧序号
        telemetry.frame_number = data[5]

        # 字节6: AUV地址
        telemetry.auv_address = data[6]

        # 字节7: 工作模式
        telemetry.work_mode = data[7]

        # ========== 首选项回显 (字节 8-21) ==========
        # AUV回显当前使用的任务参数，用于确认控制成功

        # 深度保护参数
        telemetry.depth_protect_1 = struct.unpack('>H', data[8:10])[0]
        telemetry.depth_protect_2 = struct.unpack('>H', data[10:12])[0]

        # 离底保护参数
        telemetry.bottom_protect_1 = struct.unpack('>H', data[12:14])[0]
        telemetry.bottom_protect_2 = struct.unpack('>H', data[14:16])[0]

        # 预设时间
        telemetry.preset_time = struct.unpack('>H', data[16:18])[0]

        # ========== 工作指令反馈 (字节 22) ==========
        # AUV当前执行的工作指令状态
        telemetry.work_instruction = data[22]

        # ========== 电机转速反馈 (字节 23-26) ==========

        # 主推进器转速 (Int16, RPM)
        telemetry.motor_speed1 = struct.unpack('>h', data[23:25])[0]

        # 侧推进器转速 (Int16, RPM)
        telemetry.motor_speed2 = struct.unpack('>h', data[25:27])[0]

        # ========== 舵角反馈 (字节 27-34) ==========
        # 所有舵角单位: ×0.1°

        telemetry.rudder_angle_lh = struct.unpack('>h', data[27:29])[0]  # 左水平
        telemetry.rudder_angle_rh = struct.unpack('>h', data[29:31])[0]  # 右水平
        telemetry.rudder_angle_uv = struct.unpack('>h', data[31:33])[0]  # 上垂直
        telemetry.rudder_angle_lv = struct.unpack('>h', data[33:35])[0]  # 下垂直

        # ========== 航向角 (字节 35-36) ==========
        # 当前航向 (UInt16, ×0.1°)
        telemetry.orientation_angle = struct.unpack('>H', data[35:37])[0]

        # ========== 12个参数反馈 (字节 37-68) ==========

        # 参数1-4: Int32, ×1,000,000
        telemetry.param1 = struct.unpack('>i', data[37:41])[0]
        telemetry.param2 = struct.unpack('>i', data[41:45])[0]
        telemetry.param3 = struct.unpack('>i', data[45:49])[0]
        telemetry.param4 = struct.unpack('>i', data[49:53])[0]

        # 参数5-8: Int16, ×10,000
        telemetry.param5 = struct.unpack('>h', data[53:55])[0]
        telemetry.param6 = struct.unpack('>h', data[55:57])[0]
        telemetry.param7 = struct.unpack('>h', data[57:59])[0]
        telemetry.param8 = struct.unpack('>h', data[59:61])[0]

        # 参数9-12: Int16, ×1,000
        telemetry.param9 = struct.unpack('>h', data[61:63])[0]
        telemetry.param10 = struct.unpack('>h', data[63:65])[0]
        telemetry.param11 = struct.unpack('>h', data[65:67])[0]
        telemetry.param12 = struct.unpack('>h', data[67:69])[0]

        # ========== 传感器数据 (字节 69-85) ==========

        # 注意：此处需要根据实际协议定义调整偏移量
        # 以下解析基于文档描述，可能需要根据实际情况调整

        # 内部压力 (字节 35-36 重新解析, Int16, ×0.001 psi)
        # 注：文档中显示可能与航向角重叠，需确认
        telemetry.internal_pressure = struct.unpack('>h', data[35:37])[0] * 0.001

        # 内部温度 (字节 37, signed byte)
        # 单位: 摄氏度 (°C)
        telemetry.internal_temp = struct.unpack('b', bytes([data[37]]))[0]

        # 深度 (字节 38-39, UInt16, ×0.1 m)
        # AUV当前深度，相对于水面
        telemetry.depth = struct.unpack('>H', data[38:40])[0] * 0.1

        # ========== 罗经数据 (字节 72-77) ==========

        # 航向 (Int16, ×0.1°)
        telemetry.compass_heading = struct.unpack('>h', data[72:74])[0] * 0.1

        # 俯仰角 (Int16, ×0.1°, 正值=抬头)
        telemetry.compass_pitch = struct.unpack('>h', data[74:76])[0] * 0.1

        # 横滚角 (Int16, ×0.1°, 正值=右倾)
        telemetry.compass_roll = struct.unpack('>h', data[76:78])[0] * 0.1

        # ========== GPS数据 (字节 78-81, 82-83) ==========

        # GPS航向 (UInt16, ×0.1°)
        telemetry.gps_heading = struct.unpack('>H', data[78:80])[0] * 0.1

        # GPS对地速度 (UInt16, ×0.1 m/s)
        telemetry.gps_speed = struct.unpack('>H', data[80:82])[0] * 0.1

        # ========== DVL速度 (字节 82-83) ==========
        # 多普勒测速仪提供的对地速度 (Int16, ×0.1 m/s)
        telemetry.dv1_speed = struct.unpack('>h', data[82:84])[0] * 0.1

        # ========== 高度计 (字节 84-85) ==========
        # 离底高度 (UInt16, ×0.1 m)
        telemetry.altitude = struct.unpack('>H', data[84:86])[0] * 0.1

        # ========== 位置数据 (字节 86-101) ==========

        # 推算航位经度 (Int32, ×1,000,000)
        # 基于DVL和罗经推算的位置
        telemetry.dead_reck_lon = struct.unpack('>i', data[86:90])[0] * 0.000001

        # 推算航位纬度 (Int32, ×1,000,000)
        telemetry.dead_reck_lat = struct.unpack('>i', data[90:94])[0] * 0.000001

        # GPS经度 (Int32, ×1,000,000)
        # GPS接收器提供的经度坐标
        telemetry.gps_lon = struct.unpack('>i', data[94:98])[0] * 0.000001

        # GPS纬度 (Int32, ×1,000,000)
        # GPS接收器提供的纬度坐标
        telemetry.gps_lat = struct.unpack('>i', data[98:102])[0] * 0.000001

        # ========== 电源数据 (字节 102-113) ==========

        # 总电压 (UInt16, ×0.1 V)
        telemetry.total_voltage = struct.unpack('>H', data[102:104])[0] * 0.1

        # 总电流 (UInt16, ×0.1 A)
        telemetry.total_current = struct.unpack('>H', data[104:106])[0] * 0.1

        # 荷电状态 (State of Charge, 0-100%)
        telemetry.soc = data[106]

        # 健康状态 (State of Health, 0-100%)
        telemetry.soh = data[107]

        # ========== 电池详情 (字节 108-113) ==========

        # 最高单体电压 (UInt16, ×0.001 V)
        telemetry.cell_voltage_max = struct.unpack('>H', data[108:110])[0] * 0.001

        # 最低单体电压 (UInt16, ×0.001 V)
        telemetry.cell_voltage_min = struct.unpack('>H', data[110:112])[0] * 0.001

        # 最高电芯温度 (signed byte, °C)
        telemetry.cell_temp_max = struct.unpack('b', bytes([data[112]]))[0]

        # 最低电芯温度 (signed byte, °C)
        telemetry.cell_temp_min = struct.unpack('b', bytes([data[113]]))[0]

        # ========== 系统状态 (字节 114-141) ==========
        # 这些是位字段 (bit fields)，需要进一步解析

        # 设备电源状态 (UInt32, 位掩码)
        # 每个bit对应一个设备的电源状态
        telemetry.device_power_status = struct.unpack('>I', data[114:118])[0]

        # 运行反馈 (UInt32, 位掩码)
        # 指示各种操作的执行结果
        telemetry.operation_feedback = struct.unpack('>I', data[118:122])[0]

        # 任务状态 (UInt32, 位掩码)
        # 当前任务执行状态
        telemetry.task_status = struct.unpack('>I', data[122:126])[0]

        # ========== 报警信息 (字节 127-129) ==========

        # 系统报警 (字节 127, 位掩码)
        telemetry.system_alarm = data[127]

        # 深度报警 (字节 128, 位掩码)
        telemetry.depth_alarm = data[128]

        # 离底报警 (字节 129, 位掩码)
        telemetry.bottom_alarm = data[129]

        # 更多报警字节...

        return telemetry

    def increment_frame(self):
        """
        递增帧序号计数器

        每次发送数据包后调用此方法，使帧序号在 0-255 之间循环。

        用途：
        - 跟踪数据包顺序
        - 检测丢包
        - 同步收发状态

        示例：
            builder = PacketBuilder()
            packet = builder.build_send_packet(...)
            builder.increment_frame()  # 准备下一个数据包
        """
        self.frame_counter += 1
        if self.frame_counter >= 0xFF:
            self.frame_counter = 0  # 回绕到0
