# 运行模式切换指南

本文档介绍如何在不同的运行模式之间切换，包括通信后端、控制模式和仲裁器模式。

## 概述

AUV 项目支持多种灵活的运行模式，主要分为三大类：

1. **仿真后端**（PVS / HoloOcean）
2. **通信后端**（Zenoh JSON / Protocol UDP）
3. **控制模式**（自主 / 手动 / 仲裁器）

---

## 仿真后端切换

### 选择 PVS（推荐）

PVS（Python Vehicle Simulator）是推荐的默认选择，特别是在容器环境中：

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project/scripts

# 仅启动 PVS 仿真
bash start_lin_sim.sh sim --sim-backend pvs

# 启动 PVS + 桥接
bash start_lin_sim.sh both --sim-backend pvs
```

### 选择 HoloOcean

如果需要3D可视化或更高保真度的仿真：

```bash
# 仅启动 HoloOcean 仿真
bash start_lin_sim.sh sim --sim-backend holoocean

# 启动 HoloOcean + 桥接
bash start_lin_sim.sh both --sim-backend holoocean
```

---

## 通信后端切换

通信后端定义了仿真层和决策层之间的通信方式。

### Zenoh JSON 模式（默认，推荐开发）

使用 JSON 格式的 Zenoh 通信，便于调试和开发：

```bash
# 仿真侧
bash start_lin_sim.sh both --sim-backend pvs --backend zenoh_json

# ROS2 决策侧
bash start_lin_brain.sh stack --backend zenoh_json
```

**特点**
- JSON 数据格式易于理解和调试
- 适合算法开发
- 快速迭代测试

### Protocol UDP 模式（推荐硬件对接）

使用二进制 UDP 协议，模拟真实硬件通信：

```bash
# 仿真侧（启用 Protocol UDP
bash start_lin_sim.sh both --sim-backend pvs --backend protocol_udp

# ROS2 决策侧
bash start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238
```

**特点**
- 二进制协议（$CKTH 下行，$AUV 上行
- 真实硬件通信模拟
- 支持校验和验证

---

## 配置文件说明

### PVS 配置

**sim_params.pvs.yaml
```yaml
simulation:
  backend: pvs

bridge:
  backend: zenoh_json  # 或 protocol_udp
```

### HoloOcean 配置

**sim_params.yaml**
```yaml
simulation:
  backend: holoocean

bridge:
  backend: zenoh_json
```

### Protocol UDP 专用配置

**bridge_params.protocol_udp.yaml**
```yaml
bridge:
  backend: protocol_udp
  protocol_udp:
    bind_host: 0.0.0.0
    bind_port: 52364
    remote_host: 127.0.0.1
    remote_port: 52365
```

---

## 控制模式切换

### 自主模式

自主模式启用 PID 控制器自动控制：

```bash
bash start_lin_brain.sh stack --protocol-control-mode-byte 238
```

控制模式字节说明：

| 字节值 | 说明 |
|-------|------|
| 0x00 | 手动模式 |
| 0xEA | 外部指令透传 |
| 0xEE | 自主模式（默认） |

### 手动模式

在手动模式下，决策层不进行自主控制：

```bash
bash start_lin_brain.sh stack --protocol-control-mode-byte 0
```

---

## 完整模式组合示例

### 场景 1：PVS + Zenoh JSON（标准开发）

```bash
# 终端 1
bash start_lin_sim.sh both --sim-backend pvs --backend zenoh_json

# 终端 2
bash start_lin_brain.sh stack --backend zenoh_json
```

### 场景 2：PVS + Protocol UDP（硬件仿真）

```bash
# 终端 1
bash start_lin_sim.sh both --sim-backend pvs --backend protocol_udp

# 终端 2
bash start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238
```

### 场景 3：启用仲裁器

```bash
# 终端 1
bash start_lin_sim.sh both --sim-backend pvs --backend protocol_udp

# 终端 2
bash start_lin_brain.sh stack --arbiter-profile
```

---

## 验证模式切换

### 验证仿真后端

启动后检查终端输出中的仿真后端标识：

```
[Sim] Backend: pvs  # 或 holoocean
```

### 验证通信后端

启动后检查通信方式标识：

```
[Bridge] Backend: zenoh_json  # 或 protocol_udp
```

Protocol UDP 模式下会看到协议帧输出：

```
[Mock AMD] $AUV frame 1: AUV=1, Mode=AUTONOMOUS
[Mock AMD] Checksum: OK
```

---

## 常见问题

### 问题1：切换模式后通信失败

确保仿真侧和决策侧必须使用相同的通信后端：

```bash
# 错误示例（不同步）
终端1: --backend zenoh_json
终端2: --backend protocol_udp  # ❌ 不匹配

# 正确示例（同步）
终端1: --backend protocol_udp
终端2: --backend protocol_udp  # ✅ 匹配
```

### 问题2：Protocol UDP 模式下无数据

确保使用正确的控制模式字节：

```bash
# 自主模式
--protocol-control-mode-byte 238
```

---

## 下一步

- 学习如何使用 [控制调试](02_control_debugging.md) 调整控制参数
- 了解 [PVS 架构](../02_architecture/02_pvs_architecture.md) 更详细的内容
