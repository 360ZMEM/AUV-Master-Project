# 系统架构概览

本文档从高层次介绍 AUV 联合开发平台的整体架构设计。

## 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户界面层                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Foxglove    │  │  Python GUI  │  │  命令行工具  │          │
│  │  可视化       │  │  上位机      │  │  & 脚本     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└────────┬──────────────────┬──────────────────┬─────────────────┘
         │                  │                  │
         │ Zenoh/UDP        │ ROS2             │ ROS2
         ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      决策与控制层 (brain_linux)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │decision  │  │controller│  │localization│ │  bridge  │       │
│  │行为树决策 │  │ PID控制  │  │ ES-EKF   │  │ 桥接节点 │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
│       │             │             │             │              │
│       └─────────────┴─────────────┴─────────────┘              │
│                         ROS2 DDS                                 │
└────────────────────────────┬────────────────────────────────────┘
                             │ Zenoh / UDP
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       仿真层 (sim_holoocean)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ HoloOcean│  │ 传感模拟 │  │ 物理引擎 │  │ Zenoh    │       │
│  │ 渲染引擎 │  │          │  │          │  │ 桥接     │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
└────────────────────────────┬────────────────────────────────────┘
                             │ UDP
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       实物层 (可选)                              │
│  ┌──────────┐  ┌──────────┐                                    │
│  │   AMD    │  │  传感器  │                                    │
│  │  运动控制 │  │  实物设备 │                                    │
│  └──────────┘  └──────────┘                                    │
└─────────────────────────────────────────────────────────────────┘
```

## 分层说明

### 1. 用户界面层
提供多种交互方式：
- **Foxglove**: 基于 Web 的实时数据可视化
- **Python GUI**: 上位机控制界面
- **命令行工具**: 自动化脚本和调试工具

### 2. 决策与控制层 (brain_linux)
基于 ROS2 Humble 的决策系统：
- **decision**: 行为树决策节点
- **controller**: PID 控制器
- **localization**: ES-EKF 状态估计
- **bridge**: 通信桥接节点

### 3. 仿真层 (sim_holoocean)
基于 HoloOcean 的高保真仿真：
- **HoloOcean**: UE4 渲染引擎
- **传感模拟**: IMU、DVL、深度计等传感器仿真
- **物理引擎**: 水动力学仿真
- **Zenoh 桥接**: 数据通信桥接

### 4. 实物层 (可选)
支持与实物硬件连接：
- **AMD**: 实物运动控制器
- **传感器**: 实物传感器设备

## 数据流向

### 上行数据流 (传感器数据)

```
HoloOcean 仿真
  ↓ (原始传感器数据)
sim_holoocean/interfaces/holoocean_physics_bridge.py
  ↓ (统一 JSON 格式，经过 common.protocol 校验)
Zenoh Topic 发布 (rt/auv/sensors/*)
  ↓
brain_bridge (桥接层)
  ↓ (ROS2 消息)
auv_localization (ES-EKF 滤波)
  ↓
/auv/state/filtered (状态估计)
```

### 下行数据流 (控制指令)

```
auv_decision (行为树)
  ↓
/auv/control/setpoint (控制目标)
  ↓
auv_controller (PID 控制器)
  ↓
/cmd_vel (底层控制指令)
  ↓
brain_bridge (桥接层)
  ↓ (归一化与仲裁)
Zenoh Topic 发布 (rt/auv/control/cmd_vel)
  ↓
sim_holoocean (执行控制命令)
```

## 核心设计原则

### 1. 单一真值源

所有数据定义、协议、枚举、常量都来自 `common/` 目录：

```
common/
├── protocol.py    # Topic 路径、JSON 键名、校验函数
├── enums.py       # 状态、故障码、枚举定义
└── physics.py     # 物理常量、限幅函数
```

### 2. 环境分离

- **仿真层** 不含决策逻辑
- **ROS2 层** 不含 HoloOcean API 调用
- **算法层** 环境无关，可单独测试

### 3. 通信边界校验

所有跨模块消息必须经过校验：

```python
# 仿真侧发布前
common.protocol.validate_sensor_payload(topic, payload)

# 决策侧消费时
保留原始语义，不在 UI 层偷偷改名
```

### 4. 坐标系统一

使用 NED（北东地）坐标系：

```
UE4 坐标系 ←→ NED 坐标系
sim_holoocean/interfaces/frame_transform.py
```

## 模块职责

### common (契约层)
- 定义数据结构
- 定义通信协议
- 定义物理常量
- 提供校验函数

### algorithm (算法层)
- PID 控制器
- 导引算法
- 轨迹生成
- 状态滤波

### sim_holoocean (仿真层)
- HoloOcean 场景管理
- 传感器数据模拟
- 物理仿真
- Zenoh 桥接

### brain_linux (决策层)
- ROS2 节点管理
- 行为决策
- 状态估计
- 通信桥接

## 扩展性设计

### 可插拔的桥接后端

支持多种通信方式：

```python
# bridge_backends.py
class ZenohJsonBackend:
    """Zenoh JSON 通信"""

class ProtocolUdpBackend:
    """二进制 UDP 协议"""
```

### 可配置的仲裁器

支持不同的控制仲裁策略：

```python
# arbiter.py
class CommandArbiter:
    """命令仲裁器"""
    - Remote 透传
    - Autonomous 自主
    - Manual 手动抢占
```

## 技术栈

| 层级 | 技术栈 |
|------|--------|
| 界面层 | Foxglove, PySide6 |
| 决策层 | ROS2 Humble, Python |
| 通信层 | Zenoh, UDP |
| 仿真层 | HoloOcean, UE4 |
| 算法层 | Python, NumPy |

## 下一步

继续了解：
- [分层设计](02_layered_design.md) - 各层的详细设计
- [数据流设计](03_data_flow.md) - 数据如何流动
- [仲裁器架构](04_arbiter_architecture.md) - 控制仲裁设计
