"""
AUV 操控台应用程序 - 数据结构定义
====================================

本模块定义了 AUV 操控台使用的所有数据结构。

C# 源码参考：Form1.cs

主要数据结构：
1. Preferences - 任务首选项（任务配置参数）
2. AutoFixedPoint - 自主定点航路点
3. TelemetryData - 遥测数据（从AUV接收的完整状态）
4. GPSQueue - GPS轨迹队列（最多1000个点）

使用说明：
- 所有数据结构使用 dataclass 装饰器，自动生成 __init__ 等方法
- GPS坐标缩放因子为 ×1,000,000 (如 115.368621° → 115368621)
- 角度单位通常为 ×0.1° (度数的十倍)
- 深度单位为 ×0.1 m (分米)
"""

from dataclasses import dataclass
from typing import List
from collections import deque


@dataclass
class Preferences:
    """
    任务首选项结构体

    本结构体包含了 AUV 任务的所有配置参数，在发送数据包中
    占据字节 6-21 和字节 23-30（回航航路点）。

    C# 源码参考：Form1.cs lines 101-114

    属性说明：
        obj_address (int): 目标AUV地址
            - 1: AUV #1
            - 2: AUV #2
            - 3: AUV #3
            - 用于多AUV编队控制

        work_mode (int): 工作模式
            - 0: 仅发送模式（Send Only）- 只发送数据不执行任务
            - 1: 遥控模式（Remote Control）- 远程手动控制
            - 2: 自主定点模式（Auto Fixed Point）- 按航点自动航行
            - 3: 自主定向模式（Directional）- 保持定航向航行
            - 4: 自主回航模式（Return Home）- 返回起始点

        depth_proprotect_param1 (int): 深度保护参数1 (单位: 米)
            - 第一级深度保护阈值
            - 当深度超过此值时触发保护动作
            - 典型值: 500m

        depth_proprotect_param2 (int): 深度保护参数2 (单位: 米)
            - 第二级深度保护阈值
            - 更严格的深度限制
            - 典型值: 29m

        bottom_proprotect_param1 (int): 离底保护参数1 (单位: 米)
            - 第一级离底保护阈值
            - 当离底距离小于此值时触发保护
            - 典型值: 300m

        bottom_proprotect_param2 (int): 离底保护参数2 (单位: 米)
            - 第二级离底保护阈值
            - 更严格的离底限制
            - 典型值: 200m

        preset_time (int): 预设任务时间 (单位: ×0.1 分钟)
            - 任务的最长执行时间
            - 示例: 600 = 60分钟
            - 超时后自动上浮或返回

        spare_param1 (int): 备用参数1 (Int16)
            - 保留用于未来功能扩展
            - 当前未使用

        spare_param2 (int): 备用参数2 (Int16)
            - 保留用于未来功能扩展
            - 当前未使用

        return_longitude (int): 回航经度 (Int32, ×1,000,000)
            - 自主回航模式的目标经度
            - 示例: 115.368621°E → 115368621
            - 东经为正，西经为负

        return_latitude (int): 回航纬度 (Int32, ×1,000,000)
            - 自主回航模式的目标纬度
            - 示例: 22.754909°N → 22754909
            - 北纬为正，南纬为负

    使用示例：
        >>> prefs = Preferences()
        >>> prefs.obj_address = 1
        >>> prefs.work_mode = 2  # 自主定点模式
        >>> prefs.depth_proprotect_param1 = 500  # 500m深度保护
        >>> prefs.return_longitude = 115368621  # 115.368621°E
        >>> prefs.return_latitude = 22754909  # 22.754909°N
    """
    obj_address: int = 1                     # Byte: 1-3, 目标地址
    work_mode: int = 0                       # Byte: 0-4, 工作模式
                                            # 0x00=仅发送, 0x01=遥控, 0x02=定点,
                                            # 0x03=定向, 0x04=回航
    depth_proprotect_param1: int = 500       # UInt16, 航行超深保护参数1 (meters)
    depth_proprotect_param2: int = 29        # UInt16, 航行超深保护参数2 (meters)
    bottom_proprotect_param1: int = 300      # UInt16, 离底超限保护参数1 (meters)
    bottom_proprotect_param2: int = 200      # UInt16, 离底超限保护参数2 (meters)
    preset_time: int = 10                    # UInt16, 预设时间 (×0.1 minutes)
    spare_param1: int = 0                    # Int16, 备用参数1
    spare_param2: int = 0                    # Int16, 备用参数2
    return_longitude: int = 0                # Int32, 回航经度 (×1000000)
    return_latitude: int = 0                 # Int32, 回航纬度 (×1000000)


