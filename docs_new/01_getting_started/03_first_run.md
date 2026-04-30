# 第一次运行

安装完成后，让我们启动第一个仿真！

## ⚠️ 重要：选择仿真后端

本项目支持**两个独立的仿真后端**，你可以根据需求选择：

### 🎯 后端选择指南

| 后端 | 特点 | 适用场景 | 推荐程度 |
|------|------|---------|---------|
| **PVS** (推荐) | 纯 Python 实现，无需图形环境，轻量快速，可在容器中运行 | 算法开发、CI/CD、容器环境、长期测试 | ⭐⭐⭐⭐⭐ |
| **HoloOcean** | 高保真物理仿真，UE4 渲染，真实水下环境 | 可视化演示、传感器仿真、3D 可视化 | ⭐⭐⭐ |

### 📌 后端对比详解

#### **PVS 后端 (Python Vehicle Simulator)**
```
✅ 优点：
  - 纯 Python，无图形依赖
  - 可在 headless 环境（容器）中完美运行
  - 启动速度快，资源占用低
  - 内置 PID 控制器和轨迹生成
  - 适合算法验证和快速迭代

❌ 局限：
  - 没有 3D 可视化（但可通过 Foxglove 可视化数据）
  - 物理模型较为简化

🖥️ 命令标识：
  --sim-backend pvs
```

#### **HoloOcean 后端**
```
✅ 优点：
  - UE4 物理引擎，真实水下环境
  - 3D 可视化窗口
  - 多种海洋场景和 AUV 模型
  - 高保真传感器仿真

❌ 局限：
  - 需要图形驱动支持
  - 在容器/服务器环境运行较困难
  - 启动较慢，资源占用高

🖥️ 命令标识：
  --sim-backend holoocean (默认)
```

---

## 🚀 启动方式选择（PVS 优先）

### ✨ 方式 1: 仅启动 PVS 仿真（强烈推荐新手）

**最简单的启动方式！** 只启动 PVS 仿真，不涉及 ROS2 决策端。

```bash
cd ~/AUV_Master_Project/scripts
bash start_lin_sim.sh sim --sim-backend pvs
```

**预期结果**:
- 终端显示仿真进度
- 显示传感器数据（IMU、DVL、深度等）
- AUV 按照预设轨迹运动
- 运行完成后显示性能指标（RMS、误差等）

### ✨ 方式 2: PVS 仿真 + 桥接

启动 PVS 仿真并启用 Zenoh 数据桥接。

```bash
cd ~/AUV_Master_Project/scripts
bash start_lin_sim.sh both --sim-backend pvs
```

**预期结果**:
- 终端显示仿真和桥接日志
- 传感器数据通过 Zenoh 发布
- 可以看到桥接发布的 topic 日志

### ✨ 方式 3: PVS 仿真 + Protocol UDP 桥接

模拟真实硬件通信（二进制 UDP 协议）。

```bash
cd ~/AUV_Master_Project/scripts
bash start_lin_sim.sh both --sim-backend pvs --backend protocol_udp
```

**预期结果**:
- 显示 Mock AMD 服务器日志
- 二进制协议包编码/解码信息
- 可看到 $AUV 上行和 $CKTH 下行协议帧

### ✨ 方式 4: 完整系统（PVS + 决策）

一键启动完整系统（如果有 Foxglove SDK）：

```bash
cd ~/AUV_Master_Project/scripts
bash start_foxglove_pvs_ros.sh
```

或者分别启动（推荐调试）：

**终端 1 - 启动 PVS 仿真和桥接**:
```bash
cd ~/AUV_Master_Project/scripts
bash start_lin_sim.sh both --sim-backend pvs
```

**终端 2 - 启动 ROS2 决策端**:
```bash
cd ~/AUV_Master_Project/scripts
bash start_lin_brain.sh stack
```

---

## 🐳 如何在容器中运行（PVS 完美支持）

如果你在容器环境中，**只使用 PVS 后端**，完全没问题！

### 快速烟测（容器环境）
```bash
# 快速验证 PVS 后端
cd ~/AUV_Master_Project/scripts
timeout 10s bash start_lin_sim.sh sim --sim-backend pvs
```

### 运行完整测试
```bash
# 运行完整测试（会自动终止）
cd ~/AUV_Master_Project
/usr/bin/python3 -m pytest tests/ -v
```

