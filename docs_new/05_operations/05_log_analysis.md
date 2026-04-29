# 日志解读指南

本文档说明如何解读系统中的两种主要日志：ROS2 bag 记录和 Mock AMD 测试日志。

## 日志类型概览

```
AUV 系统
├── ROS2 Bag 日志                    # ROS2 标准格式，记录话题数据
│   ├── 位置: log/experiments/*
│   ├── 格式: .mcap 或 .sqlite3
│   └── 内容: ROS2 话题数据流
│
└── Mock AMD 测试日志                 # 二进制协议通信日志
    ├── 位置: 终端输出或 experiment_runs/*
    ├── 格式: 三种格式可选
    │   ├── 单行摘要格式 (默认)
    │   ├── ASCII 详细格式 (可读性最高)
    │   └── 原始紧凑格式 (CSV，适合脚本)
    └── 内容: $CKTH/$AUV 协议报文
```

## 日志路径详解

### 项目根目录结构

```
AUV_Master_Project/
├── log/                             # 总日志目录
│   └── experiments/                 # 实验日志
│       └── phase78_bundle_20260410_231717/
│           ├── experiment_runs/     # 单次运行日志
│           │   ├── 20260410_232022/
│           │   │   ├── metadata.txt      # 元数据
│           │   │   ├── launcher.log      # 启动器日志（含 Mock AMD）
│           │   │   ├── *.mcap            # ROS2 bag 数据
│           │   │   └── bridge_telemetry.jsonl
│           │   └── 20260410_235355/
│           ├── sniffer.log               # Sniffer 独立日志
│           ├── arbiter_status.log        # 仲裁器状态日志
│           └── execution_report_*.md     # 执行报告
│
├── brain_linux/log/                 # ROS2 节点日志
│   └── *.log
│
└── scripts/log/                     # 脚本日志
    └── *.log
```

### 日志格式选择

| 格式 | 配置 | 适用场景 | 输出示例 |
|------|------|---------|----------|
| **单行摘要** | `log_raw_format: false`<br>`log_ascii_format: false` | 正常运行 | `[mock-amd RX][CKTH] frame=138 obj=1 mode=0xE E cmd=(15.0,10.0,-15.0,-10.0,50.0)` |
| **ASCII 详细** | `log_ascii_format: true` | 问题诊断 | `==================================================\nASCII PROTOCOL PACKET...` |
| **原始紧凑** | `log_raw_format: true` | 脚本处理 | `$CKTH,138,1,238,0,15.0,10.0,-15.0,-10.0,50.0,750,0,87.2` |

### 日志类型说明

#### 1. ROS2 Bag 日志

**路径**: `log/experiments/*/experiment_runs/*/*.mcap`

**用途**: 记录 ROS2 话题数据，用于回放和分析

**包含内容**:
- `/auv/sensors/*` - 所有传感器数据
- `/auv/state/filtered` - 融合状态估计
- `/cmd_vel` - 控制指令
- `/auv/control/setpoint` - 控制目标
- `/auv/arbiter/status` - 仲裁器状态

**查看方法**:
```bash
# 使用 Foxglove（推荐）
foxglove path/to/bag.mcap

# 使用命令行
mcap info path/to/bag.mcap
mcap filter path/to/bag.mcap --filter "topic == '/auv/sensors/imu'"
```

#### 2. Mock AMD 测试日志

**路径**: `experiment_runs/*/launcher.log`

**用途**: 记录二进制协议通信详情

**包含内容**:
- `$CKTH` 下行命令（PC → AUV）
- `$AUV` 上行遥测（AUV → PC）
- 解析后的字段值
- 校验和验证结果

**查看方法**:
```bash
# 直接查看
cat experiment_runs/*/launcher.log

# 过滤特定类型
grep "DOWNLINK" launcher.log    # 只看下行
grep "UPLINK" launcher.log      # 只看上行
```

#### 3. Sniffer 日志

**路径**: `sniffer.log`（实验 bundle 根目录）

**用途**: 独立的协议嗅探日志，不影响系统运行

