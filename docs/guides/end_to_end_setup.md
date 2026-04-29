# 🔄 完整端到端设置指南

本文档介绍如何实现从 HoloOcean 仿真到 ROS2 决策的完整闭环系统，包含可视化监控。

---

## 系统架构概览

```
┌──────────────────────────────────────────────────────────────┐
│ 1. HoloOcean 仿真 (Python)                                  │
│    - 环境初始化与物理仿真                                    │
│    - 传感器模拟（IMU、DVL、位置等）                           │
└──────────────────────┬───────────────────────────────────────┘
                       │ Zenoh JSON 或 Protocol UDP
┌──────────────────────┴───────────────────────────────────────┐
│ 2. Zenoh 桥接 (Python)                                       │
│    - 发布仿真传感数据到 ROS2 compatible topics              │
│    - 接收决策指令反馈给仿真                                  │
└──────────────────────┬───────────────────────────────────────┘
                       │ ROS2 DDS
┌──────────────────────┴───────────────────────────────────────┐
│ 3. ROS2 决策栈 (Linux Humble)                               │
│    - auv_bridge: Zenoh ↔ ROS2 适配                         │
│    - auv_localization: ES-EKF 状态估计                      │
│    - auv_controller: PID 控制器                              │
│    - auv_decision: 行为树决策                               │
└──────────────────────┬───────────────────────────────────────┘
                       │ /cmd_vel
┌──────────────────────┴───────────────────────────────────────┐
│ 4. Foxglove 可视化 (Web Browser)                            │
│    - 实时显示车体位置、朝向、深度                            │
│    - 显示来自决策栈的控制指令                                │
│    - 参数动态调整                                            │
└──────────────────────────────────────────────────────────────┘
```

---

## 一键启动（推荐）

如果你已经配置好所有环保，可以使用一个脚本启动整个系统：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/start_foxglove_holoocean_ros.sh
```

**预期输出**：
- HoloOcean 仿真环境启动
- Zenoh 桥接启动
- ROS2 决策栈启动（4 个核心节点）
- Foxglove 浏览器窗口打开

**耗时**：30-60 秒

---

## 分步启动（用于调试和理解）

如果需要分别控制各个部分，按以下步骤操作：

### 步骤 1：启动 HoloOcean 仿真 + Zenoh 桥接

**终端 1**：
```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/start_lin_sim.sh both
```

**验证**：
- HoloOcean 环境窗口出现
- 仿真循环每秒打印状态
- Zenoh 发布消息到以下 topic：
  - `rt/auv/sensors/imu`
  - `rt/auv/sensors/dvl`
  - `rt/auv/telemetry`

### 步骤 2：激活 ROS2 环境并启动决策栈

**终端 2**：
```bash
source /opt/ros/humble/setup.bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/start_lin_brain.sh bootstrap  # 首次需要编译
bash scripts/start_lin_brain.sh stack
```

**验证**：
- 看到 4 个节点启动成功
- `ros2 topic list` 显示以下 topic：
  - `/imu` （来自 Zenoh 桥接的 IMU 数据）
  - `/dvl` （来自 Zenoh 桥接的 DVL 数据）
  - `/auv/state/filtered` （定位器输出）
  - `/auv/control/setpoint` （决策输出）
  - `/cmd_vel` （控制器输出）

### 步骤 3：启动 Foxglove 可视化

**终端 3**：
```bash
source /opt/ros/humble/setup.bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/start_lin_brain.sh foxglove
```

或手动启动：
```bash
ros2 launch foxglove_bridge foxglove_bridge_launch.xml
```

**验证**：
- 在浏览器中打开 `http://localhost:3000`
- 应该看到 Foxglove 界面加载

---

## 实时监控与调试

### 查看 Topic 数据

```bash
# 查看 IMU 数据更新频率
ros2 topic hz /imu

# 实时查看定位器输出
ros2 topic echo /auv/state/filtered

# 实时查看控制指令
ros2 topic echo /cmd_vel
```

