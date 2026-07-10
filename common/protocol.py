"""AUV 共享协议常量与边界验证器 - 双端通信契约的单一真值源。

本模块定义了 AUV 系统中所有跨模块、跨进程的通信协议，包括：
1. Zenoh 发布/订阅主题路径定义（传感器、控制命令、可视化等）
2. 有效负载键名（KEY_* 常量）
3. 二进制协议框架（$CKTH 下行、$AUV 上行）定义
4. 数据合法性验证（validate_sensor_payload、validate_control_payload）
5. 编码/解码函数（build_* 和 parse_* 系列）

核心特性：
- 所有符号仅使用标准库，可被仿真侧（sim_holoocean）和决策侧（brain_linux）直接导入
- 无运行时耦合：协议定义与具体实现无关
- DLT 1278 合规性：传感器数据必须包含必需字段（位置、RPY、深度等）
- 坐标系统一：所有位置/速度数据使用 NED（北东地）坐标系

典型使用流程：
1. 仿真侧通过 enrich_meta() 为传感器负载添加时间戳和步数
2. validate_sensor_payload() 在通信边界检查数据合法性
3. 二进制协议函数用于与实物 AUV 通信（Protocol UDP）
4. 控制命令通过 normalize_control_command() 正则化并进行边界检查

作者：AUV_Master_Project 核心协议组
版本：1.0（2026 年 4 月）
"""

from __future__ import annotations

import math
import struct
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Sequence

from .enums import ArbiterMode, ArbiterSource, AutoState, DenyReason
from .physics import clamp_rudder_deg, clamp_thrust_percent

# =============================================================================
# Zenoh 主题路径常量 - 单一真值源（跨仿真、决策、可视化端）
# =============================================================================
# 所有 Zenoh 主题名称在此统一定义，禁止在其他模块中硬编码路径。
# 遵守命名约定：rt/auv/{domain}/{subdomain}，其中：
#  - domain: control（控制）/ telemetry（遥测）/ sensors（传感）/ visual（可视）
#  - subdomain: 设备或功能标识符
# 修改主题名称时必须同步更新所有订阅方（仿真、决策、可视化）

Z_PATH_CMD_VEL = "rt/auv/control/cmd_vel"  # 控制命令：Twist 消息（线速度、角速度）
Z_PATH_PC_CMD_RAW = "rt/pc/cmd_raw"  # PC 原始控制命令（备用）
Z_PATH_AUV_TELEMETRY = "rt/auv/telemetry"  # AUV 遥测数据（电压、电流、温度等）
Z_PATH_AUV_VIZ_INTERNAL = "rt/auv/viz/internal"  # 仅用于可视化的内部状态

# 死推进状态专用（仅在无外部定位下使用）
Z_PATH_AUV_STATE_RAW_DR = "rt/auv/state/raw_dr"  # 原始死推进位置估计（用于 Foxglove 预显示）

# 传感器数据主题（所有传感器输出需在此定义）
Z_PATH_GROUND_TRUTH = "rt/auv/sensors/ground_truth"  # 地面真值（仅仿真侧，包含位置、RPY、最近电缆点）
Z_PATH_IMU = "rt/auv/sensors/imu"  # 惯性测量单元（加速度、角速度 NED）
Z_PATH_DVL = "rt/auv/sensors/dvl"  # 多普勒速度计（水体相对速度 NED）
Z_PATH_DEPTH = "rt/auv/sensors/depth"  # 深度传感器
Z_PATH_ALTITUDE = "rt/auv/sensors/altitude"  # 离底高度传感器
Z_PATH_MAGNETIC = "rt/auv/sensors/magnetic"  # 磁传感器（地磁场）
Z_PATH_SONAR = "rt/auv/sensors/sonar"  # 声纳传感器
Z_PATH_FORWARD_SONAR = "rt/auv/sensors/forward_sonar"  # 前视声呐地形预瞄

# 可视化主题（用于 Foxglove 3D 场景、轨迹显示等）
Z_PATH_SEABED_CLOUD = "rt/auv/visual/seabed_cloud"  # 海床点云（来自声纳或视觉）
Z_PATH_CABLE_MARKER = "rt/auv/visual/cable_marker"  # 检测到的电缆标记点
Z_PATH_TRUTH_POSE = "rt/auv/visual/truth_pose"  # 地面真值位姿显示
Z_PATH_HISTORY_TRAIL = "rt/auv/visual/history_trail"  # 行进轨迹历史
Z_PATH_VIEW_RANGE = "rt/auv/visual/view_range"  # 可见范围圆锥
Z_PATH_MOCK_AMD_TIME = "rt/auv/mock_amd/time"  # Mock AMD 时间戳（用于时间同步验证）

# =============================================================================
# 有效负载键名常量 - 数据字典中的标准化键
# =============================================================================
# 这些常量定义了所有 JSON/dict 形式的有效负载中使用的键名。
# 策略：优先使用这些常量，不要在代码中硬编码字符串。

# 通用元数据键（所有消息可选）
KEY_STEP = "step"  # 仿真步数
KEY_SIM_TIME = "sim_time"  # 仿真时间（秒）
KEY_TS = "ts"  # 系统时间戳（Unix 秒）

# 位置与姿态（NED 坐标系）
KEY_POSITION_NED = "position_ned"  # 位置 [x, y, z] (m)，z 正向下（深度）
KEY_RPY_NED = "rpy_ned"  # 欧拉角（横滚-pitch-yaw）[rad]
KEY_CABLE_CLOSEST_NED = "cable_closest_ned"  # 最近电缆点位置 [m]
KEY_CABLE_DISTANCE_M = "cable_distance_m"  # 到最近电缆的距离 (m)

# 惯性传感器（IMU）
KEY_ACCEL_NED = "accel_ned"  # 加速度 [m/s²]，NED 坐标系
KEY_GYRO_NED = "gyro_ned"  # 角速度 [rad/s]，NED 坐标系

# 速度（来自 DVL 或车体估计）
KEY_VEL_NED = "vel_ned"  # 速度 [m/s]，NED 坐标系

# 深度与结构
KEY_DEPTH_M = "depth_m"  # 深度 (m)
KEY_ALTITUDE_M = "altitude_m"  # 离底高度 (m)
KEY_CONFIDENCE = "confidence"  # 测量置信度 (0-1)
KEY_LEAK_LEVEL = "leak_level"  # 漏水等级
KEY_TOTAL_VOLTAGE_V = "total_voltage_v"  # 总电压 (V)

# 磁场传感器
KEY_B_NED = "B_ned"  # 磁场向量 [T]，NED 坐标系
KEY_B_NORM = "B_norm"  # 磁场模值 (T)

# 声纳与可视化数据
KEY_SONAR_BINS = "bins"  # 声纳扫描数据 (bin 数组)
KEY_SLOPE = "slope"  # 前视声呐估计的地形坡度 dz/dx
KEY_LOOKAHEAD_M = "lookahead_m"  # 前视距离 (m)
KEY_POINTS_NED = "points_ned"  # 3D 点集 [[x,y,z], ...]
KEY_TRAIL_NED = "trail_ned"  # 轨迹点集 [[x,y,z], ...]
KEY_CENTER_NED = "center_ned"  # 圆心位置 [x,y,z]
KEY_RADIUS_M = "radius_m"  # 半径 (m)
KEY_HEIGHT_M = "height_m"  # 高度 (m)

# 控制命令键（推进器与舵面控制）
KEY_COMMAND = "command"  # 电容器控制命令 [right, top, left, bottom, thrust]
KEY_SOURCE = "source"  # 命令来源（remote / autonomous）
KEY_VALID = "valid"  # 命令有效标志
KEY_HEALTHY = "healthy"  # 系统健康标志
KEY_NOTE = "note"  # 注记（诊断信息）
KEY_RIGHT = "right"  # 右舵叶偏角 (°)
KEY_TOP = "top"  # 上舵叶偏角 (°)
KEY_LEFT = "left"  # 左舵叶偏角 (°)
KEY_BOTTOM = "bottom"  # 下舵叶偏角 (°)
KEY_THRUST = "thrust"  # 推力百分比 (-100~100 %)

# 二进制协议特定字段
KEY_FRAME_NUMBER = "frame_number"  # 数据帧序号
KEY_OBJ_ADDRESS = "obj_address"  # 目标地址（下行）
KEY_AUV_ADDRESS = "auv_address"  # AUV 地址（上行）
KEY_CONTROL_MODE_BYTE = "control_mode_byte"  # 控制模式字节（与实物 AUV 定义一致）
KEY_WORK_INSTRUCTION = "work_instruction"  # 工作指令字节
KEY_ORIENTATION_DEG = "orientation_deg"  # 方向角 (°)
KEY_MAIN_MOTOR_RPM = "main_motor_rpm"  # 主推进马达转速 (RPM)
KEY_SIDE_MOTOR_RPM = "side_motor_rpm"  # 侧推进马达转速 (RPM)
KEY_DEPTH_PROTECT_PARAMS = "depth_protect_params"  # 深度保护参数 [min, max]
KEY_BOTTOM_PROTECT_PARAMS = "bottom_protect_params"  # 底部保护参数 [min, max]
KEY_PRESET_TIME_TENTHS_MIN = "preset_time_tenths_min"  # 预设时间（0.1 分钟单位）
KEY_SPARE_PARAMS = "spare_params"  # 备用参数对
KEY_PARAMETERS = "parameters"  # 扩展参数集合（12 个值）

