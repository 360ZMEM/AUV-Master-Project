# 03 - 动力学补偿与配平 (Dynamics & Trim)

> 本文件详细说明 `feedforward_trim_deg` 和速度前馈模型 `control.speed.feedforward` 的调节逻辑。  
> 这是仿真与实机差异最大的区域：仿真中浮力模型理想、流体阻力均匀；实机中压载不均、海流干扰、船体污损均会破坏理想假设。

---

## 1. 俯仰前馈配平 (`feedforward_trim_deg`)

### 1.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机可能范围 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `control.feedforward_trim_deg` | float | `-1.5` | `-5.0 ~ 3.0` (°) | `params.yaml:73` |

在 `auv_pid_controller.py:compute` 中（line 235）：

```python
# 俯仰 PID 输出后叠加 Trim 前馈
elevator_cmd += self.feedforward_trim
elevator_cmd = np.clip(elevator_cmd, -fin_deg_max, fin_deg_max)
```

其中 `self.feedforward_trim = np.deg2rad(feedforward_trim_deg)`（line 112）。

### 1.2 物理意义：为何 AUV 必须带稳态下潜角

AUV 在海缆巡检任务中需要在固定深度（通常 3~5 米）水平航行。理想情况下，零舵角 + 零浮力偏差 = 水平巡航。但实机存在以下不可避免的物理偏差：

| 偏差源 | 对姿态的影响 | 需要的补偿方向 |
|:---|:---|:---|
| **正浮力** (Buoyancy > Weight) | AUV 自然上浮倾向 | 需要 **负 Trim**（Top 舵面向下偏 / Bottom 舵面向上偏 → 产生下俯力矩） |
| **重心偏移** (CG 不在几何中心) | 产生固有俯仰力矩 | 根据偏移方向调整 Trim |
| **船体外形不对称** | 水动力中心 (CP) ≠ CG | 速度相关，需非线性补偿 |
| **海流剪切** | 上下层流速不同导致俯仰扰动 | 动态补偿（Trim 不够用，需增大 PID） |

**`feedforward_trim_deg = -1.5`** 的含义：
- 负值 → 在 PID 计算的舵角基础上 **额外增加下俯角度**
- 这抵消正浮力引起的上浮倾向，使 AUV 在零 PID 输出时仍保持微下潜角
- 在 1.1 m/s 巡航速度下，约 -1.5° 的下潜角产生足够的水动力升力来平衡正浮力

### 1.3 不同压载重量下的调节指南

| 压载状态 | 浮力特性 | 推荐 `feedforward_trim_deg` | 调整方向 |
|:---|:---|:---:|:---|
| **正浮力** (略浮于水面) | 自然上浮 | `-2.0 ~ -5.0` | 增大负值（更下俯） |
| **中性浮力** (刚好悬浮) | 无自然倾向 | `-1.0 ~ -2.0` | 微调即可 |
| **微负浮力** (缓慢下沉) | 自然下沉 | `0.0 ~ 1.0` | 减小负值甚至变正 |
| **显著负浮力** | 快速下沉 | `1.0 ~ 3.0` | 正值（仰首补偿） |

### 1.4 调节 SOP

**目标**：在目标巡航速度下，使 AUV 保持水平（Pitch ≈ 0°）且深度稳定。

**步骤**：

1. **初始设置**：
   ```bash
   ros2 param set /auv_bridge_node feedforward_trim_deg -1.5
   ```

2. **第一次试航**（以 1.1 m/s 巡航，目标深度 4m）：
   - 观察稳态 Pitch 角（速度稳定后的平均俯仰）
   - 记录 `稳态_pitch`（取 30 秒均值）

3. **计算调整量**：
   ```
   trim_adjustment = -稳态_pitch(度)
   new_trim_deg = old_trim_deg + trim_adjustment
   ```

   | 现象 | 稳态 Pitch | 调整方向 | 示例 |
   |:---|:---:|:---:|:---|
   | 艇首上仰 | +2.0° | 减小 Trim | `-1.5 + (-2.0) = -3.5` |
   | 艇首下俯 | -3.0° | 增大 Trim | `-1.5 + 3.0 = +1.5` |
   | 水平 | ≈ 0° | 无需调整 | 保持 `-1.5` |

