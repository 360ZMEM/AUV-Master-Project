# 01 - 系统整体架构

## 五层架构总览

系统采用分层架构设计，自顶向下分为应用层、接口层、行为层、算法层和协议层。每层职责单一，通过明确的接口与相邻层交互。

```
┌─────────────────────────────────────────────────────────┐
│                    应用层 (apps/)                        │
│   main.py / run_zenoh_bridge.py                         │
├─────────────────────────────────────────────────────────┤
│                    接口层 (interfaces/)                  │
│   sim_wrapper / pvs_sim_wrapper / zenoh_bridge          │
│   mock_amd_server / holoocean_physics_bridge            │
├─────────────────────────────────────────────────────────┤
│                    行为层 (behavior/)                    │
│   command_guard / safety_monitor / state_machine         │
├─────────────────────────────────────────────────────────┤
│                    算法层 (algorithm/)                   │
│   pid_controller / mpc_controller / es_ekf / guidance   │
├─────────────────────────────────────────────────────────┤
│                    协议层 (common/)                      │
│   protocol / enums / physics / env_utils                │
└─────────────────────────────────────────────────────────┘
```

### 各层职责

- **应用层**：入口脚本，负责初始化配置、组装依赖、启动主循环
- **接口层**：对外部系统（仿真器、通信中间件、硬件）的适配封装
- **行为层**：安全守卫、状态机、命令过滤等运行时行为管理
- **算法层**：核心控制/导航/估计算法的纯计算实现
- **协议层**：数据结构定义、枚举、物理常量、环境工具等公共基础设施

---

## 两条数据流路径

系统支持两种运行模式，对应两条截然不同的数据流路径：

### 路径一：独立仿真闭环

由 `main_loop.py` 驱动，无需外部ROS2系统，整个控制闭环在单进程内完成。适用于算法快速验证和CI测试。

### 路径二：桥接通信闭环

由 `run_zenoh_bridge.py` + `brain_linux`（ROS2决策栈）协作完成。仿真环境通过Zenoh桥接向ROS2发布传感器数据，ROS2决策栈处理后将控制命令经Zenoh回传。适用于全系统集成测试。

---

## 独立仿真数据流详解

```
TrajectoryGenerator
       │
       ▼
  guidance (LOS)          ← 计算期望航向/深度
       │
       ▼
  PIDController           ← 生成舵角/推力命令
       │
       ▼
  safety_monitor          ← 限幅、死区保护
       │
       ▼
  sim_wrapper             ← PVS或HoloOcean步进
       │
       ▼
  传感器读取              ← 位置/姿态/速度
       │
       └──────→ 回到 guidance (闭环)
```

每帧时序：
1. `TrajectoryGenerator` 根据当前时间输出目标路点
2. `guidance` 模块（LOS算法）根据当前位置与目标路点计算期望航向和深度
3. `PIDController` 将误差转换为控制输入（舵角偏转、螺旋桨转速）
4. `safety_monitor` 执行限幅检查和安全约束
5. `sim_wrapper` 将控制命令送入仿真器并步进一步
6. 读取新的传感器状态，进入下一帧

---

## 桥接通信数据流详解

```
sim_wrapper (HoloOcean)
       │
       ▼
holoocean_physics_bridge     ← 坐标变换 + 噪声注入 + 降采样
       │
       ▼
zenoh publish (多topic)      ← rt/auv/sensors/*
       │
       ▼ (网络传输)
auv_bridge (ROS2)            ← Zenoh订阅 → ROS2 Topic发布
       │
       ▼
localization (EKF)           ← 多传感器融合定位
       │
       ▼
controller (PID/MPC)         ← 生成控制命令
       │
       ▼
decision (BT)                ← 行为树任务调度
       │
       ▼
cmd_vel                      ← 5元控制命令
       │
       ▼
zenoh publish                ← rt/auv/control/cmd_vel
       │
       ▼ (网络传输)
sim_wrapper                  ← 接收命令并执行步进
```

---

## 坐标系约定

系统中存在两个主要坐标系，需要在接口层进行转换：

| 坐标系 | 手系 | 前方 | 右方 | 下方 | 使用场景 |
|--------|------|------|------|------|----------|
| HoloOcean (UE4) | 左手系 | +X | +Y | +Z（向上为正） | 仿真器内部 |
| NED | 右手系 | +X (北) | +Y (东) | +Z (下) | 控制/导航算法 |

转换规则：
- 位置：`x_ned = x_ue4`, `y_ned = y_ue4`, `z_ned = -z_ue4`
- 姿态：`roll_ned = roll_ue4`, `pitch_ned = -pitch_ue4`, `yaw_ned = -yaw_ue4`（具体实现参见 `common/physics.py`）

转换在 `holoocean_physics_bridge` 中统一完成，确保算法层始终工作在NED坐标系下。

---

## 模块依赖图

```
apps/main.py
  ├── interfaces/sim_wrapper
  │     └── interfaces/pvs_sim_wrapper (或 HoloOcean)
  ├── algorithm/guidance
  ├── algorithm/pid_controller
  └── behavior/safety_monitor

apps/run_zenoh_bridge.py
  ├── interfaces/zenoh_bridge
  ├── interfaces/holoocean_physics_bridge
  │     ├── common/physics (坐标变换)
  │     └── common/protocol (协议编解码)
  └── interfaces/sim_wrapper

brain_linux (ROS2)
  ├── auv_bridge_node (Zenoh ↔ ROS2)
  ├── localization_node (ES-EKF)
  ├── controller_node (PID/MPC)
  ├── decision_node (行为树)
  └── arbiter_node (仲裁器)
```

各模块通过依赖注入（配置文件选择具体实现）解耦，便于测试时替换mock组件。
