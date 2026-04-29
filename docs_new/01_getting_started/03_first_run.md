# 第一次运行

安装完成后，让我们启动第一个仿真！

## 启动方式选择

根据你的需求选择合适的启动方式：

### 方式 1: 仅启动仿真（推荐新手）

这种方式只启动 HoloOcean 仿真，不涉及 ROS2 决策端。

```bash
cd ~/AUV_Master_Project/scripts
bash start_lin_sim.sh sim
```

**预期结果**:
- HoloOcean 窗口打开
- 显示水下场景和 AUV 模型
- AUV 开始按照预设轨迹运动

### 方式 2: 仿真 + 桥接

启动仿真并启用 Zenoh 数据桥接。

```bash
cd ~/AUV_Master_Project/scripts
bash start_lin_sim.sh both
```

**预期结果**:
- HoloOcean 仿真窗口
- 终端显示传感器数据发布（IMU、DVL、深度等）
- 可以看到 Zenoh topic 发布日志

### 方式 3: 完整系统（仿真 + 决策）

一键启动完整系统：仿真、桥接、ROS2 决策栈。

```bash
cd ~/AUV_Master_Project/scripts
bash start_foxglove_holoocean_ros.sh
```

**预期结果**:
- HoloOcean 仿真窗口
- Foxglove 可视化界面
- ROS2 节点运行
- 完整的数据闭环

### 方式 4: 分别启动（适合调试）

分别启动仿真和决策端，适合调试使用。

**终端 1 - 启动仿真和桥接**:
```bash
cd ~/AUV_Master_Project/scripts
bash start_lin_sim.sh both
```

**终端 2 - 启动 ROS2 决策端**:
```bash
cd ~/AUV_Master_Project/scripts
bash start_lin_brain.sh stack
```

## 验证系统运行

### 检查 ROS2 Topics

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

### 使用 Foxglove 可视化

如果使用了完整系统启动，Foxglove 窗口会自动打开。你可以看到：
- 3D 轨迹显示
- 传感器实时数据
- 控制指令可视化
- 系统状态监控

## 停止系统

在各个运行窗口按 `Ctrl+C` 停止对应的程序。

**停止顺序建议**:
1. 先停止 ROS2 决策端（brain_linux）
2. 再停止仿真桥接
3. 最后关闭 HoloOcean

## 运行模式说明

### zenoh_json 模式（默认）

使用 Zenoh JSON 格式通信，适合仿真开发和调试。

```bash
bash start_lin_brain.sh stack --backend zenoh_json
```

### protocol_udp 模式

使用二进制 UDP 协议，模拟实物通信。

```bash
bash start_lin_sim.sh both --backend protocol_udp
bash start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238
```

### arbiter 模式

启用控制仲裁器，支持自主/手动模式切换。

```bash
bash start_lin_brain.sh stack --arbiter-profile
```

## 第一次运行建议

对于第一次运行，建议：

1. **先跑 standalone 仿真** - 确保仿真环境正常
2. **再试仿真+桥接** - 确认数据通信正常
3. **最后跑完整系统** - 验证端到端闭环

## 性能参考

正常运行的性能指标：

- 传感器延迟: < 1ms
- 状态融合延迟: ~10ms
- 控制延迟: ~20ms
- 总端到端延迟: < 50ms

## 下一步

成功运行后，你可以：
- 阅读 [系统架构概览](../02_architecture/01_system_architecture.md) 了解系统设计
- 查看 [常见问题](04_faq.md) 解决遇到的问题
- 开始修改配置和参数进行实验

## 遇到问题？

如果第一次运行遇到问题：
1. 检查 [常见问题](04_faq.md)
2. 查看 [日志解读指南](../05_operations/03_log_analysis.md)
3. 参考 [控制调试指南](../05_operations/02_control_debugging.md)
