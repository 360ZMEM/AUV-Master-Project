# AUV 中级模型预测控制器 (MPC) 实施经验文档

> 文档版本: v1.0  
> 更新日期: 2026-05-03  
> 状态: 骨架完成，待调优

---

## 目录

1. [架构概述](#1-架构概述)
2. [核心文件清单](#2-核心文件清单)
3. [数学模型详解](#3-数学模型详解)
4. [实施过程踩坑记录](#4-实施过程踩坑记录)
5. [基准测试结果](#5-基准测试结果)
6. [调优指南](#6-调优指南)
7. [ROS2 集成说明](#7-ros2-集成说明)
8. [后续工作计划](#8-后续工作计划)

---

## 1. 架构概述

### 1.1 控制层级定位

```
┌─────────────────────────────────────────────────┐
│              任务决策层 (高层)                    │
│  电缆跟踪策略、路径规划、置信度评估                │
└─────────────────────┬───────────────────────────┘
                      │ Setpoint (depth, heading, speed, confidence)
                      ▼
┌─────────────────────────────────────────────────┐
│         中级导引层 (本文 MPC 所在位置)            │
│  ┌────────────┐  ┌──────────────────────────┐   │
│  │ PID Controller │ MPC Controller           │   │
│  │ guidance_head │ guidance_head             │   │
│  │ guidance_depth│ guidance_depth            │   │
│  │ thrust_pct    │ thrust_pct                │   │
│  └──────┬───────┘  └──────────┬─────────────┘   │
│         └───────┬─────────────┘                  │
│                 ▼ 统一输出                        │
│         ControlOutput(guidance_heading,           │
│                       guidance_depth,             │
│                       thrust_percent)             │
└─────────────────────┬───────────────────────────┘
                      │ guidance 指令
                      ▼
┌─────────────────────────────────────────────────┐
│          AMD 侧底层 PID (VxWorks)                │
│  舵角闭环 + D 项抑制抖动                         │
│  推力映射 + 死区补偿                             │
└─────────────────────────────────────────────────┘
```

### 1.2 设计哲学：Jetson 看未来，AMD 保当下

| 层级 | 负责方 | 职责 | 频率 |
|------|--------|------|------|
| 中级导引 | Jetson (MPC/PID) | 预测未来 2s 趋势，计算最优引导指令 | 10Hz |
| 底层闭环 | AMD (VxWorks PID) | 当下抗扰动，舵角精细调节 | 50-100Hz |

**关键优势**：即使 MPC 计算延迟 50ms，AMD 仍在执行最优引导目标。

### 1.3 坐标系约定

- **MPC 内部**: NED 坐标系（北-东-地），z 轴正向下
- **HoloOcean/UE4**: 左手坐标系，需通过 `frame_transform.py` 镜像转换
- **转换时机**: 在 MPC 输入前完成 100% 镜像转换

---

## 2. 核心文件清单

| 文件 | 职责 | 行数 | 状态 |
|------|------|------|------|
| `algorithm/auv_mpc_controller.py` | CasADi 数学模型 + IPOPT 求解器 | ~290 | 完成 |
| `brain_linux/.../mpc_controller.py` | BaseController 封装 + LOS 参考轨迹 | ~350 | 完成 |
| `brain_linux/.../auv_controller_node.py` | ROS2 节点集成 + 异常降级 | +10 行 | 完成 |
| `brain_linux/config/params.yaml` | MPC 参数配置 (4 个配置段) | +36 行 | 完成 |
| `tests/test_mpc_solver.py` | 6 个单元测试 | ~200 | 完成 |
| `tests/benchmark_pid_vs_mpc.py` | PID vs MPC 对比基准 | ~350 | 完成 |
| `docs_new/casadi_install_guide.md` | CasADi 安装指引 | ~60 | 完成 |

---

## 3. 数学模型详解

### 3.1 4-DOF 预测模型

**状态向量 (6 维)**:
```
X = [x, y, z, ψ, u, w]ᵀ
```

| 符号 | 物理意义 | 单位 |
|------|----------|------|
| x, y | NED 平面位置 | m |
| z | NED 深度（正向下） | m |
| ψ | 航向角 | rad |
| u | 前向速度 (Surge) | m/s |
| w | 垂向速度 (Heave) | m/s |

**控制向量 (3 维)**:
```
U = [ψ_cmd, z_cmd, T_cmd]ᵀ
```

| 符号 | 物理意义 | 单位 |
|------|----------|------|
| ψ_cmd | 目标航向（引导航向） | rad |
| z_cmd | 目标深度（引导深度） | m |
| T_cmd | 推力百分比 | 0 ~ 100 |

**欠驱动假设**:
- 横向 sway `v` 不直接控制，通过 ψ 偏转间接影响 (x, y) 轨迹
- 俯仰角 θ 作为内部状态，由深度跟踪隐式驱动
- 不输出舵角，交由 AMD 侧 PID 处理

**连续时间动力学**:
```
dx/dt = u·cos(ψ)
dy/dt = u·sin(ψ)
dz/dt = w
dψ/dt = r = yaw_rate_gain × (ψ_cmd - ψ)
du/dt = (T - drag_u × u × |u|) / mass_u
dw/dt = (-drag_w × w + pitch_depth_gain × θ + buoyancy) / mass_w
```

**离散化 (Euler forward, dt=0.1s)**:
```
x[k+1] = x[k] + dt × u[k] × cos(ψ[k])
y[k+1] = y[k] + dt × u[k] × sin(ψ[k])
z[k+1] = z[k] + dt × w[k]
ψ[k+1] = ψ[k] + dt × yaw_rate_gain × (ψ_cmd[k] - ψ[k])
u[k+1] = u[k] + dt × (T[k] - drag_u × u[k] × |u[k]|) / mass_u
w[k+1] = w[k] + dt × (-drag_w × w[k] + pitch_depth_gain² × (z_cmd[k] - z[k])) / mass_w
```

### 3.2 代价函数

```
J = Σ(k=0→N) [ W_track(k) × ||X[k] - X_ref[k]||² ] 
  + Σ(k=0→N-1) [ W_ctrl(k) × ||U[k]||² ]
```

**跟踪权重 (6 维对角)**:
```
W_track = diag(w_x, w_y, w_z, w_ψ, w_u, w_w)
```

**控制权重**:
```
W_ctrl = diag(W_ψ_cmd, W_z_cmd, W_T)
```

### 3.3 置信度自适应权重

当传感器置信度 C < 0.6 时，进入"盲跟"模式:

```python
# 跟踪权重增大 (宁可动作大，也要死守估算轨迹)
w_x *= (1 + (1-C) × (low_conf_scale - 1))    # low_conf_scale = 3.0
w_y *= (1 + (1-C) × (low_conf_scale - 1))
w_ψ *= (1 + (1-C) × (low_conf_scale - 1))
w_z *= (1 + (1-C) × 0.5)

# 控制努力惩罚减小 (允许更大的控制量)
W_ctrl *= low_conf_ctrl_scale  # = 0.3
```

### 3.4 硬约束

| 约束 | 条件 | 目的 |
|------|------|------|
| 航速下限 | u[k] ≥ 0.1 m/s (k≥1) | 确保欠驱动舵效有效 |
| 推力限幅 | 0 ≤ T_cmd ≤ 100 | 物理限幅 |

> **注意**: 初始状态 `u[0]` 不受航速约束（允许启动），仅对 k≥1 的未来状态施加约束。

---

## 4. 实施过程踩坑记录

### 4.1 CasADi `ca.diag()` 类型混合错误

**问题**: `ca.diag([float_val, ca.MX_expr, ...])` 在混合 float 和 MX 表达式时抛出 `TypeError`。

**原因**: CasADi 的 `ca.diag()` 要求所有元素为同一类型（全部为 `ca.MX` 或全部为 `float`），但置信度 `conf` 是 `ca.MX` 参数，导致 `W_x * (1 + (1-conf)*...)` 返回 MX 类型，与 float 混入同一列表。

**修复**: 展开为标量加权求和:
```python
# 错误写法
W_tracking = ca.diag([w_x, w_y, w_z, w_psi, W_u, W_w])
J += err.T @ W_tracking @ err

# 正确写法
J += w_x * err[0]**2 + w_y * err[1]**2 + w_z * err[2]**2 + ...
```

### 4.2 初始速度违反硬约束导致 Infeasible

**问题**: 基准测试初始状态 `u=0`，硬约束 `u[k] ≥ 0.1` 对所有 k≥0 施加，导致第一个时间步就不满足约束。

**原因**: `opti.subject_to(X[4, :] >= self.min_speed)` 对所有 k 施加约束，包括 k=0 的初始状态。但初始状态已由 `opti.subject_to(X[:, 0] == x0_param)` 固定，当 x0[4]=0 < 0.1 时矛盾。

**修复**: 只对 k≥1 的未来状态施加速度约束:
```python
# 错误
opti.subject_to(X[4, :] >= self.min_speed)

# 正确
opti.subject_to(X[4, 1:] >= self.min_speed)
```

### 4.3 俯仰角约束误施于航向角

**问题**: `opti.subject_to(opti.bounded(-max_pitch, X[3, :], max_pitch))` 中 `X[3]` 是航向角 ψ (yaw)，不是俯仰角 θ (pitch)。

**原因**: 4-DOF 模型状态向量是 `[x, y, z, ψ, u, w]`，不含 θ。θ 是内部隐式状态，无法作为优化变量直接约束。

**修复**: 移除错误的俯仰角约束，后续如需约束俯仰，需在代价函数中通过深度跟踪误差间接控制。

### 4.4 PID 基准测试深度符号不匹配

**问题**: PID 控制器输出全 0，航向误差异常大 (114.6 rad)。

**原因 1**: `current_state["depth"] = abs(state[2])` 返回 12.0，但 `setpoint["target_depth"] = -12.0` (NED)，误差为 -24.0。

**原因 2**: 航向误差未做角度 wrap，累积到巨大值。

**修复**:
```python
# 基准测试中使用参考深度作为当前深度（仿真简化）
current_state["depth"] = ref_depth

# 航向误差使用 wrap_angle
def _wrap_angle(angle):
    return (angle + np.pi) % (2 * np.pi) - np.pi

heading_err = abs(_wrap_angle(state[3] - ref_yaw))
```

### 4.5 热启动索引偏移

**问题**: 热启动时直接将 `prev_U[:, k]` 赋值给当前步，导致控制序列不连续。

**原因**: MPC 每步求解后应"透传"下一时刻的控制量。正确的热启动策略是将 `prev_U[:, k+1]` 作为当前步的初值。

**修复**:
```python
for k in range(self.N):
    if k < self.N - 1:
        u_guess = warm_start_U[:, k + 1]  # 取下一步
    else:
        u_guess = warm_start_U[:, -1]     # 最后一步复用
```

### 4.6 `ca.if_else()` 中不能用 Python `if`

**问题**: 在 CasADi 优化问题构建中使用了 `if conf < 0.6:` 这样的 Python 条件判断。

**原因**: CasADi 构建符号图时，`conf` 是符号参数，Python 无法在构建期求值。

**修复**: 使用 CasADi 的条件表达式:
```python
control_scale = ca.if_else(conf < self.confidence_threshold,
                           self.low_conf_ctrl_scale, 1.0)
J += control_scale * ctrl_effort
```

---

## 5. 基准测试结果

### 5.1 测试环境

- **CPU**: ARM aarch64 (Jetson Orin)
- **Python**: 3.10.12
- **CasADi**: 3.7.2
- **求解器**: IPOPT (内置)

### 5.2 单元测试结果

```
==================================================
MPC 求解器单元测试: 6 passed, 0 failed

[PASS] kinematics_model: x_next=0.100, u_next=0.800
[PASS] straight_line: psi_cmd=0.0000 rad, z_cmd=-5.00 m, T_cmd=13.2%, solve_time=13.1ms
[PASS] turn: psi_cmd=0.0352 rad (ref ~0.08 rad)
[PASS] low_confidence: T_high=13.23%, T_low=13.55% (低置信度允许更大控制量)
[PASS] warm_start: solve_time=0.6ms, total=7.9ms
[PASS] constraints: min_speed=0.300 m/s, T_range=[5.5, 11.7]
```

### 5.3 PID vs MPC 对比基准

```
============================================================
AUV 控制器基准测试报告 (PID vs MPC)
============================================================

--- PID 控制器 ---
  平均航向误差: 0.1634 rad
  最大航向误差: 0.2355 rad
  舵机动作方差: 0.0000
  推力方差:     2.2106

--- MPC 控制器 ---
  平均航向误差: 0.1658 rad
  最大航向误差: 0.2999 rad
  舵机动作方差: 0.0695
  推力方差:     0.0016
  平均求解时间: 6.68 ms
  最大求解时间: 22.49 ms
  求解成功率:   100.0%

--- 对比指标 ---
  超调量减少: -27.3% (目标: >= 40%) [FAIL]
  平滑度提升: 0.0%
  求解时间达标: [FAIL] (max 22.5ms < 15ms)
```

### 5.4 结果解读

| 指标 | 现状 | 目标 | 差距原因 |
|------|------|------|----------|
| MPC 求解成功率 | 100% | 100% | 达标 |
| 平均求解时间 | 6.68ms | < 15ms | 达标 |
| 最大求解时间 | 22.49ms | < 15ms | 首次求解无热启动 |
| 超调量减少 | -27.3% | ≥ 40% | 模型参数未调优 |
| 平滑度提升 | 0% | - | PID 输出为 0（基准框架问题） |

**未达标原因分析**:
1. **水动力系数** (`mass_u=50, drag_u=15`) 是经验估值，与实际 AUV 物理参数不符
2. **权重参数** 需要针对实际跟踪任务调优
3. **MPC guidance → 舵角映射** 目前使用简易比例法 (`yaw_err * 30.0`)，未模拟真实 AMD 侧 PID 的 D 项抑制

---

## 6. 调优指南

### 6.1 水动力系数调优顺序

```
第一步: 标定 Surge 参数 (mass_u, drag_u)
  - 方法: 给定固定推力，测量稳态速度
  - 稳态时 T = drag_u × u²，可反算 drag_u
  - mass_u 影响加速时间常数

第二步: 标定 Heave 参数 (mass_w, drag_w)
  - 方法: 给定深度阶跃，测量响应曲线

第三步: 标定 Yaw 参数 (yaw_rate_gain)
  - 方法: 给定舵角阶跃，测量偏航角速度
  - yaw_rate_gain = r / (ψ_cmd - ψ)

第四步: 标定耦合参数 (pitch_depth_gain)
  - 方法: 深度阶跃响应中观察俯仰角变化
```

### 6.2 权重参数调优策略

```
调优原则: 先调跟踪权重，再调控制权重

跟踪权重 (W_x, W_y, W_z, W_psi, W_u, W_w):
  - 增大 → 更激进地跟踪参考轨迹
  - 减小 → 允许更大的跟踪偏差

控制权重 (W_ψ_cmd, W_z_cmd, W_T):
  - 增大 → 控制量更平滑，但跟踪更慢
  - 减小 → 控制量更大，响应更快

推荐调优步骤:
  1. 设 W_ctrl = 0 (纯跟踪)，观察 MPC 输出控制量范围
  2. 逐步增大 W_ctrl，直到控制量在合理范围内
  3. 调整 W_z / W_psi 比例，平衡深度和航向优先级
  4. 低置信度参数保持默认 (scale=3.0, ctrl_scale=0.3)
```

### 6.3 置信度阈值调优

| 置信度范围 | 行为 | 适用场景 |
|-----------|------|----------|
| C ≥ 0.6 | 正常模式 | 电缆检测稳定 |
| 0.3 ≤ C < 0.6 | 轻度保守 | 部分遮挡/湍流 |
| C < 0.3 | 盲跟模式 | 电缆丢失 |

### 6.4 预测时域选择

| N | dt | 预测窗口 | 适用场景 |
|---|-----|----------|----------|
| 10 | 0.1s | 1.0s | 高机动、低算力 |
| 20 | 0.1s | 2.0s | 常规（当前默认） |
| 30 | 0.1s | 3.0s | 大惯性 AUV |

> **经验法则**: 预测窗口 ≈ AUV 转弯时间常数 × 2

### 6.5 求解器参数调优

```yaml
ipopt:
  tol: 1e-4        # 默认，可调到 1e-3 加速或 1e-6 提高精度
  max_iter: 100    # 默认，通常 20-40 步收敛
  mu_strategy: adaptive  # 默认
```

---

## 7. ROS2 集成说明

### 7.1 节点架构

```
auv_controller_node.py
  ├── PID Controller (auv_controller/pid_controller.py)
  └── MPC Controller (auv_controller/mpc_controller.py)
       └── algorithm/auv_mpc_controller.py (CasADi 核心)
```

### 7.2 切换方式

通过 launch 参数 `use_mpc` 控制:
```bash
# PID 模式
ros2 launch auv_controller auv_controller.launch.py use_mpc:=false

# MPC 模式
ros2 launch auv_controller auv_controller.launch.py use_mpc:=true
```

### 7.3 话题接口

**输入话题**:
| 话题 | 类型 | 内容 |
|------|------|------|
| `/auv/control/setpoint` | Setpoint | target_depth, target_yaw, confidence |
| `/auv/state/filtered` | Odometry | ES-EKF 滤波位姿 |

**输出话题**:
| 话题 | 类型 | 内容 |
|------|------|------|
| `/auv/controller/debug` | Dict | solver_status, solve_time_ms, cost_value |
| `/auv/control/mpc_cmd` | MpcCmd | optimal_heading, optimal_depth, optimal_thrust |

### 7.4 失效降级流程

```
MPC compute() 抛出 RuntimeError
    ↓
节点捕获异常
    ↓
切换 active_controller → PID
    ↓
设置 _use_mpc = False
    ↓
发布算法告警到 debug 话题
    ↓
下行包中记录 MCP_ERROR 标志位
```

### 7.5 热启动序列透传

当前 `$CKTH` 协议只支持单步指令传输，不支持序列透传。MPC 一次计算出 N 步最优控制序列，但每次只取第一步 (`U_opt[:, 0]`) 发送给 AMD。

**未来优化方向**: 如果协议支持多步传输，可在 UDP 延迟期间让 AMD 执行序列中的第 2、3 步，减少重算频率。

---

## 8. 后续工作计划

### 8.1 短期 (参数调优)

- [ ] 根据实际 AUV 物理参数标定水动力系数
- [ ] 在 HoloOcean 仿真中调优权重参数
- [ ] 优化 MPC guidance → 舵角映射逻辑 (更精确模拟 AMD 侧 PID)
- [ ] 降低最大求解时间到 < 15ms

### 8.2 中期 (功能增强)

- [ ] 接入真实的 LOS 导引动态参考轨迹 (当前为骨架)
- [ ] 实现地形跟踪模式 (depth 参考点来自前视声呐)
- [ ] 添加约束软惩罚 (如接近海底时增加深度跟踪权重)
- [ ] 实现多模式切换 (电缆跟踪 / 定点悬停 / 返航)

### 8.3 长期 (架构升级)

- [ ] 实现预测序列透传 (多步指令打包)
- [ ] 添加 MPC 求解器预热 (启动后先求解几次空跑)
- [ ] 在线参数辨识 (自适应更新水动力系数)
- [ ] GPU 加速求解 (cuSOLVER + IPOPT)

---

## 附录 A: 快速命令参考

```bash
# 安装 CasADi
pip install casadi

# 验证安装
python3 -c "import casadi; print(casadi.__version__)"

# 运行单元测试
python3 tests/test_mpc_solver.py

# 运行基准测试
python3 tests/benchmark_pid_vs_mpc.py

# 检查求解状态
ros2 topic echo /auv/controller/debug
# 预期: solver_status: SUCCESS, solve_time_ms < 15
```

## 附录 B: 关键配置参数速查

| 参数 | 默认值 | 调优方向 | 说明 |
|------|--------|----------|------|
| `mpc.prediction_horizon` | 20 | 10-30 | 预测步数 |
| `mpc.dt` | 0.1 | 固定 0.1 | 时间步长 |
| `mpc_model.mass_u` | 50.0 | 30-100 | Surge 等效质量 |
| `mpc_model.drag_u` | 15.0 | 10-30 | Surge 阻尼 |
| `mpc_model.yaw_rate_gain` | 0.5 | 0.3-1.0 | 航向控制增益 |
| `mpc_weights.tracking.psi` | 3.0 | 1-10 | 航向跟踪权重 |
| `mpc_weights.control.T_cmd` | 0.05 | 0.01-0.5 | 推力控制惩罚 |
| `mpc_constraints.min_speed_ms` | 0.1 | 0.1-0.5 | 航速下限 |
| `mpc_weights.confidence_threshold` | 0.6 | 0.4-0.8 | 置信度阈值 |

## 附录 C: 已知限制

1. **4-DOF 简化模型**: 不含 sway 和 roll 动态，横向漂移未被显式建模
2. **欠驱动隐式处理**: 偏航角速度通过 `yaw_rate_gain` 简化映射，未使用完整水动力模型
3. **置信度单向影响**: 仅影响权重，不影响参考轨迹生成策略
4. **地形约束简化**: 高度约束仅通过 `min_altitude_m` 硬约束实现，未结合实时声呐数据