---

## 🔍 验证系统运行

### 检查 ROS2 Topics（如果启动了决策端）

在新的终端中：

```bash
# Source 环境
source /opt/ros/humble/setup.bash
source ~/AUV_Master_Project/brain_linux/install/setup.bash

# 查看话题列表
ros2 topic list

# 应该看到以下话题：
# /auv/sensors/imu
# /auv/sensors/dvl
# /auv/sensors/depth
# /auv/state/filtered
# /auv/control/setpoint
# /cmd_vel
```

### 查看实时数据

```bash
# 查看 IMU 数据
ros2 topic echo /auv/sensors/imu --once

# 查看深度数据
ros2 topic echo /auv/sensors/depth --once

# 查看控制指令
ros2 topic echo /cmd_vel --once

# 查看状态估计
ros2 topic echo /auv/state/filtered --once
```

---

## 📊 PVS 配置参数

如果需要调整 PVS 仿真，编辑 `config/sim_params.pvs.yaml`：

```yaml
# 控制参数
control:
  target_u: 1.1             # 目标前向速度 (m/s)
  depth:
    kp: 0.30               # 深度环 P 增益
    ki: 0.01               # 深度环 I 增益
  yaw:
    kp: 9.0                # 航向环 P 增益

# 轨迹参数
trajectory:
  kind: cable_like_3d     # 轨迹类型
  duration: 54.5          # 轨迹持续时间 (s)
  start: [0.0, 0.0, -12.0]  # 起始位置
```

---

## 🛑 停止系统

在各个运行窗口按 `Ctrl+C` 停止对应的程序。

**停止顺序建议**:
1. 先停止 ROS2 决策端（brain_linux）
2. 再停止仿真桥接
3. 最后关闭仿真

---

## 🎛️ 运行模式说明

### 通信后端选择

项目支持两种通信桥接模式（与仿真后端独立选择）：

#### **zenoh_json 模式（默认，推荐开发）**
使用 Zenoh JSON 格式通信，易于调试和开发。
```bash
bash start_lin_sim.sh both --sim-backend pvs --backend zenoh_json
bash start_lin_brain.sh stack --backend zenoh_json
```

#### **protocol_udp 模式（推荐硬件对接）**
使用二进制 UDP 协议，模拟真实硬件通信。
```bash
bash start_lin_sim.sh both --sim-backend pvs --backend protocol_udp
bash start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238
```

### 仲裁器模式
启用控制仲裁器，支持自主/手动模式切换。
```bash
bash start_lin_brain.sh stack --arbiter-profile
```

---

## 💡 第一次运行建议

对于第一次运行，**强烈建议按以下顺序**：

1. **先跑 PVS standalone 仿真**
   - 命令：`bash start_lin_sim.sh sim --sim-backend pvs`
   - 目的：确认仿真环境和算法正常
   - 观察：终端输出和性能指标

2. **再试 PVS + Zenoh 桥接**
   - 命令：`bash start_lin_sim.sh both --sim-backend pvs`
   - 目的：确认数据通信正常
   - 观察：Zenoh topic 发布日志

3. **最后跑完整系统（可选）**
   - 命令：分别启动仿真和决策端
   - 目的：验证端到端闭环

---

## 📈 性能参考

正常运行的性能指标（PVS 后端）：

| 指标 | 预期值 |
|------|--------|
| 仿真帧率 | 30-50 Hz |
| 传感器延迟 | < 1ms |
| 状态融合延迟 | ~10ms |
| 控制延迟 | ~20ms |
| 总端到端延迟 | < 50ms |
| 轨迹跟踪 RMS | < 2.5m |

---

## 🔗 下一步

成功运行后，你可以：
- 阅读 [系统架构概览](../02_architecture/01_system_architecture.md) 了解系统设计
- 查看 [常见问题](04_faq.md) 解决遇到的问题
- 了解 [Mock AMD](../03_core_concepts/04_mock_amd.md) 硬件模拟
- 开始修改配置和参数进行实验

---

## ❓ 遇到问题？

如果第一次运行遇到问题：
1. 检查 [常见问题](04_faq.md)
2. 查看 [日志解读指南](../05_operations/05_log_analysis.md)
3. 参考 [控制调试指南](../05_operations/02_control_debugging.md)
4. 确认选择了正确的仿真后端（PVS vs HoloOcean）