# 仲裁与控制状态键
KEY_ACTIVE_ARBITER = "active_arbiter"  # 当前活跃的仲裁器（REMOTE / AUTONOMOUS）
KEY_ARBITER_SOURCE = "arbiter_source"  # 仲裁数据来源
KEY_AUTO_STATE = "auto_state"  # 自主控制状态（LOCKED / REQUESTING / ACTIVE / DENIED）
KEY_DENY_REASON = "deny_reason"  # 自主被拒原因
KEY_TELEMETRY_FRESHNESS_MS = "telemetry_freshness_ms"  # 遥测数据新鲜度 (ms)
KEY_STATE_SOURCE = "state_source"  # 状态来源（仿真 / 实物）
KEY_MOCK_AMD_TIMESTAMP_US = "mock_amd_timestamp_us"  # Mock AMD 时间戳 (微秒)
KEY_TARGET_DEPTH_M = "target_depth_m"  # 目标深度 (m)

# =============================================================================
# 二进制协议字节偏移量 - Para1-Para12 可调参数字段位置
# =============================================================================
# 下行协议 ($CKTH, 72 字节) 与上行协议 ($AUV, 145 字节) 中的参数字段偏移。
# 这 12 个参数用于实时调试和在水通信。结构：
#  - Para1-4: 32 位整数 (int32)
#  - Para5-12: 16 位整数 (int16)

# 下行协议 ($CKTH) 中的参数字段位置
PROTOCOL_DOWNLINK_PARA1_OFFSET = 37  # offset +37: Para1 (int32)
PROTOCOL_DOWNLINK_PARA2_OFFSET = 41  # offset +41: Para2 (int32)
PROTOCOL_DOWNLINK_PARA3_OFFSET = 45  # offset +45: Para3 (int32)
PROTOCOL_DOWNLINK_PARA4_OFFSET = 49  # offset +49: Para4 (int32)
PROTOCOL_DOWNLINK_PARA5_OFFSET = 53  # offset +53: Para5 (int16)
PROTOCOL_DOWNLINK_PARA6_OFFSET = 55  # offset +55: Para6 (int16)
PROTOCOL_DOWNLINK_PARA7_OFFSET = 57  # offset +57: Para7 (int16)
PROTOCOL_DOWNLINK_PARA8_OFFSET = 59  # offset +59: Para8 (int16)
PROTOCOL_DOWNLINK_PARA9_OFFSET = 61  # offset +61: Para9 (int16)
PROTOCOL_DOWNLINK_PARA10_OFFSET = 63  # offset +63: Para10 (int16)
PROTOCOL_DOWNLINK_PARA11_OFFSET = 65  # offset +65: Para11 (int16)
PROTOCOL_DOWNLINK_PARA12_OFFSET = 67  # offset +67: Para12 (int16)

# 上行协议 ($AUV) 中的参数字段位置
PROTOCOL_UPLINK_PARA1_OFFSET = 40  # offset +40: Para1 (int32)
PROTOCOL_UPLINK_PARA2_OFFSET = 44  # offset +44: Para2 (int32)
PROTOCOL_UPLINK_PARA3_OFFSET = 48  # offset +48: Para3 (int32)
PROTOCOL_UPLINK_PARA4_OFFSET = 52  # offset +52: Para4 (int32)
PROTOCOL_UPLINK_PARA5_OFFSET = 56  # offset +56: Para5 (int16)
PROTOCOL_UPLINK_PARA6_OFFSET = 58  # offset +58: Para6 (int16)
PROTOCOL_UPLINK_PARA7_OFFSET = 60  # offset +60: Para7 (int16)
PROTOCOL_UPLINK_PARA8_OFFSET = 62  # offset +62: Para8 (int16)
PROTOCOL_UPLINK_PARA9_OFFSET = 64  # offset +64: Para9 (int16)
PROTOCOL_UPLINK_PARA10_OFFSET = 66  # offset +66: Para10 (int16)
PROTOCOL_UPLINK_PARA11_OFFSET = 68  # offset +68: Para11 (int16)
PROTOCOL_UPLINK_PARA12_OFFSET = 70  # offset +70: Para12 (int16)

# 控制键组合（用于验证完整性）
CONTROL_KEYS = (KEY_RIGHT, KEY_TOP, KEY_LEFT, KEY_BOTTOM, KEY_THRUST)  # 5 元控制向量

# =============================================================================
# 二进制 AUV 协议框架常量 - 与水下实物 AUV 通信的协议定义
# =============================================================================
# 协议格式：
#   下行 ($CKTH) 72 字节：PC → AUV，包含推进、舵面、推进马达 RPM 等控制命令
#   上行 ($AUV) 145 字节：AUV → PC，包含位置、深度、姿态、电源等遥测数据
# 
# 特点：
#   - 大端字节序 (big-endian)
#   - 固定帧头和帧尾
#   - 字节和校验（低 8 位）
#   - 所有角度单位 0.1° 存储（乘以 10 后转 int16 存储）
#   - 经纬度单位 10^-6 度存储

PROTOCOL_DOWNLINK_HEADER = b"$CKTH"  # 下行帧头：$CKTH (5 字节)
PROTOCOL_UPLINK_HEADER = bytes((0x24, 0x41, 0x55, 0x56, 0x91))  # 上行帧头：$AUV\x91 (5 字节)
PROTOCOL_FRAME_TAIL = bytes((0xFF, 0xFF))  # 帧尾（下行、上行通用，2 字节）

PROTOCOL_DOWNLINK_SIZE = 72  # 下行帧总长度（字节）
PROTOCOL_UPLINK_SIZE = 145  # 上行帧总长度（字节）

# 校验和字段位置（都是帧长度 - 3 的位置，即倒数第三个字节）
PROTOCOL_DOWNLINK_CHECKSUM_INDEX = 69  # 下行校验和：offset 69（在帧尾前）
PROTOCOL_UPLINK_CHECKSUM_INDEX = 142  # 上行校验和：offset 142（在帧尾前）

# 默认 RPM 到推力百分比的转换系数，用于将协议中的 RPM 值转换为实际推力百分比（仅供调试使用，实际控制算法中不应依赖此转换）
DEFAULT_MAIN_MOTOR_RPM_SCALE = 15.0  # 主推进马达：15 RPM/% (推力百分比 = RPM / 15)
DEFAULT_SIDE_MOTOR_RPM_SCALE = 1.0  # 侧推进马达：1 RPM/% (备用)


@dataclass(frozen=True)
class ProtocolDownlinkState:
    """
    @brief 解码后的下行控制命令状态（$CKTH 协议）
    
    @details
    表示从 PC 下发给水下 AUV 的 72 字节控制帧（$CKTH）解码后的工程量形式。
    字段都是工程单位（角度用度数、推力用百分比、RPM 用转速），已从二进制格式转换。
    
    用途：
      1. 二进制通信时：parse_downlink_packet() 的返回值
      2. 数据审计：记录发送给 AUV 的确切控制状态
      3. 协议转换：兼容旧协议与新基于 ROS2 的控制
    
    关键字段：
      - frame_number: 帧序号（0-255 循环），用于检测数据丢失
      - control_mode_byte: 与实物 AUV 的模式字节（0x01=遥控, 0xEE=自主）
      - {right,top,left,bottom}_fin_deg: 舵叶偏角 (度数)，范围 ±30°
      - thrust_percent: 推力百分比 (-100~100)，对应主推进马达转速
      - parameters: 12 元参数组，用于在水调试 PID 和算法参数
    
    @note 所有角度单位为度数（°），单精度存储时以 0.1° 为最小单位
    """

    frame_number: int
    obj_address: int
    control_mode_byte: int
    work_instruction: int
    right_fin_deg: float
    top_fin_deg: float
    left_fin_deg: float
    bottom_fin_deg: float
    thrust_percent: float
    main_motor_rpm: int
    side_motor_rpm: int
    orientation_deg: float
    depth_protect_params: tuple[int, int]
    bottom_protect_params: tuple[int, int]
    preset_time_tenths_min: int
    spare_params: tuple[int, int]
    parameters: tuple[int, ...]
    mock_amd_timestamp_us: int = 0
    target_depth_m: float = 0.0


@dataclass(frozen=True)
class ProtocolUplinkTelemetry:
    """
    @brief 解码后的上行遥测数据状态（$AUV 协议）
    
    @details
    表示从水下 AUV 上发的 145 字节遥测帧（$AUV\x91）解码后的工程量形式。
    包含位置、姿态、深度、电源、警告等实时诊断数据。
    
    用途：
      1. 二进制通信时：parse_uplink_packet() 的返回值
      2. 状态评估：监控 AUV 健康与运行状态
      3. 控制反馈：供决策循环使用（仅上行数据确认时）
    
    关键字段：
      - frame_number / auv_address: 帧序号与 AUV 地址
      - {heading,pitch,roll}_deg: 姿态角 (度数)
      - depth_m: 深度 (m)
      - {total_voltage_v,total_current_a,soc,soh}: 电源状态
      - {gps,dvl,dead_reckoning}_{lon,lat,speed}: 位置估计与速度
      - {device_power_status, operation_feedback, task_status}: 状态字节
      - {depth_alarm, bottom_alarm, system_alarm}: 告警标志
    
    坐标系统：
      - heading_deg: 相对北 (0~360°)
      - pitch/roll_deg: 相对水平面（负值为下俯/左倾）
      - depth_m: 正值表示水下深度
    
    @note 所有角度单位为度数（°）；经纬度精度 10^-6 度；所有浮点数工程量
    """

    frame_number: int
    auv_address: int
    control_mode_byte: int
    work_instruction: int
    main_motor_rpm: int
    side_motor_rpm: int
    right_fin_deg: float
    top_fin_deg: float
    left_fin_deg: float
    bottom_fin_deg: float
    orientation_deg: float
    internal_pressure_psi: float
    internal_temp_c: int
    depth_m: float
    heading_deg: float
    pitch_deg: float
    roll_deg: float
    gps_heading_deg: float
    gps_speed_mps: float
    dvl_speed_mps: float
    altitude_m: float
    dead_reckoning_lon_deg: float
    dead_reckoning_lat_deg: float
    gps_lon_deg: float
    gps_lat_deg: float
    total_voltage_v: float
    total_current_a: float
    soc: int
    soh: int
    device_power_status: int
    operation_feedback: int
    task_status: int
    system_alarm: int
    depth_alarm: int
    bottom_alarm: int
    # DVL Body Frame 三轴速度 (m/s)，从 Para5/6/7 解析
    dvl_body_x_mps: float = 0.0
    dvl_body_y_mps: float = 0.0
    dvl_body_z_mps: float = 0.0
    # IMU 三轴角速度 (rad/s)，从 Para8/9/10 解析
    gyro_x_rps: float = 0.0
    gyro_y_rps: float = 0.0
    gyro_z_rps: float = 0.0

