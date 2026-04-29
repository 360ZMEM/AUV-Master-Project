# 控制调试指南

本文档帮助你诊断和修复控制回路问题。

## 控制回路概览

```
传感器输入 → 状态估计 → 控制器 → 执行器 → AUV
    ↑                                        ↓
    └──────────────── 反馈 ───────────────────┘
```

## 问题诊断流程

### 第一步：确认数据流

#### 1.1 检查传感器数据

```bash
# 查看 IMU 数据
ros2 topic echo /auv/sensors/imu --once

# 查看深度数据
ros2 topic echo /auv/sensors/depth --once

# 查看 DVL 数据
ros2 topic echo /auv/sensors/dvl --once
```

**健康标志**:
- 数据持续更新
- 数值在合理范围内
- 时间戳递增

#### 1.2 检查状态估计

```bash
# 查看融合后的状态
ros2 topic echo /auv/state/filtered --once
```

**健康标志**:
- `pose.pose.position.z` (深度) 合理
- `twist.twist.linear.x` (速度) 合理
- `pose.pose.orientation` (姿态) 合理

#### 1.3 检查控制目标

```bash
# 查看决策层输出
ros2 topic echo /auv/control/setpoint --once
```

**健康标志**:
- `target_depth_m` 有明确值
- `target_heading_rad` 有明确值
- `target_speed_mps` 有明确值

#### 1.4 检查控制指令

```bash
# 查看控制器输出
ros2 topic echo /cmd_vel --once
```

**健康标志**:
- `linear.x` (推力) 不为 0
- `angular.*` (舵角) 在 [-45, 45] 范围内

### 第二步：定位问题环节

#### 场景 1: 传感器数据异常

**症状**: 传感器数据缺失或异常

**检查**:
```bash
# 检查话题发布频率
ros2 topic hz /auv/sensors/imu

# 检查传感器原始数据
ros2 topic echo /auv/sensors/imu
```

**可能原因**:
- 仿真侧未正确发布
- 桥接节点问题
- 网络连接问题

**解决方案**:
```bash
# 1. 重启桥接节点
ros2 run auv_bridge zenoh_json_bridge_node

# 2. 检查仿真侧
# 在仿真终端查看日志
```

#### 场景 2: 状态估计发散

**症状**: 状态估计值异常或不稳定

**检查**:
```bash
# 查看诊断信息
ros2 topic echo /auv/diagnostics --once

# 查看状态估计详情
ros2 topic echo /auv/state/filtered
```

**可能原因**:
- EKF 参数不合理
- 传感器数据质量差
- 初值设置错误

**解决方案**:
```bash
# 1. 调整 EKF 参数
# 编辑 brain_linux/config/params.yaml
localization:
  ekf:
    process_noise: 0.01
    measurement_noise: 0.1

# 2. 重启 localization 节点
ros2 run auv_localization localization_node
```

#### 场景 3: 控制器饱和

**症状**: 舵面长期打满，控制效果差

**检查**:
```bash
# 查看控制器调试信息
ros2 topic echo /auv/controller/debug --once
```

**健康指标**:
- `depth_error` < 1.0 m
- `yaw_error` < 10 deg
- `pitch_saturated`: false
- `yaw_saturated`: false

**可能原因**:
- 目标值不合理
- PID 参数过大
- 角速度反馈缺失

**解决方案**:

1. **检查目标值**
```bash
# 查看目标是否合理
ros2 topic echo /auv/control/setpoint | grep target
```

2. **降低 PID 增益**
```yaml
# brain_linux/config/params.yaml
control:
  pitch:
    kp: 0.3  # 降低增益
    kd: 0.1
  yaw:
    kp: 0.5  # 降低增益
    kd: 0.2
```

3. **检查角速度反馈**
```bash
# 查看角速度是否为 0
ros2 topic echo /auv/state/filtered --once | grep angular
```

#### 场景 4: 深度控制不稳定

**症状**: 深度振荡或无法收敛

**诊断步骤**:

1. **查看深度误差**
```bash
ros2 topic echo /auv/diagnostics | grep depth_error
```

2. **查看目标俯仰角**
```bash
ros2 topic echo /auv/controller/debug | grep target_pitch
```

