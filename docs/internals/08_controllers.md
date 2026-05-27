# 控制器原理

## 级联 PID 控制器

实现位于 `algorithm/auv_pid_controller.py`

### 架构

```
目标深度 → [深度PID] → 目标俯仰 → [俯仰PID] → 升降舵
目标航向 → [航向PID] → 方向舵
目标速度 → [速度PID + 前馈] → 推力
```

深度控制采用级联结构：外环（深度PID）产生目标俯仰角，内环（俯仰PID）驱动升降舵偏角。航向和速度为单环控制。

### PIDAxis 类

单轴 PID 调节器，提供：

- **积分限幅**：防止积分饱和（windup），限制积分项绝对值
- **导数反馈**：对测量值而非误差求导，避免设定值突变引起的微分尖峰
- **饱和回退（Anti-windup）**：当输出饱和时暂停积分器累积

```python
class PIDAxis:
    def compute(self, error, measurement, dt) -> float:
        P = self.Kp * error
        self.integral = clamp(self.integral + error * dt, -self.i_max, self.i_max)
        I = self.Ki * self.integral
        D = self.Kd * (measurement - self.prev_measurement) / dt
        output = clamp(P + I - D, self.out_min, self.out_max)
        return output
```

### 输入/输出

**输入 state（当前状态）：**

| 字段 | 单位 | 说明 |
|------|------|------|
| roll | rad | 横滚角 |
| pitch | rad | 俯仰角 |
| yaw | rad | 航向角 |
| depth | m | 深度 |
| u | m/s | 纵向速度 |
| v | m/s | 横向速度 |
| w | m/s | 垂向速度 |
| p | rad/s | 横滚角速度 |
| q | rad/s | 俯仰角速度 |
| r | rad/s | 航向角速度 |

**输入 target（目标）：**

| 字段 | 单位 | 说明 |
|------|------|------|
| target_depth | m | 目标深度 |
| target_yaw | rad | 目标航向 |
| target_u | m/s | 目标航速 |
| dt | s | 控制周期 |

**输出 command[5]：**

| 索引 | 含义 | 单位 |
|------|------|------|
| 0 | right（右舵） | 度 |
| 1 | top（上舵） | 度 |
| 2 | left（左舵） | 度 |
| 3 | bottom（下舵） | 度 |
| 4 | thrust（推力） | 百分比 |

### 特殊机制

#### 速度相关增益缩放

低速时舵效下降，需提高增益补偿：

```python
gain_scale = (u0 / u) ** 2  # u0为参考航速
```

当 `u < u_min` 时，`gain_scale` 被限幅到最大值，防止零速时增益爆炸。

#### 目标俯仰角速率限制

深度外环输出的目标俯仰角经过速率限制器：

```python
target_pitch = clamp(target_pitch, prev_target_pitch ± max_pitch_rate * dt)
```

避免深度大偏差时产生过大俯仰指令。

#### 姿态保护

当横滚或俯仰超出安全范围时进入恢复模式：

- `|roll| > roll_limit` 或 `|pitch| > pitch_limit`
- 恢复模式：忽略任务目标，优先恢复水平姿态

#### 低速积分器自动重置

当航速低于阈值时，自动清零各轴积分器：

```python
if u < u_reset_threshold:
    pid_depth.reset_integral()
    pid_yaw.reset_integral()
```

防止停车时积分累积，重新启动后产生突变。

#### 推力前馈

速度环包含前馈项，加速响应：

```python
FF = a * target_u**2 + b * target_u + c
thrust = pid_speed.output + FF
```

系数 `a, b, c` 由水池实验标定。

---

## MPC 控制器

实现位于 `algorithm/auv_mpc_controller.py`

### 运动学模型 (AUVKinematicsModel)

4-DOF 欠驱动模型：

- **状态向量** X[6] = [x, y, z, ψ, u, w]
  - x, y, z: 世界坐标系位置
  - ψ: 航向角
  - u: 纵向速度
  - w: 垂向速度