REQUIRED_BY_TOPIC: dict[str, tuple[str, ...]] = {
    Z_PATH_GROUND_TRUTH: (KEY_POSITION_NED, KEY_RPY_NED, KEY_CABLE_CLOSEST_NED, KEY_CABLE_DISTANCE_M),
    Z_PATH_IMU: (KEY_ACCEL_NED, KEY_GYRO_NED),
    Z_PATH_DVL: (KEY_VEL_NED,),
    Z_PATH_DEPTH: (KEY_DEPTH_M,),
    Z_PATH_ALTITUDE: (KEY_ALTITUDE_M,),
    Z_PATH_MAGNETIC: (KEY_B_NED, KEY_B_NORM),
    Z_PATH_SONAR: (KEY_SONAR_BINS,),
    Z_PATH_FORWARD_SONAR: (KEY_SLOPE, KEY_LOOKAHEAD_M),
    Z_PATH_SEABED_CLOUD: (KEY_POINTS_NED,),
    Z_PATH_CABLE_MARKER: (KEY_POINTS_NED,),
    Z_PATH_TRUTH_POSE: (KEY_POSITION_NED, KEY_RPY_NED),
    Z_PATH_HISTORY_TRAIL: (KEY_TRAIL_NED,),
    Z_PATH_VIEW_RANGE: (KEY_CENTER_NED, KEY_RADIUS_M, KEY_HEIGHT_M),
}
"""
@brief 各 Zenoh 主题的必需字段映射表 - 用于 validate_sensor_payload() 检查

@details
这个字典定义了每个传感器主题必须包含的键名。任何发布到 Zenoh 的消息
若缺少此处定义的必需字段，会导致验证失败。

用途：
  1. 数据質量检查：确保传感器数据完整性（DLT 1278 合规）
  2. 接口契约：明确定义仿真端 → 决策端的数据格式期望
  3. 自动化测试：产生测试用例和 Mock 数据

修改策略：
  - 若新增传感器，添加相应的 (Z_PATH_*, (KEY_*, ...)) 条目
  - 若修改存在的主题，同时更新此表和所有订阅方代码
  - 禁止删除现有条目（可能破坏后向兼容）
"""


def _is_number(value: Any) -> bool:
    """检查值是否为数字（int 或 float，但不包括 bool）"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_number_list(value: Any, *, length: int | None = None) -> bool:
    """
    检查值是否为数字列表。
    
    @param value 待检查值
    @param length 期望的列表长度（若为 None 则不检查）
    @return True 表示这是一个数字列表，且长度符合要求
    """
    if not isinstance(value, list):
        return False
    if length is not None and len(value) != length:
        return False
    return all(_is_number(v) for v in value)


def _is_point_list(value: Any) -> bool:
    """
    检查值是否为 3D 点集（list[list[3]]）。
    
    @param value 待检查值
    @return True 表示这是一个 3D 点列表
    """
    if not isinstance(value, list):
        return False
    return all(_is_number_list(point, length=3) for point in value)


def _missing_keys(payload: dict[str, Any], required: Iterable[str]) -> list[str]:
    """
    找出 payload 中缺少的必需键。
    
    @param payload 数据字典
    @param required 必需键的列表
    @return 缺少的键名列表
    """
    return [k for k in required if k not in payload]


def _enum_value(value: Enum | str | None) -> str | None:
    """
    将枚举或字符串值转换为字符串形式，用于 JSON 序列化。
    
    @param value 枚举、字符串或 None
    @return 如果为 Enum，返回其 value 字符串形式；否则返回原值字符串；None 则返回 None
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def enrich_meta(payload: dict[str, Any], *, step: int, sim_time: float, ts: float | None = None) -> dict[str, Any]:
    """
    @brief 为传感器/状态有效负载附加通用元数据字段
    
    @param [in,out] payload 输入字典（会被原地修改）
    @param [in] step 仿真步数（整数序号）
    @param [in] sim_time 仿真时间（秒）
    @param [in] ts 系统时间戳（可选，默认为当前 time.time()）
    
    @return 返回修改后的同一个字典对象（直接返回 payload 引用）
    
    @details
    该函数在模块化的 Zenoh 发布流程中使用，为每条消息自动注入：
      - KEY_STEP: 当前仿真步数
      - KEY_SIM_TIME: 当前仿真时间
      - KEY_TS: 发送时的系统时间戳
    
    用途：
      1. 时间同步与事件追踪：支持离线分析
      2. 步数检测：识别消息丢失与乱序
      3. 系统延迟计算：(ts - sim_time) 反映从仿真到发布的处理延迟
    
    @note 此函数直接修改 dict 原对象，不创建副本（性能考虑）
    @warning ts 若为 None，自动调用 time.time()，注意多线程竞态条件
    """
    payload[KEY_STEP] = int(step)
    payload[KEY_SIM_TIME] = float(sim_time)
    payload[KEY_TS] = float(time.time() if ts is None else ts)
    return payload


def validate_sensor_payload(topic: str, payload: Any) -> tuple[bool, list[str]]:
    """
    @brief 在通信边界验证传感器有效负载的形状和数据类型
    
    @param [in] topic Zenoh 主题名称（Z_PATH_* 常量之一）
    @param [in] payload 待验证的有效负载（应为 dict）
    
    @return (ok, errors) 元组：
      - ok: bool，True 表示所有字段有效
      - errors: list[str]，错误信息列表（为空表示无错误）
    
    @details
    本函数在 Zenoh 订阅侧执行，确保接收到的数据符合协议规范（DLT 1278 合规）。
    验证内容包括：
      1. payload 必须是 dict 类型
      2. 必需字段检查（由 REQUIRED_BY_TOPIC 定义）
      3. 向量/标量数据格式检查：
         - 位置/RPY/加速度等必须是 3 元数字列表
         - 深度/B_norm 等必须是单个数字
         - 点云序列必须是 list[list[3]]
      4. 元数据字段（KEY_STEP, KEY_SIM_TIME 等）的类型检查
    
    验证流程：
      - 若 topic 不在 REQUIRED_BY_TOPIC 中，返回错误"unsupported topic"
      - 若缺少必需字段，报告 missing keys
      - 若类型不匹配，逐字段报告具体错误
    
    用法：
      ```python
      ok, errors = validate_sensor_payload(Z_PATH_IMU, {
          "accel_ned": [0.1, 0.2, 9.8],
          "gyro_ned": [0.01, 0.02, 0.03],
          "step": 42,
          "sim_time": 21.5
      })
      if not ok:
          logger.error(f"IMU 数据验证失败: {errors}")
      ```
    
    @note 本函数设计轻量级，用于运行时频繁调用（每个 Zenoh 消息）
    @warning 验证失败不会抛异常，由调用方决定是否降级处理
    """
    errors: list[str] = []

    if not isinstance(payload, dict):
        return False, ["payload must be a dict"]

    required = REQUIRED_BY_TOPIC.get(topic)
    if required is None:
        return False, [f"unsupported topic: {topic}"]

    # DLT 1278-oriented traceability: critical telemetry fields must be explicit.
    missing = _missing_keys(payload, required)
    if missing:
        errors.append(f"missing keys: {missing}")

    if topic == Z_PATH_GROUND_TRUTH:
        if KEY_POSITION_NED in payload and not _is_number_list(payload[KEY_POSITION_NED], length=3):
            errors.append("position_ned must be list[3] of numbers")
        if KEY_RPY_NED in payload and not _is_number_list(payload[KEY_RPY_NED], length=3):
            errors.append("rpy_ned must be list[3] of numbers")
        if KEY_CABLE_CLOSEST_NED in payload and not _is_number_list(payload[KEY_CABLE_CLOSEST_NED], length=3):
            errors.append("cable_closest_ned must be list[3] of numbers")
        if KEY_CABLE_DISTANCE_M in payload and not _is_number(payload[KEY_CABLE_DISTANCE_M]):
            errors.append("cable_distance_m must be a number")

    elif topic == Z_PATH_IMU:
        if KEY_ACCEL_NED in payload and not _is_number_list(payload[KEY_ACCEL_NED], length=3):
            errors.append("accel_ned must be list[3] of numbers")
        if KEY_GYRO_NED in payload and not _is_number_list(payload[KEY_GYRO_NED], length=3):
            errors.append("gyro_ned must be list[3] of numbers")

    elif topic == Z_PATH_DVL:
        if KEY_VEL_NED in payload and not _is_number_list(payload[KEY_VEL_NED], length=3):
            errors.append("vel_ned must be list[3] of numbers")

    elif topic == Z_PATH_DEPTH:
        if KEY_DEPTH_M in payload and not _is_number(payload[KEY_DEPTH_M]):
            errors.append("depth_m must be a number")

    elif topic == Z_PATH_ALTITUDE:
        if KEY_ALTITUDE_M in payload and not _is_number(payload[KEY_ALTITUDE_M]):
            errors.append("altitude_m must be a number")

    elif topic == Z_PATH_MAGNETIC:
        if KEY_B_NED in payload and not _is_number_list(payload[KEY_B_NED], length=3):
            errors.append("B_ned must be list[3] of numbers")
        if KEY_B_NORM in payload and not _is_number(payload[KEY_B_NORM]):
            errors.append("B_norm must be a number")

    elif topic == Z_PATH_SONAR:
        if KEY_SONAR_BINS in payload and not _is_number_list(payload[KEY_SONAR_BINS]):
            errors.append("bins must be list of numbers")

    elif topic == Z_PATH_FORWARD_SONAR:
        if KEY_SLOPE in payload and not _is_number(payload[KEY_SLOPE]):
            errors.append("slope must be a number")
        if KEY_LOOKAHEAD_M in payload and not _is_number(payload[KEY_LOOKAHEAD_M]):
            errors.append("lookahead_m must be a number")

    elif topic == Z_PATH_SEABED_CLOUD:
        if KEY_POINTS_NED in payload and not _is_point_list(payload[KEY_POINTS_NED]):
            errors.append("points_ned must be list[list[3] of numbers]")

    elif topic == Z_PATH_CABLE_MARKER:
        if KEY_POINTS_NED in payload and not _is_point_list(payload[KEY_POINTS_NED]):
            errors.append("points_ned must be list[list[3] of numbers]")

    elif topic == Z_PATH_TRUTH_POSE:
        if KEY_POSITION_NED in payload and not _is_number_list(payload[KEY_POSITION_NED], length=3):
            errors.append("position_ned must be list[3] of numbers")
        if KEY_RPY_NED in payload and not _is_number_list(payload[KEY_RPY_NED], length=3):
            errors.append("rpy_ned must be list[3] of numbers")

    elif topic == Z_PATH_HISTORY_TRAIL:
        if KEY_TRAIL_NED in payload and not _is_point_list(payload[KEY_TRAIL_NED]):
            errors.append("trail_ned must be list[list[3] of numbers]")

    elif topic == Z_PATH_VIEW_RANGE:
        if KEY_CENTER_NED in payload and not _is_number_list(payload[KEY_CENTER_NED], length=3):
            errors.append("center_ned must be list[3] of numbers")
        if KEY_RADIUS_M in payload and not _is_number(payload[KEY_RADIUS_M]):
            errors.append("radius_m must be a number")
        if KEY_HEIGHT_M in payload and not _is_number(payload[KEY_HEIGHT_M]):
            errors.append("height_m must be a number")

    if KEY_STEP in payload and not isinstance(payload[KEY_STEP], int):
        errors.append("step must be int")
    if KEY_SIM_TIME in payload and not _is_number(payload[KEY_SIM_TIME]):
        errors.append("sim_time must be a number")
    if KEY_TS in payload and not _is_number(payload[KEY_TS]):
        errors.append("ts must be a number")

    return len(errors) == 0, errors


