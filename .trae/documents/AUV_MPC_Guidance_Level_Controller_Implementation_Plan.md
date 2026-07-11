# AUV 中级模型预测控制器 (MPC) 实施计划

## 架构定位

- **控制层级**：中级导引层（Reference Generation），与 PID 控制器平级
- **输出**：目标航向 `guidance_heading`、目标深度 `guidance_depth`、推力百分比 `thrust_percent`
- **不输出**：舵角（交由 AMD 侧底层 PID 处理，利用其 D 项抑制抖动）
- **输入**：ES-EKF 滤波后的平滑位姿 + 外部参考（电缆最近点、置信度、地形坡度）
- **坐标系**：MPC 内部统一使用 **NED** 坐标系，HoloOcean 输入前由 `frame_transform.py` 完成镜像转换

---

## 第一步：安装 CasADi 依赖 & 环境准备

### 1.1 安装 CasADi

```bash
pip install casadi
```

- Python 版本：3.10.12（ARM 架构）
- 验证安装：`python3 -c "import casadi; print(casadi.__version__)"`

### 1.2 在 `docs_new/` 中编写 CasADi 安装指引文档

- 文档路径：`docs_new/casadi_install_guide.md`
- 内容：ARM 架构安装步骤、常见错误排查、验证方法

---

## 第二步：实现 4-DOF AUV 预测模型

### 2.1 文件位置
- `algorithm/auv_mpc_controller.py`（新建，替代现有占位实现）

### 2.2 预测模型设计

**状态向量** (n_states = 6):
```
X = [x, y, z, ψ, u, w]ᵀ
```
- `x, y`：NED 平面位置
- `z`：NED 深度（正向下）
- `ψ`：航向角
- `u`：前向速度（Surge）
- `w`：垂向速度（Heave）

**控制向量** (n_controls = 3):
```
U = [ψ_cmd, z_cmd, T_cmd]ᵀ
```
- `ψ_cmd`：目标航向（引导航向）
- `z_cmd`：目标深度
- `T_cmd`：目标推力百分比

**4-DOF 运动学模型（欠驱动）**：
```
ẋ = u·cos(ψ)
ẏ = u·sin(ψ)
ż = w
ψ̇ = r (通过偏航角速度控制，由航向偏差间接驱动)
u̇ = (T - D_u·u|u|) / m_u
ẇ = (Z_w·w + Z_δ·δ_pitch + ρg∇·θ) / m_w
```

其中：
- 横向 sway `v` 不直接控制，而是通过 `ψ` 的偏转间接影响 `(x, y)` 轨迹
- 俯仰角 `θ` 作为内部状态，由深度跟踪隐式驱动
- 水动力阻尼系数 `D_u, Z_w` 从仿真物理参数中估计

**离散化**（Euler forward）：
```
x[k+1] = x[k] + dt·u[k]·cos(ψ[k])
y[k+1] = y[k] + dt·u[k]·sin(ψ[k])
z[k+1] = z[k] + dt·w[k]
ψ[k+1] = ψ[k] + dt·r[k]    # r 由 MPC 间接通过 ψ_cmd 控制
u[k+1] = u[k] + dt·(T[k] - D_u·u[k]|u[k]|) / m_u
w[k+1] = w[k] + dt·(Z_w·w[k] + Z_δ·θ[k] + buoyancy) / m_w
```

### 2.3 模型参数配置

在 `params.yaml` 中新增 `mpc_model` 配置段：
```yaml
mpc_model:
  # 质量与水动力系数
  mass_u: 50.0          # Surge 等效质量 (kg)
  mass_w: 50.0          # Heave 等效质量 (kg)
  drag_u: 15.0          # Surge 阻尼系数
  drag_w: 30.0          # Heave 阻尼系数
  buoyancy_term: 0.0    # 静浮力项（已配平时为 0）
  # 欠驱动耦合系数
  yaw_rate_gain: 0.5    # 航向控制对 r 的增益
  pitch_depth_gain: 0.3 # 俯仰对垂向速度的影响系数
```

---

## 第三步：实现 MPC 核心优化器

### 3.1 预测时域配置
- **预测步数** N = 20
- **时间步长** dt = 0.1s
- **预测窗口** = 2.0s
- **控制频率** = 10Hz（与控制节点主循环一致）

