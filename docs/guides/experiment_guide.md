# 🧪 实验配置指南

本文档介绍如何运行长时间实验、数据记录、性能评估等。

---

## 快速启动长实验（120s Benchmark）

推荐的标准实验窗口是 120 秒，便于覆盖多个轨迹循环与系统变化：

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/start_experiment.sh --duration 120 --bag-storage mcap
```

**预期流程**：
1. 自动启动 HoloOcean 仿真
2. 启动 ROS2 决策栈
3. 运行 120 秒
4. 自动记录 rosbag 到 `log/` 目录
5. 自动停止并生成摘要

---

## 参数调整

### 修改实验时长

```bash
# 60 秒短实验
bash scripts/start_experiment.sh --duration 60 --bag-storage mcap

# 300 秒长实验（5 分钟）
bash scripts/start_experiment.sh --duration 300 --bag-storage mcap
```

### 调整轨迹参数

在 `config/sim_params.yaml` 中修改：

```yaml
trajectory:
  duration: 150.0              # 轨迹总时长（应略长于实验时长）
  surge_speed: 1.1             # 前进速度
  lateral_wavenumber: 0.25     # 蛇形频率（越小越频繁）
  lateral_amplitude: 20.0      # 蛇形摆幅
```

### 覆盖更多 zig-zag 循环

若需要多次蛇形运动：
```yaml
trajectory:
  duration: 150.0              # → 延长时长
  lateral_wavenumber: 0.12     # → 降低波数（增加频率）
  surge_speed: 0.8             # → 降低前进速度（留出更多空间）
```

---

## 数据回放与分析

### 查看记录的 rosbag 文件

```bash
# 列出所有实验日志
ls -lh log/

# 查看某个 rosbag 的信息
ros2 bag info log/rosbag2_2026-04-25_12-34-56/rosbag2.db3
```

### 回放数据

```bash
# 回放 rosbag（速度 1 倍）
ros2 bag play log/rosbag2_2026-04-25_12-34-56/

# 回放并以特定速度播放
ros2 bag play log/rosbag2_2026-04-25_12-34-56/ --rate 0.5  # 0.5 倍速
ros2 bag play log/rosbag2_2026-04-25_12-34-56/ --rate 2.0  # 2 倍速
```

### 导出特定 topic 数据

```bash
# 导出 IMU 数据到 CSV
ros2 bag export log/rosbag2_2026-04-25_12-34-56/ -o /tmp/imu.csv -t /imu

# 导出控制指令
ros2 bag export log/rosbag2_2026-04-25_12-34-56/ -o /tmp/cmd.csv -t /cmd_vel
```

---

## 性能评估

### 记录系统资源占用

实验运行时，在另一个终端监控：

```bash
# 实时查看 CPU 与内存占用
watch -n 1 'ps aux | grep -E "(python|ros2)" | grep -v grep'

# 或使用 top
top -p $(pgrep -f "main.py")  # 监控仿真进程
```

### 检查延迟

```bash
# 查看消息发布频率
ros2 topic hz /imu
ros2 topic hz /cmd_vel

# 查看网络延迟（Zenoh）
ros2 topic hz /auv/telemetry
```

---

## 常见问题

### Q: 实验中途中断，如何恢复？
**A**: 
1. 由于 Zenoh 连接问题，仿真会自动降级续行
2. ROS2 如果掉线，需要重启
3. 查看 `log/` 目录中的记录，可能已部分保存

### Q: rosbag 文件过大？
**A**: 
1. 增加 bag 轮转天数：修改 launch 文件中的参数
2. 减少记录的 topic（仅记录关键数据）
3. 使用压缩：`--compression-mode record`

### Q: 如何对比不同实验的结果？
**A**: 
1. 修改参数后再运行一次实验
2. 使用 rosbag 导处数据到 CSV
3. 用 Python/Matplotlib 对比绘图

---

**更新日期**：2026-04-25
