# Mock AMD 协议通信详解

## 目录

1. [协议概述](#协议概述)
2. [$CKTH 下行协议](#ckth-下行协议)
3. [$AUV 上行协议](#auv-上行协议)
4. [数据流向](#数据流向)
5. [调试技巧](#调试技巧)
6. [协议扩展](#协议扩展)

## 协议概述

Mock AMD 实现的是 AUV 与水面控制单元之间的二进制通信协议，包含两条单向链路：

- **下行链路（Downlink）**：水面 → AUV，使用 `$CKTH` 报文
- **上行链路（Uplink）**：AUV → 水面，使用 `$AUV` 报文

### 协议特性

| 特性 | 说明 |
|------|------|
| 传输层 | UDP |
| 字节序 | 大端序（Big Endian） |
| 下行报文长度 | 72 字节 |
| 上行报文长度 | 145 字节 |
| 帧头标识 | `$CKTH` / `$AUV\x91` |
| 帧尾标识 | `0xFFFF` |
| 校验机制 | 字节累加和 |

### 通信拓扑

```
┌─────────────────────┐
│  ROS2 决策层        │
│  (bridge_node)      │
└──────────┬──────────┘
           │ UDP :52365
           v
┌─────────────────────┐     UDP :52364     ┌─────────────────────┐
│                     │ <────────────────── │                     │
│   Mock AMD Server   │                     │  ROS2 Bridge       │
│   (UDP Server)      │ ──────────────────> │  (protocol_udp)    │
│                     │     UDP :52365      │                     │
└──────────┬──────────┘                     └─────────────────────┘
           │
           v
┌─────────────────────┐
│  HoloOcean 仿真      │
└─────────────────────┘
```

## $CKTH 下行协议

### 报文结构

下行报文总长度 72 字节，结构如下：

```
┌──────────────────────────────────────────────────────────────┐
│ 字段                     │ 偏移 │ 长度 │ 类型    │ 说明       │
├──────────────────────────────────────────────────────────────┤
│ 帧头                      │ 0    │ 5    │ bytes  │ "$CKTH"    │
│ 长度                      │ 5    │ 1    │ u8     │ 0x8A       │
│ 帧号                      │ 6    │ 1    │ u8     │ 0-255      │
│ 对象地址                  │ 7    │ 1    │ u8     │ 通常为 1    │
│ 控制模式字节              │ 8    │ 1    │ u8     │ 见下文      │
│ 作业指令                  │ 9    │ 1    │ u8     │ 0x00       │
│ 右舵角                    │ 10   │ 2    │ i16    │ ×0.1 度    │
│ 上舵角                    │ 12   │ 2    │ i16    │ ×0.1 度    │
│ 左舵角                    │ 14   │ 2    │ i16    │ ×0.1 度    │
│ 下舵角                    │ 16   │ 2    │ i16    │ ×0.1 度    │
│ 推力百分比                │ 18   │ 2    │ i16    │ ×1 %       │
│ 主电机 RPM                │ 20   │ 2    │ u16    │ 直接值     │
│ 侧电机 RPM                │ 22   │ 2    │ u16    │ 直接值     │
│ 目标航向                  │ 24   │ 2    │ u16    │ ×0.1 度    │
│ 深度保护参数              │ 26   │ 4    │ u16×2  │ (高, 低)   │
│ 近底保护参数              │ 30   │ 4    │ u16×2  │ (高, 低)   │
│ 预设时间                  │ 34   │ 2    │ u16    │ ×0.1 分    │
│ 备用参数                  │ 36   │ 4    │ u16×2  │ -          │
│ 参数值                    │ 40   │ 28   │ u16×14 │ -          │
│ 填充                      │ 68   │ 1    │ u8     │ 0x00       │
│ 校验和                    │ 69   │ 1    │ u8     │ 累加和     │
│ 帧尾                      │ 70   │ 2    │ bytes  │ 0xFFFF     │
└──────────────────────────────────────────────────────────────┘
```

### 控制模式字节

控制模式字节决定了 AUV 的运行模式，高位与低位分别有不同含义：

| 模式 | 字节值 | 名称 | 说明 |
|------|--------|------|------|
| 手动模式 | `0x01` | MANUAL | 完全手动控制 |
| 手动模式 | `0x02` | REMOTE | 远程手动控制 |
| 自主模式 | `0xEE` | AUTONOMOUS | 自主运行 |
| 巡检模式 | `0xDD` | INSPECTION | 电缆巡检 |
| 保持模式 | `0xCC` | HOVER | 定点悬停 |

**特殊模式**：

| 模式 | 高位 | 低位 | 说明 |
|------|------|------|------|
| 手动接管 | `0x91` | 0x90 | 0x01 | 请求手动控制 |
| 自主请求 | `0xEE` | - | - | 请求自主控制 |

### 示例报文

#### 手动模式报文

```python
# 十六进制表示
packet = bytes([
    0x24, 0x43, 0x4B, 0x54, 0x48,  # "$CKTH"
    0x8A,                         # 长度
    0x00,                         # 帧号 0
    0x01,                         # 对象地址 1
    0x01,                         # 控制模式: MANUAL
    0x00,                         # 作业指令
    0x00, 0x00,                   # 右舵角: 0.0°
    0x00, 0x00,                   # 上舵角: 0.0°
    0x00, 0x00,                   # 左舵角: 0.0°
    0x00, 0x00,                   # 下舵角: 0.0°
    0x00, 0x00,                   # 推力: 0%
    0x00, 0x00,                   # 主电机 RPM: 0
    0x00, 0x00,                   # 侧电机 RPM: 0
    0x00, 0x00,                   # 目标航向: 0.0°
    # ... (其他字段)
    0x00,                         # 填充
    0x3A,                         # 校验和
    0xFF, 0xFF                    # 帧尾
])
```

#### 自主模式报文（含控制量）

```python
# 控制量示例：右舵 -15°, 上舵 -20°, 左舵 15°, 下舵 20°, 推力 50%
packet = bytes([
    0x24, 0x43, 0x4B, 0x54, 0x48,  # "$CKTH"
    0x8A,                         # 长度
    0x01,                         # 帧号 1
    0x01,                         # 对象地址 1
    0xEE,                         # 控制模式: AUTONOMOUS
    0x00,                         # 作业指令
    0xFF, 0x96,                   # 右舵角: -15.0° (0xFF96 = -150)
    0xFF, 0x8C,                   # 上舵角: -20.0° (0xFF8C = -200)
    0x00, 0x96,                   # 左舵角: +15.0° (0x0096 = +150)
    0x00, 0xC8,                   # 下舵角: +20.0° (0x00C8 = +200)
    0x00, 0x32,                   # 推力: +50% (0x0032 = +50)
    0x02, 0xEE,                   # 主电机: 750 RPM (50 * 15)
    # ... (其他字段)
])
```

### 协议解析

**文件位置**: `common/protocol.py`

```python
def parse_downlink_packet(
    packet: bytes,
    *,
    main_motor_rpm_scale: float = DEFAULT_MAIN_MOTOR_RPM_SCALE,
) -> ProtocolDownlinkState:
    """解析 $CKTH 下行报文"""
    # 1. 验证帧头
    if bytes(packet[:5]) != PROTOCOL_DOWNLINK_HEADER:
        raise ValueError("Invalid header")

    # 2. 验证长度
    if len(packet) != PROTOCOL_DOWNLINK_SIZE:
        raise ValueError(f"Invalid size: {len(packet)}")

    # 3. 验证校验和
    calculated_checksum = sum(packet[:69]) & 0xFF
    if calculated_checksum != packet[69]:
        raise ValueError(f"Checksum mismatch")

    # 4. 验证帧尾
    if bytes(packet[70:72]) != PROTOCOL_FRAME_TAIL:
        raise ValueError("Invalid frame tail")

    # 5. 解析各字段
    return ProtocolDownlinkState(
        frame_number=int(packet[6]),
        obj_address=int(packet[7]),
        control_mode_byte=int(packet[8]),
        work_instruction=int(packet[9]),
        right_fin_deg=float(int.from_bytes(packet[10:12], 'big', signed=True) * 0.1),
        top_fin_deg=float(int.from_bytes(packet[12:14], 'big', signed=True) * 0.1),
        left_fin_deg=float(int.from_bytes(packet[14:16], 'big', signed=True) * 0.1),
        bottom_fin_deg=float(int.from_bytes(packet[16:18], 'big', signed=True) * 0.1),
        thrust_percent=float(int.from_bytes(packet[18:20], 'big', signed=True)),
        # ... (其他字段)
    )
```

## $AUV 上行协议

### 报文结构

上行报文总长度 145 字节，结构如下：

```
┌──────────────────────────────────────────────────────────────┐
│ 字段                     │ 偏移 │ 长度 │ 类型    │ 说明       │
├──────────────────────────────────────────────────────────────┤
│ 帧头                      │ 0    │ 5    │ bytes  │ "$AUV\x91" │
│ 长度                      │ 5    │ 1    │ u8     │ 0x8F       │
│ 帧号                      │ 6    │ 1    │ u8     │ 0-255      │
│ AUV 地址                  │ 7    │ 1    │ u8     │ 通常为 1    │
│ 控制模式字节              │ 8    │ 1    │ u8     │ 回显模式    │
│ 作业指令                  │ 9    │ 1    │ u8     │ 回显指令    │
│ 主电机 RPM                │ 10   │ 2    │ u16    │ 当前 RPM    │
│ 侧电机 RPM                │ 12   │ 2    │ u16    │ 当前 RPM    │
│ 右舵角                    │ 14   │ 2    │ i16    │ ×0.1 度    │
│ 上舵角                    │ 16   │ 2    │ i16    │ ×0.1 度    │
│ 左舵角                    │ 18   │ 2    │ i16    │ ×0.1 度    │
│ 下舵角                    │ 20   │ 2    │ i16    │ ×0.1 度    │
│ 目标航向                  │ 22   │ 2    │ u16    │ ×0.1 度    │
│ 内部压力                  │ 24   │ 2    │ u16    │ ×1 PSI     │
│ 内部温度                  │ 26   │ 2    │ i16    │ ×1 °C      │
│ 深度                      │ 38   │ 2    │ u16    │ ×0.1 m     │
│ 航向角                    │ 40   │ 2    │ u16    │ ×0.1 度    │
│ 俯仰角                    │ 42   │ 2    │ i16    │ ×0.1 度    │
│ 横滚角                    │ 44   │ 2    │ i16    │ ×0.1 度    │
│ GPS 航向                  │ 80   │ 2    │ u16    │ ×0.1 度    │
│ GPS 速度                  │ 82   │ 2    │ u16    │ ×0.1 节    │
│ DVL 速度                  │ 84   │ 2    │ u16    │ ×0.1 m/s   │
│ 高度                      │ 86   │ 2    │ u16    │ ×0.1 m     │
│ 推算经度                  │ 94   │ 4    │ i32    │ ×1e-7 度   │
│ 推算纬度                  │ 98   │ 4    │ i32    │ ×1e-7 度   │
│ GPS 经度                  │ 102  │ 4    │ i32    │ ×1e-7 度   │
│ GPS 纬度                  │ 106  │ 4    │ i32    │ ×1e-7 度   │
│ 总电压                    │ 102  │ 2    │ u16    │ ×0.1 V     │
│ 总电流                    │ 104  │ 2    │ u16    │ ×0.1 A     │
│ SOC                       │ 108  │ 1    │ u8     │ %          │
│ SOH                       │ 109  │ 1    │ u8     │ %          │
│ 设备电源状态              │ 110  │ 1    │ u8     │ 位掩码     │
│ 运行反馈                  │ 111  │ 1    │ u8     │ 位掩码     │
│ 任务状态                  │ 112  │ 1    │ u8     │ 位掩码     │
│ 系统告警                  │ 127  │ 1    │ u8     │ 位掩码     │
│ 深度告警                  │ 128  │ 1    │ u8     │ 位掩码     │
│ 近底告警                  │ 129  │ 1    │ u8     │ 位掩码     │
│ ... (其他字段)            │      │      │         │            │
│ 填充                      │ 140  │ 2    │ u16    │ 0x0000     │
│ 校验和                    │ 142  │ 1    │ u8     │ 累加和     │
│ 帧尾                      │ 143  │ 2    │ bytes  │ 0xFFFF     │
└──────────────────────────────────────────────────────────────┘
```

### 关键遥测字段

#### 位姿信息

| 字段 | 偏移 | 格式 | 范围 | 说明 |
|------|------|------|------|------|
| 深度 | 38-39 | u16×0.1 | 0-6553.5 m | 深度值 |
| 航向 | 40-41 | u16×0.1 | 0-359.9° | 从北向东 |
| 俯仰 | 42-43 | i16×0.1 | ±180° | 抬头为正 |
| 横滚 | 44-45 | i16×0.1 | ±180° | 右倾为正 |

#### 速度信息

| 字段 | 偏移 | 格式 | 单位 | 说明 |
|------|------|------|------|------|
| DVL 速度 | 84-85 | u16×0.1 | m/s | 前向速度 |
| GPS 速度 | 80-81 | u16×0.1 | 节 | 对地速度 |

#### 电源状态

| 字段 | 偏移 | 格式 | 说明 |
|------|------|------|------|
| 总电压 | 102-103 | u16×0.1 V | 电池总电压 |
| 总电流 | 104-105 | u16×0.1 A | 电池总电流 |
| SOC | 108 | u8 % | 荷电状态 |
| SOH | 109 | u8 % | 健康状态 |

#### 告警状态

| 字段 | 偏移 | 位掩码说明 |
|------|------|-----------|
| 系统告警 | 127 | bit0: 内部漏水, bit1: 外部漏水 |
| 深度告警 | 128 | 各位对应不同深度区域 |
| 近底告警 | 129 | 各位对应不同近底区域 |

### 示例报文

```python
# 典型的上行报文示例
packet = bytes([
    0x24, 0x41, 0x55, 0x56, 0x91,  # "$AUV\x91"
    0x8F,                         # 长度
    0x01,                         # 帧号 1
    0x01,                         # AUV 地址 1
    0xEE,                         # 控制模式回显
    0x00,                         # 作业指令回显
    0x02, 0xEE,                   # 主电机: 750 RPM
    0x00, 0x00,                   # 侧电机: 0 RPM
    0xFF, 0x96,                   # 右舵角: -15.0°
    0xFF, 0x8C,                   # 上舵角: -20.0°
    0x00, 0x96,                   # 左舵角: +15.0°
    0x00, 0xC8,                   # 下舵角: +20.0°
    0x1B, 0x58,                   # 目标航向: 70.0° (700 × 0.1)
    0x00, 0x0E,                   # 内部压力: 14 PSI
    0x00, 0x19,                   # 内部温度: 25°C
    # ... (深度 7.6m @ 偏移 38-39: 0x001C = 76 × 0.1 = 7.6m)
    0x00, 0x1C,                   # 深度: 7.6m
    0x03, 0x68,                   # 航向: 87.2°
    0x00, 0x00,                   # 俯仰: 0.0°
    0x00, 0x00,                   # 横滚: 0.0°
    # ... (GPS 信息)
    0x01, 0xE0,                   # 总电压: 48.0V (480 × 0.1)
    0x00, 0x78,                   # 总电流: 12.0A (120 × 0.1)
    0x64,                         # SOC: 100%
    0x64,                         # SOH: 100%
    # ... (告警和状态)
    0x00,                         # 系统告警: 无
    0x00,                         # 深度告警: 无
    0x00,                         # 近底告警: 无
    # ... (校验和和帧尾)
    0xAB,                         # 校验和
    0xFF, 0xFF                    # 帧尾
])
```

### 协议打包

**文件位置**: `common/protocol.py`

```python
def build_uplink_packet(
    frame_counter: int,
    auv_address: int,
    control_mode_byte: int,
    work_instruction: int,
    main_motor_rpm: int,
    side_motor_rpm: int,
    right_fin_deg: float,
    top_fin_deg: float,
    left_fin_deg: float,
    bottom_fin_deg: float,
    orientation_deg: float,
    depth_m: float,
    heading_deg: float,
    pitch_deg: float,
    roll_deg: float,
    gps_heading_deg: float,
    gps_speed_mps: float,
    dvl_speed_mps: float,
    altitude_m: float,
    total_voltage_v: float,
    total_current_a: float,
    soc: int,
    soh: int,
    # ... (其他参数)
) -> bytes:
    """构建 $AUV 上行报文"""
    packet = bytearray(145)

    # 帧头
    packet[0:5] = PROTOCOL_UPLINK_HEADER
    packet[5] = 0x8F  # 长度
    packet[6] = frame_counter & 0xFF
    packet[7] = auv_address
    packet[8] = control_mode_byte
    packet[9] = work_instruction

    # 电机和舵角
    packet[10:12] = int(main_motor_rpm).to_bytes(2, 'big')
    packet[12:14] = int(side_motor_rpm).to_bytes(2, 'big')
    packet[14:16] = int(right_fin_deg * 10).to_bytes(2, 'big', signed=True)
    packet[16:18] = int(top_fin_deg * 10).to_bytes(2, 'big', signed=True)
    packet[18:20] = int(left_fin_deg * 10).to_bytes(2, 'big', signed=True)
    packet[20:22] = int(bottom_fin_deg * 10).to_bytes(2, 'big', signed=True)
    packet[22:24] = int(orientation_deg * 10).to_bytes(2, 'big')

    # 位姿信息
    packet[38:40] = int(depth_m * 10).to_bytes(2, 'big')
    packet[40:42] = int(heading_deg * 10).to_bytes(2, 'big')
    packet[42:44] = int(pitch_deg * 10).to_bytes(2, 'big', signed=True)
    packet[44:46] = int(roll_deg * 10).to_bytes(2, 'big', signed=True)

    # 速度信息
    packet[80:82] = int(gps_heading_deg * 10).to_bytes(2, 'big')
    packet[82:84] = int(gps_speed_mps / 0.514444 * 10).to_bytes(2, 'big')  # m/s → 节
    packet[84:86] = int(dvl_speed_mps * 10).to_bytes(2, 'big')
    packet[86:88] = int(altitude_m * 10).to_bytes(2, 'big')

    # 电源状态
    packet[102:104] = int(total_voltage_v * 10).to_bytes(2, 'big')
    packet[104:106] = int(total_current_a * 10).to_bytes(2, 'big')
    packet[108] = soc
    packet[109] = soh

    # 告警状态
    packet[127] = system_alarm
    packet[128] = depth_alarm
    packet[129] = bottom_alarm

    # 校验和
    packet[142] = sum(packet[:142]) & 0xFF

    # 帧尾
    packet[143:145] = PROTOCOL_FRAME_TAIL

    return bytes(packet)
```

## 数据流向

### 完整通信流程

```
┌──────────────────────────────────────────────────────────────────┐
│                         1. 用户/决策层                           │
│  设置目标深度、航向、速度 → 行为树决策                           │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             v
┌──────────────────────────────────────────────────────────────────┐
│                      2. 控制器 (auv_controller)                  │
│  PID 控制计算 → 推力 + 舵角 → /cmd_vel                           │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             v
┌──────────────────────────────────────────────────────────────────┐
│              3. 桥接节点 (bridge_node, protocol_udp)             │
│  订阅 /cmd_vel → 仲裁 → 打包 $CKTH → UDP 发送                    │
└────────────────────────────┬─────────────────────────────────────┘
                             │ UDP 127.0.0.1:52364
                             v
┌──────────────────────────────────────────────────────────────────┐
│                    4. Mock AMD (UDP Server)                      │
│  接收 $CKTH → 解析 → CommandGuard → HoloOcean 执行               │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             v
┌──────────────────────────────────────────────────────────────────┐
│                    5. HoloOcean 仿真环境                          │
│  物理仿真 → AUV 状态更新                                          │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             v
┌──────────────────────────────────────────────────────────────────┐
│                    6. Mock AMD (遥测生成)                         │
│  查询状态 → 坐标转换 → 打包 $AUV → UDP 发送                       │
└────────────────────────────┬─────────────────────────────────────┘
                             │ UDP 127.0.0.1:52365
                             v
┌──────────────────────────────────────────────────────────────────┐
│              7. 桥接节点 (bridge_node, protocol_udp)             │
│  接收 $AUV → 解析 → 发布到 ROS2 Topics                           │
└────────────────────────────┬─────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        v                    v                    v
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ /auv/sensors/ │   │ /auv/state/   │   │ /auv/arbiter/ │
│   * 话题      │   │   filtered    │   │   status      │
└───────────────┘   └───────────────┘   └───────────────┘
        │                    │                    │
        v                    v                    v
┌──────────────────────────────────────────────────────────────────┐
│              8. 状态估计与决策 (ES-EKF + 决策层)                  │
│  融合传感器数据 → 更新状态 → 行为树决策 → 回到步骤 1              │
└──────────────────────────────────────────────────────────────────┘
```

### 端口映射

| 端口 | 方向 | 用途 | 绑定方 |
|------|------|------|--------|
| 52364 | ↓ | 接收 $CKTH 下行命令 | Mock AMD |
| 52365 | ↑ | 发送 $AUV 上行遥测 | Mock AMD |
| 52366 | ↔ | Sniffer 镜像端口 | Mock AMD |

### Topic 映射（协议 → ROS2）

| 协议字段 | ROS2 Topic | 消息类型 |
|----------|-----------|----------|
| depth_m | /auv/sensors/depth | sensor_msgs/FluidPressure |
| heading/pitch/roll | /auv/state/filtered | nav_msgs/Odometry |
| dvl_speed_mps | /auv/sensors/dvl | geometry_msgs/TwistStamped |
| control_mode_byte | /auv/arbiter/status | auv_interfaces/ArbiterStatus |
| total_voltage_v | /auv/sensors/status | auv_interfaces/SensorStatus |

## 调试技巧

### 1. 使用 Sniffer

Sniffer 是一个独立的 UDP 监听工具，可以捕获协议报文而不影响正常通信。

```bash
# 监听下行报文
/usr/bin/python3 scripts/sniffer.py --bind-port 52364 --ascii-format

# 监听上行报文
/usr/bin/python3 scripts/sniffer.py --bind-port 52365 --ascii-format

# 监听镜像端口
/usr/bin/python3 scripts/sniffer.py --bind-port 52366 --ascii-format

# 记录到文件
/usr/bin/python3 scripts/sniffer.py --ascii-format --no-color > sniffer.log
```

### 2. 分析日志

#### 提取特定字段

```bash
# 提取所有深度值
grep "depth=" launcher.log | awk '{print $NF}'

# 提取所有控制模式
grep "Control Mode Byte:" launcher.log

# 统计帧率
grep "frame=" launcher.log | wc -l
```

#### 验证校验和

```bash
# 查找校验和错误
grep "Checksum:" launcher.log | grep -v "OK"

# 统计错误数量
grep "Checksum:" launcher.log | grep -v "OK" | wc -l
```

#### 分析时序

```bash
# 提取时间戳
grep "Timestamp:" launcher.log | awk '{print $2}'

# 计算平均间隔
grep "Timestamp:" launcher.log | \
  awk 'NR>1 {print ($2-prev)*1000; prev=$2}' | \
  awk '{sum+=$1; count++} END {print "平均间隔:", sum/count, "ms"}'
```

### 3. 协议一致性测试

创建测试脚本验证协议实现的一致性：

```python
#!/usr/bin/env python3
"""协议一致性测试"""

from common.protocol import (
    build_uplink_packet,
    parse_downlink_packet,
    build_downlink_packet,
    parse_uplink_packet,
)

# 测试 1: 下行报文往返
def test_downlink_roundtrip():
    original = {
        'right': 15.0,
        'top': -10.0,
        'left': -15.0,
        'bottom': 10.0,
        'thrust': 50.0,
    }
    packet = build_downlink_packet(original)
    decoded = parse_downlink_packet(packet)

    assert abs(decoded.right_fin_deg - original['right']) < 0.1
    assert abs(decoded.thrust_percent - original['thrust']) < 1.0
    print("下行报文往返测试: PASSED")

# 测试 2: 上行报文往返
def test_uplink_roundtrip():
    original = {
        'depth_m': 7.6,
        'heading_deg': 87.2,
        'total_voltage_v': 48.0,
    }
    packet = build_uplink_packet(**original)
    decoded = parse_uplink_packet(packet)

    assert abs(decoded.depth_m - original['depth_m']) < 0.01
    assert abs(decoded.heading_deg - original['heading_deg']) < 0.1
    print("上行报文往返测试: PASSED")

# 测试 3: 边界值测试
def test_boundary_values():
    # 最大推力
    packet = build_downlink_packet({'thrust': 100.0})
    decoded = parse_downlink_packet(packet)
    assert abs(decoded.thrust_percent - 100.0) < 1.0

    # 最小推力
    packet = build_downlink_packet({'thrust': -100.0})
    decoded = parse_downlink_packet(packet)
    assert abs(decoded.thrust_percent - (-100.0)) < 1.0

    print("边界值测试: PASSED")

if __name__ == '__main__':
    test_downlink_roundtrip()
    test_uplink_roundtrip()
    test_boundary_values()
    print("\n所有测试通过!")
```

### 4. Wireshark 分析

使用 Wireshark 捕获 UDP 流量：

1. 安装 Wireshark
2. 开始捕获 loopback 接口
3. 设置过滤器：`udp.port == 52364 || udp.port == 52365`
4. 右键报文 → "Follow UDP Stream"

### 5. Python 交互式调试

```python
#!/usr/bin/env python3
"""交互式协议调试"""

from common.protocol import parse_downlink_packet, format_protocol_packet_ascii
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('127.0.0.1', 52370))  # 端口转发
sock.settimeout(1.0)

print("等待报文...")
try:
    while True:
        packet, addr = sock.recvfrom(2048)

        # 尝试解析
        try:
            state = parse_downlink_packet(packet)
            print("\n收到报文:")
            print(f"  来源: {addr}")
            print(f"  帧号: {state.frame_number}")
            print(f"  模式: 0x{state.control_mode_byte:02X}")
            print(f"  控制: ({state.right_fin_deg:.1f}, {state.top_fin_deg:.1f}, "
                  f"{state.left_fin_deg:.1f}, {state.bottom_fin_deg:.1f}, "
                  f"{state.thrust_percent:.1f})")
        except Exception as e:
            print(f"解析失败: {e}")
            print(f"  原始: {packet.hex()}")

except KeyboardInterrupt:
    print("\n停止监听")
finally:
    sock.close()
```

## 协议扩展

### 添加新字段

当需要向协议添加新字段时，遵循以下步骤：

#### 1. 定义字段常量

```python
# common/protocol.py
KEY_NEW_FIELD = "new_field"
```

#### 2. 更新数据结构

```python
@dataclass(frozen=True)
class ProtocolDownlinkState:
    # ... 现有字段
    new_field: float  # 新增字段
```

#### 3. 更新解析/打包函数

```python
def parse_downlink_packet(packet: bytes) -> ProtocolDownlinkState:
    # ... 现有解析
    new_field = float(int.from_bytes(packet[NEW_OFFSET:NEW_OFFSET+2], 'big', signed=True) * 0.1)
    return ProtocolDownlinkState(..., new_field=new_field)

def build_downlink_packet(...) -> bytes:
    # ... 现有打包
    packet[NEW_OFFSET:NEW_OFFSET+2] = int(new_field * 10).to_bytes(2, 'big', signed=True)
    return packet
```

#### 4. 更新文档

- 更新本文档的协议结构表
- 添加新字段的说明
- 更新相关测试用例

### 版本兼容性

协议版本管理建议：

| 版本 | 特性 | 兼容性 |
|------|------|--------|
| v1.0 | 基础 $CKTH/$AUV 协议 | - |
| v1.1 | 添加仲裁器字段 | 向后兼容 |
| v1.2 | 扩展告警字段 | 向后兼容 |

**向后兼容原则**：
- 新增字段放在报文末尾
- 现有字段偏移量不变
- 旧版本忽略未知字段

### 测试协议扩展

创建完整的回归测试：

```python
def test_protocol_version_compatibility():
    """测试协议版本兼容性"""
    v1_0_packet = bytes([...])  # v1.0 格式报文

    # v1.1 解析器应该能解析 v1.0 报文
    parsed = parse_downlink_packet(v1_0_packet)
    assert parsed.frame_number == 0

    # v1.1 打包的报文，v1.0 解析器应该至少能读取基础字段
    v1_1_packet = build_downlink_packet({...}, new_field=0)
    # 旧版本解析器可以忽略新字段
```

## 相关文档

- [Mock AMD 技术详解](../03_core_concepts/04_mock_amd.md) - 技术实现细节
- [Mock AMD 使用指南](08_mock_amd_guide.md) - 使用说明
- [协议日志使用示例](06_protocol_logging_examples.md) - 日志调试
- [控制调试指南](02_control_debugging.md) - 控制问题排查