**优势**:
- 可选择性启用
- 不干扰正常通信
- 可保存到文件

**启动方法**:
```bash
# 独立启动
/usr/bin/python3 scripts/sniffer.py --ascii-format > sniffer.log

# 或使用镜像端口（配置文件中设置 sniffer_mirror_port）
/usr/bin/python3 scripts/sniffer.py --bind-port 52366
```

#### 4. 仲裁器状态日志

**路径**: `arbiter_status.log`

**用途**: 记录控制仲裁状态变化

**包含内容**:
- `active_arbiter` - 当前活跃仲裁器（REMOTE/AUTONOMOUS/MANUAL_OVERRIDE）
- `auto_state` - 自主状态（LOCKED/REQUESTING/ACTIVE/DENIED）
- `deny_reason` - 拒绝原因

**查看方法**:
```bash
# 查看状态变化
cat arbiter_status.log

# 统计状态分布
grep "active_arbiter" arbiter_status.log | sort | uniq -c
```

## 通信协议架构

### 协议栈分析

```
应用层:    $CKTH/$AUV 二进制协议 (自定义)
           ↓
传输层:    UDP (User Datagram Protocol)
           ↓
网络层:    IP
           ↓
物理层:    网络接口
```

### 关键特性

| 特性 | 说明 |
|------|------|
| **传输协议** | UDP（无连接，不可靠但快速） |
| **数据格式** | 二进制协议（72 字节下行 / 145 字节上行） |
| **端口配置** | 52364（绑定）, 52365（远程） |
| **协议标识** | `$CKTH`（下行），`$AUV\x91`（上行） |
| **校验机制** | XOR 校验和 |
| **帧尾标识** | `0xFFFF` |

### 数据流向

```
┌────────────────────────────────────────────────────────────────┐
│                        PC 上位机                                │
│  (发送 $CKTH 命令)                                               │
└────────────────────────┬───────────────────────────────────────┘
                         │ UDP (127.0.0.1:52364 → 127.0.0.1:52365)
                         ▼
┌────────────────────────────────────────────────────────────────┐
│                    Mock AMD Server                              │
│  sim_holoocean/interfaces/mock_amd_server.py                   │
│  1. 解析 $CKTH 命令                                              │
│  2. 更新仿真状态                                                 │
│  3. 生成 $AUV 遥测                                              │
└────────────────────────┬───────────────────────────────────────┘
                         │ UDP (127.0.0.1:52365 → 127.0.0.1:52364)
                         ▼
┌────────────────────────────────────────────────────────────────┐
│                      ROS2 Bridge                                │
│  brain_linux/src/auv_bridge/.../protocol_udp_bridge_node.py   │
│  1. 接收 $AUV 遥测                                               │
│  2. 发布到 ROS2 话题                                             │
│  3. 生成控制命令                                                 │
└────────────────────────────────────────────────────────────────┘
```

## 日志类型 1: ROS2 Bag 记录

### 日志位置

```bash
# 实验日志根目录
log/experiments/

# 具体实验运行
log/experiments/phase78_bundle_20260410_231717/experiment_runs/20260410_235355/
├── metadata.txt           # 实验元数据
├── launcher.log          # 启动器日志
├── *.mcap                # ROS2 bag 数据
└── bridge_telemetry.jsonl # 桥接遥测
```

### 查看日志

#### 安装工具

```bash
# mcap 工具
pip install mcap

# Foxglove (推荐)
# 下载: https://foxglove.dev/download
```

#### 命令行查看

```bash
# 列出 bag 中的话题
mcap info path/to/bag.mcap

# 提取特定话题
mcap filter path/to/bag.mcap --filter "topic == '/auv/sensors/imu'" -o output.mcap

# 转换为 JSON
mcap to-json path/to/bag.mcap -o output.json
```

#### 使用 Foxglove 查看

1. 打开 Foxglove
2. File → Open
3. 选择 `.mcap` 文件
4. 可视化查看所有话题数据

### 日志内容解读

#### 关键话题

