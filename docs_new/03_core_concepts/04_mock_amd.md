# Mock AMD 技术详解

## 目录

1. [概述](#概述)
2. [设计目的](#设计目的)
3. [系统架构](#系统架构)
4. [核心组件](#核心组件)
5. [协议处理流程](#协议处理流程)
6. [坐标系统一](#坐标系统一)
7. [仿真集成](#仿真集成)
8. [日志与调试](#日志与调试)
9. [与真实 AMD 的差异](#与真实-amd-的差异)

## 概述

Mock AMD（Mock AUV Main Device）是一个在仿真环境中模拟真实 AMD（AUV 主控设备）行为的 UDP 服务器。它实现了 `$CKTH`（下行控制命令）和 `$AUV`（上行遥测数据）二进制协议，使得在没有实物硬件的情况下可以进行完整的控制回路测试。

### 核心特性

- **完整协议实现**：支持 `$CKTH/$AUV` 二进制协议的编解码
- **仿真集成**：与 HoloOcean 仿真环境深度集成
- **坐标转换**：内置 UE4 ↔ NED 坐标系转换
- **协议调试**：提供彩色日志输出和多种格式化选项
- **数据镜像**：支持 sniffer 镜像端口，便于抓包分析
- **实时控制**：支持 50Hz 控制频率

### 在系统中的位置

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  ROS2 决策层    │────────>│   Bridge Node   │────────>│   Mock AMD      │
│  (brain_linux)  │<────────│  (protocol_udp) │<────────│   (UDP Server)  │
└─────────────────┘         └─────────────────┘         └─────────────────┘
                                                              │
                                                              v
                                                        ┌─────────────────┐
                                                        │  HoloOcean      │
                                                        │  仿真环境        │
                                                        └─────────────────┘
```

## 设计目的

Mock AMD 的设计目标是在开发阶段提供一个可替代真实硬件的仿真环境，主要解决以下问题：

### 1. 硬件无关开发

- **场景**：在实物硬件未到位时进行软件开发
- **优势**：不依赖特定硬件，可以在任何有仿真环境的机器上开发
- **价值**：缩短开发周期，降低硬件依赖

### 2. 协议验证

- **场景**：验证 `$CKTH/$AUV` 协议实现的正确性
- **优势**：提供可控的测试环境，便于复现和调试协议问题
- **价值**：提高协议实现的可靠性

### 3. 控制算法测试

- **场景**：测试控制器在闭环环境下的表现
- **优势**：可以安全地进行各种边界测试和故障注入
- **价值**：降低实物测试风险

### 4. 长时间稳定性测试

- **场景**：进行数小时的连续运行测试
- **优势**：不受电池、水温等物理限制
- **价值**：提前发现潜在的系统稳定性问题

### 5. 协议教学与培训

- **场景**：向新团队成员介绍 AUV 通信协议
- **优势**：提供可视化的协议数据流
- **价值**：降低学习曲线

## 系统架构

### 架构层次

```
┌─────────────────────────────────────────────────────────────┐
│                     应用层 (Application)                      │
│  - run_zenoh_bridge.py                                       │
│  - 协议配置加载                                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│                   Mock AMD 服务器层                           │
│  - MockAmdUdpServer 类                                       │
│  - UDP 通信管理                                               │
│  - 协议编解码                                                 │
│  - 日志输出                                                   │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          v                   v                   v
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  命令守护模块   │ │  仿真接口模块   │ │  协议调试模块   │
│  CommandGuard   │ │  SimWrapper     │ │  ProtocolDebug  │
└─────────────────┘ └─────────────────┘ └─────────────────┘
          │                   │                   │
          v                   v                   v
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  命令边界保护   │ │  HoloOcean API  │ │  彩色日志输出   │
│  超时检测       │ │  状态查询       │ │  多格式支持     │
│  默认回退       │ │  控制执行       │ │  数据镜像       │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### 数据流向

#### 下行（Downlink）数据流

```
ROS2 决策层 → /cmd_vel → Bridge Node
                                    │
                                    v
                            Protocol UDP Backend
                                    │
                                    v
                        $CKTH 二进制包 (72 字节)
                                    │
                                    v
                    UDP Socket → 127.0.0.1:52364
                                    │
                                    v
                            Mock AMD 接收并解析
                                    │
                                    v
                        提取控制量：四舵角 + 推力
                                    │
                                    v
                        CommandGuard 边界保护
                                    │
                                    v
                            HoloOcean 执行控制
```

#### 上行（Uplink）数据流

```
HoloOcean 仿真步进
        │
        v
查询 AUV 状态（位姿、DVL、深度等）
        │
        v
UE4 坐标 → NED 坐标转换
        │
        v
打包 $AUV 二进制包 (145 字节)
        │
        v
UDP Socket → 127.0.0.1:52365
        │
        v
Bridge Node 接收
        │
        v
解析并发布到 ROS2 Topics
        │
        v
ROS2 决策层消费
```

## 核心组件

### 1. MockAmdUdpServer 类

**文件位置**: `sim_holoocean/interfaces/mock_amd_server.py`

**主要职责**:
- 管理 UDP 服务器生命周期
- 处理下行控制命令
- 生成上行遥测数据
- 协调仿真执行

**关键方法**:

| 方法 | 功能 |
|------|------|
| `open()` | 初始化仿真环境和 UDP 服务器 |
| `close()` | 清理资源，关闭服务器 |
| `run_forever()` | 主循环：接收命令、执行仿真、发送状态 |
| `_poll_command_packet()` | 非阻塞接收下行命令 |
| `_build_uplink_packet()` | 构建上行遥测包 |
| `_mirror_packet()` | 镜像数据到 sniffer 端口 |

### 2. CommandGuard 类

**文件位置**: `sim_holoocean/behavior/command_guard.py`

**主要职责**:
- 命令边界检查
- 超时保护
- 默认回退机制

**保护机制**:

```python
def sanitize(self, cmd_msg, default_cmd, last_cmd_ts):
    """命令安全处理流程"""
    # 1. 检查是否超时
    if time.time() - last_cmd_ts > self.cmd_timeout_s:
        return default_cmd  # 超时使用默认命令

    # 2. 检查命令格式
    if cmd_msg is None:
        return default_cmd

    # 3. 限幅检查
    cmd = np.clip(cmd_msg, self.min_limit, self.max_limit)

    # 4. 变化率限制
    if np.linalg.norm(cmd - self.last_safe_cmd) > self.max_delta:
        return self.last_safe_cmd  # 变化过大，使用上次安全命令

    return cmd
```

### 3. ProtocolDebug 模块

**文件位置**: `common/protocol_debug.py`

**主要职责**:
- 统一的协议包格式化
- 彩色日志输出
- 多种格式支持（单行、ASCII、原始十六进制）

**格式化选项**:

```python
# 单行摘要格式
[mock-amd RX][CKTH][127.0.0.1:52364] frame=138 obj=1 mode=0xEE cmd=(15.0,10.0,-15.0,-10.0,50.0)

# ASCII 详细格式
==================================================
ASCII PROTOCOL PACKET - DOWNLINK ($CKTH)
Timestamp: 2026-04-10 23:54:12.123
Source: 127.0.0.1:52364
--------------------------------------------------
HEADER INFO:
  Frame Number: 138
  Control Mode Byte: 0xEE (AUTONOMOUS)
...

# 原始十六进制格式
[mock-amd RX] len=72 24 43 4B 54 48 91 8A 00 ...
```

## 协议处理流程

### 下行命令处理（$CKTH）

```
┌─────────────────────────────────────────────────────────────┐
│ 1. UDP 接收                                                 │
│    socket.recvfrom() → 72 字节二进制数据                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ 2. 协议解析                                                 │
│    parse_downlink_packet()                                  │
│    - 验证帧头 (0x24 0x43 0x4B 0x54 0x48 0x91)                │
│    - 验证校验和                                              │
│    - 验证帧尾 (0xFF 0xFF)                                    │
│    - 提取各字段                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ 3. 日志记录                                                 │
│    format_protocol_packet()                                 │
│    - 根据配置选择格式                                        │
│    - 彩色输出到控制台                                        │
│    - 镜像到 sniffer 端口                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ 4. 命令提取                                                 │
│    提取控制量：                                              │
│    - right_fin_deg: 右舵角                                  │
│    - top_fin_deg: 上舵角                                    │
│    - left_fin_deg: 左舵角                                   │
│    - bottom_fin_deg: 下舵角                                 │
│    - thrust_percent: 推力百分比                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ 5. 命令守护                                                 │
│    CommandGuard.sanitize()                                  │
│    - 超时检查                                                │
│    - 边界限幅                                                │
│    - 变化率限制                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ 6. 仿真执行                                                 │
│    wrapper.step(cmd)                                        │
│    - 将控制量应用到 HoloOcean                               │
│    - 执行物理仿真步进                                        │
└─────────────────────────────────────────────────────────────┘
```

### 上行遥测生成（$AUV）

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 查询仿真状态                                             │
│    get_agent_state()                                        │
│    - PoseSensor: 位姿（位置 + 旋转）                        │
│    - DVLSensor: 多普勒速度                                  │
│    - DepthSensor: 深度                                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ 2. 坐标转换                                                 │
│    UE4 坐标系 → NED 坐标系                                  │
│    - pose_matrix_ue_to_ned(): 位姿矩阵转换                  │
│    - body_vector_ue_to_ned(): 速度向量转换                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ 3. 数据提取与处理                                           │
│    - depth_m: 深度（米）                                    │
│    - heading_deg: 航向角（度）                              │
│    - pitch_deg: 俯仰角（度）                                │
│    - roll_deg: 横滚角（度）                                 │
│    - dvl_speed_mps: DVL 速度（米/秒）                       │
│    - altitude_m: 高度（米）                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ 4. 协议打包                                                 │
│    build_uplink_packet()                                    │
│    - 填充 145 字节固定格式                                  │
│    - 计算校验和                                              │
│    - 添加帧尾                                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ 5. UDP 发送                                                 │
│    socket.sendto(packet, client_addr)                       │
│    - 发送到上次下行命令的来源地址                            │
│    - 同时镜像到 sniffer 端口                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              v
┌─────────────────────────────────────────────────────────────┐
│ 6. 日志记录                                                 │
│    - 单行摘要 / ASCII 格式                                  │
│    - 彩色输出                                                │
│    - 包含仿真步数                                            │
└─────────────────────────────────────────────────────────────┘
```

## 坐标系统一

Mock AMD 负责处理仿真环境（UE4 坐标系）与控制系统（NED 坐标系）之间的转换。

### 坐标系定义

#### UE4 坐标系（左手系）

```
      Z (上)
      │
      │
      └─── X (前)
     ╱
    ╱
   Y (右)
```

- X 轴：前向
- Y 轴：右向
- Z 轴：向上

#### NED 坐标系（右手系）

```
      N (北)
      │
      │
      │
      └─── E (东)
     ╱
    ╱
   ╱
  D (下)
```

- N 轴（X）：北向
- E 轴（Y）：东向
- D 轴（Z）：下向

### 转换关系

#### 位置转换

```
x_ned =  y_ue4
y_ned =  x_ue4
z_ned = -z_ue4
```

#### 旋转转换

```
Roll_NED  = -Roll_UE4
Pitch_NED =  Pitch_UE4
Yaw_NED   =  Yaw_UE4 + 90°
```

### 转换实现

**文件位置**: `sim_holoocean/interfaces/frame_transform.py`

```python
def pose_matrix_ue_to_ned(pose_ue4):
    """将 UE4 位姿矩阵转换为 NED 坐标系"""
    # 提取 UE4 位置和旋转
    position_ue4 = pose_ue4[:3, 3]
    rotation_ue4 = pose_ue4[:3, :3]

    # 位置转换
    position_ned = np.array([
        position_ue4[1],   # N = Y_ue4
        position_ue4[0],   # E = X_ue4
        -position_ue4[2]   # D = -Z_ue4
    ])

    # 旋转矩阵转换
    # ... (省略详细实现)

    return {
        'position_ned': position_ned,
        'rpy_ned': rpy_ned,
        'rotation_matrix_ned': rotation_matrix_ned
    }

def body_vector_ue_to_ned(vector_ue4):
    """将机体系向量从 UE4 转换到 NED"""
    return np.array([
        vector_ue4[1],   # 前向速度 (North)
        vector_ue4[0],   # 侧向速度 (East)
        -vector_ue4[2]   # 垂向速度 (Down)
    ])
```

## 仿真集成

Mock AMD 与 HoloOcean 仿真环境的集成通过 `HoloOceanSimWrapper` 实现。

### SimWrapper 接口

**文件位置**: `sim_holoocean/interfaces/sim_wrapper.py`

**主要方法**:

| 方法 | 功能 |
|------|------|
| `open()` | 启动 HoloOcean 仿真 |
| `reset_and_tick()` | 重置场景并执行一步 |
| `step(cmd)` | 应用控制命令并执行一步 |
| `close()` | 关闭仿真 |

### 控制命令映射

ROS2 `/cmd_vel` 到 HoloOcean 控制命令的映射：

```
ROS2 /cmd_vel.msg:
  linear.x  → thrust (推力百分比)
  angular.x → right_fin (右舵角)
  angular.y → top_fin (上舵角)
  angular.z → yaw (航向，用于方向舵)

HoloOcean 控制命令:
  [right_fin, top_fin, left_fin, bottom_fin, thrust]
```

### 传感器数据映射

HoloOcean 传感器到协议字段的映射：

| HoloOcean 传感器 | 协议字段 | 转换说明 |
|-----------------|---------|---------|
| PoseSensor | depth, heading, pitch, roll | UE4 → NED |
| DVLSensor | dvl_speed_mps | 体坐标系转换 |
| DepthSensor | depth_m | 符号处理 |
| (仿真配置) | altitude_m | 海底深度 - AUV 深度 |

## 日志与调试

### 日志级别

Mock AMD 提供三级日志详细程度：

#### 1. 单行摘要模式（默认）

```bash
[mock-amd RX][CKTH][127.0.0.1:52364] frame=138 obj=1 mode=0xEE cmd=(15.0,10.0,-15.0,-10.0,50.0)
[mock-amd TX][AUV][127.0.0.1:52365] frame=138 auv=1 mode=0xEE depth=7.60m heading=87.2deg step=051690
```

**适用场景**:
- 正常运行监控
- 长时间稳定性测试
- 性能基准测试

#### 2. ASCII 详细模式

```bash
==================================================
ASCII PROTOCOL PACKET - DOWNLINK ($CKTH)
Timestamp: 2026-04-10 23:54:12.123
Source: 127.0.0.1:52364
--------------------------------------------------
HEADER INFO:
  Frame Number: 138
  Control Mode Byte: 0xEE (AUTONOMOUS)
...
```

**适用场景**:
- 协议调试
- 问题诊断
- 数据验证

#### 3. 原始十六进制模式

```bash
[mock-amd RX] len=72 hex=24 43 4B 54 48 91 8A 00 01 EE 00 ...
```

**适用场景**:
- 底层协议分析
- 二进制数据问题排查
- 协议兼容性测试

### 配置选项

```yaml
# config/bridge_params.protocol_udp.yaml
protocol_udp:
  # 日志相关
  log_packets: true              # 是否记录报文
  log_raw_format: false           # 原始十六进制格式
  log_ascii_format: false         # ASCII 详细格式
  log_packet_hex: false           # 单行格式中包含十六进制
  log_hex_bytes: 48               # 十六进制显示字节数
  log_every_n: 1                  # 每 N 个报文记录一次

  # Sniffer 镜像
  sniffer_mirror_host: 127.0.0.1
  sniffer_mirror_port: 52366
```

### 调试技巧

#### 1. 检查命令接收

```bash
# 启用 ASCII 格式
vim config/bridge_params.protocol_udp.yaml
# 设置: log_ascii_format: true

# 启动仿真
bash scripts/start_lin_sim.sh both --backend protocol_udp

# 查看日志
grep "DOWNLINK" launcher.log | head -10
```

#### 2. 验证坐标转换

```bash
# 比较深度值
grep "depth=" launcher.log | tail -10

# 检查航向角范围
grep "heading=" launcher.log | awk '{print $NF}' | sort -n
```

#### 3. 监控控制频率

```bash
# 统计帧率
grep "frame=" launcher.log | wc -l

# 计算平均频率
# (帧数 / 运行时间)
```

## 与真实 AMD 的差异

### 相同点

| 特性 | Mock AMD | 真实 AMD |
|------|----------|---------|
| 协议格式 | ✅ `$CKTH/$AUV` 二进制 | ✅ `$CKTH/$AUV` 二进制 |
| 字段定义 | ✅ 完全一致 | ✅ 完全一致 |
| 通信方式 | ✅ UDP | ✅ UDP |
| 端口配置 | ✅ 可配置 | ✅ 固定/可配置 |
| 控制频率 | ✅ 可配置 | ✅ 固定 |

### 差异点

| 特性 | Mock AMD | 真实 AMD | 影响 |
|------|----------|---------|------|
| 数据来源 | HoloOcean 仿真 | 真实传感器 | 传感器噪声模型不同 |
| 物理延迟 | < 1ms | 10-100ms | 响应速度不同 |
| 通信延迟 | 本地 (μs) | 串口/网络 (ms) | 控制回路延迟不同 |
| 环境干扰 | 无 | 存在 | 需添加噪声模型 |
| 电源管理 | 模拟 | 真实 | 电压/电流数据不同 |
| 故障模式 | 有限 | 多样 | 需模拟更多故障 |

### 使用建议

#### 开发阶段

- 使用 Mock AMD 进行快速迭代
- 验证协议和算法逻辑
- 进行大部分功能测试

#### 集成测试阶段

- 在 Mock AMD 中添加传感器噪声
- 模拟通信延迟和丢包
- 测试各种故障模式

#### 实物验证阶段

- 在真实 AMD 上进行最终验证
- 重点关注环境相关特性
- 调整控制参数以适配真实硬件

## 常见问题

### Q1: Mock AMD 能完全替代真实 AMD 吗？

**答**: 不能。Mock AMD 主要用于协议验证和算法开发，无法完全模拟真实环境中的所有因素（如传感器噪声、通信干扰、硬件特性等）。

### Q2: 如何在 Mock AMD 中模拟传感器噪声？

**答**: 在 `_build_uplink_packet()` 中对传感器数据添加噪声：

```python
# 示例：添加高斯噪声
noisy_depth = depth_ned + np.random.normal(0, 0.03)
```

### Q3: Mock AMD 的控制频率可以调整吗？

**答**: 可以。在配置文件中设置 `rate_hz` 参数：

```yaml
bridge:
  rate_hz: 50.0  # 50 Hz
```

### Q4: 如何模拟通信延迟？

**答**: 在 `_poll_command_packet()` 或 `_build_uplink_packet()` 中添加 `time.sleep()`：

```python
# 模拟 20ms 单向延迟
time.sleep(0.02)
```

## 相关文档

- [Mock AMD 使用指南](../05_operations/08_mock_amd_guide.md) - 如何使用 Mock AMD
- [Mock AMD 协议通信详解](../05_operations/09_mock_amd_protocol.md) - 协议层面的详细说明
- [协议日志使用示例](../05_operations/06_protocol_logging_examples.md) - 日志和调试技巧
- [坐标系转换](../03_core_concepts/02_coordinate_systems.md) - 坐标系详细说明