def normalize_control_command(payload: Any) -> dict[str, float]:
    """
    @brief 正则化控制命令输入为统一的 dict[str, float] 形式，并执行推进/舵叶边界检查
    
    @param [in] payload 控制命令输入，支持多种格式：
      - dict with "command" 键: {"command": [right, top, left, bottom, thrust]}
      - 完整 dict: {"right": ..., "top": ..., "left": ..., "bottom": ..., "thrust": ...}
      - 列表/元组: [right, top, left, bottom, thrust]
    
    @return dict[str, float]，规范化后的控制向量，键为 KEY_RIGHT 等常量
    
    @details
    该函数是所有控制命令的入口点，执行三层处理：
      1. 格式匹配：识别输入格式（dict/list/tuple）
      2. 正则化：统一提取 [right, top, left, bottom, thrust] 五元向量
      3. 边界检查：使用 physics.clamp_*() 函数饱和到有效范围
        - 舵叶: ±30° (调用 clamp_rudder_deg)
        - 推力: -100~100% (调用 clamp_thrust_percent)
    
    异常处理：
      - 列表长度不等于 5: ValueError
      - 缺少必需的 ctrl 键: ValueError
      - 值非数字: ValueError
    
    用法示例：
      ```python
      # 格式 1: 列表
      cmd = normalize_control_command([0.0, 10.0, 0.0, -10.0, 50.0])
      # 格式 2: 字典
      cmd = normalize_control_command({
          "right": 5.0, "top": 10.0, "left": -5.0, "bottom": -10.0, "thrust": 50.0
      })
      # 格式 3: ROS2 Twist 兼容格式
      cmd = normalize_control_command({"command": [0, 0, 0, 0, 100]})
      ```
    
    @note 返回值总是 float，NaN 或 infinity 会被 clamp_* 处理为边界值
    @warning 不检查返回值的物理合理性（如加速度梯度），仅做边界防护
    """
    cmd: Any

    if isinstance(payload, dict) and KEY_COMMAND in payload:
        cmd = payload[KEY_COMMAND]
    else:
        cmd = payload

    if isinstance(cmd, (list, tuple)):
        if len(cmd) != 5:
            raise ValueError("command list length must be 5")
        right, top, left, bottom, thrust = cmd
    elif isinstance(cmd, dict):
        missing = _missing_keys(cmd, CONTROL_KEYS)
        if missing:
            raise ValueError(f"missing control keys: {missing}")
        right = cmd[KEY_RIGHT]
        top = cmd[KEY_TOP]
        left = cmd[KEY_LEFT]
        bottom = cmd[KEY_BOTTOM]
        thrust = cmd[KEY_THRUST]
    else:
        raise ValueError("unsupported control payload format")

    values = [right, top, left, bottom, thrust]
    if not all(_is_number(v) for v in values):
        raise ValueError("control values must be numeric")

    right = _sanitize_float(float(right))
    top = _sanitize_float(float(top))
    left = _sanitize_float(float(left))
    bottom = _sanitize_float(float(bottom))
    thrust = _sanitize_float(float(thrust))

    return {
        KEY_RIGHT: float(clamp_rudder_deg(right)),
        KEY_TOP: float(clamp_rudder_deg(top)),
        KEY_LEFT: float(clamp_rudder_deg(left)),
        KEY_BOTTOM: float(clamp_rudder_deg(bottom)),
        KEY_THRUST: float(clamp_thrust_percent(thrust)),
    }


def validate_control_payload(payload: Any) -> tuple[bool, list[str]]:
    """
    @brief 验证并正则化控制有效负载，确保执行器安全边界
    
    @param [in] payload 控制有效负载
    
    @return (ok, errors) 元组：
      - ok: bool，True 表示有效
      - errors: list[str]，错误信息列表
    
    @details
    包装 normalize_control_command() 的异常捕获版本，运行时安全性更高。
    捕获所有 Exception（设计上宽泛），返回错误列表而非抛异常。
    
    使用场景：
      1. 遥控/自主模式切换时的验证
      2. Zenoh 命令订阅的防守性检查
      3. 实物 AUV 通信前的最后防线
    
    执行流程：
      - 调用 normalize_control_command()
      - 若成功: 返回 (True, [])
      - 若异常: 返回 (False, [异常信息字符串])
    
    @note 此函数设计用于外部命令源（遥控器、远程工作站），允许降级运行
    """
    try:
        normalize_control_command(payload)
    except Exception as exc:  # broad by design to keep caller lightweight
        return False, [str(exc)]
    return True, []


def downlink_state_to_payload(state: ProtocolDownlinkState) -> dict[str, Any]:
    """
    @brief 将解码后的下行状态对象转换为字典形式，用于仲裁与日志记录
    
    @param [in] state ProtocolDownlinkState 对象
    
    @return dict[str, Any]，包含所有字段的映射
    
    @details
    数据类 → 字典的转换器，保持所有字段的工程量单位和精度不变。
    用途：
      1. 二进制协议 → 仲裁引擎（仲裁器需要字典形式）
      2. 遥测日志记录（便于 JSON 序列化）
      3. ROS2 消息构建（字典 → ROS2 结构化消息）
    
    @note 返回值中的键与 KEY_* 常量对应，便于表中查询和策略映射
    """
    return {
        KEY_FRAME_NUMBER: int(state.frame_number),
        KEY_OBJ_ADDRESS: int(state.obj_address),
        KEY_CONTROL_MODE_BYTE: int(state.control_mode_byte),
        KEY_WORK_INSTRUCTION: int(state.work_instruction),
        KEY_RIGHT: float(state.right_fin_deg),
        KEY_TOP: float(state.top_fin_deg),
        KEY_LEFT: float(state.left_fin_deg),
        KEY_BOTTOM: float(state.bottom_fin_deg),
        KEY_THRUST: float(state.thrust_percent),
        KEY_MAIN_MOTOR_RPM: int(state.main_motor_rpm),
        KEY_SIDE_MOTOR_RPM: int(state.side_motor_rpm),
        KEY_ORIENTATION_DEG: float(state.orientation_deg),
        KEY_DEPTH_PROTECT_PARAMS: tuple(state.depth_protect_params),
        KEY_BOTTOM_PROTECT_PARAMS: tuple(state.bottom_protect_params),
        KEY_PRESET_TIME_TENTHS_MIN: int(state.preset_time_tenths_min),
        KEY_SPARE_PARAMS: tuple(state.spare_params),
        KEY_PARAMETERS: tuple(state.parameters),
    }


def parse_downlink_packet_to_payload(
    packet: bytes,
    *,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
) -> dict[str, Any]:
    """
    @brief 直接从原始 $CKTH 字节包解析为共享仲裁字典格式
    
    @param [in] packet 72 字节的下行原始数据包
    @param [in] main_motor_rpm_scale RPM 到推力百分比的转换系数（默认 15.0）
    
    @return dict[str, Any]，解码后的字典形式
    
    @details
    一步式解析：byte → ProtocolDownlinkState → dict，便于协议处理流程。
    
    等价于：
      ```python
      state = parse_downlink_packet(packet, main_motor_rpm_scale=...)
      payload = downlink_state_to_payload(state)
      ```
    """
    return downlink_state_to_payload(parse_downlink_packet(packet, main_motor_rpm_scale=main_motor_rpm_scale))