| 话题 | 用途 | 关键字段 |
|------|------|---------|
| `/auv/sensors/imu` | IMU 数据 | `linear_acceleration`, `angular_velocity` |
| `/auv/sensors/dvl` | DVL 数据 | `vel_ned[0]`, `valid` |
| `/auv/sensors/depth` | 深度数据 | `fluid_pressure`, `depth_m` |
| `/auv/state/filtered` | 融合状态 | `pose.position.z`, `twist.linear` |
| `/cmd_vel` | 控制指令 | `linear.x`, `angular.*` |
| `/auv/arbiter/status` | 仲裁器状态 | `active_arbiter`, `auto_state` |

#### 解读示例

```python
# 查询深度变化趋势
# 1. 导入 bag
from mcap.reader import McapReader

with McapReader("bag.mcap") as reader:
    # 2. 遍历深度消息
    for schema, channel, message in reader.messages():
        if channel.topic == "/auv/sensors/depth":
            depth = message.depth_m
            print(f"时间: {message.log_time}, 深度: {depth}m")

# 3. 分析控制效果
# 查看 /cmd_vel 与 /auv/state/filtered 的时序关系
```

## 日志类型 2: Mock AMD 测试日志

### 日志位置

```bash
# 终端输出（运行时）
# 或保存到文件
experiment_runs/*/launcher.log

# 独立 sniffer 日志
sniffer.log
```

### 日志格式

#### 格式 1: 单行摘要（默认）

```
[mock-amd RX][CKTH][127.0.0.1:52364] frame=138 obj=1 mode=0xEE instr=0x00 cmd=(15.0,10.0,-15.0,-10.0,50.0) main_rpm=750 side_rpm=0 heading=87.2deg
[mock-amd TX][AUV][127.0.0.1:52365] frame=138 auv=1 mode=0xEE instr=0x00 depth=7.60m heading=87.2deg gps=(0.000000,0.000000) voltage=48.0V cmd=(15.0,10.0,-15.0,-10.0,750)
```

**启用方法**: 默认格式，无需特殊配置

#### 格式 2: ASCII 详细格式

```
==================================================
ASCII PROTOCOL PACKET - DOWNLINK ($CKTH)
Timestamp: 2026-04-10 23:54:12.123
Source: 127.0.0.1:52364
--------------------------------------------------
HEADER INFO:
  Frame Number: 138
  Control Mode Byte: 0xEE → AUTONOMOUS (自主模式)

CONTROL SURFACES:
  Right Fin:    +15.0 deg
  Top Fin:      +10.0 deg
  Thrust:       +50.0 %

FRAME INTEGRITY:
  Checksum: OK
  Frame Tail: OK
==================================================
```

**启用方法**: 设置 `log_ascii_format: true`

#### 格式 3: 原始紧凑格式 ⭐

```
$CKTH,138,1,238,0,15.0,10.0,-15.0,-10.0,50.0,750,0,87.2
$AUV,138,1,238,0,7.60,87.2,0.5,0.0,0.000000,0.000000,48.0,12.0,750,15.0,10.0,-15.0,-10.0
```

**启用方法**: 设置 `log_raw_format: true`

**特点**:
- ✅ 直接以协议标识开头（$CKTH/$AUV）
- ✅ 逗号分隔的数值，无字段名
- ✅ 紧凑单行，适合快速浏览
- ✅ 易于脚本处理（CSV 格式）

**字段映射**:

下行 ($CKTH):
```
$CKTH,帧号,目标地址,模式字节,指令,右舵,上舵,左舵,下舵,推力,主电机RPM,侧推RPM,航向
```

上行 ($AUV):
```
$AUV,帧号,AUV地址,模式字节,指令,深度,航向,俯仰,横滚,GPS经度,GPS纬度,电压,电流,主电机RPM,右舵,上舵,左舵,下舵
```

#### 彩色摘要格式

