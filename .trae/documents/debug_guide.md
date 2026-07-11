# AUV 调试指南

## 调试模式说明

### DebugLevel 调试级别

| 级别 | 值 | 激活行为 | 用途 |
|------|----|----------|------|
| `AUTO` | 0 | 主任务流 | 正常巡检模式 |
| `HOLD` | 1 | 定深定航 | 验证 PID 控制稳定性 |
| `PATH` | 2 | 解析式轨迹跟踪 | 验证 LOS 导引律 |
| `FULL` | 3 | 主任务流 | 全功能调试 |

### 设置调试级别

在 `SensorStatusData` 中设置 `debug_level` 字段：

```python
from auv_decision_core.models import SensorStatusData

status = SensorStatusData(
    debug_level=1,  # 0=AUTO, 1=HOLD, 2=PATH, 3=FULL
    depth_m=4.0,
    heading_rad=0.0,
    # ... 其他字段
)
engine.set_sensor_status(status)
```

## 常用调试命令

### 启动仿真 + 桥接

```bash
# 启动仿真和 Zenoh 桥接
bash scripts/start_lin_sim.sh both

# 使用 Protocol UDP 后端
bash scripts/start_lin_sim.sh both --bridge-backend protocol_udp
```

### 启动 ROS2 决策栈

```bash
# 启动完整决策栈
bash scripts/start_lin_brain.sh stack

# 仅启动控制器节点
ros2 run auv_controller auv_controller_node

# 启动决策节点
ros2 run auv_decision_ros decision_node
```

### Foxglove 可视化

```bash
# 生成布局文件
cd foxglove_layout_project
python -m foxglove_layout_project.generator.build_layout --pretty

# 一键联动启动
bash scripts/start_foxglove_holoocean_ros.sh
```

## 监控与日志

### ROS2 话题监听

```bash
# 监听控制命令
ros2 topic echo /cmd_vel

# 监听控制目标
ros2 topic echo /auv/control/setpoint

# 监听滤波状态
ros2 topic echo /auv/state/filtered

# 监听控制器调试信息
ros2 topic echo /auv/controller/debug

# 查看所有话题
ros2 topic list

# 查看话题信息
ros2 topic info /auv/controller/debug
```

### Zenoh 数据查看

```bash
# 订阅 Zenoh 主题
zenoh sub "rt/auv/sensors/imu"

# 发布测试数据
zenoh pub "rt/auv/control/cmd_vel" '{"right": 0.0, "top": 0.0, "left": 0.0, "bottom": 0.0, "thrust": 50.0}'
```

## 故障排查

### 常见问题

#### 1. 控制器无输出

**症状**: `/cmd_vel` 无消息发布

**排查步骤**:
```bash
# 检查 Setpoint 是否到达
ros2 topic echo /auv/control/setpoint

# 检查状态估计是否到达
ros2 topic echo /auv/state/filtered

# 检查控制器日志
ros2 node info /auv_controller_node
```

**可能原因**:
- Setpoint 未发布
- 状态估计未发布
- 控制器节点未启动

---

#### 2. 行为树不执行

**症状**: 行为树 tick 无输出

**排查步骤**:
```python
# 检查行为树状态
engine = DecisionTreeEngine()
print(engine.unicode_tree())
print(f"当前行为: {engine.current_behavior_name()}")
print(f"激活路径: {engine.active_path()}")
```

**可能原因**:
- `sensor_status` 未正确设置
- 紧急条件被触发（漏水/低电/穿底）
- 置信度阈值未满足

---

#### 3. 仲裁器问题

**症状**: 控制命令不响应或模式切换失败

**排查步骤**:
```bash
# 检查仲裁器状态
ros2 topic echo /auv/arbiter/status

# 检查 PC 原始命令
zenoh sub "rt/pc/cmd_raw"

# 检查 MPC 命令
ros2 topic echo /auv/mpc/cmd
```

**切换到遥控模式**:
```python
arbiter = CommandArbiter()
arbiter.force_remote()  # 强制切换到遥控模式
```

---

#### 4. 通信延迟