def build_downlink_packet_from_payload(
    payload: Any,
    *,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
) -> bytes:
    """
    @brief 从共享仲裁字典构建 $CKTH 二进制数据包，用于发送给实物 AUV
    
    @param [in] payload 控制有效负载（或其他格式）
    @param [in] main_motor_rpm_scale RPM 到推力百分比的转换系数
    
    @return bytes，72 字节的下行数据包
    
    @details
    "反向"编码过程：字典 → 控制命令验证 → 二进制编码
    
    支持两种输入：
      1. dict: 自动从常见的键中提取参数
      2. 其他: 直接转发给 build_downlink_packet()
    
    dict 提取的键（若不存在则使用默认值）：
      - KEY_FRAME_NUMBER (default 0)
      - KEY_OBJ_ADDRESS (default 1)
      - KEY_CONTROL_MODE_BYTE (default 0x01)
      - KEY_WORK_INSTRUCTION (default 0x00)
      - KEY_ORIENTATION_DEG (default 0.0)
      - KEY_DEPTH_PROTECT_PARAMS, KEY_BOTTOM_PROTECT_PARAMS, etc.
    
    @note 若检测到参数缺失/非法，返回默认安全值（所有舵叶归零、推力零）
    """
    if not isinstance(payload, dict):
        return build_downlink_packet(payload, main_motor_rpm_scale=main_motor_rpm_scale)

    return build_downlink_packet(
        payload,
        frame_counter=int(payload.get(KEY_FRAME_NUMBER, 0)),
        obj_address=int(payload.get(KEY_OBJ_ADDRESS, 1)),
        control_mode_byte=int(payload.get(KEY_CONTROL_MODE_BYTE, 0x01)),
        work_instruction=int(payload.get(KEY_WORK_INSTRUCTION, 0x00)),
        orientation_deg=float(payload.get(KEY_ORIENTATION_DEG, 0.0)),
        depth_protect_params=payload.get(KEY_DEPTH_PROTECT_PARAMS),
        bottom_protect_params=payload.get(KEY_BOTTOM_PROTECT_PARAMS),
        preset_time_tenths_min=int(payload.get(KEY_PRESET_TIME_TENTHS_MIN, 0)),
        spare_params=payload.get(KEY_SPARE_PARAMS),
        parameter_values=payload.get(KEY_PARAMETERS),
        mock_amd_timestamp_us=int(payload.get(KEY_MOCK_AMD_TIMESTAMP_US, 0)),
        target_depth_m=float(payload.get(KEY_TARGET_DEPTH_M, 0.0)),
        main_motor_rpm_scale=main_motor_rpm_scale,
        side_motor_rpm=int(payload.get(KEY_SIDE_MOTOR_RPM, 0)),
    )


def build_bridge_telemetry_payload(
    telemetry: ProtocolUplinkTelemetry,
    *,
    ts: float | None = None,
    active_arbiter: ArbiterMode | str | None = None,
    arbiter_source: ArbiterSource | str | None = None,
    auto_state: AutoState | str | None = None,
    deny_reason: DenyReason | str | None = None,
    telemetry_freshness_ms: float | None = None,
) -> dict[str, Any]:
    """
    @brief 将解码的 $AUV 上行遥测转换为桥接遥测负载，并附加仲裁器状态
    
    @param [in] telemetry ProtocolUplinkTelemetry 对象（从 parse_uplink_packet 得来）
    @param [in] ts 系统时间戳（可选，默认 time.time()）
    @param [in] active_arbiter 当前活跃的仲裁器模式（枚举或字符串）
    @param [in] arbiter_source 仲裁数据来源（枚举或字符串）
    @param [in] auto_state 自主控制状态（LOCKED/REQUESTING/ACTIVE/DENIED）
    @param [in] deny_reason 自主被拒的原因（若 auto_state == DENIED）
    @param [in] telemetry_freshness_ms 数据新鲜度，从接收到当前的延迟 (ms)
    
    @return dict[str, Any]，完整的桥接遥测有效负载
    
    @details
    该函数是 $AUV 协议 → 桥接 Zenoh 话题的适配器。负责：
      1. 工程量单位转换（二进制 → float）
      2. 附加系统级元数据（时间戳、新鲜度）
      3. 融合仲裁器状态（决策端的自主控制权状态）
    
    仲裁器字段说明：
      - active_arbiter: 当前哪个模式在主宰控制（REMOTE / AUTONOMOUS）
      - arbiter_source: 仲裁数据的来源标识
      - auto_state: 自主控制权的申请/授予/拒绝状态
      - deny_reason: 若拒绝，原因是什么（深度超限/故障/etc）
    
    这些字段可选，仅当仲裁器启用时才需要填充。
    
    @note 若仲裁器字段为 None，则不添加到返回字典中（保持向后兼容）
    """
    payload = {
        KEY_TS: float(time.time() if ts is None else ts),
        KEY_FRAME_NUMBER: int(telemetry.frame_number),
        KEY_AUV_ADDRESS: int(telemetry.auv_address),
        KEY_CONTROL_MODE_BYTE: int(telemetry.control_mode_byte),
        KEY_WORK_INSTRUCTION: int(telemetry.work_instruction),
        KEY_MAIN_MOTOR_RPM: int(telemetry.main_motor_rpm),
        KEY_SIDE_MOTOR_RPM: int(telemetry.side_motor_rpm),
        KEY_RIGHT: float(telemetry.right_fin_deg),
        KEY_TOP: float(telemetry.top_fin_deg),
        KEY_LEFT: float(telemetry.left_fin_deg),
        KEY_BOTTOM: float(telemetry.bottom_fin_deg),
        KEY_ORIENTATION_DEG: float(telemetry.orientation_deg),
        "internal_pressure_psi": float(telemetry.internal_pressure_psi),
        "internal_temp_c": int(telemetry.internal_temp_c),
        KEY_DEPTH_M: float(telemetry.depth_m),
        "heading_deg": float(telemetry.heading_deg),
        "pitch_deg": float(telemetry.pitch_deg),
        "roll_deg": float(telemetry.roll_deg),
        "gps_heading_deg": float(telemetry.gps_heading_deg),
        "gps_speed_mps": float(telemetry.gps_speed_mps),
        "dvl_speed_mps": float(telemetry.dvl_speed_mps),
        "altitude_m": float(telemetry.altitude_m),
        "dead_reckoning_lon_deg": float(telemetry.dead_reckoning_lon_deg),
        "dead_reckoning_lat_deg": float(telemetry.dead_reckoning_lat_deg),
        "gps_lon_deg": float(telemetry.gps_lon_deg),
        "gps_lat_deg": float(telemetry.gps_lat_deg),
        KEY_TOTAL_VOLTAGE_V: float(telemetry.total_voltage_v),
        "total_current_a": float(telemetry.total_current_a),
        "soc": int(telemetry.soc),
        "soh": int(telemetry.soh),
        "device_power_status": int(telemetry.device_power_status),
        "operation_feedback": int(telemetry.operation_feedback),
        "task_status": int(telemetry.task_status),
        "system_alarm": int(telemetry.system_alarm),
        "depth_alarm": int(telemetry.depth_alarm),
        "bottom_alarm": int(telemetry.bottom_alarm),
    }

    active_arbiter_value = _enum_value(active_arbiter)
    if active_arbiter_value is not None:
        payload[KEY_ACTIVE_ARBITER] = active_arbiter_value

    arbiter_source_value = _enum_value(arbiter_source)
    if arbiter_source_value is not None:
        payload[KEY_ARBITER_SOURCE] = arbiter_source_value

    auto_state_value = _enum_value(auto_state)
    if auto_state_value is not None:
        payload[KEY_AUTO_STATE] = auto_state_value

    deny_reason_value = _enum_value(deny_reason)
    if deny_reason_value is not None:
        payload[KEY_DENY_REASON] = deny_reason_value

    if telemetry_freshness_ms is not None:
        payload[KEY_TELEMETRY_FRESHNESS_MS] = float(telemetry_freshness_ms)

    return payload


def calculate_byte_sum_checksum(data: bytes | bytearray) -> int:
    """
    @brief 计算协议帧的校验和（低 8 位字节和）
    
    @param [in] data 输入数据字节序列（不含帧尾）
    
    @return int，范围 0-255，表示校验和
    
    @details
    使用简单的字节和算法（所有字节相加，取低 8 位）。
    协议规范：
      - 下行帧：校验 offset 0-68 的字节（共 69 字节），结果存储在 offset 69
      - 上行帧：校验 offset 0-141 的字节（共 142 字节），结果存储在 offset 142
      - 帧尾不参与校验（总是 0xFF 0xFF）
    
    计算过程：
      ```python
      checksum = sum(data[:checksum_offset]) & 0xFF
      packet[checksum_offset] = checksum
      ```
    
    @note 本校验算法不提供 CRC 级别的错误检测（仅防止程序错误），
          生产环境应考虑升级到 CRC-16
    """
    return sum(data) & 0xFF


def _clamp_int(value: int, low: int, high: int) -> int:
    """
    整数范围限制（饱和）。
    
    @param value 输入值
    @param low 下界（含）
    @param high 上界（含）
    @return max(low, min(high, value))
    """
    return max(low, min(high, int(value)))


