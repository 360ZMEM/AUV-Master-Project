# 第 4 章：决策与控制系统

## 4.1 引言

### 4.1.1 欠驱动 AUV 运动约束分析

AUV 通常采用 REMUS 100 型布局：尾部一个主推进器和两个十字形舵面（水平舵 + 垂直舵）。这种构型在水平面内可以通过舵角控制航向和前进速度，但在横移方向上没有直接执行器，属于典型的欠驱动系统。垂直面内通过水平舵控制俯仰角，间接改变深度。这种约束决定了：控制器不能期望在横移方向上产生直接力，而必须通过航向调节实现间接横向位移。

 PVS 仿真中，AUV 接受 5 元控制命令 `[surge, sway, heave, yaw_rate, pitch_rate]`，映射为 `rudder_angle`（垂直舵）、`stern_angle`（水平舵）和 `rpm`（推进器转速）。执行器具有一阶惯性动态，因此舵角和推力的实际响应滞后于命令。

 6 个变量：`X = [x, y, z, ψ, u, w]^T`，其中 `x, y` 为 NED 平面位置（m），`z` 为 NED 深度（m，正向下），`ψ` 为航向角（rad），`u` 为前向速度 surge（m/s），`w` 为垂向速度 heave（m/s）。横向速度 `v`（sway）不被控制，通过 `ψ` 偏转间接影响 `(x, y)` 轨迹。

### 4.1.2 决策与控制系统的分层解耦逻辑

AUV 海缆巡检任务需要把"去哪里巡检"、"如何沿电缆走"、"感知不可靠时如何降级"和"出现安全风险时如何退出"放在同一个系统中处理。本文采用分层解耦设计：

| 层级 | 职责 | 实现 |
|---|---|---|
| 任务调度层 | 决定当前应处于搜索/锁定/跟踪/上浮/返航/急停哪个阶段 | 行为树（Behavior Tree） |
| 轨迹生成层 | 根据任务阶段产生参考路径和参考速度 | 之字形扫描 + 电缆跟踪轨迹 |
| 参考生成层 | 把参考路径转化为航向/深度/速度指令 | LOS / MPC guidance-level |
| 低层控制层 | 把参考指令转化为舵角和推力 | PID/PVS depthHeadingAutopilot |
| 安全仲裁层 | 监控感知、通信和执行器状态，必要时限制或回退输出 | CommandGuard + failsafe 节点 |



## 4.2 基于行为树的任务规划与调度

### 4.2.1 行为树节点设计

rd_start_mock_amd_Condition）和行动节点（Action）组成。条件节点检查系统状态并返回成功、失败或运行中；行动节点执行具体操作。

| 节点类型 | 名称 | 职责 |
|---|---|---|
| Condition | `isBatteryOk` | 检查电池电压是否高于安全阈值 |
| Condition | `isCableDetected` | 检查声磁观测是否确认电缆存在 |
| Condition | `isCommunicationOk` | 检查与上位机/执行层的通信状态 |
| Condition | `isSafetyMarginViolated` | 检查离底高度是否低于安全阈值 |
| Action | `searchPattern` | 执行之字形扫描搜索 |
| Action | `cableTracking` | 沿电缆中心线跟踪 |
| Action | `emergencySurface` | 紧急上浮到安全深度 |
| Action | `returnToHome` | 返回起始位置 |

### 4.2.2 巡检任务逻辑流

#
rd_start_mock_amd_bg

1. **搜索阶段（Zig-zag）**：在未知区域执行之字形扫描，扩大探测范围，等待声磁观测确认电缆。
2. **锁定阶段**：当观测确认电缆存在后，切换到电缆中心线附近，建立稳定的相对位置估计。
3. **跟踪阶段**：沿电缆路由持续更新航向、速度和离底高度，同时监控感知质量和安全约束。
4. **异常处理**：当感知不可靠时降低速度或切换到搜索模式；当安全约束被违反时触发紧急上浮。

PATH="$PATH:/root/.trae-cn-server/bin/stable-18a1ac5cc57753e4f248b4095f404def974ec17b-debian10/node_modules/@vscode/ripgrep/bin"PATH="$PATH:/root/.trae-cn-server/bin/stable-18a1ac5cc57753e4f248b4095f404def974ec17b-debian10/node_modules/@vscode/ripgrep/bin""正常任务可组合、异常任务可抢占"的结构，尤其适合把搜索、锁定、跟踪、应急上浮、失联保护等行为组织在同一个决策框架中。

