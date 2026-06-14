# PID 控制器调优经验指南

> 基于 PythonVehicleSimulator (PVS) REMUS 100 物理模型的系统化调优实践

## 1. 核心物理模型理解

### 1.1 Fossen/PVS NED 坐标系约定

**这是所有符号问题的根源！**

```
NED (North-East-Down) 右手坐标系:
- X轴: 北 (North)
- Y轴: 东 (East)
- Z轴: 下 (Down) → z正 = 深度增加
```

**关键运动学方程** (Fossen 2021, Eq. 2.85):

```python
# 从体轴速度到NED位置的变换
dz/dt = -u*sin(theta) + w*cos(theta)  # 当 phi=0, v=0 时简化

# 关键发现:
# theta > 0 (正俯仰角) => sin(theta) > 0 => dz/dt = -u*(正) < 0 => z减小 => 上浮!
# theta < 0 (负俯仰角) => sin(theta) < 0 => dz/dt = -u*(负) > 0 => z增大 => 下潜!
```

**反直觉结论**:
| theta (俯仰角) | 物理含义 | 深度变化 |
|---------------|---------|---------|
| **正** | 船头**上仰** | **上浮** (z减小) |
| **负** | 船头**下俯** | **下潜** (z增大) |

> ⚠️ **重要**: 这与直觉相反！通常认为"船头向下=下潜"，但在Fossen约定中，theta正=船头上仰。

### 1.2 舵面力符号约定

**PVS remus100.py 公式**:

```python
# 尾翼力 (heave force, Z方向)
Z_s = -0.5 * rho * U_rv² * A_s * CL_delta_s * delta_s

# 舵力 (sway force, Y方向)
Y_r = -0.5 * rho * U_rh² * A_r * CL_delta_r * delta_r

# 力矩 (PVS remus100.py:L378-379)
tau[4] = -x_s * Z_s  # 俯仰力矩
tau[5] = x_r * Y_r   # 偏航力矩
```

**物理推导** (x_s = x_r = -0.8m):

| delta_s | Z_s 方向 | tau[4] | theta变化 | 深度变化 |
|---------|---------|--------|-----------|---------|
| **正** | 向上 (Z_s<0) | 负 | 增加(更正) | **上浮** |
| **负** | 向下 (Z_s>0) | 正 | 减少(更负) | **下潜** |

### 1.3 PVS 深度控制器架构

**级联控制结构** (remus100.py:L457-470):

```
外环 (PI): 深度误差 → 期望俯仰角
  theta_d = Kp_z * ((z - z_d) + (1/T_z)*z_int)

内环 (PID): 俯仰角跟踪 → 尾翼角
  delta_s = -Kp_theta * ssa(theta - theta_d) 
            - Kd_theta * q 
            - Ki_theta * theta_int 
            - K_w * w
```

**PVS 默认参数**:
```python
Kp_z = 0.1       # 深度外环比例增益
T_z = 100.0      # 深度积分时间常数
Kp_theta = 5.0   # 俯仰内环比例增益
Kd_theta = 2.0   # 俯仰内环微分增益
Ki_theta = 0.3   # 俯仰内环积分增益
K_w = 5.0        # 垂向速度反馈增益
```

**符号分析**:
```
场景: z=0, z_d=5 (需要下潜5m)
  z - z_d = 0 - 5 = -5 (负误差)
  theta_d = Kp_z * (-5) = -0.5 rad (-28.6°)
  theta - theta_d = 0 - (-0.5) = +0.5
  delta_s = -Kp_theta * (+0.5) = -2.5 rad (负舵角)
  
负delta_s => Z_s>0 (向下力) => tau[4]>0 => dq>0 => theta增加
但theta_d是负的，所以theta会向theta_d收敛 (更负)
theta更负 => 下潜! ✓
```

## 2. AUVPIDController 与 PVS 的映射

### 2.1 坐标系差异