4. **在线调整命令**：
   ```bash
   # 假设稳态 Pitch = +2°（艇首上仰），需要更负的 Trim
   ros2 param set /auv_bridge_node feedforward_trim_deg -3.5
   ```

5. **重复验证**：每次调整后等待 20 秒观察稳态效果，迭代直到 Pitch 在 ±0.5° 内。

> **仿真默认**：`-1.5`（模拟轻微正浮力）  
> **实机暗病**：如果 Trim 设得太负（如 -8°），下潜时会产生过度下俯，深度环超调 → 深度振荡。  
> **关键约束**：`|feedforward_trim_deg|` 不应超过 `limits.fin_deg_max` 的 50%（即 ±7.5°），否则留给 PID 的调节余量不足。

---

## 2. 速度-阻尼模型 (`control.speed.feedforward`)

### 2.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机可能范围 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `control.speed.feedforward.a` | float | `0.0` | `1.0 ~ 5.0` | `params.yaml:103` |
| `control.speed.feedforward.b` | float | `0.0` | `10.0 ~ 40.0` | `params.yaml:104` |
| `control.speed.feedforward.c` | float | `0.0` | `0.0 ~ 2.0` | `params.yaml:105` |

在 `auv_pid_controller.py:compute` 中（line 258-259）：

```python
# 二次多项式前馈：推力 = a·u² + b·u + c
thrust_feedforward = self.speed_ff_a * (target_u ** 2) + self.speed_ff_b * target_u + self.speed_ff_c
thrust_cmd = thrust_feedforward + thrust_feedback  # 前馈 + PID 反馈
```

### 2.2 物理意义

该前馈模型将**目标速度映射为推力参考值**，用于抵消水阻力的稳态分量：

```
F_thrust = a·u² + b·u + c
```

其中各项的物理含义：

| 系数 | 对应物理效应 | 数学来源 |
|:---|:---|:---|
| **a** | **平方阻尼** (Quadratic Drag)：高速下占主导，与速度平方成正比 | `F_drag = ½ρCdA·u²` |
| **b** | **线性阻尼** (Linear Drag)：低速粘性阻力 | `F_viscous = k·u` |
| **c** | **常数偏移**：克服静浮力/静摩擦的基线推力 | `F_bias = 常数` |

在仿真参数 `sim_params.yaml` 中，已标定的实机拟合值为：
```yaml
feedforward:
  a: 2.497183    # 平方阻尼系数
  b: 27.729751   # 线性阻尼系数
  c: 0.546851    # 常数偏移
```

### 2.3 实测拟合 SOP

**目标**：通过实机航速试验，拟合出 `a`, `b`, `c` 三个系数。

**设备要求**：
- 高精度 GPS 或 DVL（提供真实地速）
- 推力/电流监测（可选，用于交叉验证）

**步骤**：

1. **数据采集**：
   - 在平静水域（无流/浪 < 0.1 m/s）
   - 依次设定不同推力百分比，等待速度稳定后记录：

   | 推力指令 (%) | 稳态速度 (m/s) | 记录次数 |
   |:---:|:---:|:---:|
   | 10 | u₁ | 3 次取均值 |
   | 20 | u₂ | 同上 |
   | 30 | u₃ | 同上 |
   | 40 | u₄ | 同上 |
   | 50 | u₅ | 同上 |
   | 60 | u₆ | 同上 |
   | 70 | u₇ | 同上 |
   | 80 | u₈ | 同上 |

2. **数据拟合**：
   - 对每组数据 `(thrust_pct, u_steady)`，建立方程：
     ```
     thrust_pct = a·u² + b·u + c
     ```
   - 使用最小二乘法拟合（Python 示例）：
     ```python
     import numpy as np
     
     # 实测数据
     u = np.array([u1, u2, u3, ...])     # 稳态速度
     T = np.array([T1, T2, T3, ...])     # 对应推力百分比
     
     # 二次多项式拟合
     coeffs = np.polyfit(u, T, 2)  # 返回 [a, b, c]
     a, b, c = coeffs[0], coeffs[1], coeffs[2]
     print(f"a = {a:.6f}, b = {b:.6f}, c = {c:.6f}")
     ```

