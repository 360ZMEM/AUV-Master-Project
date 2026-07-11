# AUV 核心组件接口

## 1. AUVPIDController（PID 控制器）

### 类定义
```python
class AUVPIDController:
    def __init__(self, control_cfg, limits_cfg):
        """
        Args:
            control_cfg: 控制器配置字典
            limits_cfg: 物理约束配置字典
        """
```

### 配置结构

#### control_cfg
```yaml
control:
  u0: 1.0              # 标称速度 (m/s)
  u_min: 0.2           # 最小有效速度 (m/s)
  target_u: 0.6        # 默认目标速度 (m/s)
  feedforward_trim_deg: 0.0  # 前馈配平角度
  
  depth:               # 深度外环 PID
    kp: 1.0
    ki: 0.1
    kd: 0.0
    integral_limit: 10.0
    target_pitch_deg_max: 15.0
    target_pitch_rate_limit_deg_s: 10.0
  
  pitch:               # 俯仰内环 PID
    kp: 8.0
    ki: 0.5
    kd: 2.0
    integral_limit: 30.0
  
  yaw:                 # 航向内环 PID
    kp: 6.0
    ki: 0.3
    kd: 1.5
    integral_limit: 30.0
  
  speed:               # 速度环 PID
    kp: 5.0
    ki: 2.0
    kd: 0.0
    integral_limit: 50.0
    feedforward:       # 速度前馈系数
      a: 0.0
      b: 0.0
      c: 0.0
  
  attitude_guard:      # 姿态保护
    enable: false
    roll_deg_max: 120.0
    pitch_deg_max: 45.0
    recovery_target_pitch_deg: 0.0
    recovery_thrust: 20.0
```

#### limits_cfg
```yaml
limits:
  fin_deg_max: 30.0    # 舵叶最大偏角 (°)
  thrust_min: 0.0      # 最小推力 (%)
  thrust_max: 100.0    # 最大推力 (%)
```

### compute() 方法

```python
def compute(self, state, target):
    """
    Args:
        state (dict): 当前状态
            - roll: 横滚角 (rad)
            - pitch: 俯仰角 (rad)
            - yaw: 航向角 (rad)
            - depth: 当前深度 (m)
            - u: 前进速度 (m/s)
            - q: 俯仰角速度 (rad/s)
            - r: 航向角速度 (rad/s)
        
        target (dict): 目标状态
            - dt: 控制周期 (s)
            - target_depth: 目标深度 (m)
            - target_yaw: 目标航向 (rad)
            - target_u: 目标速度 (m/s)
    
    Returns:
        tuple[np.ndarray, dict]: 
            - command: [right, top, left, bottom, thrust]
            - debug: 调试信息字典
    """
```

---

## 2. DecisionTreeEngine（行为树引擎）

### 类定义
```python
class DecisionTreeEngine:
    def __init__(self, confidence_threshold: float = 0.7):
        """
        Args:
            confidence_threshold: 置信度阈值，超过此值进入精准巡检
        """
```

### 核心方法

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| `set_sensor_status(status)` | 更新传感器状态到黑板 | `status: SensorStatusData` | None |
| `tick()` | 执行一次行为树 tick | 无 | None |
| `get_target_motion_state()` | 获取目标运动状态 | 无 | `Optional[Dict]` |
| `current_behavior_name()` | 获取当前激活行为名称 | 无 | `str` |
| `active_path()` | 获取当前激活路径 | 无 | `str` |
| `unicode_tree()` | 获取树形文本表示 | 无 | `str` |

### SensorStatusData 结构

```python
@dataclass
class SensorStatusData:
    confidence: float = 0.5              # 置信度 [0,1]
    leak_level: int = 0                  # 漏水等级 (0-3)
    battery_low: bool = False            # 低电标志
    total_voltage_v: float = 48.0        # 总电压 (V)
    anomaly_detected: bool = False       # 异常检测标志
    depth_m: float = 0.0                 # 当前深度 (m)
    speed_mps: float = 0.0               # 当前速度 (m/s)
    seabed_depth_m: float = 15.0         # 海底深度 (m)
    seabed_clearance_m: float = 15.0     # 到海底净空 (m)
    seabed_proximity_warning: bool = False   # 近底警告
    seabed_penetration_warning: bool = False # 穿底警告
    heading_rad: float = 0.0             # 当前航向 (rad)
    mock_amd_timestamp_us: int = 0       # Mock AMD 时间戳 (us)
    debug_level: int = 0                 # 调试级别 (0-3)
```

### MotionGoal 结构

```python
@dataclass
class MotionGoal:
    mode: str = 'IDLE'                   # 行为模式
    target_depth_m: float = 0.0          # 目标深度 (m)
    target_speed_mps: float = 0.0        # 目标速度 (m/s)
    sine_amplitude: float = 0.0          # 正弦扰动幅值
    sine_period_s: float = 0.0           # 正弦扰动周期 (s)
    high_priority: bool = False          # 高优先级标志
    note: str = ''                       # 备注说明
    target_heading_rad: float = 0.0      # 目标航向 (rad)
    target_x_m: float = 0.0              # 目标 x 坐标 (m)
    target_y_m: float = 0.0              # 目标 y 坐标 (m)
```

---

## 3. CommandArbiter（命令仲裁器）