| 维度 | AUVPIDController | PVS remus100 |
|------|------------------|--------------|
| **深度约定** | depth正 = 下潜 | z正 = 下潜 |
| **俯仰约定** | pitch正 = **下俯** = 下潜 | theta正 = **上仰** = 上浮 |
| **符号关系** | pitch = -theta | |

**结论**: AUVPIDController 和 PVS 的俯仰角定义是**相反**的！

### 2.2 控制输出映射

**AUVPIDController 输出** (auv_pid_controller.py:L263-268):
```python
command = np.zeros(5)
command[0] = -elevator_cmd  # right_fin
command[2] = +elevator_cmd  # left_fin
command[1] = -rudder_cmd    # top_fin
command[3] = +rudder_cmd    # bottom_fin
command[4] = thrust_cmd     # thrust %
```

**正确映射到 PVS 的 [delta_r, delta_s, n]**:
```python
# 深度控制: elevator_cmd 正 = 期望pitch正(下俯) = 期望下潜
# 但PVS中: delta_s负 = 下潜
# 所以: stern_deg = -elevator_cmd 才能正确映射

# 由于 PID 输出: command[0] = -elevator_cmd
# 因此: elevator_cmd = -command[0]
# 所以: stern_deg = -elevator_cmd = command[0]

# 航向控制: rudder_cmd 正 = 右转
# PVS中: delta_r正 = 右转
# 由于 PID 输出: command[1] = -rudder_cmd
# 因此: rudder_cmd = -command[1]

stern_deg = cmd[0]       # = -elevator_cmd
rudder_deg = -cmd[1]     # = rudder_cmd
thrust_pct = cmd[4]      # = thrust %
```

> ⚠️ **关键修正**: 在 `tools/pid_tuner.py` 中使用 `stern_deg = cmd[0]` 而非 `-cmd[0]`

## 3. 调优方法论

### 3.1 分离调优原则

**深度和航向必须分开调优！**

原因:
1. **动力学解耦**: 深度控制通过尾翼 (stern planes) 产生俯仰力矩，航向控制通过方向舵 (rudder) 产生偏航力矩
2. **速度耦合**: 深度控制的性能严重依赖于前进速度 u (舵面力 ∝ u²)
3. **调优干扰**: 同时调优会导致参数相互影响，无法确定最优解

**调优顺序**:
1. 先调优深度通道 (使用固定航向参数)
2. 再调优航向通道 (使用固定深度参数)
3. 最后综合评估 (电缆跟踪轨迹)

### 3.2 搜索空间设计

**深度通道**:
```python
# 基于 PVS 默认值进行扩展
Kp_z: [0.1, 0.3, 0.5, 0.8, 1.0]       # PVS默认=0.1
Kp_theta: [3.0, 5.0, 8.0, 12.0, 15.0]  # PVS默认=5.0
Kd_theta: [1.0, 2.0, 3.0, 5.0]         # PVS默认=2.0
Ki_theta: [0.1, 0.3, 0.5, 1.0]         # PVS默认=0.3
```

**航向通道** (PVS 使用 Integral SMC):
```python
lam: [0.05, 0.1, 0.2, 0.3]             # PVS默认=0.1
phi_b: [0.05, 0.1, 0.2]                # PVS默认=0.1
K_d: [0.3, 0.5, 0.8, 1.0]              # PVS默认=0.5
K_sigma: [0.03, 0.05, 0.1]             # PVS默认=0.05
```

### 3.3 评估指标

**核心指标**: RMSE (均方根误差)

```python
RMSE = sqrt(mean(error²))

# 评估场景:
# 1. 阶跃响应: z=0 → z=5m (40秒)
# 2. 阶跃响应: ψ=0 → ψ=30° (40秒)
# 3. 电缆跟踪: 正弦深度变化 + 余弦航向变化 (60秒)
```

**性能基准** (PVS 默认控制器):
- 深度 RMSE: 3.764m (从0到5m阶跃，40秒)
- 航向 RMSE: 0.0001 rad (保持0°航向)