3. **写入参数**：
   ```bash
   ros2 param set /auv_bridge_node a <a值>
   ros2 param set /auv_bridge_node b <b值>
   ros2 param set /auv_bridge_node c <c值>
   ```

4. **验证**：
   - 设定目标速度 `target_u = 1.1`，观察实际速度是否快速收敛
   - 若收敛快且超调小 → 前馈模型准确
   - 若稳态误差大 → 调整 `c`；若加速慢 → 调整 `b`；若高速段误差大 → 调整 `a`

### 2.4 仿真 vs 实机对照

| 场景 | a | b | c | 说明 |
|:---|:---:|:---:|:---:|:---|
| **仿真 (默认)** | 0.0 | 0.0 | 0.0 | 无前馈，纯 PID 反馈 |
| **仿真 (标定)** | 2.497 | 27.730 | 0.547 | 基于仿真流体模型的拟合值 |
| **实机 (清水)** | 2.0~3.5 | 20.0~35.0 | 0.0~1.5 | 船体干净，阻力接近仿真 |
| **实机 (污损)** | 3.5~6.0 | 35.0~50.0 | 1.0~3.0 | 船体附生物增加阻力，系数全线上移 |
| **实机 (强流)** | 2.0~3.5 | 20.0~35.0 | 3.0~8.0 | `c` 显著增大（需额外推力对抗流） |

> **暗病排查**：实机中若 `feedforward` 全为零（仿真默认值），速度环将完全依赖 PID 积分项 → 加速时响应慢、减速时超调大。  
> **建议**：首次实机部署时，先使用仿真标定值作为起点，再根据实际响应微调。

---

## 3. 速度增益缩放 (`_gain_scale`)

### 3.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机可能范围 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `control.u0` | float | `1.0` | `0.8 ~ 1.5` | `params.yaml:71` |
| `control.u_min` | float | `0.6` | `0.3 ~ 0.8` | `params.yaml:72` |
| `control.target_u` | float | `1.1` | `0.5 ~ 2.0` | `params.yaml:70` |

在 `auv_pid_controller.py:_gain_scale` 中（line 142-143）：

```python
def _gain_scale(self, u_forward):
    effective_u = max(abs(u_forward), self.u_min)
    return (self.u0 / effective_u) ** 2
```

### 3.2 物理意义

舵面的水动力效率与航速的平方成正比。低速时舵面几乎无效，高速时舵面响应灵敏。增益缩放因子用于补偿这一非线性：

```
gain_scale = (u0 / max(|u|, u_min))²
```

- 当 `|u| = u0` 时，`gain_scale = 1.0`（标准增益）
- 当 `|u| < u0` 时，`gain_scale > 1.0`（增大 PID 输出补偿舵效不足）
- 当 `|u| > u0` 时，`gain_scale < 1.0`（减小 PID 输出防止过度敏感）
- 当 `|u| < u_min` 时，使用 `u_min` 计算，防止增益发散

### 3.3 仿真 vs 实机对照

| 参数 | 仿真默认 | 实机建议 | 说明 |
|:---|:---:|:---:|:---|
| `u0` | 1.0 m/s | 1.0 ~ 1.2 m/s | 设计巡航速度 |
| `u_min` | 0.6 m/s | 0.3 ~ 0.5 m/s | 低于此速度舵效极低，建议停机或改推进器控制 |
| `target_u` | 1.1 m/s | 0.8 ~ 1.5 m/s | 任务目标速度 |

**调试命令**：
```bash
# 降低 u_min 使低速时增益不过度放大
ros2 param set /auv_bridge_node u_min 0.4

# 根据实际巡航速度调整 u0
ros2 param set /auv_bridge_node u0 1.2
```

