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
| `pvs.initial_state.position` | 初始位置 [x,y,z] | `[0, 0, -5]` |
| `pvs.initial_state.attitude` | 初始姿态 [r,p,y] | `[0, 0, 0]` |
| `pvs.rpm_max` | 最大螺旋桨转速 | `1525` |
| `pvs.rpm_min` | 最小螺旋桨转速 | `-1525` |
| `pvs.rudder_max` | 最大舵角（rad） | `0.52` |
| `pvs.dt` | 仿真步长（秒） | `0.02` |
| `pvs.ocean_current.speed` | 洋流速度（m/s） | `0.0` |
| `pvs.ocean_current.direction` | 洋流方向（rad） | `0.0` |