## 4. 最优参数结果

### 4.1 深度通道 (基于 PVS 原生控制器)

```yaml
Kp_z: 1.0          # PVS默认=0.1, 提升10倍
Kp_theta: 15.0     # PVS默认=5.0, 提升3倍
Kd_theta: 2.0      # PVS默认=2.0, 保持
Ki_theta: 1.0      # PVS默认=0.3, 提升3倍

# 性能:
深度 RMSE: 3.515m  # 比PVS默认改善 6.6%
最大误差: 5.005m
```

### 4.2 AUVPIDController 配置 (params.yaml)

```yaml
control:
  depth:
    kp: 1.0              # 深度外环比例
    ki: 0.01             # 深度外环积分
    kd: 0.0
    integral_limit: 50.0
    target_pitch_deg_max: 15.0
    target_pitch_rate_limit_deg_s: 10.0
  pitch:
    kp: 12.0             # 俯仰内环比例
    ki: 0.3              # 俯仰内环积分
    kd: 1.0              # 俯仰内环微分
    integral_limit: 45.0
  yaw:
    kp: 40.0             # 航向比例
    ki: 5.0              # 航向积分
    kd: 5.0              # 航向微分
    integral_limit: 45.0
  speed:
    kp: 5.0
    ki: 2.0
    kd: 1.0
    integral_limit: 30.0
    feedforward:
      a: 0.0
      b: 0.0
      c: 0.0
```

### 4.3 综合评估 (电缆跟踪轨迹)

```
深度 RMSE: 3.317 m
航向 RMSE: 0.193 rad (11.05°)
深度最大误差: 5.013 m
航向最大误差: 16.83°
```

## 5. 常见陷阱与解决方案

### 5.1 陷阱 1: 运动学符号错误

**问题**: 使用 `dz/dt = w` 而非 Fossen 方程

**错误代码**:
```python
self.z += dt * self.w  # 错误!
```

**正确代码**:
```python
# Fossen (2021) 运动学方程
self.z += dt * (-self.u * np.sin(self.theta) + self.w * np.cos(self.theta))
```

**影响**: 深度控制完全反向，AUV无法下潜

### 5.2 陷阱 2: 控制器约定不匹配

**问题**: AUVPIDController 和 PVS 的俯仰角定义相反

**症状**: 
- PID 输出正舵角，但 AUV 上浮而非下潜
- 深度误差越来越大

**解决方案**:
```python
# 正确映射 (见 2.2 节)
stern_deg = cmd[0]       # 不是 -cmd[0]!
rudder_deg = -cmd[1]
```

### 5.3 陷阱 3: 速度增益缩放

**问题**: 舵面力 ∝ u²，但控制器未进行增益缩放

**AUVPIDController 的解决方案**:
```python
def _gain_scale(self, u_forward):
    effective_u = max(abs(u_forward), self.u_min)
    return (self.u0 / effective_u) ** 2
```

**影响**: 低速时控制过强 (振荡)，高速时控制过弱 (响应慢)

### 5.4 陷阱 4: 积分限幅不当

**问题**: integral_limit 过小导致稳态误差，过大导致超调

**经验值**:
- 深度外环: 50.0 (足够大以消除稳态误差)
- 俯仰内环: 45.0 (防止舵角饱和)
- 航向: 45.0 (与俯仰相同)

### 5.5 陷阱 5: 目标俯仰角变化率限制

**问题**: 深度外环输出的目标俯仰角跳变过大

**AUVPIDController 的解决方案**:
```python
max_pitch_delta = target_pitch_rate_limit * dt  # 10°/s * 0.02s = 0.2°
target_pitch = clip(target_pitch_raw, 
                    prev_target_pitch - max_pitch_delta,
                    prev_target_pitch + max_pitch_delta)
```

**影响**: 防止舵角饱和和执行器饱和