def _sanitize_float(value: float, default: float = 0.0) -> float:
    """
    浮点数安全性检查 — 拦截 NaN 和 Inf，返回安全默认值。
    
    @param value 待检查的浮点值
    @param default 当 value 为 NaN/Inf 时返回的默认值
    @return value（若有限）或 default
    
    @details
    用于在 struct.pack 前拦截控制器输出的非法浮点数，
    防止整数溢出导致舵角/推力异常跳变。
    """
    if not math.isfinite(value):
        return default
    return float(value)


def _coerce_pair(values: Sequence[int] | None, *, low: int, high: int) -> tuple[int, int]:
    """
    强制转换二元参数组。若为 None 返回 (0, 0)，否则限制范围。
    
    @param values 输入序列（应有 2 个元素）
    @param low 下界
    @param high 上界
    @return (clamped_first, clamped_second)
    @throws ValueError 若 values 长度不等于 2
    """
    if values is None:
        return 0, 0
    if len(values) != 2:
        raise ValueError("expected exactly 2 values")
    return (_clamp_int(values[0], low, high), _clamp_int(values[1], low, high))


def _coerce_parameters(values: Sequence[int] | None) -> tuple[int, ...]:
    """
    强制转换 12 元参数组（协议规定为 12 个可调参数）。
    
    若为 None 返回全零 12 元组；否则按协议的位宽限制：
      - Para1-4: 32 位整数 (-2^31 ~ 2^31-1)
      - Para5-12: 16 位整数 (-32768 ~ 32767)
    
    @param values 输入序列（应有 12 个元素）
    @return 12 元组，所有值已饱和限制
    @throws ValueError 若 values 长度不等于 12
    """
    if values is None:
        return (0,) * 12
    if len(values) != 12:
        raise ValueError("expected exactly 12 parameter values")
    packed = [
        _clamp_int(values[0], -2147483648, 2147483647),
        _clamp_int(values[1], -2147483648, 2147483647),
        _clamp_int(values[2], -2147483648, 2147483647),
        _clamp_int(values[3], -2147483648, 2147483647),
    ]
    packed.extend(_clamp_int(value, -32768, 32767) for value in values[4:])
    return tuple(packed)


def _validate_frame(packet: bytes | bytearray, *, expected_size: int, header: bytes, checksum_index: int) -> None:
    """
    验证二进制协议帧的完整性。检查长度、帧头、帧尾和校验和。
    
    @param packet 待验证的数据包
    @param expected_size 期望的帧长度
    @param header 期望的帧头
    @param checksum_index 校验和字节的位置
    
    @throws ValueError 若任何检查失败（长度错误、帧头错误、帧尾错误、校验和错误）
    
    @note 校验和检查对象为 packet[:checksum_index] 的字节和（低 8 位）
    """
    if len(packet) != expected_size:
        raise ValueError(f"packet length must be {expected_size}, got {len(packet)}")
    if bytes(packet[: len(header)]) != header:
        raise ValueError("packet header mismatch")
    if bytes(packet[-2:]) != PROTOCOL_FRAME_TAIL:
        raise ValueError("packet tail mismatch")
    checksum = calculate_byte_sum_checksum(packet[:checksum_index])
    if int(packet[checksum_index]) != checksum:
        raise ValueError(
            f"checksum mismatch: expected 0x{checksum:02X}, got 0x{int(packet[checksum_index]):02X}"
        )