- **控制输入** U[3] = [ψ_cmd, z_cmd, T_cmd]
  - ψ_cmd: 航向指令
  - z_cmd: 深度指令
  - T_cmd: 推力指令

- **运动方程**：
  ```
  ẋ = u * cos(ψ)
  ẏ = u * sin(ψ)
  ż = -K_z * (z - z_cmd)
  ψ̇ = K_ψ * (ψ_cmd - ψ)
  u̇ = K_T * T_cmd - D_u * u
  ẇ = -K_z * (z - z_cmd) 相关项
  ```

### 优化器 (AUVMPCOptimizer)

- **求解器**：CasADi + IPOPT
- **预测步长**：N = 20 步
- **采样周期**：与控制周期匹配

### 代价函数

```
J = Σ_{k=0}^{N-1} [ (x_k - x_ref)^T Q (x_k - x_ref) + u_k^T R u_k ] 
    + (x_N - x_ref)^T Q_f (x_N - x_ref)
```

- **状态跟踪项**：Q 加权状态偏差，惩罚偏离参考轨迹
- **控制能耗项**：R 加权控制输入，惩罚过大控制量
- **终端代价**：Q_f 增大终端权重，改善稳定性

### 置信度自适应

根据定位置信度动态调整优化参数：

| 置信度 | Q 权重调整 | R 权重调整 | 行为 |
|--------|-----------|-----------|------|
| 高 (>0.8) | 正常 | 正常 | 积极跟踪 |
| 中 (0.5~0.8) | 增加位置权重 | 增加控制惩罚 | 保守跟踪 |
| 低 (<0.5) | 大幅增加 | 大幅增加 | 近乎保持 |

### 硬约束

- **最小航速**：`u >= u_min`，防止失速
- **推力限幅**：`T_min <= T_cmd <= T_max`
- **航向变化率**：`|Δψ| <= ψ_rate_max`

### 热启动 (Warm Start)

每次求解使用上一步的最优解作为初值：

```python
solver.set_initial(X_init=X_opt_prev[:, 1:], U_init=U_opt_prev[:, 1:])
```

大幅减少迭代次数，提高实时性。

### 输入/输出

**输入：**

| 参数 | 形状 | 说明 |
|------|------|------|
| x0 | (6,) | 当前状态 |
| ref_trajectory | (6, N+1) | 参考轨迹 |
| confidence | scalar [0,1] | 定位置信度 |

**输出：**

| 参数 | 形状 | 说明 |
|------|------|------|
| U_opt | (3, N) | 最优控制序列 |
| X_opt | (6, N+1) | 预测状态序列 |
| solver_status | int | 求解器状态码 |
| solve_time_ms | float | 求解耗时 (ms) |
| cost_value | float | 最优代价值 |

---

## 控制模式切换（ROS2 节点层）

### state_source 参数

| 值 | 数据源 | 适用场景 |
|----|--------|----------|
| `filtered` | EKF 融合输出 (`/auv/state/filtered`) | 正常任务 |
| `raw` | 传感器直接数据 (`/auv/sensors/*`) | EKF 异常时降级 |

### 仲裁器非 AUTONOMOUS 时

当仲裁器处于 REMOTE 模式：

1. **自动重置积分器**：所有 PID 轴的积分项清零
2. **Setpoint Shadowing**：控制器持续跟踪当前状态，准备无扰切换

### 地形跟踪引擎 (terrain_engine.py)

基于历史深度斜率估计和声呐前瞻的自适应深度控制：

```
estimated_slope = linear_fit(depth_history[-N:])
lookahead_depth = sonar_altitude_ahead
target_depth = max(safety_min, terrain_depth + clearance)
```

- 根据海底地形实时调整目标深度
- 保持恒定离底高度
- 声呐前瞻提供预判，减少响应延迟