**症状**: 控制响应缓慢

**排查步骤**:
```bash
# 查看控制器延迟日志
ros2 topic echo /auv/controller/debug | grep latency

# 使用 ros2 topic hz 检查频率
ros2 topic hz /auv/sensors/imu
ros2 topic hz /cmd_vel
```

**延迟指标**:
- IMU: 期望 100Hz
- 控制输出: 期望 20Hz
- 状态估计: 期望 30Hz

---

#### 5. 姿态保护触发

**症状**: 控制器输出异常，速度被限制

**排查步骤**:
```python
# 检查调试信息中的 attitude_guard_active
debug = engine.get_target_motion_state()
print(f"姿态保护激活: {debug.get('attitude_guard_active')}")
print(f"当前俯仰: {debug.get('current_pitch_deg')}")
print(f"当前横滚: {debug.get('current_roll_deg')}")
```

**姿态保护阈值**:
- 横滚: ±120°（默认）
- 俯仰: ±45°（默认）

---

#### 6. 海底安全限速

**症状**: 速度突然降低

**排查步骤**:
```python
status = SensorStatusData()
print(f"近底警告: {status.seabed_proximity_warning}")
print(f"穿底警告: {status.seabed_penetration_warning}")
print(f"海底净空: {status.seabed_clearance_m}m")
```

## 调试工具

### 行为树可视化

```python
# 打印行为树结构
engine = DecisionTreeEngine()
print(engine.unicode_tree())

# 获取当前激活路径
print(f"Active Path: {engine.active_path()}")

# 获取当前行为名称
print(f"Current Behavior: {engine.current_behavior_name()}")
```

### PID 控制器调试

```python
# 查看控制器调试信息
cmd, debug = controller.compute(state, target)
print(f"深度误差: {debug['depth_error']:.2f}m")
print(f"俯仰误差: {math.degrees(debug['pitch_error']):.2f}°")
print(f"航向误差: {math.degrees(debug['yaw_error']):.2f}°")
print(f"速度误差: {debug['speed_error']:.2f}m/s")
print(f"增益缩放: {debug['gain_scale']:.2f}")
print(f"饱和状态: pitch={debug['pitch_saturated']}, yaw={debug['yaw_saturated']}, thrust={debug['thrust_saturated']}")
```

### 协议调试

```python
# 验证传感器数据
from common.protocol import validate_sensor_payload, Z_PATH_IMU

payload = {
    "accel_ned": [0.1, 0.2, 9.8],
    "gyro_ned": [0.01, 0.02, 0.03],
    "step": 42,
    "sim_time": 21.5
}

ok, errors = validate_sensor_payload(Z_PATH_IMU, payload)
if not ok:
    print(f"验证失败: {errors}")

# 验证控制命令
from common.protocol import validate_control_payload

cmd_payload = {"command": [0.0, 10.0, 0.0, -10.0, 50.0]}
ok, errors = validate_control_payload(cmd_payload)
if not ok:
    print(f"控制命令验证失败: {errors}")
```

## 参数调优

### PID 参数调整

修改 `brain_linux/config/params.yaml`:

```yaml
control:
  depth:
    kp: 1.0    # 增大加快响应，减小更稳定
    ki: 0.1    # 增大消除稳态误差，减小避免积分饱和
    kd: 0.0    # 增大抑制振荡，减小避免噪声放大
  
  pitch:
    kp: 8.0
    ki: 0.5
    kd: 2.0
  
  yaw:
    kp: 6.0
    ki: 0.3
    kd: 1.5
```

### 限制参数调整

```yaml
limits:
  fin_deg_max: 30.0      # 舵叶最大偏角，仿真环境通常设为 30°
  thrust_min: 0.0        # 最小推力
  thrust_max: 100.0      # 最大推力
```

## 常用日志级别

```bash
# 设置 ROS2 日志级别
ros2 run auv_controller auv_controller_node --ros-args --log-level DEBUG

# 设置特定节点日志级别
ros2 param set /auv_controller_node logger.level debug
```

---

**生成时间**: 2026-04-29
