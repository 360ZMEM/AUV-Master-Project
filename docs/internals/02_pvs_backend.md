# 02 - PVS仿真后端

## 概述

PVS（PythonVehicleSimulator）是一个轻量级6-DOF刚体动力学仿真器，基于Thor I. Fossen的船舶动力学模型实现。它无需UE4引擎即可运行完整的REMUS 100 AUV动力学仿真，适合快速算法验证和CI持续集成流水线。

PVS后端通过 `pvs_sim_wrapper` 接口适配为与HoloOcean相同的抽象接口，上层代码无需关心底层使用哪个仿真器。

---

## 与HoloOcean的对比

| 维度 | HoloOcean | PVS |
|------|-----------|-----|
| 物理保真度 | 高（流体、碰撞） | 中（Fossen模型） |
| 启动速度 | 慢（UE4加载） | 快（纯Python） |
| 视觉渲染 | 有 | 无 |
| 传感器模拟 | 完整（含噪声模型） | 合成（解析计算） |
| CI友好 | 否（需GPU/显示） | 是（纯CPU） |
| 多体碰撞 | 支持 | 不支持 |
| 洋流建模 | 外部注入 | 内置OceanCurrentModel |

选择策略：
- 算法开发/调试/CI → PVS
- 系统集成/视觉验证/多AUV场景 → HoloOcean

---

## 状态向量

PVS使用经典的Fossen 12维状态向量加执行器状态：

```
eta[6] = [x, y, z, roll, pitch, yaw]     # 位置与姿态（NED + 欧拉角）
nu[6]  = [u, v, w, p, q, r]              # 体坐标系下的线速度与角速度
u_actual[3] = [rudder, stern, rpm]        # 实际执行器状态
```

其中：
- `eta` 为地球固定坐标系（NED）下的位姿
- `nu` 为体坐标系（body-fixed）下的速度
- `u_actual` 为执行器当前实际值（含执行器动态响应延迟）

---

## 两种控制模式

### 模式一：stepInput（外部控制）

外部控制器直接提供5元控制命令，PVS将其映射为舵角和推力：

```
外部5元命令 [surge, sway, heave, yaw_rate, pitch_rate]
        │
        ▼
  映射为 → rudder_angle, stern_angle, rpm
        │
        ▼
  执行器动态模型（一阶惯性）
        │
        ▼
  6-DOF dynamics() 步进
```

此模式下PVS仅作为"动力学黑箱"，所有决策由外部完成。

### 模式二：depthHeadingAutopilot（内置自动驾驶仪）

PVS内置自动驾驶仪接受高层目标指令：

```
目标 [desired_depth, desired_heading, desired_speed]
        │
        ▼
  内部PID控制器
    ├── depth_PID → stern_angle
    ├── heading_PID → rudder_angle
    └── speed_PID → rpm
        │
        ▼
  执行器动态模型
        │
        ▼
  6-DOF dynamics() 步进
```

此模式适用于验证制导算法（如LOS），无需关心底层控制细节。

### 模式三：kinematic_setpoint（运动学设定值，轻量位形响应）

前两种模式走完整 6-DOF 刚体动力学积分。但在电缆巡检闭环等场景中，我们只需要车体对**高层横向/艏向/深度设定值**产生可观测的位形响应，不必依赖执行器动态与水动力细节。为此新增第三条路径 `autonomy_motion_model: kinematic_setpoint`（实现于 `pvs_sim_wrapper.py` 的 `_step_kinematic_autonomy()`）：

```
目标 [reference_heading, reference_depth, reference_speed]
        │
        ▼
  航向误差 → yaw_rate（限幅 kinematic_max_yaw_rate_deg_s）→ 更新 eta[5]
  深度误差 → depth_rate = depth_error / kinematic_depth_time_constant_s → nu[2]
  前进速度 → nu[0] = reference_speed
        │
        ▼
  attitudeEuler() 积分运动学（roll/pitch 强制归零）
```