---

## 4. 姿态保护 (Attitude Guard)

### 4.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机可能范围 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `control.attitude_guard.enable` | bool | `true` | `true/false` | `params.yaml:75` |
| `control.attitude_guard.roll_deg_max` | float | `120.0` | `90.0 ~ 150.0` | `params.yaml:76` |
| `control.attitude_guard.pitch_deg_max` | float | `45.0` | `30.0 ~ 60.0` | `params.yaml:77` |
| `control.attitude_guard.recovery_target_pitch_deg` | float | `0.0` | `-5.0 ~ 5.0` | `params.yaml:78` |
| `control.attitude_guard.recovery_thrust` | float | `20.0` | `10.0 ~ 40.0` | `params.yaml:79` |

在 `auv_pid_controller.py:compute` 中（line 176-204）：

```python
attitude_guard_active = enable and (
    abs(roll_deg) > roll_deg_max or abs(pitch_deg) > pitch_deg_max
)

if attitude_guard_active:
    # 重置积分，关闭正常控制
    depth_pid.reset_integral()
    yaw_pid.reset_integral()
    # 目标俯仰设为 recovery 值
    target_pitch = recovery_target_pitch_rad
    # 推力设为 recovery 值
    thrust_cmd = recovery_thrust
    # 禁用积分，防止恢复时积分风暴
```

### 4.2 触发逻辑

```
正常控制 ←→ [Roll > 120° 或 Pitch > 45°] → 姿态保护模式
                                              │
                                              ├── 目标 Pitch = 0° (水平)
                                              ├── 推力 = 20% (维持速度)
                                              ├── 舵面 = 仅 Pitch 环工作
                                              └── 积分清零（防风暴）
                                              │
                                              ← [姿态回到安全范围内] ←→ 恢复正常控制
```

### 4.3 仿真 vs 实机对照

| 场景 | `roll_deg_max` | `pitch_deg_max` | 说明 |
|:---|:---:|:---:|:---|
| **仿真** | 120.0° | 45.0° | 仿真中 AUV 很少翻滚，阈值宽松 |
| **实机 (海缆巡检)** | 90.0° | 30.0° | 提前触发保护，防止碰撞海缆 |
| **实机 (浅水)** | 90.0° | 25.0° | 更严格的 Pitch 限制，防穿底 |

**调试命令**：
```bash
# 收紧姿态保护阈值（浅水环境）
ros2 param set /auv_bridge_node roll_deg_max 90.0
ros2 param set /auv_bridge_node pitch_deg_max 25.0

# 调整保护模式下的推力
ros2 param set /auv_bridge_node recovery_thrust 30.0
```

---

## 5. 动力学参数汇总对照表

| 参数名 | 仿真默认值 | 实机可能范围 | 调节频率 | 影响范围 |
|:---|:---:|:---:|:---:|:---|
| `feedforward_trim_deg` | -1.5° | -5.0 ~ 3.0° | 每次压载变化后 | 稳态俯仰角 |
| `speed.feedforward.a` | 0.0 | 1.0 ~ 6.0 | 每季度（船体状态变化） | 高速段推力 |
| `speed.feedforward.b` | 0.0 | 10.0 ~ 50.0 | 同上 | 中速段推力 |
| `speed.feedforward.c` | 0.0 | 0.0 ~ 8.0 | 每次海况变化后 | 基线推力 |
| `u0` | 1.0 m/s | 0.8 ~ 1.5 m/s | 初始标定 | 增益缩放基准 |
| `u_min` | 0.6 m/s | 0.3 ~ 0.8 m/s | 初始标定 | 低速增益上限 |
| `target_u` | 1.1 m/s | 0.5 ~ 2.0 m/s | 每次任务 | 目标速度 |
| `roll_deg_max` (guard) | 120.0° | 90.0 ~ 150.0° | 根据任务环境 | 保护触发阈值 |
| `pitch_deg_max` (guard) | 45.0° | 25.0 ~ 60.0° | 根据水深 | 保护触发阈值 |