### 4.2.3 应急自救行为的优先级机制

Failsafe 节点对低电压、漏水、失联、传感器失效和控制器异常保持更高优先级。当任一安全条件被违反时，行为树中断当前任务，切换到相应的应急行为。

| 故障类型 | 触发条件 | 响应行为 |
|---|---|---|
| 低电压 | 电池电压低于阈值 | 上浮到安全深度 + 返航 |
| 漏水 | 漏水传感器触发 | 立即上浮 + 急停 |
| 失联 | 与 AMD/VxWorks 通信超时 1 s | 执行器停机（VxWorks 侧失联保护） |
| 传感器失效 | DVL/声呐/磁场连续异常 | 减速 + 切换到搜索模式 |
| 控制器异常 | MPC 求解超时或发散 | 回退到 PID baseline |

`docs/experiment/benchmark_test_log.md` 中已有单次 BT vs FSM 基准结果（n=1），可作为行为树单次效果的初步证据。

## 4.3 不确定的感知轨迹生成策略

### 4.3.1 对齐行业标准的"之字形"空间扫描轨迹设计

/dev/null /dev/null/dev/null--------对探测覆盖率的要求。扫描间距应根据声呐波束宽度和磁传感器有效探测距离确定，确保相邻扫描带之间有足够的重叠，避免漏检。

> **表格占位符**：正式论文中需补充扫描间距计算公式、不同波束宽度下的扫描带宽度表和覆盖率统计表。

### 4.3.2 基于感知置信度的动态航速规划模型

rd_start_mock_amd_bgAUV 可以以设计速度沿电缆巡检；当感知置信度降低时，控制器应降低航速，增加安全裕度。动态航速规划的核心是把感知不确定性映射为速度上限调节。

rd_start_mock_amd_bg UA-MPC 的权重调整机制深度耦合。具体而言：

1. **感知置信度到速度上限的映射**：系统维护一个实时置信度值 `confidence ∈ [0, 1]`，由 ES-EKF 的协方差矩阵经 `cov_to_conf` 模块计算得到。当置信度低于 `confidence_threshold`（默认 0.6）时，参考速度 `target_speed_mps` 随置信度下降而降低，形成"感知越不可靠、行驶越保守"的行为。

2. **与 UA-MPC 权重联动的闭环**：置信度降低不仅导致速度上限下降，同时触发 UA-MPC 内部代价函数的动态调整——增大控制惩罚权重（使指令变化更平滑），放大跟踪权重（在已知参考附近保持保守跟随）。这种联动机制确保速度和参考生成两个通道都响应不确定性变化。

3. **降级策略的层次化响应**：第一级为速度调节（confidence > 0.3），第二级为切换到搜索模式（confidence ∈ [0.1, 0.3]），第三级为紧急上浮（confidence < 0.1）。

#
--------的实现路径为：ES-EKF 协方差 → `cov_to_conf` → `confidence` → UA-MPC 代价权重 + 参考速度。完整链路详见第 3 章。

## 4.4 不确定性感知模型预测控制设计

### 4.4.1 离散化运动学预测模型

MPC 在当前系统中的定位是 **guidance-level reference generator**。它输出 `ψ_cmd / z_cmd / T_cmd`（目标航向、目标深度、推力百分比），再由 PVS 内层 `depthHeadingAutopilot` 或 AMD 侧 PID 执行，因此不等同于直接舵面级控制器。这个定位使 MPC 更适合讨论路径预瞄、速度调节、约束处理和不确定性权重，而不是在低层深度闭环中强行与 PID 竞争。

MPC 的预测模型基于 AUV 4-DOF 运动学/动力学方程离散化得到，状态向量为 6 维：

```
X = [x, y, z, ψ, u, w]^T
```

 3 维：

```
U = [ψ_cmd, z_cmd, T_cmd]^T
```

rd_start_mock_amd_bg