```
[mock-amd RX][CKTH][127.0.0.1:52364] frame=138 obj=1 mode=0xEE instr=0x00 cmd=(15.0,10.0,-15.0,-10.0,50.0) main_rpm=750 side_rpm=0 heading=87.2deg
[mock-amd TX][AUV][127.0.0.1:52365] frame=138 auv=1 mode=0xEE instr=0x00 depth=7.60m heading=87.2deg gps=(0.000000,0.000000) voltage=48.0V cmd=(15.0,10.0,-15.0,-10.0,750)
```

#### 颜色含义

| 颜色 | 含义 |
|------|------|
| 🔵 青色 | 下行命令（$CKTH） |
| 🟢 绿色 | 上行遥测（$AUV） |
| 🟡 黄色 | 未知协议 |
| 🔴 红色 | 解析失败 |

### 日志字段解读

#### 下行命令 ($CKTH)

```
frame=138           # 帧序号
obj=1               # 目标地址
mode=0xEE           # 控制模式字节 (0xEE = 自主模式)
instr=0x00          # 工作指令
cmd=(15.0,10.0,-15.0,-10.0,50.0)  # 舵面推力: (右,上,左,下,主推)
main_rpm=750        # 主电机 RPM
side_rpm=0          # 侧推器 RPM
heading=87.2deg     # 目标航向
```

#### 上行遥测 ($AUV)

```
frame=138           # 帧序号
auv=1               # AUV 地址
mode=0xEE           # 控制模式字节
instr=0x00          # 工作指令
depth=7.60m         # 当前深度
heading=87.2deg     # 当前航向
gps=(0.000000,0.000000)  # GPS 位置 (lon, lat)
voltage=48.0V       # 总电压
cmd=(15.0,10.0,-15.0,-10.0,750)  # 执行的控制命令
```

### 二进制报文查看

#### 启用十六进制显示

```bash
# Mock AMD 配置
# config/bridge_params.protocol_udp.yaml
protocol_udp:
  log_packet_hex: true
  log_hex_bytes: 48

# Sniffer
/usr/bin/python3 scripts/sniffer.py --show-hex --hex-bytes 145
```

#### 十六进制格式

```
[mock-amd RX][CKTH] frame=138 obj=1 mode=0xEE instr=0x00 cmd=(15.0,10.0,-15.0,-10.0,50.0) main_rpm=750 side_rpm=0 heading=87.2deg hex=24 43 4b 54 48 00 8a 01 ...
```

#### 协议结构

**$CKTH 下行 (72 字节)**:
```
偏移   长度   说明
0x00   4      帧头 "$CKTH"
0x04   2      帧序号
0x06   1      目标地址
0x07   1      控制模式字节
0x08   1      工作指令
0x09-0x0C 4   舵面角度 (右,上,左,下)
0x0D-0x0E 2   主电机 RPM
0x0F-0x10 2   侧推器 RPM
0x11-0x12 2   目标航向
...           其他参数
0x45   1      XOR 校验和
0x46-0x47 2   帧尾 0xFFFF
```

**$AUV 上行 (145 字节)**:
```
偏移   长度   说明
0x00   5      帧头 "$AUV\x91"
0x05   2      帧序号
0x07   1      AUV 地址
0x08   1      控制模式字节
0x09   1      工作指令
...           遥测数据
0x26-0x27 2   深度 (0.1m 单位)
0x34-0x35 2   航向 (0.1deg 单位)
0x58-0x59 2   电压 (0.1V 单位)
0x8E   1      XOR 校验和
0x8F-0x90 2   帧尾 0xFFFF
```

## ASCII 报文记录

### 功能说明

除了二进制报文和十六进制显示外，系统还支持 ASCII 报文记录，便于人工阅读和文本处理。

### 启用 ASCII 记录

#### 方法 1: 配置文件

```yaml
# config/bridge_params.protocol_udp.yaml
protocol_udp:
  log_packets: true
  log_ascii_format: true      # 启用 ASCII 格式
  log_packet_hex: false       # 关闭十六进制（可选）
```

#### 方法 2: 命令行

```bash
# 使用 ASCII 格式输出
/usr/bin/python3 scripts/sniffer.py --ascii-format
```

### ASCII 格式输出