### 3.2 CasADi Opti 构建

```python
import casadi as ca

opti = ca.Opti()

# 预测状态和控制变量
X = opti.variable(n_states, N + 1)  # (6, 21)
U = opti.variable(n_controls, N)     # (3, 20)

# 初始状态参数
x0_param = opti.parameter(n_states)
opti.set_value(x0_param, current_state)

# 参考轨迹参数（从 LOS 导引获取）
ref_X = opti.parameter(n_states, N + 1)
opti.set_value(ref_X, reference_trajectory)

# 置信度参数
confidence_param = opti.parameter()
opti.set_value(confidence_param, sensor_confidence)

# 约束：初始状态
opti.subject_to(X[:, 0] == x0_param)

# 约束：动力学方程（逐帧）
for k in range(N):
    x_next = kinematics_model(X[:, k], U[:, k], dt)
    opti.subject_to(X[:, 1:, k+1] == x_next)

# 约束：物理硬约束
opti.subject_to(opti.bounded(0.3, U[2, :], 100))   # 航速 u > 0.3m/s 确保舵效
opti.subject_to(opti.bounded(-20°, X[3, :], 20°))   # 最大俯仰角 < 20°
opti.subject_to(opti.bounded(0, -X[2, :], 14))      # 高度 h > 1.5m（海底15m时）

# 代价函数（软约束）
J = 0
for k in range(N + 1):
    # 跟踪误差（加权）
    tracking_error = X[:, k] - ref_X[:, k]
    # 置信度自适应权重
    W_conf = ca.diag([1, 1, W_z, W_psi, W_u, W_w])
    W_conf[0, 0] *= (2.0 - confidence)   # 置信度低时增大横向权重
    W_conf[1, 1] *= (2.0 - confidence)
    W_conf[3, 3] *= (2.0 - confidence)   # 航向权重增大
    J += tracking_error.T @ W_conf @ tracking_error

for k in range(N):
    # 控制努力
    control_effort = U[:, k].T @ diag([W_ψ_cmd, W_z_cmd, W_T]) @ U[:, k]
    # 置信度低时减小推力惩罚
    if confidence < 0.6:
        control_effort *= 0.5  # 允许更大的控制量
    J += control_effort

opti.minimize(J)
opti.solver('ipopt', {'print_time': False, 'ipopt.print_level': 0})
```

### 3.3 置信度自适应权重机制

```python
def compute_confidence_weights(confidence):
    """根据传感器置信度动态调整代价函数权重"""
    base_weights = {
        'W_x': 1.0, 'W_y': 1.0,    # 平面位置
        'W_z': 5.0,                  # 深度（更重要）
        'W_psi': 3.0,                # 航向
        'W_u': 0.5, 'W_w': 1.0,     # 速度
        'W_ψ_cmd': 0.1,              # 控制努力
        'W_z_cmd': 0.1,
        'W_T': 0.05,
    }
    if confidence < 0.6:
        # "盲跟"模式：宁可动作大，也要死守估算轨迹
        base_weights['W_x'] *= 3.0
        base_weights['W_y'] *= 3.0
        base_weights['W_psi'] *= 3.0
        base_weights['W_z'] *= 2.0
        base_weights['W_T'] *= 0.3   # 减小推力惩罚
    return base_weights
```

---

## 第四步：实现 `MPCController` 类（替代占位）

### 4.1 文件修改
- `brain_linux/src/auv_controller/auv_controller/mpc_controller.py`

### 4.2 核心接口