```
dx/dt  = u · cos(ψ)
dy/dt  = u · sin(ψ)
dz/dt  = -u · sin(θ_approx) + w · cos(θ_approx)
dψ/dt  = yaw_rate_gain · (ψ_cmd - ψ)
du/dt  = (thrust_actual - drag_u · u · |u|) / mass_u
dw/dt  = (-drag_w · w + depth_to_heave_gain · (z_cmd - z) + buoyancy_term) / mass_w
```

-------- `θ_approx` 由目标深度误差经 `pitch_depth_gain` 限幅得到，限幅范围为 `[-max_pitch_rad, +max_pitch_rad]`（默认 ±15°）。NED 约定下，深度 z 正向下，俯仰角正为船头向上，因此目标深度更深时需要负俯仰角。推力经 `max(0, T_cmd)` 限幅，确保不产生反向推力。

#
 Euler 向前法：

```
X_{k+1} = X_k + dt · f(X_k, U_k)
```

-------- `dt` 为 MPC 时间步长（默认 0.1 s），预测时域 `N` 为 20 步，覆盖 2 s 未来状态。

### 4.4.2 代价函数构建

MPC 在每个控制周期求解以下优化问题：

```
min J = J_tracking + J_control
```

**跟踪代价** `J_tracking`（对预测时域内每步 k = 0…N）：

```
J_tracking = Σ [w_x · (x_k - x_ref_k)² + w_y · (y_k - y_ref_k)²
               + w_z · (z_k - z_ref_k)² + w_ψ · (ψ_k - ψ_ref_k)²
               + w_u · (u_k - u_ref_k)² + w_w · (w_k - w_ref_k)²]
```

rd_start_mock_amd_bg`W_x = 1.0, W_y = 1.0, W_z = 5.0, W_ψ = 3.0, W_u = 0.5, W_w = 1.0`。

**控制代价** `J_control`（对控制时域内每步 k = 0…N-1）：

```
J_control = Σ control_scale · [W_ψ_cmd · ψ_cmd_k² + W_z_cmd · z_cmd_k² + W_T · T_cmd_k²]
```

rd_start_mock_amd_bg`W_ψ_cmd = 0.1, W_z_cmd = 0.1, W_T = 0.05`。

### 4.4.3 UA-MPC 不确定性感知权重动态调整算法

UA-MPC（Uncertainty-Aware MPC）是本文的核心创新点之一。其核心思想是把感知置信度或协方差变化映射到控制代价权重，使控制器在观测不可靠时自动降低激进程度，在观测可靠时积极跟踪参考路径。

#### （1）跟踪权重的不确定性感知调整

 UA 模式下，跟踪权重根据置信度动态缩放。对 x、y、ψ 维度：

```
w_x = W_x · [1 + (low_conf_scale - 1) · (1 - conf)^α]
w_y = W_y · [1 + (low_conf_scale - 1) · (1 - conf)^α]
w_ψ = W_ψ · [1 + (low_conf_scale - 1) · (1 - conf)^α]
```

         z 维度，放大系数减半：

```
w_z = W_z · [1 + 0.5 · (1 - conf)^α]
```

--------：
- `conf ∈ [0, 1]` 为感知置信度，由 EKF 协方差计算得到
- `low_conf_scale` 为低置信度缩放因子（默认 3.0），控制不确定性最大可放大跟踪权重多少倍
- `α`（`confidence_alpha`）为幂指数（默认 1.5），控制权重随置信度下降的非线性程度。当 `α = 1` 时退化为线性调整

rd_start_mock_amd_bg-------- `(1 - conf)^α` 确保：置信度高时权重接近基础值；置信度低时权重放大，优化器更倾向于在参考轨迹附近保守跟随，减少偏离。

#### （2）控制代价的 sigmoid 平滑调整

#
`control_scale` 采用 sigmoid 函数实现平滑过渡：

```
sig = 1 / [1 + exp(k · (conf - confidence_threshold))]
control_scale = low_conf_ctrl_scale + (1 - low_conf_ctrl_scale) · (1 - sig)
```

--------：
- `k`（`confidence_smoothness_k`）为 sigmoid 陡峭度（默认 8.0）
- `confidence_threshold` 为置信度阈值（默认 0.6）
- `low_conf_ctrl_scale` 为低置信度控制缩放因子（默认 0.3）