@dataclass
class AutoFixedPoint:
    """
    自主定点航路点结构体

    本结构体定义了一个自主定点航行的航路点，包含位置、控制策略、
    电机转速和设备控制等信息。

    C# 源码参考：Form1.cs lines 66-74

    属性说明：
        longitude (float): 航路点经度 (单位: 度)
            - 示例: 115.368621
            - 东经为正，西经为负

        latitude (float): 航路点纬度 (单位: 度)
            - 示例: 22.754909
            - 北纬为正，南纬为负

        control_strategy (int): 控制策略 (Byte)
            - 0: 定深航行（Constant Depth）
              保持固定深度航行到航路点

            - 1: 定高航行（Constant Altitude）
              保持离底高度航行到航路点
              适用于海底地形复杂的区域

        control_param (float): 控制参数 (Float)
            - 当 control_strategy = 0 时: 目标深度（米）
            - 当 control_strategy = 1 时: 离底高度（米）
            - 示例: 定深50m 或 定高30m

        motor_speed (int): 主电机转速 (Int16, RPM)
            - 到达此航路点时的推进器转速
            - 范围: -1500 ~ 1500 RPM
            - 负值表示反转，正值表示正转
            - 示例: 1000 RPM

        device_control (int): 设备控制位 (Byte, 8位位掩码)
            - 每个bit控制一个设备的开关状态
            - bit 0: 主推进器 (1=开, 0=关)
            - bit 1: 侧推进器
            - bit 2: 水平舵机
            - bit 3: 垂直舵机
            - bit 4: DVL
            - bit 5: 罗经
            - bit 6-7: 备用
            - 示例: 0x03 = 开启主推和侧推

    使用示例：
        >>> point = AutoFixedPoint()
        >>> point.longitude = 115.368621
        >>> point.latitude = 22.754909
        >>> point.control_strategy = 0  # 定深航行
        >>> point.control_param = 50.0  # 深度50m
        >>> point.motor_speed = 1000  # 1000 RPM
        >>> point.device_control = 0x03  # 开启主推和侧推
    """
    longitude: float = 0.0                   # Double, 经度 (度)
    latitude: float = 0.0                    # Double, 纬度 (度)
    control_strategy: int = 0                # Byte: 0=定深, 1=定高
    control_param: float = 0.0               # Float, 控制参数 (深度或高度, 单位:米)
    motor_speed: int = 0                     # Int16, 主电机转速 (RPM)
    device_control: int = 0                  # Byte, 设备控制位 (8-bit flags)


