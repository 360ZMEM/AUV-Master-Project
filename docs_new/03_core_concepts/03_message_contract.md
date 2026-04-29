# 消息契约与数据真值表

本文档介绍系统中所有消息格式的权威定义。

## 核心原则

**`common/` 目录是单一真值源**

所有 topic 路径、JSON 键名、枚举、物理常量都必须从这里导入，禁止在各个子系统中重复定义。

## Topic 映射表

### 上行 Topic (仿真 → 决策)

| 逻辑名 | Zenoh 路径 | ROS2 Topic | 数据类型 |
|--------|-----------|-----------|----------|
| 真实状态 | `rt/auv/sensors/ground_truth` | - | JSON |
| IMU | `rt/auv/sensors/imu` | `/auv/sensors/imu` | sensor_msgs/Imu |
| DVL | `rt/auv/sensors/dvl` | `/auv/sensors/dvl` | 自定义 |
| Depth | `rt/auv/sensors/depth` | `/auv/sensors/depth` | sensor_msgs/FluidPressure |
| Magnetic | `rt/auv/sensors/magnetic` | `/auv/sensors/magnetic` | geometry_msgs/Vector3 |
| Sonar | `rt/auv/sensors/sonar` | `/auv/sensors/sonar` | 自定义 |

### 下行 Topic (决策 → 仿真)

| 逻辑名 | Zenoh 路径 | ROS2 Topic | 数据类型 |
|--------|-----------|-----------|----------|
| 控制指令 | `rt/auv/control/cmd_vel` | `/cmd_vel` | geometry_msgs/Twist |
| 控制目标 | - | `/auv/control/setpoint` | auv_interfaces/Setpoint |

### ROS2 内部 Topic

| Topic | 类型 | 说明 |
|-------|------|------|
| `/auv/state/filtered` | nav_msgs/Odometry | 融合后的状态估计 |
| `/auv/controller/debug` | auv_interfaces/ControllerDebug | 控制器调试信息 |
| `/auv/diagnostics` | auv_interfaces/Diagnostics | 系统诊断信息 |

## 消息格式定义

### ground_truth (真实状态)

```json
{
  "step": 1000,
  "sim_time": 10.5,
  "ts": 1712808000.0,
  "position_ned": [100.0, 50.0, -5.0],
  "rpy_ned": [0.1, 0.05, 1.57],
  "cable_closest_ned": [95.0, 50.0, -10.0],
  "cable_distance_m": 5.5
}
```

### imu (IMU 数据)

```json
{
  "step": 1000,
  "sim_time": 10.5,
  "ts": 1712808000.0,
  "accel_ned": [0.01, -0.02, 9.81],
  "gyro_ned": [0.001, 0.002, 0.003]
}
```

### dvl (DVL 数据)

```json
{
  "step": 1000,
  "sim_time": 10.5,
  "ts": 1712808000.0,
  "vel_ned": [1.0, 0.0, -0.1],
  "valid": true
}
```

### depth (深度数据)

```json
{
  "step": 1000,
  "sim_time": 10.5,
  "ts": 1712808000.0,
  "depth_m": 5.23
}
```

### 控制指令 (cmd_vel)

ROS2 Twist 格式：

```json
{
  "linear": {
    "x": 10.0,    // 主推 (%) -100 到 100
    "y": 0.0,
    "z": 0.0      // 垂向推力
  },
  "angular": {
    "x": 15.0,    // 右舵角 (deg) -45 到 45
    "y": -10.0,   // 上舵角 (deg)
    "z": 0.0      // 下舵角 (deg)
  }
}
```

### 控制目标 (setpoint)

```json
{
  "mode": "ZIGZAG_SEARCH",
  "target_depth_m": 4.0,
  "target_heading_rad": 0.0,
  "target_speed_mps": 0.4
}
```

## 枚举定义

### 行为模式 (BehaviorMode)

| 枚举值 | 字符串 | 说明 |
|--------|--------|------|
| `IDLE` | `"IDLE"` | 空闲 |
| `DIVING` | `"DIVING"` | 下潜 |
| `ZIGZAG_SEARCH` | `"ZIGZAG_SEARCH"` | Z 字搜索 |
| `PARALLEL_TRACK` | `"PARALLEL_TRACK"` | 并行巡检 |
| `EMERGENCY_SURFACE` | `"EMERGENCY_SURFACE"` | 紧急上浮 |

### 故障码 (FaultCode)

| 枚举值 | 字符串 | 说明 |
|--------|--------|------|
| `LEAK_DETECTED` | `"LEAK_DETECTED"` | 漏水检测 |
| `LOW_VOLTAGE` | `"LOW_VOLTAGE"` | 低电压 |

### 漏水等级 (LeakLevel)

| 枚举值 | 数值 | 说明 |
|--------|------|------|
| `NONE` | 0 | 无漏水 |
| `INTERNAL` | 1 | 内部漏水 |
| `EXTERNAL` | 2 | 外部漏水 |
| `BOTH` | 3 | 内外同时漏水 |

## 物理常量

| 常量名 | 数值 | 单位 | 说明 |
|--------|------|------|------|
| `GRAVITY_MPS2` | 9.81 | m/s² | 重力加速度 |
| `MAX_THRUST_PERCENT` | 100.0 | % | 最大推力 |
| `MAX_RUDDER_DEG` | 45.0 | deg | 最大舵角 |
| `WATER_DENSITY_KGPM3` | 1000.0 | kg/m³ | 水密度 |

## 字段校验

### 校验函数位置
```python
# common/protocol.py
def validate_sensor_payload(topic: str, payload: dict) -> bool:
    """校验传感器数据包"""
    ...

def normalize_control_command(cmd: dict) -> dict:
    """归一化控制指令"""
    ...
```

### 校验规则

1. **类型校验**: 确保字段类型正确
2. **范围校验**: 数值在合理范围内
3. **完整性校验**: 必需字段存在
4. **单位校验**: 单位正确（如角度 vs 弧度）

## 使用建议

### 修改字段的标准流程

1. **先改 `common/`**
   ```python
   # common/protocol.py
   NEW_TOPIC = "rt/auv/sensors/new_sensor"
   ```

2. **再改仿真侧**
   ```python
   # sim_holoocean/interfaces/holoocean_physics_bridge.py
   payload[NEW_FIELD] = value
   ```

3. **再改 ROS2 侧**
   ```python
   # brain_linux/src/auv_bridge/auv_bridge/bridge_node.py
   msg.new_field = payload[NEW_FIELD]
   ```

4. **最后改文档**
   ```markdown
   # 更新本文档
   ```

**禁止** 只在单个子系统修改字段！

## 参考代码

### Topic 常量定义
```python
# common/protocol.py
class Topics:
    # 上行
    GROUND_TRUTH = "rt/auv/sensors/ground_truth"
    IMU = "rt/auv/sensors/imu"
    DVL = "rt/auv/sensors/dvl"
    DEPTH = "rt/auv/sensors/depth"

    # 下行
    CMD_VEL = "rt/auv/control/cmd_vel"
```

### 校验示例
```python
# common/protocol.py
def validate_sensor_payload(topic: str, payload: dict) -> bool:
    required_keys = ['step', 'sim_time', 'ts']
    if not all(k in payload for k in required_keys):
        return False

    if topic == Topics.IMU:
        return 'accel_ned' in payload and 'gyro_ned' in payload

    return True
```

## 相关文档

- [字段真值表详细版](../06_reference/01_field_truth_table.md) - 完整的字段参考
- [通信协议](02_communication_protocol.md) - 协议层设计
- [坐标系统一](01_coordinate_systems.md) - 坐标系转换