```python
class MPCController(BaseController):
    def __init__(self, ctrl_cfg, lim_cfg, mapper_cfg=None):
        # 加载模型参数
        self.model_params = ctrl_cfg.get('mpc_model', {})
        self.N = ctrl_cfg.get('mpc', {}).get('prediction_horizon', 20)
        self.dt = ctrl_cfg.get('mpc', {}).get('dt', 0.1)
        self.confidence = 1.0  # 默认满置信度
        
        # 构建 CasADi 优化器（编译一次，反复求解）
        self._build_solver()
        
        # 热启动：上一次的最优控制序列
        self._prev_U = np.zeros((3, self.N))
        
        # 求解统计
        self.solve_time_ms = 0.0
        self.solver_status = "NOT_RUN"

    def compute(self, state, setpoint):
        """
        Args:
            state: dict 来自 ES-EKF，包含 {x, y, z, roll, pitch, yaw, u, v, w}
            setpoint: dict 包含 {target_depth_m, target_heading_rad, target_speed_mps,
                               dt, cable_closest_point, confidence}
        Returns:
            ControlOutput(thrust_percent, guidance_heading, guidance_depth, debug)
        """
        # 1. 检查 use_mpc 参数
        # 2. 构建当前状态向量
        # 3. 生成参考轨迹（LOS 导引）
        # 4. 设置优化器初值（热启动）
        # 5. 求解
        # 6. 提取最优控制序列的第一步
        # 7. 返回 ControlOutput
        # 8. 记录求解时间和状态
```

### 4.3 热启动实现

```python
def _set_warm_start(self):
    """使用上一时刻的控制序列作为初值"""
    for k in range(self.N):
        if k < self.N - 1:
            self._opti.set_initial(self.U[:, k], self._prev_U[:, k+1])
        else:
            self._opti.set_initial(self.U[:, k], self._prev_U[:, -1])
```

### 4.4 失效降级（Fail-safe）

```python
try:
    sol = self._opti.solve()
    self.solver_status = sol.stats()['return_status']
    self.solve_time_ms = sol.stats()['t_proc_total'] * 1000
except Exception as e:
    self.solver_status = f"FAILED: {str(e)}"
    # 抛出异常信号，由 auv_controller_node.py 捕获并回退到 PID
    raise RuntimeError(f"MPC solver failed: {self.solver_status}") from e

if self.solver_status not in ('Solve_Succeeded', 'Search_Direction_Becomes_Too_Small'):
    raise RuntimeError(f"MPC infeasible: {self.solver_status}")
```

---

## 第五步：ROS2 节点集成

### 5.1 文件修改
- `brain_linux/src/auv_controller/auv_controller/auv_controller_node.py`

### 5.2 关键修改点

#### 5.2.1 定时器频率适配

当前节点控制频率默认为 20Hz（`control_rate_hz`），但 MPC 设计为 10Hz 求解：
```python
# 当 use_mpc=true 时，MPC 求解器使用 10Hz
# 节点仍然以 control_rate_hz 运行，但 MPC compute() 内部每 100ms 求解一次
# 中间帧复用上一次 MPC 输出的预测序列
```

#### 5.2.2 MPC 求解异常捕获

在 `_on_timer()` 中：
```python
try:
    ctrl_output = self._active_controller.compute(state, setpoint)
except RuntimeError as e:
    # MPC 求解失败，立即回退到 PID
    self.get_logger().error(f'MPC failed, falling back to PID: {e}')
    self._active_controller = self._pid_controller
    self._use_mpc = False  # 自动关闭 MPC 模式
    ctrl_output = self._pid_controller.compute(state, setpoint)
    # 在上行包中记录算法告警
    self._publish_algorithm_alert('MPC_SOLVER_FAILURE')
```

#### 5.2.3 调试话题发布

确保 `/auv/controller/debug` 包含：
```json
{
    "solver_status": "SUCCESS",
    "solve_time_ms": 12.3,
    "prediction_horizon": 20,
    "confidence": 0.85,
    "cost_value": 0.045,
    "reference_trajectory": [[x0,y0,z0], ...],
    "optimal_trajectory": [[x0,y0,z0], ...]
}
```

#### 5.2.4 Setpoint 增强

需要在 Setpoint 消息中增加 `confidence` 字段（当前 `Setpoint.msg` 已有 `confidence` 字段，直接引用即可）：
```python
setpoint = {
    'dt': 1.0 / max(self.control_rate_hz, 1e-3),
    'target_depth_m': float(sp.target_depth_m),
    'target_heading_rad': smoothed_heading,
    'target_speed_mps': float(sp.target_speed_mps),
    'confidence': float(self.latest_setpoint.confidence),  # 来自 SensorStatus
    'cable_closest_point': ...  # 来自 ground_truth
}
```

---

## 第六步：LOS 导引集成（参考轨迹生成）

