# 🧠 决策侧启动指南

本文档介绍如何在 Linux 环境下启动 AUV 的 ROS2 决策栈（包含行为树、控制器、定位器等）。

---

## 前置条件

### 必需
- **ROS2 Humble** 已安装：`source /opt/ros/humble/setup.bash`
- **本项目** 已克隆：`/home/gwxie/master_work-tmp/AUV_Master_Project`
- **colcon** 工具：通常随 ROS2 一起安装

### 可选
- **HoloOcean 仿真**（若需完整闭环）
- **Foxglove** 可视化（若需实时监控）

---

## 快速启动

### 第一次使用：Bootstrap（编译与配置）

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/start_lin_brain.sh bootstrap
```

**耗时**：5-10 分钟（首次编译）  
**输出日志**：
- `colcon build` 编译日志
- 成功后：`Summary: X packages finished [OK]`

---

### 启动完整决策栈

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/start_lin_brain.sh stack
```

**预期启动的节点**：
1. **auv_bridge** — Zenoh ↔ ROS2 DDS 适配器（预留）
2. **auv_localization** — ES-EKF 状态估计器，订阅 `/imu` 和 `/dvl`，发布 `/auv/state/filtered`
3. **auv_controller** — 控制器，订阅 `/auv/control/setpoint` 和 `/auv/state/filtered`，发布 `/cmd_vel`
4. **auv_decision** — 行为树决策，发布 `/auv/control/setpoint`

**成功标志**：
```
[INFO] [auv_bridge-1]: process started with PID [...]
[INFO] [auv_localization-1]: process started with PID [...]
[INFO] [auv_controller-1]: process started with PID [...]
[auv_decision-1]: process started with PID [...]
```

---

### 启动特定节点

```bash
# 仅启动行为树决策
bash scripts/start_lin_brain.sh decision

# 仅启动控制器
bash scripts/start_lin_brain.sh controller

# 仅启动定位器
bash scripts/start_lin_brain.sh localization

# 启动调试示例（接收 /imu 数据并打印）
bash scripts/start_lin_brain.sh example
```

---

### 高级启动选项

#### 使用特定的桥接后端

```bash
# Zenoh JSON 后端（默认）
bash scripts/start_lin_brain.sh stack --backend zenoh_json

# 二进制协议（protocol_udp）
bash scripts/start_lin_brain.sh stack --backend protocol_udp

# 指定控制模式字节（与实物协议相同）
bash scripts/start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238
```

#### 启用仲裁器（自主/遥控权仲裁）

```bash
bash scripts/start_lin_brain.sh stack --arbiter-profile
```

**说明**：启用自主控制权仲裁机制。详见 [仲裁器长期路线图](../仲裁器长期路线图_2026-04-08.md)

---

## 配置参数

所有 ROS2 相关参数位于 `config/` 和 `brain_linux/`：

### 主配置文件
- `brain_linux/config/controller_params.yaml` — 控制器参数（PID 增益等）
- `brain_linux/config/localization_params.yaml` — 定位器参数（ES-EKF）
- `brain_linux/config/decision_params.yaml` — 决策参数（行为树配置）

### 调整示例

```yaml
# 加大深度环的 Kp
controller:
  depth:
    kp: 0.50  # 从默认 0.30 提高

# 调整 ES-EKF 的过程噪声
localization:
  process_noise:
    velocity: 0.1
```

更多详见 [配置参数详解](configuration.md)

---

## 监控与调试

### 查看发布的 Topic

启动后，可用 ROS2 工具查看：

```bash
# 列出所有 topic
ros2 topic list

# 查看 /auv/state/filtered 的消息格式
ros2 topic info /auv/state/filtered

# 实时订阅并打印
ros2 topic echo /auv/state/filtered
```

### 启动 Foxglove 可视化

```bash
# 在另一个终端运行
bash scripts/start_lin_brain.sh foxglove

# 或手动启动 ROS2 Foxglove 桥接
ros2 launch foxglove_bridge foxglove_bridge_launch.xml
```

然后在 Foxglove 中可视化：
- `/auv/state/filtered` — 当前位置、朝向、速度
- `/cmd_vel` — 发送的速度指令
- `/auv/control/setpoint` — 当前的控制目标

### 查看节点日志

```bash
# 查看所有节点日志
ros2 topic list  # 或查看 logs/ 目录

# 某个节点专属日志（若应用支持）
grep "auv_controller" log/*/stdout
```

---

## 常见问题与排障

### Q: colcon build 失败
**A**: 确保 ROS2 环境已激活：
```bash
source /opt/ros/humble/setup.bash
cd brain_linux
colcon build --symlink-install
```

### Q: 节点启动但无消息输出
**A**: 检查消息来源：
1. 确保仿真侧也在运行（若需闭环）：`bash scripts/start_lin_sim.sh both`
2. 查看 `/auv/sensors/imu` 和 `/auv/sensors/dvl` 是否有数据
3. 检查日志级别：调整 `launch/*.py` 中的 `log_level`

### Q: 与实物通信失败
**A**: 检查协议配置：
```bash
# 查看当前使用的协议
grep "backend\|protocol_control_mode" config/*.yaml

# 与实物相同的配置
bash scripts/start_lin_brain.sh stack --backend protocol_udp --protocol-control-mode-byte 238
```

更多详见 [实物通信协议对接建议](../实物通信协议对接建议_2026-03-31.md)

### Q: 决策侧与仿真侧数据不同步
**A**: 检查 Zenoh 桥接或协议适配器：
1. 确保 `bridge_params.yaml` 中的 Zenoh 配置正确
2. 查看 auv_bridge 节点的日志
3. 使用 `ros2 topic hz /auv/sensors/imu` 检查消息频率

---

## 下一步

- ✅ 决策栈成功启动后，阅读 [完整端到端设置](end_to_end_setup.md) 来实现仿真↔决策闭环
- 📊 若需要参数调优，查看 [配置参数详解](configuration.md)
- 🔍 遇到问题，查看 [HoloOcean 联调指南](holoocean_debugging.md) 或控制问题记录
- 👁️ 若需实时可视化，启动 [Foxglove 配置指南](foxglove_setup.md)

---

**更新日期**：2026-04-25
