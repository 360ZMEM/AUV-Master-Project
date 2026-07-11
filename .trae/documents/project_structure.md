# AUV Master Project 架构概览

## 项目定位
统一后的 AUV 项目根目录，目标是将仿真侧与 Linux ROS2 决策侧组织为一个可演进仓库。

## 目录结构

| 目录 | 说明 | 用途 |
|------|------|------|
| **common/** | 双端共享协议、枚举、物理常量 | 协议契约与常数定义 |
| **algorithm/** | 与环境无关的控制/导引算法 | PID、Guidance、ES-EKF、轨迹生成 |
| **brain_linux/** | ROS2 Humble 工作区 | 决策栈：定位、控制、行为树 |
| **config/** | 仿真与桥接配置 | YAML 配置文件（仿真、桥接、实物） |
| **foxglove_layout_project/** | Foxglove 布局生成器 | 可视化系统配置与生成 |

## 核心组件

### 1. 共享层 (common/)
- `protocol.py`: Zenoh 主题路径、有效负载键名、二进制协议定义
- `enums.py`: 行为模式、仲裁模式、故障码等枚举定义
- `physics.py`: 物理常量和限制函数

### 2. 算法层 (algorithm/)
- `auv_pid_controller.py`: 级联 PID 控制器（深度/俯仰/航向/速度）
- `es_ekf.py`: ES-EKF 状态估计器
- `guidance.py`: LOS 导引律实现
- `trajectory_generator.py`: 解析式轨迹生成器

### 3. 决策层 (brain_linux/src/auv_decision/)
- `bt_engine.py`: 行为树引擎封装
- `behaviors.py`: 行为节点定义（紧急上浮、下潜、并行跟踪、之字形搜索等）
- `decorators.py`: 装饰器（异常降速、海底安全限速）
- `models.py`: 核心数据模型（SensorStatusData、MotionGoal）

### 4. 控制层 (brain_linux/src/auv_controller/)
- `auv_controller_node.py`: ROS2 控制节点，订阅 Setpoint 和状态估计，发布 /cmd_vel

### 5. 桥接层 (brain_linux/src/auv_bridge/)
- `arbiter.py`: 命令仲裁核心，负责遥控/自主模式切换
- `bridge_node.py`: Zenoh ↔ ROS2 桥接节点
- `protocol_udp_bridge_node.py`: 二进制协议 UDP 桥接

## 数据流架构

```
传感器数据 → Zenoh → Bridge → ROS2 → Decision → Controller → /cmd_vel → Bridge → Zenoh → AUV
```

### 五层架构
1. **感知层**: 传感器数据采集与预处理
2. **状态估计层**: ES-EKF 滤波融合
3. **决策层**: 行为树任务规划
4. **控制层**: PID 级联控制
5. **执行层**: 舵面/推力执行

## 关键协议主题

### Zenoh 主题路径
- `rt/auv/sensors/ground_truth`: 地面真值
- `rt/auv/sensors/imu`: IMU 数据
- `rt/auv/sensors/dvl`: DVL 速度
- `rt/auv/sensors/depth`: 深度传感器
- `rt/auv/control/cmd_vel`: 控制命令
- `rt/auv/telemetry`: AUV 遥测数据

### ROS2 主题
- `/auv/control/setpoint`: 控制目标
- `/auv/state/filtered`: 滤波状态估计
- `/auv/state/raw_dr`: 原始死推进状态
- `/cmd_vel`: 五通道控制命令输出

## 仲裁机制

### 仲裁模式
- **REMOTE**: 遥控模式，使用 PC 原始命令
- **AUTONOMOUS**: 自主模式，使用 MPC 输出

### 切换条件
- 收到 `TASK_CANCEL` 或 `CLEAR_FAULT` 工作指令 → 切换到 REMOTE
- 控制模式字节为 `JETSON_PROTOCOL(0xEE)` → 切换到 AUTONOMOUS
- MPC 超时或无效 → 安全回退（零舵、零推力）

## 行为树结构

```
RootSelector
├── EmergencySequence (紧急条件 → 紧急上浮)
└── DebugCascadeSelector
    ├── HoldSequence (L1: 定深定航)
    ├── PathSequence (L2: 解析式轨迹跟踪)
    └── MainMissionSequence
        ├── DiveToDepth (下潜到 4m)
        └── RouteSelector
            ├── PreciseInspection (置信度 > 0.7 → 并行跟踪)
            └── ZigZagSearch (置信度 ≤ 0.7 → 之字形搜索)
```

## 控制输出映射

Twist 消息映射到五通道控制：
- `linear.x`: thrust（推力百分比）
- `angular.x`: right fin（右舵角度）
- `angular.y`: top fin（上舵角度）
- `angular.z`: left fin（左舵角度）
- `linear.z`: bottom fin（下舵角度）

## 安全机制

### 紧急条件
- 漏水检测 (`leak_level > 0`)
- 低电压 (`battery_low = True`)
- 穿底警告 (`seabed_penetration_warning = True`)

### 安全装饰器
- **AnomalySpeedLimiter**: 检测到异常时降低速度
- **SeabedSafetyLimiter**: 接近海底时保守限速

---

**生成时间**: 2026-04-29  
**项目版本**: AUV_Master_Project v1.0