### 6.1 利用现有 `algorithm/guidance.py`

```python
from algorithm.guidance import compute_los_target, find_nearest_index

def generate_reference_trajectory(self, state, cable_points, N, dt):
    """生成未来 N 步的参考轨迹"""
    ref_states = np.zeros((6, N + 1))
    current_idx = find_nearest_index(state['x'], state['y'], cable_points)
    
    for k in range(N + 1):
        future_idx = current_idx + k * 2  # 前视步长
        future_idx = min(future_idx, len(cable_points) - 1)
        ref_pt = cable_points[future_idx]
        
        ref_states[0, k] = ref_pt.x  # x_ref
        ref_states[1, k] = ref_pt.y  # y_ref
        ref_states[2, k] = state['target_z']  # 深度参考
        ref_states[3, k] = np.arctan2(
            cable_points[future_idx+1].y - ref_pt.y,
            cable_points[future_idx+1].x - ref_pt.x
        )  # 航向参考
        ref_states[4, k] = state['target_u']  # 速度参考
        ref_states[5, k] = 0.0  # 垂向速度参考
    
    return ref_states
```

---

## 第七步：仿真验证与调参

### 7.1 修改 `mock_amd_delay.py` 注入 100ms 传输延迟

在仿真配置中设置：
```yaml
mock_amd:
  transport_delay_ms: 100.0
  transport_jitter_ms: 10.0
```

### 7.2 验证指标

| 指标 | 目标值 | 验证方式 |
|------|--------|----------|
| `solver_status` | `SUCCESS` | `ros2 topic echo /auv/controller/debug` |
| `solve_time_ms` | < 15ms | 同上 |
| 超调量减少 | > 40%（vs PID） | 对比电缆急转弯处的 yaw 跟踪曲线 |
| 舵机动作平滑度 | 更高 | 对比 fin command 方差 |
| 失效降级 | 自动切换到 PID | 人为注入不可行场景，验证回退 |

### 7.3 验收测试场景

1. **直线跟踪**：验证 MPC 在直线路径上的稳态跟踪精度
2. **急转弯**：对比 PID 与 MPC 在 90° 急转弯处的超调量
3. **低置信度**：注入 confidence=0.3，验证权重自适应和"盲跟"行为
4. **求解失败降级**：人为制造不可行约束（如 h < 0.5m），验证 PID 回退

---

## 第八步：配置文件更新

### 8.1 `params.yaml` 新增 MPC 配置

```yaml
mpc:
  prediction_horizon: 20
  dt: 0.1
  solver: 'ipopt'
  warm_start: true
  max_solve_time_ms: 50.0
  fail_safe_fallback: true

mpc_model:
  mass_u: 50.0
  mass_w: 50.0
  drag_u: 15.0
  drag_w: 30.0
  buoyancy_term: 0.0
  yaw_rate_gain: 0.5
  pitch_depth_gain: 0.3

mpc_weights:
  tracking:
    x: 1.0
    y: 1.0
    z: 5.0
    psi: 3.0
    u: 0.5
    w: 1.0
  control:
    psi_cmd: 0.1
    z_cmd: 0.1
    T_cmd: 0.05
  confidence_threshold: 0.6
  low_confidence_scale: 3.0
  low_confidence_control_scale: 0.3

mpc_constraints:
  min_speed_ms: 0.3
  max_pitch_deg: 20.0
  min_altitude_m: 1.5
  max_thrust_percent: 100.0
```

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `algorithm/auv_mpc_controller.py` | **新建** | MPC 核心数学模型、CasADi 优化器 |
| `brain_linux/src/auv_controller/auv_controller/mpc_controller.py` | **重写** | 从占位类改为完整 MPC 实现 |
| `brain_linux/src/auv_controller/auv_controller/auv_controller_node.py` | **修改** | 增加 MPC 异常捕获、置信度传递、调试发布 |
| `brain_linux/config/params.yaml` | **修改** | 新增 mpc/mpc_model/mpc_weights/mpc_constraints 配置段 |
| `sim_holoocean/interfaces/mock_amd_server.py` | **确认** | 已有延迟注入支持，无需修改 |
| `docs_new/casadi_install_guide.md` | **新建** | CasADi 安装指引 |