### 类定义
```python
class CommandArbiter:
    def __init__(self, *, mpc_timeout_s: float = 0.5, default_obj_address: int = 1):
        """
        Args:
            mpc_timeout_s: MPC 命令超时时间 (s)
            default_obj_address: 默认目标地址
        """
```

### 核心方法

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| `update_pc_raw_command(payload)` | 更新 PC 原始命令 | `payload: Any` | `ArbiterDecision` |
| `update_mpc_command(payload)` | 更新 MPC 命令 | `payload: dict` | `ArbiterDecision` |
| `force_remote(payload)` | 强制切换到遥控模式 | `payload: Optional[dict]` | `ArbiterDecision` |
| `decide()` | 执行仲裁决策 | 无 | `ArbiterDecision` |

### ArbiterDecision 结构

```python
@dataclass(frozen=True)
class ArbiterDecision:
    active_arbiter: ArbiterMode     # 当前活跃仲裁器
    arbiter_source: ArbiterSource   # 命令来源
    command_payload: dict           # 最终命令负载
    mpc_command_valid: bool         # MPC 命令是否有效
    manual_override_active: bool    # 是否手动覆盖
```

### 仲裁逻辑流程

```
                    ┌──────────────────────┐
                    │   update_pc_raw()    │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │ 检查工作指令/模式字节 │
                    └──────────┬───────────┘
                               ▼
         ┌─────────────────────┴─────────────────────┐
         │                                           │
    ┌────▼────┐                              ┌───────▼───────┐
    │ TASK_CANCEL│                              │ CONTROL_MODE  │
    │ CLEAR_FAULT│                              │  == JETSON   │
    └────┬────┘                              └───────┬───────┘
         │                                           │
         ▼                                           ▼
    ┌──────────┐                              ┌──────────────┐
    │ REMOTE   │                              │ AUTONOMOUS   │
    └────┬─────┘                              └──────┬───────┘
         │                                           │
         │                              ┌────────────┴────────────┐
         │                              ▼                         ▼
         │                       ┌───────────┐            ┌──────────────┐
         │                       │MPC 新鲜有效?│            │ MPC 过期/无效 │
         │                       └─────┬─────┘            └──────┬───────┘
         │                             │                         │
         │                             ▼                         ▼
         │                       ┌───────────┐            ┌──────────────┐
         │                       │JETSON_MPC │            │SAFETY_FALLBACK│
         │                       └─────┬─────┘            └──────┬───────┘
         │                             │                         │
         └─────────────────────────────┴─────────────────────────┘
                                       │
                                       ▼
                            ┌────────────────┐
                            │ ArbiterDecision│
                            └────────────────┘
```

---

## 4. AUVControllerNode（ROS2 控制节点）

### 订阅主题

| 主题 | 消息类型 | 说明 |
|------|----------|------|
| `/auv/control/setpoint` | `Setpoint` | 控制目标 |
| `/auv/state/filtered` | `Odometry` | 滤波状态估计 |
| `/auv/state/raw_dr` | `Odometry` | 原始死推进状态 |
| `/auv/sensors/imu` | `Imu` | IMU 数据 |

### 发布主题

| 主题 | 消息类型 | 说明 |
|------|----------|------|
| `/cmd_vel` | `Twist` | 五通道控制命令 |
| `/auv/controller/debug` | `String` | 调试信息（JSON） |

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `params_file` | string | `brain_linux/config/params.yaml` | 控制器参数文件 |
| `filtered_state_topic` | string | `/auv/state/filtered` | 滤波状态话题 |
| `raw_state_topic` | string | `/auv/state/raw_dr` | 原始状态话题 |
| `bypass_ekf` | bool | false | 是否绕过 EKF |
| `control_rate_hz` | float | 20.0 | 控制频率 |

### Setpoint 消息结构

```msg
string mode                          # 行为模式
float64 target_depth_m               # 目标深度 (m)
float64 target_heading_rad           # 目标航向 (rad)
float64 target_speed_mps             # 目标速度 (m/s)
float64 sine_amplitude               # 正弦扰动幅值
float64 sine_period_s                # 正弦扰动周期 (s)
```

---

## 5. 物理常量

### 物理参数

| 常量 | 值 | 单位 | 说明 |
|------|----|------|------|
| `GRAVITY_MPS2` | 9.81 | m/s² | 重力加速度 |
| `MAX_THRUST_PERCENT` | 100.0 | % | 最大推力 |
| `MAX_RUDDER_DEG` | 45.0 | ° | 舵叶最大角度 |
| `SIM_DEFAULT_MAX_RUDDER_DEG` | 30.0 | ° | 仿真默认舵叶角度 |
| `BURIED_DEPTH_ERROR_LIMIT_M` | 0.2 | m | 埋深误差极限 |
| `SEA_BOTTOM_Z` | 15.0 | m | 海底深度 |
| `CABLE_SUSPENSION_HEIGHT` | 1.0 | m | 电缆悬挂高度 |

### 辅助函数

| 函数 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| `clamp(value, low, high)` | 范围限制 | `value, low, high` | 限幅后的值 |
| `clamp_rudder_deg(value_deg, max_rudder_deg)` | 舵角限制 | `value_deg: float` | 限幅后的角度 |
| `clamp_thrust_percent(value_percent)` | 推力限制 | `value_percent: float` | 限幅后的推力 |

---

**生成时间**: 2026-04-29