该模式**镜像 Direction A 解耦轻量闭环的语义**：让 protocol_udp/PVS 自主路径能产生可观测的 x/y/yaw/depth 运动，即使安装的 PVS 包停留在 step-input 模式也不受影响。

引入动机（(3f) 直接依赖）：§5.5.11 (3d) 附注发现 PVS mock 车体的 Y/yaw 全程恒为 0.0——制导层虽发布非平凡目标航向，车体位形却不响应，导致横偏无法被真实横向操舵吸收。启用本模式后，heavy 起始横偏约 −10.25 m 在约 12 s 内收敛进 ±3.4 m 廊道并保持，即车体被真实横向操舵去贴合修正后的先验。原理链见 [12_cable_tracking_mag_integration.md](12_cable_tracking_mag_integration.md)。

激活条件：`autonomy_motion_model` ∈ `{kinematic_setpoint, kinematic, lightweight}`。

---

## 每步积分流程

每次仿真步进（`tick()`）的内部流程：

```python
def tick(dt, control_input):
    # 1. 根据控制模式解析输入
    u_command = parse_control(control_input)
    
    # 2. 执行器动态（一阶惯性滤波）
    u_actual = actuator_dynamics(u_actual, u_command, dt)
    
    # 3. 计算水动力、重力/浮力、洋流力
    tau = dynamics(nu, u_actual, ocean_current)
    
    # 4. 刚体运动方程积分 (RK4)
    nu_dot = M_inv @ (tau - C(nu)@nu - D(nu)@nu - g(eta))
    nu = rk4_step(nu, nu_dot, dt)
    
    # 5. 运动学方程：体速度 → 地坐标速度
    eta_dot = J(eta) @ nu
    eta = rk4_step(eta, eta_dot, dt)
    
    # 6. 欧拉角归一化
    eta[3:6] = attitudeEuler(eta[3:6])
    
    # 7. 构建HoloOcean兼容状态字典
    state = build_compatible_state(eta, nu, u_actual)
    return state
```

`build_compatible_state()` 将PVS内部状态转换为与HoloOcean传感器输出格式一致的字典，确保上层代码无感知切换。

---

## 洋流注入接口

PVS内置 `OceanCurrentModel` 支持以下洋流类型：

- **恒定洋流**：固定方向和速度的均匀流场
- **深度相关洋流**：流速随深度衰减
- **时变洋流**：正弦变化的流场

洋流对动力学的影响通过相对速度实现：

```
nu_r = nu - nu_c    # nu_c为洋流在体坐标系下的投影
tau_hydro = f(nu_r) # 水动力基于相对速度计算
```

---

## 配置关键参数

在 `bridge_params.yaml` 中的 `pvs` 段：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `pvs.control_mode` | 控制模式选择 | `stepInput` |
| `pvs.autonomy_motion_model` | 自主运动模型（`native`/`kinematic_setpoint`） | `native` |
| `pvs.kinematic_max_yaw_rate_deg_s` | 运动学模式最大 yaw rate | `12.0` |
| `pvs.kinematic_depth_time_constant_s` | 运动学模式深度一阶时间常数 | `4.0` |
| `pvs.initial_state.position` | 初始位置 [x,y,z] | `[0, 0, -5]` |
| `pvs.initial_state.attitude` | 初始姿态 [r,p,y] | `[0, 0, 0]` |
| `pvs.rpm_max` | 最大螺旋桨转速 | `1525` |
| `pvs.rpm_min` | 最小螺旋桨转速 | `-1525` |
| `pvs.rudder_max` | 最大舵角（rad） | `0.52` |
| `pvs.dt` | 仿真步长（秒） | `0.02` |
| `pvs.ocean_current.speed` | 洋流速度（m/s） | `0.0` |
| `pvs.ocean_current.direction` | 洋流方向（rad） | `0.0` |