3. **查看舵面输出**
```bash
ros2 topic echo /cmd_vel --once
```

**解决方案**:

1. **降低深度外环的期望俯仰角**
```yaml
# brain_linux/config/params.yaml
control:
  depth:
    target_pitch_deg_max: 8.0  # 从 15 降低
```

2. **调整 pitch PID**
```yaml
control:
  pitch:
    kp: 0.3   # 降低比例
    kd: 0.15  # 增加阻尼
```

3. **增加深度微分项**
```yaml
control:
  depth:
    kd: 0.5   # 增加深度微分增益
```

#### 场景 5: 航向控制失效

**症状**: 航向偏差大或持续旋转

**诊断步骤**:

1. **查看航向误差**
```bash
ros2 topic echo /auv/controller/debug | grep yaw_error
```

2. **确认目标航向**
```bash
ros2 topic echo /auv/control/setpoint | grep target_heading
```

**解决方案**:

1. **确保决策层输出合理航向目标**
   - 检查行为树是否正确设置航向
   - 避免目标航向固定为 0

2. **调整 yaw PID**
```yaml
control:
  yaw:
    kp: 0.8   # 根据实际情况调整
    kd: 0.3
```

## 常用调试命令

### 实时监控
```bash
# 监控深度
ros2 topic hz /auv/sensors/depth

# 监控控制指令
ros2 topic hz /cmd_vel

# 监控状态估计
ros2 topic hz /auv/state/filtered
```

### 数据记录
```bash
# 记录所有话题
ros2 bag record -a -o debug_bag

# 记录特定话题
ros2 bag record /auv/sensors/depth /cmd_vel /auv/state/filtered

# 回放数据
ros2 bag play debug_bag
```

### 参数查看
```bash
# 查看当前参数
ros2 param list

# 查看特定参数
ros2 param get /controller_node control.depth.kp
```

## 性能指标

### 延迟参考

| 环节 | 正常延迟 | 警告阈值 |
|------|---------|---------|
| 传感器采集 | < 1 ms | > 5 ms |
| 状态估计 | < 10 ms | > 30 ms |
| 控制计算 | < 5 ms | > 20 ms |
| 总延迟 | < 50 ms | > 100 ms |

### 频率参考

| 信号 | 期望频率 | 最低频率 |
|------|---------|---------|
| 传感器数据 | 50-100 Hz | > 20 Hz |
| 状态估计 | 50-100 Hz | > 20 Hz |
| 控制指令 | 20-50 Hz | > 10 Hz |

## 调参建议

### 调参顺序

1. **先调外环，再调内环**
   - 深度 → 俯仰 → 舵面
   - 航向 → 偏航 → 方向舵

2. **先调比例，再调微分，最后调积分**
   - kp → kd → ki

3. **从小到大，逐步增加**
   - 避免参数过大导致振荡

### PID 参数参考

#### 深度控制
```yaml
control:
  depth:
    kp: 0.3    # 比例增益
    ki: 0.01   # 积分增益（消除稳态误差）
    kd: 0.5    # 微分增益（增加阻尼）
    target_pitch_deg_max: 8.0  # 最大期望俯仰角
```

#### 俯仰控制
```yaml
control:
  pitch:
    kp: 0.3    # 不要太大，避免打满
    ki: 0.0    # 一般不用积分
    kd: 0.15   # 增加阻尼
```

#### 偏航控制
```yaml
control:
  yaw:
    kp: 0.5    # 根据实际情况调整
    ki: 0.0    # 一般不用积分
    kd: 0.2    # 增加阻尼
```

## 高级调试

### 使用 rqt_console 查看日志
```bash
ros2 run rqt_console rqt_console
```

### 使用 rqt_graph 查看节点图
```bash
ros2 run rqt_graph rqt_graph
```

### 使用 Foxglove 可视化
```bash
# 启动完整系统
bash scripts/start_foxglove_holoocean_ros.sh

# 在 Foxglove 中查看：
# - 实时数据曲线
# - 控制指令可视化
# - 系统状态监控
```

## 相关文档

- [运行模式切换](01_mode_switching.md) - 切换不同运行模式
- [日志解读](03_log_analysis.md) - 分析系统日志
- [性能监控](04_performance_monitoring.md) - 监控系统性能