@dataclass
class TelemetryData:
    """
    AUV 遥测数据结构体

    本结构体包含了从 AUV 接收的完整遥测数据，占用145字节接收数据包的
    绝大部分字段。数据包括传感器读数、位置信息、电源状态、系统状态等。

    C# 源码参考：Form1.cs display() method, lines 603-1189

    数据字段说明：
    ============== 基本信息 ==============
        frame_number (int): 帧序号
            - 用于跟踪数据包顺序
            - 范围: 0-255, 循环

        auv_address (int): AUV地址
            - 1-3: AUV编号
            - 用于多AUV编队

        work_mode (int): 当前工作模式
            - 0: 仅发送
            - 1: 遥控
            - 2: 自主定点
            - 3: 自主定向
            - 4: 自主回航

    ============== 保护参数回显 ==============
        AUV回显当前使用的保护参数，用于确认控制指令生效

        depth_protect_1/2 (int): 深度保护参数 (UInt16, 米)
        bottom_protect_1/2 (int): 离底保护参数 (UInt16, 米)
        preset_time (int): 预设时间 (UInt16, ×0.1分钟)

    ============== 工作指令反馈 ==============
        work_instruction (int): 当前执行的工作指令 (Byte, 位掩码)
            - 指示AUV正在执行的指令
            - 0x11: 主推上电
            - 0x13: 侧推上电
            - 等等...

    ============== 电机状态反馈 ==============
        motor_speed1 (int): 主推进器转速 (Int16, RPM)
            - 范围: -1500 ~ 1500

        motor_speed2 (int): 侧推进器转速 (Int16, RPM)
            - 范围: -4000 ~ 4000

    ============== 舵角反馈 ==============
        所有舵角单位: ×0.1°, 范围: ±30° (±300)

        rudder_angle_lh (int): 左水平舵角 (Int16, ×0.1°)
        rudder_angle_rh (int): 右水平舵角 (Int16, ×0.1°)
        rudder_angle_uv (int): 上垂直舵角 (Int16, ×0.1°)
        rudder_angle_lv (int): 下垂直舵角 (Int16, ×0.1°)

        orientation_angle (int): 航向角 (UInt16, ×0.1°)
            - 范围: 0-3599 (0-359.9°)
            - 0 = 正北, 90 = 正东, 180 = 正南, 270 = 正西

    ============== 12个可调参数 ==============
        param1-4 (int): 高精度参数 (Int32, ×1,000,000)
            - 常用于GPS坐标
            - 或需要高精度的其他参数

        param5-8 (int): 中等精度参数 (Int16, ×10,000)
        param9-12 (int): 低精度参数 (Int16, ×1,000)

    ============== 传感器数据 ==============
        internal_pressure (float): 内部压力 (Float, ×0.001 psi)
            - 耐压壳体内部压力
            - 用于检测密封性

        internal_temp (int): 内部温度 (Byte, 有符号, °C)
            - 电子舱温度
            - 范围: -128 ~ +127°C

        depth (float): 深度 (Float, ×0.1 m)
            - AUV当前深度（相对于水面）
            - 示例: 50.5m

    ============== 导航数据 ==============
        compass_heading (float): 罗经航向 (Float, ×0.1°)
            - 电子罗经测量的航向角
            - 示例: 90.0° = 正东

        compass_pitch (float): 罗经俯仰角 (Float, ×0.1°)
            - 船体俯仰姿态
            - 正值 = 抬头, 负值 = 低头
            - 示例: 5.0° = 微微抬头

        compass_roll (float): 罗经横滚角 (Float, ×0.1°)
            - 船体横滚姿态
            - 正值 = 右倾, 负值 = 左倾
            - 示例: -2.0° = 微微左倾

        gps_heading (float): GPS航向 (Float, ×0.1°)
            - 基于GPS移动轨迹计算的航向
            - 仅在GPS移动时有效

        gps_speed (float): GPS对地速度 (Float, ×0.1 节)
            - 基于GPS测量的对地速度
            - 示例: 25.0 = 2.5节

        dv1_speed (float): DVL速度 (Float, ×0.1 节, 有符号)
            - 多普勒测速仪测量的对地速度
            - 正值 = 前进, 负值 = 后退

        altitude (float): 离底高度 (Float, ×0.1 m)
            - 高度计测量的离底距离
            - 示例: 30.5m = 离底30.5米

    ============== 位置数据 ==============
        dead_reck_lon (float): 推算航位经度 (Float, ×0.000001)
            - 基于DVL和罗经推算的经度
            - 在GPS失灵时使用

        dead_reck_lat (float): 推算航位纬度 (Float, ×0.000001)
            - 基于DVL和罗经推算的纬度

        gps_lon (float): GPS经度 (Float, ×0.000001)
            - GPS接收器提供的精确经度
            - 示例: 115.368621°

        gps_lat (float): GPS纬度 (Float, ×0.000001)
            - GPS接收器提供的精确纬度
            - 示例: 22.754909°

    ============== 电源数据 ==============
        total_voltage (float): 总电压 (Float, ×0.1 V)
            - 电池组总电压
            - 示例: 480.0 = 48.0V

        total_current (float): 总电流 (Float, ×0.1 A)
            - 当前总电流消耗
            - 示例: 125.0 = 12.5A

        soc (int): 荷电状态 (Byte, %)
            - State of Charge
            - 剩余电量百分比
            - 范围: 0-100%

        soh (int): 健康状态 (Byte, %)
            - State of Health
            - 电池健康度百分比
            - 范围: 0-100%

    ============== 电池详情 ==============
        cell_voltage_max (float): 最高单体电压 (Float, ×0.001 V)
            - 所有电芯中的最高电压
            - 用于电池均衡监控

        cell_voltage_min (float): 最低单体电压 (Float, ×0.001 V)
            - 所有电芯中的最低电压
            - 用于检测落后电芯

        cell_temp_max (int): 最高电芯温度 (Byte, °C)
            - 电芯温度最高值
            - 用于热管理

        cell_temp_min (int): 最低电芯温度 (Byte, °C)
            - 电芯温度最低值

    ============== 系统状态（位字段）=============
        device_power_status (int): 设备电源状态 (UInt32, 位掩码)
            - 每个bit对应一个设备的电源状态
            - bit 0: 主推进器 (1=开, 0=关)
            - bit 1: 侧推进器
            - bit 2-3: 水平舵机
            - bit 4-5: 垂直舵机
            - bit 6: DVL
            - bit 7: 罗经
            - 等等...

        operation_feedback (int): 运行反馈 (UInt32, 位掩码)
            - 指示各种操作的执行结果
            - bit 0: 任务开启成功
            - bit 1: 任务取消成功
            - 等等...

        task_status (int): 任务状态 (UInt32, 位掩码)
            - 当前任务执行状态
            - bit 0: 任务运行中
            - bit 1: 任务完成
            - bit 2: 任务失败
            - 等等...

    ============== 报警信息（位字段）=============
        system_alarm (int): 系统报警 (Byte, 位掩码)
            - bit 0: 内部漏水报警
            - bit 1: 外部漏水报警
            - bit 2: 温度报警
            - 等等...

        depth_alarm (int): 深度报警 (Byte, 位掩码)
            - bit 0: 超深报警1
            - bit 1: 超深报警2
            - 等等...

        bottom_alarm (int): 离底报警 (Byte, 位掩码)
            - bit 0: 离底过近报警1
            - bit 1: 离底过近报警2
            - 等等...

        timeout_alarm (int): 超时报警 (Byte)
        energy_alarm (int): 能量报警 (Byte)
        device_alarm (int): 设备报警 (Byte)
        battery_alarm (int): 电池报警 (Byte)

    使用示例：
        >>> telemetry = TelemetryData()
        >>> # 解析后访问字段
        >>> print(f"深度: {telemetry.depth:.1f}m")
        >>> print(f"航向: {telemetry.compass_heading:.1f}°")
        >>> print(f"GPS: {telemetry.gps_lat:.6f}°N, {telemetry.gps_lon:.6f}°E")
        >>> print(f"电池: {telemetry.soc}%")
        >>>
        >>> # 检查报警
        >>> if telemetry.system_alarm & 0x01:
        ...     print("内部漏水报警！")
    """
    # ========== 基本信息 ==========
    frame_number: int = 0                   # Byte: 帧序号 (0-255)
    auv_address: int = 0                    # Byte: AUV地址 (1-3)
    work_mode: int = 0                      # Byte: 工作模式 (0-4)

    # ========== 保护参数回显 ==========
    depth_protect_1: int = 0                # UInt16: 深度保护参数1 (m)
    depth_protect_2: int = 0                # UInt16: 深度保护参数2 (m)
    bottom_protect_1: int = 0               # UInt16: 离底保护参数1 (m)
    bottom_protect_2: int = 0               # UInt16: 离底保护参数2 (m)
    preset_time: int = 0                    # UInt16: 预设时间 (×0.1分钟)

    # ========== 工作指令反馈 ==========
    work_instruction: int = 0               # Byte: 工作指令 (位掩码)

    # ========== 电机和舵角反馈 ==========
    motor_speed1: int = 0                   # Int16: 主推进器转速 (RPM)
    motor_speed2: int = 0                   # Int16: 侧推进器转速 (RPM)
    rudder_angle_lh: int = 0                # Int16: 左水平舵角 (×0.1°)
    rudder_angle_rh: int = 0                # Int16: 右水平舵角 (×0.1°)
    rudder_angle_uv: int = 0                # Int16: 上垂直舵角 (×0.1°)
    rudder_angle_lv: int = 0                # Int16: 下垂直舵角 (×0.1°)
    orientation_angle: int = 0              # UInt16: 航向角 (×0.1°, 0-3599)

    # ========== 12个可调参数 ==========
    param1: int = 0                         # Int32, ×1,000,000
    param2: int = 0                         # Int32, ×1,000,000
    param3: int = 0                         # Int32, ×1,000,000
    param4: int = 0                         # Int32, ×1,000,000
    param5: int = 0                         # Int16, ×10,000
    param6: int = 0                         # Int16, ×10,000
    param7: int = 0                         # Int16, ×10,000
    param8: int = 0                         # Int16, ×10,000
    param9: int = 0                         # Int16, ×1,000
    param10: int = 0                        # Int16, ×1,000
    param11: int = 0                        # Int16, ×1,000
    param12: int = 0                        # Int16, ×1,000

    # ========== 传感器数据 ==========
    internal_pressure: float = 0.0          # 内部压力 (psi ×0.001)
    internal_temp: int = 0                  # 内部温度 (°C, signed byte)
    depth: float = 0.0                      # 深度 (m ×0.1)

    # ========== 导航数据 ==========
    compass_heading: float = 0.0            # 罗经航向 (° ×0.1)
    compass_pitch: float = 0.0              # 罗经俯仰角 (° ×0.1)
    compass_roll: float = 0.0               # 罗经横滚角 (° ×0.1)
    gps_heading: float = 0.0                # GPS航向 (° ×0.1)
    gps_speed: float = 0.0                  # GPS速度 (节 ×0.1)
    dv1_speed: float = 0.0                  # DVL速度 (节 ×0.1, signed)
    altitude: float = 0.0                   # 离底高度 (m ×0.1)

    # ========== 位置数据 ==========
    dead_reck_lon: float = 0.0              # 推算航位经度 (×0.000001)
    dead_reck_lat: float = 0.0              # 推算航位纬度 (×0.000001)
    gps_lon: float = 0.0                    # GPS经度 (×0.000001)
    gps_lat: float = 0.0                    # GPS纬度 (×0.000001)

    # ========== 电源数据 ==========
    total_voltage: float = 0.0              # 总电压 (V ×0.1)
    total_current: float = 0.0              # 总电流 (A ×0.1)
    soc: int = 0                            # 荷电状态 (%)
    soh: int = 0                            # 健康状态 (%)

    # ========== 电池详情 ==========
    cell_voltage_max: float = 0.0           # 最高单体电压 (V ×0.001)
    cell_voltage_min: float = 0.0           # 最低单体电压 (V ×0.001)
    cell_temp_max: int = 0                  # 最高电芯温度 (°C)
    cell_temp_min: int = 0                  # 最低电芯温度 (°C)

    # ========== 系统状态（位字段）==========
    device_power_status: int = 0            # 设备电源状态 (UInt32, 位掩码)
    operation_feedback: int = 0             # 运行反馈 (UInt32, 位掩码)
    task_status: int = 0                    # 任务状态 (UInt32, 位掩码)

    # ========== 报警信息（位字段）==========
    system_alarm: int = 0                   # 系统报警 (Byte, 位掩码)
    depth_alarm: int = 0                    # 深度报警 (Byte, 位掩码)
    bottom_alarm: int = 0                   # 离底报警 (Byte, 位掩码)
    timeout_alarm: int = 0                  # 超时报警 (Byte, 位掩码)
    energy_alarm: int = 0                   # 能量报警 (Byte, 位掩码)
    device_alarm: int = 0                   # 设备报警 (Byte, 位掩码)
    battery_alarm: int = 0                  # 电池报警 (Byte, 位掩码)