### 调整参数

在运行过程中，可以无需重启就调整参数（若节点支持 ROS2 参数）：

```bash
# 查看当前参数
ros2 param list /auv_controller

# 调整控制器的深度 Kp
ros2 param set /auv_controller control.depth.kp 0.50

# 验证修改
ros2 param get /auv_controller control.depth.kp
```

---

## 长实验运行（120+ 秒 Benchmark）

对于需要覆盖多次轨迹循环的长实验：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/start_experiment.sh --duration 120 --bag-storage mcap
```

**说明**：
- 自动启动仿真 + ROS2 决策 + 数据记录
- 运行 120 秒后自动停止并保存 rosbag
- Rosbag 保存在 `log/` 目录，便于事后回放与分析

**回放记录**：
```bash
ros2 bag play log/<timestamp>/rosbag2_*
```

---

## 常见问题与排障

### Q: 仿真启动成功但决策栈无法连接
**A**: 检查 Zenoh 桥接：
```bash
# 确保 Zenoh 桥接在运行
ps aux | grep zenoh_bridge

# 检查 Zenoh topic 是否有数据
```

### Q: ROS2 节点看不到数据
**A**: 验证端口与网络配置：
```bash
# 确保 DDS 发现正常
ros2 topic list

# 检查 ROS_DOMAIN_ID（可能需要统一）
echo $ROS_DOMAIN_ID

# 若需要跨网络，检查防火墙
```

### Q: Foxglove 连接不上 ROS2
**A**: 确保 Foxglove 桥接运行在同一网络/域：
```bash
# 检查 Foxglove 桥接进程
ps aux | grep foxglove

# 尝试在本机重启桥接
bash scripts/start_lin_brain.sh foxglove
```

### Q: 决策与仿真不同步（命令没有反馈给仿真）
**A**: 检查控制指令的反向链路：
1. 确保仿真在监听 `rt/auv/control/cmd_vel` topic
2. 检查 Zenoh 桥接是否正确转发了控制指令
3. 查看仿真日志中是否收到指令

```bash
# 在仿真终端查看日志
# 应该看到类似 "Received cmd_vel: [...]"
```

---

## 高级配置

### 使用 Protocol UDP 代替 Zenoh JSON

若需要使用与水下实物相同的二进制协议：

```bash
# 仿真侧
bash scripts/start_lin_sim.sh both --backend protocol_udp

# 决策侧
bash scripts/start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238
```

### 启用仲裁器（自主/遥控权仲裁）

```bash
bash scripts/start_lin_brain.sh stack --arbiter-profile
```

详见 [仲裁器长期路线图](../仲裁器长期路线图_2026-04-08.md)

### 使用 PVS 仿真后端（更高保真）

```bash
bash scripts/start_lin_sim.sh both --sim-backend pvs
```

详见 [PVS 调试指南](pvs_debugging.md)

---

## 性能与资源

### 典型资源占用
- **HoloOcean 仿真**：CPU 2-3 核，内存 1-2 GB
- **ROS2 决策栈**：CPU 0.5-1 核，内存 500 MB
- **Foxglove**：浏览器标签，取决于 GPU

### 优化建议
- 若 CPU 占用过高，减少 `simulation.ticks_per_sec`
- 若内存占用过高，减少 `max_steps` 或禁用日志文件写入
- 若网络延迟，检查 Zenoh 配置中的传输协议（UDP vs TCP）

---

## 下一步

- 📊 完整系统测试后，查看 [实验配置指南](experiment_guide.md)
- 🔧 若遇到问题，查看对应的 [调试指南](#-调试与排障)
- 📝 若需要自定义行为，修改 `brain_linux/src/auv_decision/` 中的行为树配置
- 🤖 若需要集成实物，查看 [实物通信协议对接建议](../实物通信协议对接建议_2026-03-31.md)

---

**更新日期**：2026-04-25