## 6. 调优工具使用

### 6.1 PVS 原生控制器调优

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project
python3 tools/pid_tuner_pvs.py
```

**特点**:
- 使用 PVS remus100 完整动力学模型
- 基于 PVS 原生深度HeadingAutopilot (PI+PID+SMC)
- 符号约定完全正确

### 6.2 AUVPIDController 调优

```bash
python3 tools/pid_tuner.py
```

**特点**:
- 使用 PVS remus100 动力学 + AUVPIDController 控制逻辑
- 验证控制器映射是否正确
- 适用于实际 ROS2 部署前的验证

### 6.3 快速验证

```python
import sys
sys.path.insert(0, '/root/PythonVehicleSimulator/src')
from python_vehicle_simulator.vehicles.remus100 import remus100

# 创建车辆，目标深度5m
vehicle = remus100('depthHeadingAutopilot', 5.0, 0, 1525, 0, 0)

# 运行仿真并观察深度响应
# ... (见 pid_tuner_pvs.py 完整代码)
```

## 7. MPC 调优指南

基于 PID 调优经验，MPC 调优应遵循以下原则:

### 7.1 动力学模型一致性

- **使用相同的物理参数**: 质量、附加质量、舵面面积、力臂等
- **使用相同的运动学方程**: Fossen (2021) NED 变换
- **使用相同的执行器模型**: 一阶动态 (T_delta=0.1s, T_n=1.0s)

### 7.2 权重参数设计

**基于 PID 参数反推**:

```python
# PID 深度外环: Kp_z = 1.0 => MPC z 跟踪权重
W_z ≈ Kp_z² = 1.0

# PID 俯仰内环: Kp_theta = 12.0 => MPC theta 权重
W_theta ≈ Kp_theta² = 144.0

# PID 航向: Kp_yaw = 40.0 => MPC psi 权重
W_psi ≈ Kp_yaw² = 1600.0  # 经测试调整为 50.0 (MPC 模型简化)

# 控制 effort 权重 (防止舵角饱和)
W_u ≈ 0.1 * max(W_states)
```

### 7.3 约束设置

```python
# 基于物理限制
min_speed: 0.3 m/s           # 防止失速
max_pitch: 20°               # 防止过大俯仰
max_stern_angle: 15°         # 舵面饱和限制
max_thrust: 100%             # 推力限制
```

### 7.4 调优流程

1. **验证动力学模型**: 使用阶跃响应与 PVS 对比
2. **调整跟踪权重**: 从 PID 参数反推初始值
3. **调整控制权重**: 平衡跟踪性能和控制 effort
4. **验证约束**: 确保不违反物理限制
5. **综合评估**: 使用电缆跟踪轨迹测试

## 8. 参考资源

### 8.1 PVS 源码位置

- **主入口**: `/root/PythonVehicleSimulator/src/python_vehicle_simulator/main.py`
- **REMUS 100 模型**: `/root/PythonVehicleSimulator/src/python_vehicle_simulator/vehicles/remus100.py`
- **控制器**: `remus100.depthHeadingAutopilot()` (L427-503)
- **动力学**: `remus100.dynamics()` (L247-399)
- **执行器**: `/root/PythonVehicleSimulator/src/python_vehicle_simulator/lib/actuator.py`

### 8.2 理论参考

- Fossen, T. I. (2021). *Handbook of Marine Craft Hydrodynamics and Motion Control*. 2nd Edition, Wiley.
  - Chapter 2: Kinematics (NED坐标系)
  - Chapter 3: Hydrodynamics (质量矩阵、阻尼)
  - Chapter 7: Control (PID、SMC、MPC)

### 8.3 关键参数速查表

| 参数 | 符号 | 值 | 单位 |
|------|------|-----|------|
| 水密度 | ρ | 1026 | kg/m³ |
| 体长 | L | 1.6 | m |
| 直径 | D | 0.19 | m |
| 质量 (含附加质量) | m | ~41.4 | kg |
| 舵面面积 | A_s = A_r | 2×0.00665 | m² |
| 舵面力臂 | x_s = x_r | -0.8 | m |
| 最大舵角 | δ_max | 15 | ° |
| 舵面时间常数 | T_delta | 0.1 | s |
| 螺旋桨最大转速 | n_max | 1525 | RPM |
| 螺旋桨时间常数 | T_n | 1.0 | s |
| 稳态最大速度 | U_max | 2.5 | m/s |

---

## 9. MPC 调优结果 (v2.0)

### 9.1 MPC 模型修正

**关键修正: 运动学方程**

原始 MPC 使用简化的 `dz = w`，这与 Fossen NED 坐标系不一致。修正后:

```python
# Fossen (2021) 运动学方程
dz = -u * sin(theta) + w * cos(theta)