rd_start_mock_amd_bg      `control_scale ≈ 1`，控制指令正常输出；置信度低于阈值时 `control_scale` 平滑降至 `low_conf_ctrl_scale`，使优化器对控制量施加更大惩罚，输出更平滑的指令。相比硬切换（hard threshold），sigmoid 平滑避免了权重突变导致的控制量跳变。

#### （3）消融模式开关

UA-MPC 提供 `mpc_mode` 消融开关：
- `mpc_mode = "ua"`：启用完整的 UA 机制（跟踪权重 + 控制代价的动态调整）
- `mpc_mode = "baseline"`：忽略置信度，权重恒定，作为消融对照基线

 `AUV_MPC_MODE` 实现，支持 sweep 实验自动化。

#### （4）UA-MPC 参数完整清单

| 参数 | 默认值 | 含义 | 消融变体 |
|---|---|---|---|
| `mpc_mode` | `ua` | baseline / ua 切换 | A0 vs A1 |
| `low_confidence_scale` | 3.0 | 低置信度跟踪权重放大倍数 | A4（设为 0 退化为 baseline） |
| `low_confidence_control_scale` | 0.3 | 低置信度控制代价缩放 | — |
| `confidence_alpha` | 1.5 | 跟踪权重幂指数 | A3（设为 1.0 退化为线性） |
| `confidence_smoothness_k` | 8.0 | sigmoid 陡峭度 | A2（设为 hard 关闭 sigmoid） |
| `confidence_threshold` | 0.6 | 置信度阈值 | — |
| `prediction_horizon` | 20 | 预测步数 N | — |
| `dt` | 0.1 | 时间步长（s） | — |

### 4.4.4 参考轨迹生成

MPC 的参考轨迹支持两种模式：

1. **LOS 动态模式**（`use_los_reference = true`）：基于电缆点序列和 LOS 前视距离动态生成参考轨迹。算法沿电缆点序列逐步前推，前视距离随时间递增（`los_lookahead += target_speed · dt`），使 MPC 能预瞄前方路径。适用于有已知电缆路由的场景。

2. **恒定航向模式**：使用恒定航向 + 恒定深度的前向推进策略生成参考轨迹。适用于无电缆点或搜索阶段。

 `(6, N+1)` 维数组，包含每步的 `x, y, z, ψ, u, w` 参考值。

### 4.4.5 执行器物理饱和约束处理

MPC 需要处理舵角限幅、角速度限制和推力饱和等物理约束。在预测时域内，控制器必须在约束可行域内搜索最优解，而不是产生超出执行器能力的命令。

**硬约束体系**：

| 约束类型 | 表达式 | 默认范围 | 物理含义 |
|---|---|---|---|
| 航速下限 | `u_k ≥ min_speed` | 0.1 m/s | 确保舵效 |
| ψ_cmd 限幅 | `ψ_cmd ∈ [min_psi_cmd, max_psi_cmd]` | [-π, π] rad | 航向指令合理性 |
| z_cmd 限幅 | `z_cmd ∈ [min_z_cmd, max_z_cmd]` | [0, 50] m | 深度指令合理性 |
| 推力下限 | `T_cmd ≥ min_thrust` | 0% | 防止推力清零失稳 |
| 推力上限 | `T_cmd ≤ max_thrust` | 100% | 执行器饱和 |

**P1 扩展约束**（速率 + 带宽）：

| 约束类型 | 表达式 | 默认值 | 物理含义 |
|---|---|---|---|
| z_cmd 速率 | `|z_cmd_{k+1} - z_cmd_k| ≤ delta_z_max_per_step` | 0.5 m/step | 深度指令变化率 |
| ψ_cmd 速率 | `|ψ_cmd_{k+1} - ψ_cmd_k| ≤ delta_psi_max_per_step` | 8°/step | 航向指令变化率 |
| z_cmd 带宽 | `|z_cmd_k - z_current| ≤ z_band` | 3.0 m | 深度指令不能离当前态太远 |
| ψ_cmd 带宽 | `|ψ_cmd_k - ψ_current| ≤ psi_band` | 45° | 航向指令不能离当前态太远 |

rd_start_mock_amd_bg/禁用（`enable_rate_constraints` 和 `enable_band_constraints`）。

