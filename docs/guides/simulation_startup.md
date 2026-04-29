# 🎬 仿真侧启动指南

本文档介绍如何在 Linux 环境下启动 AUV 仿真系统（HoloOcean + Zenoh 桥接）。

---

## 前置条件

### 必需
- Python 3.10+
- HoloOcean 仿真环境（已安装）
- 依赖包：`requirements.txt` 已安装

### 可选
- Zenoh 运行时（仅在需要跨进程通信时）
- ROS2 Humble（仅在需要与决策侧联动时）

---

## 快速启动

### 方式 1：仅运行仿真（推荐用于快速验证）

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/start_lin_sim.sh sim
```

**预期输出**：
- HoloOcean 环境初始化
- 仿真主循环启动，打印每步的状态
- 默认运行 150+ 步仿真

**日志级别**：默认为 INFO，查看 `config/sim_params.yaml` 调整

---

### 方式 2：仿真 + Zenoh 桥接（推荐用于完整系统）

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/start_lin_sim.sh both
```

**预期输出**：
- 仿真主循环启动
- Zenoh 桥接启动，发布传感数据到 Zenoh topic：
  - `rt/auv/sensors/imu` — IMU 数据
  - `rt/auv/sensors/dvl` — DVL（Doppler Velocity Logger）数据
  - `rt/auv/telemetry` — 完整的遥测数据
- 监听控制指令 `rt/auv/control/cmd_vel`

---

### 方式 3：使用 PVS 仿真后端（高保真仿真）

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/start_lin_sim.sh both --sim-backend pvs --backend protocol_udp
```

**说明**：
- `--sim-backend pvs` — 切换到 PVS 仿真后端（比 HoloOcean 更高保真）
- `--backend protocol_udp` — 切换到二进制协议桥接（而非 Zenoh JSON）

详见 [PVS 调试指南](pvs_debugging.md)

---

### 方式 4：纯二进制协议（与实物相同）

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/start_lin_sim.sh both --backend protocol_udp
```

**说明**：
- 仿真通过二进制协议（而非 Zenoh JSON）发布数据
- 便于与实物协议验证一致性

---

## 配置参数

所有仿真参数位于 `config/sim_params.yaml`。常用参数：

```yaml
simulation:
  backend: holoocean          # 仿真后端：holoocean 或 pvs
  dt: 0.0333                  # 仿真步长（秒）
  ticks_per_sec: 30           # 仿真 FPS
  max_steps: 4500             # 最大仿真步数
  log_level: INFO             # 日志级别：DEBUG/INFO/WARNING

control:
  target_u: 1.1               # 目标前进速度（m/s）
  depth:
    kp: 0.30
    ki: 0.01
  # ... 其他 PID 参数

trajectory:
  kind: cable_like_3d         # 轨迹类型：cable_like_3d/straight/circle
  duration: 150.0             # 轨迹时长（秒）
  surge_speed: 1.1            # 前进速度
  lateral_wavenumber: 0.25    # 横向波数（用于蛇形运动）
```

更多参数详见 [配置参数详解](configuration.md)

---

## 常见问题与排障

### Q: 仿真启动后立即崩溃
**A**: 检查 HoloOcean 环境是否正确安装：
```bash
python -c "import holoocean; print(holoocean.__version__)"
```

### Q: Zenoh 桥接启动失败
**A**: 确保 Zenoh 后端可用或禁用：
```bash
# 检查 Zenoh 配置
cat config/bridge_params.yaml

# 或使用纯本地模式
bash scripts/start_lin_sim.sh sim  # 不启用 Zenoh
```

### Q: 仿真速度太慢
**A**: 调整以下参数：
- 增加 `simulation.ticks_per_sec` 以加快仿真速度
- 减少 `max_steps` 以缩短实验时长
- 关闭可视化（若启用）以释放 GPU

### Q: 控制指令不生效
**A**: 检查：
1. 确保 Zenoh 桥接正常运行（`bash scripts/start_lin_sim.sh both`）
2. 确保有其他进程发送 `rt/auv/control/cmd_vel` 消息
3. 查看日志确认指令被正确解析

---

## 下一步

- ✅ 仿真成功启动后，阅读 [完整端到端设置](end_to_end_setup.md) 来启动 ROS2 决策侧
- 📊 若需要进行长实验，查看 [实验配置指南](experiment_guide.md)
- 🔧 遇到问题，查看 [HoloOcean 调试指南](holoocean_debugging.md) 或 [PVS 调试指南](pvs_debugging.md)

---

**更新日期**：2026-04-25