class GPSQueue:
    """
    GPS 轨迹队列

    本类用于存储和管理AUV的GPS轨迹历史数据，用于在地图上绘制
    航迹。使用双端队列实现，最多存储1000个GPS点，超过限制时
    自动丢弃最旧的点。

    C# 源码参考：Form1.cs Queue<PointF> Queue_GPS

    特性：
    - 最大容量: 1000个点
    - 自动丢弃旧数据（FIFO）
    - 线程不安全（多线程使用需加锁）
    - 高效的插入和查询操作

    使用场景：
    - 在地图上绘制AUV的历史轨迹
    - 记录航行路径供后续分析
    - 实现轨迹回放功能

    方法说明：
        __init__(max_size): 初始化队列
            - max_size: 最大容量，默认1000

        enqueue(longitude, latitude): 添加GPS点
            - longitude: 经度（度）
            - latitude: 纬度（度）
            - 自动处理满队列情况（删除最旧的点）

        get_all_points(): 获取所有点
            - 返回: List[(longitude, latitude)]
            - 不改变队列内容

        clear(): 清空所有点
            - 删除所有历史轨迹数据

        count(): 获取当前点数
            - 返回: int, 当前队列中的GPS点数量

    使用示例：
        >>> queue = GPSQueue(max_size=1000)
        >>>
        >>> # 添加GPS点
        >>> queue.enqueue(115.368621, 22.754909)
        >>> queue.enqueue(115.368722, 22.755010)
        >>>
        >>> # 获取所有点
        >>> points = queue.get_all_points()
        >>> for lon, lat in points:
        ...     print(f"GPS: {lat:.6f}°N, {lon:.6f}°E")
        >>>
        >>> # 检查队列大小
        >>> print(f"记录了 {queue.count()} 个GPS点")
        >>>
        >>> # 清空轨迹
        >>> queue.clear()

    线程安全：
        本类不是线程安全的。在多线程环境中使用时（例如：
        UDP接收线程添加数据，UI线程读取数据），需要使用
        threading.Lock() 进行同步。
    """
    def __init__(self, max_size=1000):
        """
        初始化GPS轨迹队列

        Args:
            max_size (int): 队列最大容量，默认1000个点
                           当队列满时，添加新点会自动删除最旧的点
        """
        self.queue = deque(maxlen=max_size)

    def enqueue(self, longitude: float, latitude: float):
        """
        添加GPS点到队列

        Args:
            longitude (float): 经度（度）
                              示例: 115.368621
            latitude (float): 纬度（度）
                             示例: 22.754909

        注意：
            - 如果队列已满，自动删除最旧的点
            - 坐标不进行有效性验证，调用者需确保数据正确
        """
        self.queue.append((longitude, latitude))

    def get_all_points(self) -> List[tuple]:
        """
        获取队列中所有GPS点

        Returns:
            List[tuple]: 所有GPS点的列表，格式为 [(经度, 纬度), ...]
                        示例: [(115.368621, 22.754909), ...]

        注意：
            - 返回的是列表的副本，修改返回列表不影响队列
            - 点的顺序从旧到新排列
        """
        return list(self.queue)

    def clear(self):
        """
        清空队列中的所有GPS点

        用途：
            - 开始新任务时清除旧轨迹
            - 重新记录航迹
        """
        self.queue.clear()

    def count(self) -> int:
        """
        获取队列中当前的GPS点数量

        Returns:
            int: GPS点数量，范围 0 到 max_size
        """
        return len(self.queue)
