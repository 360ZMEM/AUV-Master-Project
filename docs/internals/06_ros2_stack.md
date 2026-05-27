# ROS2 决策栈

## 概述

`brain_linux/` ROS2 工作区包含 AUV 自主决策系统的完整节点拓扑。所有节点通过 ROS2 Topic 进行通信，由统一的 Launch 文件按序启动。

---

## 核心节点与启动时序

| 延迟 | 节点名 | 包名 | 职责 |
|------|--------|------|------|
| 0s | `zenoh_json_bridge_node` | `auv_bridge` | Zenoh-ROS2 桥接，负责协议帧与 ROS2 Topic 的双向转换 |
| 2s | `auv_localization_node` | `auv_localization` | ES-EKF 状态估计，融合 IMU/DVL/GPS/深度 |
| 3s | `zenoh_viz_bridge_node` | `auv_viz_bridge` | 可视化桥接，将状态数据推送至地面站 |
| 4s | `auv_controller_node` | `auv_controller` | 级联 PID / MPC 控制器执行 |
| 6s | `auv_decision_node` | `auv_decision_ros` | 行为树决策引擎 |

启动延迟确保上游节点就绪后下游才开始订阅，避免启动瞬态丢失关键消息。

---

## 完整 Topic 通信拓扑

### zenoh_json_bridge_node (auv_bridge)

| 方向 | Topic | 消息类型 | 说明 |
|------|-------|----------|------|
| 发布 | `/auv/sensors/imu` | `sensor_msgs/Imu` | IMU 原始数据 |
| 发布 | `/auv/sensors/dvl` | `geometry_msgs/TwistStamped` | DVL 速度 |
| 发布 | `/auv/sensors/depth` | `std_msgs/Float64` | 深度 |
| 发布 | `/auv/sensors/gps` | `sensor_msgs/NavSatFix` | GPS 定位 |
| 发布 | `/auv/sensors/status` | `auv_interfaces/SensorStatus` | 传感器健康状态 |
| 发布 | `/auv/sensors/voltage` | `std_msgs/Float64` | 电池电压 |
| 订阅 | `/cmd_vel` | `geometry_msgs/Twist` | 控制输出 |
| 订阅 | `/auv/control/arbiter_cmd` | `auv_interfaces/MpcCmd` | 仲裁后指令 |

### auv_localization_node (auv_localization)

| 方向 | Topic | 消息类型 | 说明 |
|------|-------|----------|------|
| 订阅 | `/auv/sensors/imu` | `sensor_msgs/Imu` | IMU 输入 |
| 订阅 | `/auv/sensors/dvl` | `geometry_msgs/TwistStamped` | DVL 输入 |
| 订阅 | `/auv/sensors/depth` | `std_msgs/Float64` | 深度输入 |
| 订阅 | `/auv/sensors/gps` | `sensor_msgs/NavSatFix` | GPS 输入 |
| 发布 | `/auv/state/filtered` | `nav_msgs/Odometry` | EKF 融合后状态 |

### zenoh_viz_bridge_node (auv_viz_bridge)

| 方向 | Topic | 消息类型 | 说明 |
|------|-------|----------|------|
| 订阅 | `/auv/state/filtered` | `nav_msgs/Odometry` | 融合状态 |
| 订阅 | `/auv/sensors/status` | `auv_interfaces/SensorStatus` | 传感器状态 |
| 订阅 | `/auv/bt_status` | `std_msgs/String` | 行为树状态 |
| 发布 | Zenoh 可视化通道 | — | 推送至地面站 |

### auv_controller_node (auv_controller)

| 方向 | Topic | 消息类型 | 说明 |
|------|-------|----------|------|
| 订阅 | `/auv/state/filtered` | `nav_msgs/Odometry` | 当前状态 |
| 订阅 | `/auv/control/setpoint` | `auv_interfaces/Setpoint` | 目标设定值 |
| 发布 | `/cmd_vel` | `geometry_msgs/Twist` | 控制输出 |
| 发布 | `/auv/control/mpc_cmd` | `auv_interfaces/MpcCmd` | MPC 命令 |
| 发布 | `/auv/diagnostics` | `auv_interfaces/AuvDiagnostic` | 控制器诊断 |

### auv_decision_node (auv_decision_ros)