# 俯仰角由深度误差隐式驱动
theta_approx = clip(pitch_depth_gain * depth_err, ±max_pitch)
```

**新增模型参数**:
```yaml
mpc_model:
  depth_to_heave_gain: 8.0    # 深度误差到 heave 加速度的增益
  max_pitch_deg: 15.0          # 最大俯仰角约束 (与物理舵角限制一致)
```

### 9.2 最优 MPC 参数

```yaml
mpc_model:
  mass_u: 50.0
  mass_w: 50.0
  drag_u: 15.0
  drag_w: 30.0
  buoyancy_term: 0.0
  yaw_rate_gain: 5.0           # 从 0.5 提升，匹配 PID Kp_yaw=40
  pitch_depth_gain: 0.5        # 从 0.3 提升
  depth_to_heave_gain: 8.0
  max_pitch_deg: 15.0

mpc_weights:
  tracking:
    x: 1.0
    y: 1.0
    z: 10.0                    # 从 5.0 提升
    psi: 50.0                  # 从 3.0 大幅提升
    u: 0.5
    w: 2.0                     # 从 1.0 提升
  control:
    psi_cmd: 0.01              # 从 0.1 降低 (允许更大航向指令)
    z_cmd: 0.05
    T_cmd: 0.05
```

### 9.3 MPC 性能对比

| 指标 | PID (AUVPIDController) | MPC (AUVMPCOptimizer) |
|------|------------------------|------------------------|
| **深度阶跃 RMSE** | 4.011 m | 3.572 m |
| **航向阶跃 RMSE** | 0.166 rad (9.51°) | 0.353 rad (20.21°) |
| **电缆跟踪深度 RMSE** | 2.364 m | 2.487 m |
| **电缆跟踪航向 RMSE** | 0.159 rad (9.13°) | 0.294 rad (16.86°) |

**分析**:
- MPC 深度跟踪略优于 PID (3.572m vs 4.011m)
- PID 航向跟踪显著优于 MPC (9.5° vs 20.2°)
- **原因**: MPC 使用简化动力学模型，未完全捕捉 PVS 的完整水动力特性
- **建议**: 在 ROS2 部署中使用 PID 作为主控制器，MPC 用于参考轨迹生成

### 9.4 MPC 部署建议

1. **混合架构**: MPC 生成参考轨迹 + PID 内环跟踪
   - MPC 输出: guidance_heading, guidance_depth, thrust_percent
   - PID 输出: 舵角指令 (stern, rudder)

2. **置信度自适应**: MPC 在低置信度下自动增加跟踪权重
   ```yaml
   confidence_threshold: 0.6
   low_confidence_scale: 3.0        # 低置信度时跟踪权重×3
   low_confidence_control_scale: 0.3 # 低置信度时控制权重×0.3
   ```

3. **失效降级**: MPC 求解失败时自动回退到 PID
   ```yaml
   fail_safe_fallback: true
   ```

---

**文档版本**: v2.0  
**创建日期**: 2026-05-03  
**作者**: AUV Master Project Team  
**下次更新**: 实海测试后更新性能基准