### 4.4.6 求解器实现与热启动

MPC 求解器基于 CasADi Opti + IPOPT 后端构建：

- **构建策略**：优化问题结构在初始化时编译一次（`_build_solver`），反复求解时仅更新参数值（`set_value`），避免重复编译开销。
- **热启动**（Warm Start）：使用上一次最优控制序列作为初始猜测，加速 IPOPT 收敛。热启动序列通过右移实现：`U_guess[:, k] = U_prev[:, k+1]`，最后一步重复使用上一步最后一个控制量。
- **求解器配置**：`ipopt.tol = 1e-4`，`ipopt.max_iter = 100`，`print_level = 0`。
- **求解失败处理**：当 IPOPT 返回失败状态时，抛出 `RuntimeError`。在 `MPCController` 层捕获异常后，根据 `fail_safe_fallback` 配置决定是否回退到上一次输出或直接返回设定点。

/dev/null --------，舵角限幅为 ±5°–±6°（在 PVS `depthHeadingAutopilot` 侧实现），角速度限制由 MPC 变体的 `psi_band_deg` 参数控制，推力下限由 `min_thrust` 参数约束。

## 4.5 决策与控制系统的鲁棒性分析

### 4.5.1 感知信号剧烈波动下的控制平滑度对比

#
rd_start_mock_amd_bg

**第一层：terrain-following 的近底安全性**。已有 terrain benchmark 支撑。PID terrain 在 60 s 正式结果中实现了 `seabed_clearance_rmse_to_3m = 0.1752 m`，三档 low/mid/high terrain 消融均无 `<1.5 m` 安全违规。MPC terrain 虽然改善了固定深度 baseline，但未超过调优后的 PID/PVS。

**第二层：复杂平面路径制导**。已有离线 MPC x/y/yaw 支线提供初步证据。MPC 相比 yaw-only 固定速度 PID 的横向误差有约 21%–39% 改善，但没有全面超过 LOS 强 baseline。

**第三层：高不确定性场景下的 UA-MPC 主消融**。目前已完成 3 场景 × 2 模式 × 3 seed 的主消融实验，涵盖 baseline、DVL dropout 60% 和 combined stress 场景。在 baseline 和 combined stress 场景中，UA-MPC 相比 baseline-MPC 在定位指标上展现出改善趋势，但在 DVL dropout 60% 的极重度丢包场景中优势不显著，说明 EKF 在极重度速度观测丢失下状态质量已严重退化，MPC 权重调整难以补偿。

### 4.5.2 极端工况下的安全性边界测试

rd_start_mock_amd_bg--------断等场景。当前已有 MPC x/y/yaw 支线中的 `chicane_90deg` 和 `hairpin_180deg` 极端路径，但尚未接入完整 PVS/ROS 感知闭环。

`pvs_extreme_cable_scenarios.md` 中定义了 6 个极端电缆巡检场景：S-curve、Hairpin、Slope Crossing、Buried Gap、Cross Current 和 Combined Extreme，每个场景包含真实风险分析、路径设置、观测角色和评价指标。

> **表格占位符**：正式论文中需补充极端工况下的控制平滑度对比表，包括控制量变化率、求解时间分布、fallback 触发率和安全违规次数。

## 4.6 本章小结

 AUV 的运动约束和分层控制架构，阐述了行为树任务调度、轨迹生成策略和不确定性感知控制设计。重点介绍了 UA-MPC 的完整实现：包括 4-DOF 运动学预测模型、代价函数构建、不确定性感知权重动态调整（(1-conf)^α 跟踪权重 + sigmoid 平滑控制代价）、参考轨迹生成（LOS 动态 + 恒定航向）、执行器物理约束体系（速率 + 带宽扩展）和 IPOPT 求解器热启动实现。通过三层鲁棒性分析（terrain 近底安全、复杂路径制导、UA-MPC 不确定性适应），明确了当前各控制层级的证据强弱。当前采用行为树完成任务调度和应急优先级组织，采用 PID/PVS 作为当前最可靠的近底地形跟随主控制器，并实现 guidance-level MPC 作为复杂路径预瞄和 UA-MPC 扩展基础。当前结果支持"分层控制与安全回退有效"，但不支持"MPC 全面优于 PID/LOS"。