| 方向 | Topic | 消息类型 | 说明 |
|------|-------|----------|------|
| 订阅 | `/auv/state/filtered` | `nav_msgs/Odometry` | 定位结果 |
| 订阅 | `/auv/sensors/status` | `auv_interfaces/SensorStatus` | 传感器健康 |
| 发布 | `/auv/control/setpoint` | `auv_interfaces/Setpoint` | 决策输出目标 |
| 发布 | `/auv/bt_status` | `std_msgs/String` | 行为树状态广播 |
| 发布 | `/auv/control/goal` | `auv_interfaces/ControlGoal` | 高层目标 |

---

## 数据流链路

### 正向控制链

```
传感器 → Bridge → /auv/sensors/* → Localization → /auv/state/filtered → Controller → /cmd_vel → Bridge → 执行器
```

1. 物理传感器数据经 Zenoh/UDP 到达 Bridge 节点
2. Bridge 解码后发布到 `/auv/sensors/*` 系列 Topic
3. Localization 节点融合多源传感器，输出滤波状态
4. Controller 根据状态和设定值计算控制量
5. Bridge 将 `/cmd_vel` 编码为下行协议帧发送至执行器

### 决策链

```
Localization → /auv/sensors/status → Decision → /auv/control/setpoint → Controller + Bridge
```

1. 传感器状态汇总至 Decision 节点
2. 行为树根据任务逻辑产生目标设定值
3. Controller 跟踪 setpoint 执行控制
4. Bridge 同步将仲裁后命令下发

---

## Launch 文件说明

### auv_stack.launch.py — 仿真标配

使用 `zenoh_json` 后端桥接，适用于仿真环境和桌面调试：

```bash
ros2 launch auv_bringup auv_stack.launch.py
```

### auv_arbiter_stack.launch.py — 真机标配

使用 `protocol_udp` + `arbiter` 模式，包含仲裁器和安全守卫：

```bash
ros2 launch auv_bringup auv_arbiter_stack.launch.py
```

### Launch 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `minimal` | `false` | 最小启动模式（跳过可视化） |
| `debug_level` | `0` | 决策调试等级（0=完整任务, 1=定深定航, 2=解析轨迹） |
| `bridge_backend` | `zenoh_json` | 桥接后端选择 |
| `protocol_control_mode_byte` | `0x01` | 初始控制模式字节 |

---

## 自定义消息 (auv_interfaces)

### Setpoint.msg

控制目标设定值，Decision → Controller：

- `mode` (uint8): 行为模式枚举
- `target_depth` (float64): 目标深度 (m)
- `target_heading` (float64): 目标航向 (rad)
- `target_speed` (float64): 目标航速 (m/s)
- `track_cable` (bool): 是否启用海缆跟踪
- `sine_amplitude` (float64): 正弦搜索振幅
- `sine_period` (float64): 正弦搜索周期

### ArbiterStatus.msg

仲裁器状态：

- `mode` (uint8): 当前仲裁模式 (REMOTE/AUTONOMOUS)
- `guard_state` (uint8): 守卫器状态
- `reject_reason` (string): 拒绝自主的原因
- `uplink_age_ms` (float64): 遥测新鲜度

### SensorStatus.msg

传感器健康状态汇总：

- `confidence` (float64): 定位置信度 [0, 1]
- `leak_level` (uint8): 漏水等级
- `battery_low` (bool): 低电压标志
- `voltage` (float64): 当前电压
- `dvl_valid` (bool): DVL 数据有效性
- `gps_valid` (bool): GPS 数据有效性

### ControlGoal.msg

决策层高级目标输出：

- `goal_type` (uint8): 目标类型
- `waypoints` (geometry_msgs/Point[]): 航路点序列
- `speed` (float64): 期望航速

### MpcCmd.msg

MPC 控制器命令：

- `heading_cmd` (float64): 航向指令
- `depth_cmd` (float64): 深度指令
- `thrust_cmd` (float64): 推力指令
- `timestamp` (builtin_interfaces/Time): 时间戳
- `confidence` (float64): 求解置信度

### AuvDiagnostic.msg

运行诊断信息：

- `controller_type` (string): 当前控制器类型
- `solve_time_ms` (float64): 求解耗时
- `tracking_error` (float64): 跟踪误差
- `integral_state` (float64[3]): PID 积分器状态