```
===== ASCII PROTOCOL PACKET =====
Direction: DOWNLINK ($CKTH)
Timestamp: 2026-04-10 23:54:12.123456
Source: 127.0.0.1:52364

Frame Number: 138
Object Address: 1
Control Mode: 0xEE (AUTONOMOUS)
Work Instruction: 0x00

Control Surfaces:
  Right Fin:  15.0 deg
  Top Fin:    10.0 deg
  Left Fin:  -15.0 deg
  Bottom Fin: -10.0 deg
  Thrust:     50.0 %

Motors:
  Main Motor: 750 RPM
  Side Motor: 0 RPM

Orientation:
  Heading: 87.2 deg

Checksum: OK (0x7A)
Frame Tail: OK (0xFFFF)
=================================
```

## 调试工作流

### 问题 1: 检查通信链路

```bash
# 1. 启动 sniffer
/usr/bin/python3 scripts/sniffer.py --show-hex

# 2. 启动系统
bash start_foxglove_holoocean_ros.sh --bridge-backend protocol_udp

# 3. 查看是否有报文
# sniffer 应该显示 $CKTH 和 $AUV 报文
```

### 问题 2: 解析特定报文

```python
# 解析报文内容
from common.protocol import parse_downlink_packet, parse_uplink_packet

# 读取二进制报文
with open("packet.bin", "rb") as f:
    packet = f.read()

# 解析
if packet[:4] == b"$CKTH":
    state = parse_downlink_packet(packet)
    print(f"控制模式: {state.control_mode_byte}")
    print(f"推力: {state.thrust_percent}%")
elif packet[:5] == b"$AUV\x91":
    telemetry = parse_uplink_packet(packet)
    print(f"深度: {telemetry.depth_m}m")
    print(f"航向: {telemetry.heading_deg}deg")
```

### 问题 3: 验证控制闭环

```bash
# 1. 查看 Mock AMD 日志中的控制命令
grep "mode=0xEE" launcher.log | tail -20

# 2. 验证推力非零
grep "cmd=(" launcher.log | grep -v "cmd=(0.0,0.0,0.0,0.0,0.0)"

# 3. 检查状态变化
grep "depth=" launcher.log | awk '{print $1, $NF}'
```

## 日志分析工具

### 时间轴分析

```bash
# 提取时间戳和帧序号
grep "frame=" launcher.log | awk '{print $1, $NF}'

# 计算报文频率
grep -c "CKTH" launcher.log
grep -c "AUV" launcher.log
```

### 状态机分析

```bash
# 追踪控制模式变化
grep "mode=0x" launcher.log | awk '{print $1, $6}'

# 统计各模式出现次数
grep "mode=0x" launcher.log | awk '{print $6}' | sort | uniq -c
```

### 错误检测

```bash
# 查找解析失败
grep "decode_failed" launcher.log

# 查找校验和错误
grep "checksum" launcher.log

# 查找异常值
grep "depth=" launcher.log | awk -F'depth=' '{print $2}' | awk '{print $1}' | awk '$1 > 100 || $1 < 0'
```

## 相关文档

- [控制调试指南](02_control_debugging.md) - 控制回路调试
- [运行模式切换](01_mode_switching.md) - 模式切换详解
- [命令参考](../06_reference/03_command_reference.md) - sniffer 命令

## 快速参考

### 常用命令

```bash
# 查看实时日志
ros2 topic echo /auv/sensors/imu

# 查看协议报文
/usr/bin/python3 scripts/sniffer.py --show-hex

# 分析 bag
mcap info bag.mcap

# 提取话题
mcap filter bag.mcap --filter "topic == '/auv/sensors/depth'" -o output.mcap
```

### 日志位置

```
ROS2 Bag:     log/experiments/*/experiment_runs/*/*.mcap
Mock AMD:     experiment_runs/*/launcher.log
Sniffer:      sniffer.log
Telemetry:    bridge_telemetry.jsonl
```

### 关键端口

```
UDP 绑定:     52364
UDP 远程:     52365
Sniffer 镜像: 可配置
```