def build_downlink_packet(
    command_payload: Any,
    *,
    frame_counter: int = 0,
    obj_address: int = 1,
    control_mode_byte: int = 0x01,
    work_instruction: int = 0x00,
    orientation_deg: float = 0.0,
    depth_protect_params: Sequence[int] | None = None,
    bottom_protect_params: Sequence[int] | None = None,
    preset_time_tenths_min: int = 0,
    spare_params: Sequence[int] | None = None,
    parameter_values: Sequence[int] | None = None,
    mock_amd_timestamp_us: int = 0,
    target_depth_m: float = 0.0,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
    side_motor_rpm: int = 0,
) -> bytes:
    """
    @brief 从通道控制有效负载构建 72 字节 $CKTH 下行命令帧
    
    @param [in] command_payload 控制命令（list/dict/dict+"command"键）
    @param [in] frame_counter 数据帧序号 (0-255 循环计数)
    @param [in] obj_address 目标 AUV 地址 (通常为 0x01)
    @param [in] control_mode_byte 控制模式字节 (0x01=遥控, 0xEE=自主)
    @param [in] work_instruction 工作指令字节 (任务标识)
    @param [in] orientation_deg 方向角 (°)
    @param [in] depth_protect_params 深度保护参数 [min, max] 或 None
    @param [in] bottom_protect_params 底部保护参数 [min, max] 或 None
    @param [in] preset_time_tenths_min 预设时间 (0.1 分钟单位)
    @param [in] spare_params 备用参数 [spare1, spare2] 或 None
    @param [in] parameter_values 扩展参数 12 元组 (Para1-Para12)
    @param [in] main_motor_rpm_scale RPM 到推力百分比的转换系数
    @param [in] side_motor_rpm 侧推进马达转速 (RPM)
    
    @return bytes，72 字节的完整下行数据包（含帧头、校验和、帧尾）
    
    @details
    完整的二进制编码流程：
      1. 正则化控制命令（通过 normalize_control_command）
      2. 强制所有参数进入有效范围（clamping）
      3. 使用 struct.pack_into 按大端字节序填充数据
      4. 计算校验和并填充
      5. 附加帧尾 (0xFF 0xFF)
    
    关键数据映射（详见 PROTOCOL_DOWNLINK_* 常量）：
      - offset 0-4: 帧头 "\\$CKTH"
      - offset 5-7: 帧号、地址、模式字节
      - offset 8-22: 深度/底部保护、备用参数、工作指令
      - offset 23-35: 推进马达 RPM、舵叶角度 (×10 存储)、方向角
      - offset 37-67: 12 个扩展参数 (Para1-Para12)
      - offset 69: 校验和
      - offset 70-71: 帧尾 0xFF 0xFF
    
    @throws ValueError 若 parameter_values 长度不等于 12
    
    @note 所有角度在构建前自动乘以 10.0（因协议以 0.1° 为单位存储）
    @warning 参数clamping 可能改变用户意图（如舵叶超出 ±30° 会被截断）
    """
    normalized = normalize_control_command(command_payload)
    depth_pair = _coerce_pair(depth_protect_params, low=0, high=65535)
    bottom_pair = _coerce_pair(bottom_protect_params, low=0, high=65535)
    spare_pair = _coerce_pair(spare_params, low=-32768, high=32767)
    parameters = list(_coerce_parameters(parameter_values))
    if isinstance(command_payload, dict):
        if KEY_TARGET_DEPTH_M in command_payload:
            parameters[0] = _clamp_int(round(target_depth_m * 10.0), -2147483648, 2147483647)
        if KEY_MOCK_AMD_TIMESTAMP_US in command_payload:
            parameters[1] = _clamp_int(mock_amd_timestamp_us, -2147483648, 2147483647)
    else:
        if target_depth_m != 0.0:
            parameters[0] = _clamp_int(round(target_depth_m * 10.0), -2147483648, 2147483647)
        if mock_amd_timestamp_us != 0:
            parameters[1] = _clamp_int(mock_amd_timestamp_us, -2147483648, 2147483647)

    packet = bytearray(PROTOCOL_DOWNLINK_SIZE)
    packet[0:5] = PROTOCOL_DOWNLINK_HEADER
    packet[5] = frame_counter & 0xFF
    packet[6] = obj_address & 0xFF
    packet[7] = control_mode_byte & 0xFF

    struct.pack_into(">H", packet, 8, depth_pair[0]) # ">H" 表示大端无符号短整数
    struct.pack_into(">H", packet, 10, depth_pair[1])
    struct.pack_into(">H", packet, 12, bottom_pair[0])
    struct.pack_into(">H", packet, 14, bottom_pair[1])
    struct.pack_into(">H", packet, 16, _clamp_int(preset_time_tenths_min, 0, 65535))
    struct.pack_into(">h", packet, 18, spare_pair[0]) # ">h" 表示大端有符号短整数
    struct.pack_into(">h", packet, 20, spare_pair[1])
    packet[22] = work_instruction & 0xFF

    main_motor_rpm = _clamp_int(round(_sanitize_float(normalized[KEY_THRUST]) * main_motor_rpm_scale), -32768, 32767)
    struct.pack_into(">h", packet, 23, main_motor_rpm)
    struct.pack_into(">h", packet, 25, _clamp_int(side_motor_rpm, -32768, 32767))
    struct.pack_into(">h", packet, 27, _clamp_int(round(_sanitize_float(normalized[KEY_LEFT]) * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 29, _clamp_int(round(_sanitize_float(normalized[KEY_RIGHT]) * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 31, _clamp_int(round(_sanitize_float(normalized[KEY_TOP]) * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 33, _clamp_int(round(_sanitize_float(normalized[KEY_BOTTOM]) * 10.0), -32768, 32767))
    struct.pack_into(">H", packet, 35, _clamp_int(round(_sanitize_float(orientation_deg) * 10.0), 0, 65535))

    struct.pack_into(">i", packet, 37, parameters[0])
    struct.pack_into(">i", packet, 41, parameters[1])
    struct.pack_into(">i", packet, 45, parameters[2])
    struct.pack_into(">i", packet, 49, parameters[3])
    struct.pack_into(">h", packet, 53, parameters[4])
    struct.pack_into(">h", packet, 55, parameters[5])
    struct.pack_into(">h", packet, 57, parameters[6])
    struct.pack_into(">h", packet, 59, parameters[7])
    struct.pack_into(">h", packet, 61, parameters[8])
    struct.pack_into(">h", packet, 63, parameters[9])
    struct.pack_into(">h", packet, 65, parameters[10])
    struct.pack_into(">h", packet, 67, parameters[11])

    packet[PROTOCOL_DOWNLINK_CHECKSUM_INDEX] = calculate_byte_sum_checksum(packet[:PROTOCOL_DOWNLINK_CHECKSUM_INDEX])
    packet[-2:] = PROTOCOL_FRAME_TAIL
    return bytes(packet)


def parse_downlink_packet(
    packet: bytes,
    *,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
) -> ProtocolDownlinkState:
    """
    @brief 解码 72 字节 $CKTH 下行帧为工程量结构体
    
    @param [in] packet 原始下行数据包 (72 字节)
    @param [in] main_motor_rpm_scale RPM 到推力百分比的转换系数
    
    @return ProtocolDownlinkState，包含所有解码字段
    
    @details
    完整的二进制解码流程：
      1. 帧合法性验证（_validate_frame）
         - 检查长度是否为 72 字节
         - 检查帧头是否为 "$CKTH"
         - 检查帧尾是否为 0xFF 0xFF
         - 检查校验和是否匹配
      2. 按字节偏移量提取各字段
         - 整数字段：struct.unpack 进行大端解析
         - 浮点工程量：乘以对应的转换系数（如 0.1 for 角度）
      3. 校验和反推：main_motor_rpm = struct.unpack(">h", packet[23:25])[0]
      4. 构造 ProtocolDownlinkState 对象
    
    数据映射示例：
      - offset 5: frame_number (uint8)
      - offset 29-30: right_fin_deg (int16 ÷ 10)
      - offset 23-24: main_motor_rpm (int16)，thrust_percent = RPM / scale
    
    @throws ValueError 若帧合法性检查失败（长度错误、校验和错误、帧头/尾错误）
    
    @note 解码过程中保持所有工程量精度（浮点数），无隐式截断
    @warning 若 main_motor_rpm_scale 为 0，会导致 ZeroDivisionError（应提前检查）
    """
    _validate_frame(
        packet,
        expected_size=PROTOCOL_DOWNLINK_SIZE,
        header=PROTOCOL_DOWNLINK_HEADER,
        checksum_index=PROTOCOL_DOWNLINK_CHECKSUM_INDEX,
    )

    main_motor_rpm = struct.unpack(">h", packet[23:25])[0]
    mock_amd_timestamp_us = struct.unpack(">i", packet[PROTOCOL_DOWNLINK_PARA2_OFFSET:PROTOCOL_DOWNLINK_PARA2_OFFSET + 4])[0]
    target_depth_m_raw = struct.unpack(">i", packet[PROTOCOL_DOWNLINK_PARA1_OFFSET:PROTOCOL_DOWNLINK_PARA1_OFFSET + 4])[0]
    target_depth_m = target_depth_m_raw * 0.1
    return ProtocolDownlinkState(
        frame_number=int(packet[5]),
        obj_address=int(packet[6]),
        control_mode_byte=int(packet[7]),
        work_instruction=int(packet[22]),
        right_fin_deg=struct.unpack(">h", packet[29:31])[0] * 0.1,
        top_fin_deg=struct.unpack(">h", packet[31:33])[0] * 0.1,
        left_fin_deg=struct.unpack(">h", packet[27:29])[0] * 0.1,
        bottom_fin_deg=struct.unpack(">h", packet[33:35])[0] * 0.1,
        thrust_percent=(main_motor_rpm / main_motor_rpm_scale) if main_motor_rpm_scale else 0.0,
        main_motor_rpm=main_motor_rpm,
        side_motor_rpm=struct.unpack(">h", packet[25:27])[0],
        orientation_deg=struct.unpack(">H", packet[35:37])[0] * 0.1,
        depth_protect_params=(struct.unpack(">H", packet[8:10])[0], struct.unpack(">H", packet[10:12])[0]),
        bottom_protect_params=(struct.unpack(">H", packet[12:14])[0], struct.unpack(">H", packet[14:16])[0]),
        preset_time_tenths_min=struct.unpack(">H", packet[16:18])[0],
        spare_params=(struct.unpack(">h", packet[18:20])[0], struct.unpack(">h", packet[20:22])[0]),
        parameters=(
            target_depth_m_raw,
            mock_amd_timestamp_us,
            struct.unpack(">i", packet[45:49])[0],
            struct.unpack(">i", packet[49:53])[0],
            struct.unpack(">h", packet[53:55])[0],
            struct.unpack(">h", packet[55:57])[0],
            struct.unpack(">h", packet[57:59])[0],
            struct.unpack(">h", packet[59:61])[0],
            struct.unpack(">h", packet[61:63])[0],
            struct.unpack(">h", packet[63:65])[0],
            struct.unpack(">h", packet[65:67])[0],
            struct.unpack(">h", packet[67:69])[0],
        ),
        mock_amd_timestamp_us=mock_amd_timestamp_us,
        target_depth_m=target_depth_m,
    )


def build_uplink_packet(
    *,
    frame_counter: int = 0,
    auv_address: int = 1,
    control_mode_byte: int = 0x01,
    work_instruction: int = 0x00,
    main_motor_rpm: int = 0,
    side_motor_rpm: int = 0,
    left_fin_deg: float = 0.0,
    right_fin_deg: float = 0.0,
    top_fin_deg: float = 0.0,
    bottom_fin_deg: float = 0.0,
    orientation_deg: float = 0.0,
    depth_m: float = 0.0,
    heading_deg: float = 0.0,
    pitch_deg: float = 0.0,
    roll_deg: float = 0.0,
    gps_heading_deg: float = 0.0,
    gps_speed_mps: float = 0.0,
    dvl_speed_mps: float = 0.0,
    altitude_m: float = 0.0,
    dead_reckoning_lon_deg: float = 0.0,
    dead_reckoning_lat_deg: float = 0.0,
    gps_lon_deg: float = 0.0,
    gps_lat_deg: float = 0.0,
    total_voltage_v: float = 48.0,
    total_current_a: float = 0.0,
    soc: int = 100,
    soh: int = 100,
    internal_pressure_psi: float = 0.0,
    internal_temp_c: int = 20,
    device_power_status: int = 0,
    operation_feedback: int = 0,
    task_status: int = 0,
    system_alarm: int = 0,
    depth_alarm: int = 0,
    bottom_alarm: int = 0,
    parameter_values: Sequence[int] | None = None,
) -> bytes:
    """
    @brief 从各工程量参数构建 145 字节 $AUV 上行遥测帧
    
    @param [in] frame_counter 数据帧序号 (0-255)
    @param [in] auv_address AUV 地址标识
    @param [in] control_mode_byte 当前控制模式字节
    @param [in] work_instruction 当前工作指令
    @param [in] main_motor_rpm / side_motor_rpm 两个推进马达的转速 (RPM)
    @param [in] {left,right,top,bottom}_fin_deg 舵叶偏角 (°)
    @param [in] orientation_deg / {heading,pitch,roll}_deg 姿态角
    @param [in] depth_m 当前深度 (m)
    @param [in] {gps,dvl}_* GPS 和多普勒速度计数据
    @param [in] {dead_reckoning_lon,lat}_deg 死推进估计位置 (°)
    @param [in] {gps_lon,lat}_deg GPS 位置 (°)
    @param [in] {total_voltage_v, total_current_a} 电池状态
    @param [in] {soc, soh} 电池容量百分比、健康度
    @param [in] internal_pressure_psi / internal_temp_c 舱内压力和温度
    @param [in] device_power_status / operation_feedback / task_status 状态字节
    @param [in] {system_alarm, depth_alarm, bottom_alarm} 告警标志
    @param [in] parameter_values 扩展参数（12 元组）
    
    @return bytes，145 字节的完整上行遥测数据包
    
    @details
    仿真侧生成遥测帧的主要函数。根据当前仿真状态和传感器输出，
    构造一个完整的 $AUV 协议帧以供仲裁器 & 桥接器消费。
    
    数据映射略复杂（145 字节），关键组织为：
      - offset 0-4: 帧头 "$AUV\\x91"
      - offset 5-22: 帧号、地址、模式、预留字段、工作指令
      - offset 23-40: 推进 RPM、舵叶角度、参数 Para1-4
      - offset 40-70: 参数 Para5-12
      - offset 72-129: 姿态、速度、位置（GPS、死推进）
      - offset 102-107: 电池 (V, A, SOC, SOH)
      - offset 114-129: 状态字节、告警
      - offset 142: 校验和
      - offset 143-144: 帧尾 0xFF 0xFF
    
    @note 所有工程量输入（角度、深度、位置）都自动按协议标准转换为二进制格式
    @warning 此函数仅在仿真侧使用；实物 AUV 的上行数据来自硬件（不调用此函数）
    """
    parameters = _coerce_parameters(parameter_values)
    packet = bytearray(PROTOCOL_UPLINK_SIZE)
    packet[0:5] = PROTOCOL_UPLINK_HEADER
    packet[5] = frame_counter & 0xFF
    packet[6] = auv_address & 0xFF
    packet[7] = control_mode_byte & 0xFF

    struct.pack_into(">H", packet, 8, 0)
    struct.pack_into(">H", packet, 10, 0)
    struct.pack_into(">H", packet, 12, 0)
    struct.pack_into(">H", packet, 14, 0)
    struct.pack_into(">H", packet, 16, 0)
    struct.pack_into(">h", packet, 18, 0)
    struct.pack_into(">h", packet, 20, 0)
    packet[22] = work_instruction & 0xFF

    struct.pack_into(">h", packet, 23, _clamp_int(main_motor_rpm, -32768, 32767))
    struct.pack_into(">h", packet, 25, _clamp_int(side_motor_rpm, -32768, 32767))
    struct.pack_into(">h", packet, 27, _clamp_int(round(left_fin_deg * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 29, _clamp_int(round(right_fin_deg * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 31, _clamp_int(round(top_fin_deg * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 33, _clamp_int(round(bottom_fin_deg * 10.0), -32768, 32767))
    struct.pack_into(">H", packet, 35, _clamp_int(round(orientation_deg * 10.0), 0, 65535))

    struct.pack_into(">i", packet, 40, parameters[0])
    struct.pack_into(">i", packet, 44, parameters[1])
    struct.pack_into(">i", packet, 48, parameters[2])
    struct.pack_into(">i", packet, 52, parameters[3])
    struct.pack_into(">h", packet, 56, parameters[4])
    struct.pack_into(">h", packet, 58, parameters[5])
    struct.pack_into(">h", packet, 60, parameters[6])
    struct.pack_into(">h", packet, 62, parameters[7])
    struct.pack_into(">h", packet, 64, parameters[8])
    struct.pack_into(">h", packet, 66, parameters[9])
    struct.pack_into(">h", packet, 68, parameters[10])
    struct.pack_into(">h", packet, 70, parameters[11])

    struct.pack_into(">h", packet, 35, _clamp_int(round(internal_pressure_psi * 1000.0), -32768, 32767))
    packet[37] = _clamp_int(internal_temp_c, -128, 127) & 0xFF
    struct.pack_into(">H", packet, 38, _clamp_int(round(depth_m * 10.0), 0, 65535))
    struct.pack_into(">h", packet, 72, _clamp_int(round(heading_deg * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 74, _clamp_int(round(pitch_deg * 10.0), -32768, 32767))
    struct.pack_into(">h", packet, 76, _clamp_int(round(roll_deg * 10.0), -32768, 32767))
    struct.pack_into(">H", packet, 78, _clamp_int(round(gps_heading_deg * 10.0), 0, 65535))
    struct.pack_into(">H", packet, 80, _clamp_int(round(gps_speed_mps * 10.0), 0, 65535))
    struct.pack_into(">h", packet, 82, _clamp_int(round(dvl_speed_mps * 10.0), -32768, 32767))
    struct.pack_into(">H", packet, 84, _clamp_int(round(altitude_m * 10.0), 0, 65535))
    struct.pack_into(">i", packet, 86, _clamp_int(round(dead_reckoning_lon_deg * 1_000_000.0), -2147483648, 2147483647))
    struct.pack_into(">i", packet, 90, _clamp_int(round(dead_reckoning_lat_deg * 1_000_000.0), -2147483648, 2147483647))
    struct.pack_into(">i", packet, 94, _clamp_int(round(gps_lon_deg * 1_000_000.0), -2147483648, 2147483647))
    struct.pack_into(">i", packet, 98, _clamp_int(round(gps_lat_deg * 1_000_000.0), -2147483648, 2147483647))
    struct.pack_into(">H", packet, 102, _clamp_int(round(total_voltage_v * 10.0), 0, 65535))
    struct.pack_into(">H", packet, 104, _clamp_int(round(total_current_a * 10.0), 0, 65535))
    packet[106] = _clamp_int(soc, 0, 100) & 0xFF
    packet[107] = _clamp_int(soh, 0, 100) & 0xFF
    struct.pack_into(">H", packet, 108, 0)
    struct.pack_into(">H", packet, 110, 0)
    packet[112] = 0
    packet[113] = 0
    struct.pack_into(">I", packet, 114, _clamp_int(device_power_status, 0, 0xFFFFFFFF))
    struct.pack_into(">I", packet, 118, _clamp_int(operation_feedback, 0, 0xFFFFFFFF))
    struct.pack_into(">I", packet, 122, _clamp_int(task_status, 0, 0xFFFFFFFF))
    packet[127] = system_alarm & 0xFF
    packet[128] = depth_alarm & 0xFF
    packet[129] = bottom_alarm & 0xFF

    packet[PROTOCOL_UPLINK_CHECKSUM_INDEX] = calculate_byte_sum_checksum(packet[:PROTOCOL_UPLINK_CHECKSUM_INDEX])
    packet[-2:] = PROTOCOL_FRAME_TAIL
    return bytes(packet)


def parse_uplink_packet(packet: bytes) -> ProtocolUplinkTelemetry:
    """
    @brief 解码 145 字节 $AUV 上行遥测帧为工程量结构体
    
    @param [in] packet 原始上行数据包 (145 字节)
    
    @return ProtocolUplinkTelemetry，包含所有解码的遥测字段
    
    @details
    从二进制上行帧中提取所有遥测信息：
      1. 帧合法性验证（_validate_frame）
         - 检查长度 145 字节
         - 检查帧头 "$AUV\\x91"
         - 检查帧尾 0xFF 0xFF
         - 验证校验和匹配
      2. 按大端字节序解析各字段
         - 16 位整数 (int16): 用于舵叶、速度等
         - 32 位整数 (int32): 用于位置经纬度（10^-6 精度）
         - 无符号短整数 (uint16): 用于非负的电源、深度等
      3. 应用工程量转换：
         - 角度 ÷ 10 (二进制存 ×10)
         - 经纬度 ÷ 10^-6
         - 电压/电流 ÷ 10
         - 深度 ÷ 10
    
    关键字段解析示例：
      - offset 5-7: frame_number, auv_address, control_mode_byte
      - offset 23-24: main_motor_rpm (int16, big-endian)
      - offset 72-73: heading_deg (int16 ÷ 10)
      - offset 86-89: dead_reckoning_lon_deg (int32 ÷ 10^-6)
      - offset 102-103: total_voltage_v (uint16 ÷ 10)
    
    @throws ValueError 若帧合法性检查失败
    
    @note 本函数需要完全的 145 字节数据，不支持部分帧解析
    @warning 若帧尾被截断或校验和错误，立即抛异常（设计上严格）
    
    实例：
      ```python
      try:
          telemetry = parse_uplink_packet(raw_145_bytes)
          print(f"深度: {telemetry.depth_m:.1f}m")
          print(f"电压: {telemetry.total_voltage_v:.1f}V")
      except ValueError as e:
          logger.error(f"上行解码失败: {e}")
      ```
    """
    _validate_frame(
        packet,
        expected_size=PROTOCOL_UPLINK_SIZE,
        header=PROTOCOL_UPLINK_HEADER,
        checksum_index=PROTOCOL_UPLINK_CHECKSUM_INDEX,
    )

    return ProtocolUplinkTelemetry(
        frame_number=int(packet[5]),
        auv_address=int(packet[6]),
        control_mode_byte=int(packet[7]),
        work_instruction=int(packet[22]),
        main_motor_rpm=struct.unpack(">h", packet[23:25])[0],
        side_motor_rpm=struct.unpack(">h", packet[25:27])[0],
        right_fin_deg=struct.unpack(">h", packet[29:31])[0] * 0.1,
        top_fin_deg=struct.unpack(">h", packet[31:33])[0] * 0.1,
        left_fin_deg=struct.unpack(">h", packet[27:29])[0] * 0.1,
        bottom_fin_deg=struct.unpack(">h", packet[33:35])[0] * 0.1,
        orientation_deg=struct.unpack(">H", packet[35:37])[0] * 0.1,
        internal_pressure_psi=struct.unpack(">h", packet[35:37])[0] * 0.001,
        internal_temp_c=struct.unpack("b", bytes((packet[37],)))[0],
        depth_m=struct.unpack(">H", packet[38:40])[0] * 0.1,
        heading_deg=struct.unpack(">h", packet[72:74])[0] * 0.1,
        pitch_deg=struct.unpack(">h", packet[74:76])[0] * 0.1,
        roll_deg=struct.unpack(">h", packet[76:78])[0] * 0.1,
        gps_heading_deg=struct.unpack(">H", packet[78:80])[0] * 0.1,
        gps_speed_mps=struct.unpack(">H", packet[80:82])[0] * 0.1,
        dvl_speed_mps=struct.unpack(">h", packet[82:84])[0] * 0.1,
        altitude_m=struct.unpack(">H", packet[84:86])[0] * 0.1,
        dead_reckoning_lon_deg=struct.unpack(">i", packet[86:90])[0] * 1.0e-6,
        dead_reckoning_lat_deg=struct.unpack(">i", packet[90:94])[0] * 1.0e-6,
        gps_lon_deg=struct.unpack(">i", packet[94:98])[0] * 1.0e-6,
        gps_lat_deg=struct.unpack(">i", packet[98:102])[0] * 1.0e-6,
        total_voltage_v=struct.unpack(">H", packet[102:104])[0] * 0.1,
        total_current_a=struct.unpack(">H", packet[104:106])[0] * 0.1,
        soc=int(packet[106]),
        soh=int(packet[107]),
        device_power_status=struct.unpack(">I", packet[114:118])[0],
        operation_feedback=struct.unpack(">I", packet[118:122])[0],
        task_status=struct.unpack(">I", packet[122:126])[0],
        system_alarm=int(packet[127]),
        depth_alarm=int(packet[128]),
        bottom_alarm=int(packet[129]),
        # Para5-7: DVL Body Frame (mm/s → m/s, ÷1000)
        dvl_body_x_mps=struct.unpack(">h", packet[56:58])[0] * 0.001,
        dvl_body_y_mps=struct.unpack(">h", packet[58:60])[0] * 0.001,
        dvl_body_z_mps=struct.unpack(">h", packet[60:62])[0] * 0.001,
        # Para8-10: IMU Angular Velocity (×1000 int16 → rad/s, ÷1000)
        gyro_x_rps=struct.unpack(">h", packet[62:64])[0] * 0.001,
        gyro_y_rps=struct.unpack(">h", packet[64:66])[0] * 0.001,
        gyro_z_rps=struct.unpack(">h", packet[66:68])[0] * 0.001,
    )
