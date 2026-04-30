# Jetson 端混合控制引擎与 MPC 预留接口开发计划

## 1. 仓库现状分析

### 1.1 已存在的代码

| 模块 | 文件路径 | 现状 | 与任务的关系 |
|------|----------|------|-------------|
| PID 控制器 | `algorithm/auv_pid_controller.py` | **完整级联 PID**：深度外环→俯仰内环、航向内环、速度环；已含 anti-windup、attitude guard、speed feedforward | 需要在其基础上增加 `AUVPIDController` 的速度环独立性，并重构输出接口 |
| 控制节点 | `brain_linux/src/auv_controller/auv_controller/auv_controller_node.py` | 动态加载 PID，周期 20Hz，输出 Twist，发布 debug | **需要重构**：引入 BaseController 架构 + 仲裁逻辑 + 参数化 MPC 切换 |
| 仲裁器 | `brain_linux/src/auv_bridge/auv_bridge/arbiter.py` | PC RAW 与 JETSON_MPC 之间的仲裁，使用 `ControlModeByte.JETSON_PROTOCOL = 0xEE` | 已支持 MPC 命令仲裁；新任务要求新增 `0xEF` 模式，需要澄清边界（见 1.4） |
| Mappers（决策层） | `brain_linux/src/auv_control/auv_decision_ros/mappers.py` | ROS msg ↔ Core 数据模型转换 | **不冲突**：这是决策层映射；本次任务是控制器层到协议的映射 |
| MpcCmd 消息 | `brain_linux/src/auv_interfaces/msg/MpcCmd.msg` | 已定义：包含 fin_deg、thrust_percent、valid、healthy | 可直接使用作为 MPC 输出消息类型 |
| Setpoint 消息 | `brain_linux/src/auv_interfaces/msg/Setpoint.msg` | 已定义：包含 target_depth_m、target_heading_rad、target_speed_mps 等 | 现有 PID 已使用这些字段 |
| 枚举定义 | `common/enums.py` | 已有 `ControlModeByte`（含 0xEE JETSON_PROTOCOL）和 `ArbiterSource.JETSON_MPC` | 需要新增 `0xEF` 或复用现有 |
| 决策节点 | `brain_linux/src/auv_control/auv_decision_ros/decision_node.py` | 行为树→Setpoint，10Hz 发布 | **不需要修改**：决策层保持原样 |
| Bridge 节点 | `brain_linux/src/auv_bridge/auv_bridge/bridge_node.py` | 接收 MPC 命令、仲裁、编码为协议 | **不需要修改**：底层传输保持原样 |

### 1.2 缺失的代码

| 模块 | 需要新建文件 | 说明 |
|------|-------------|------|
| 物理映射层 | `brain_linux/src/auv_controller/auv_controller/mappers.py` | 舵机映射、推进器线性化、死区/电压补偿 |
| 控制器基类 | `brain_linux/src/auv_controller/auv_controller/base_controller.py` | BaseController 接口定义 |
| PID 控制器封装 | `brain_linux/src/auv_controller/auv_controller/pid_controller.py` | 继承 BaseController，包装现有 AUVPIDController |
| MPC 控制器占位 | `brain_linux/src/auv_controller/auv_controller/mpc_controller.py` | 继承 BaseController，预留 casadi 接口 |

### 1.3 架构关系

```
Decision Node (10Hz)
  └─> /auv/control/setpoint (Setpoint)
        │
        ▼
Controller Node (20Hz)  ◄── 本次重构的核心
  ├─ BaseController 接口
  ├─ PIDController  ← 包装 algorithm/auv_pid_controller.py
  ├─ MPCController  ← 占位类（预留 casadi）
  │     (通过 ROS2 param use_mpc 切换)
  │
  └─ 输出: Twist (/cmd_vel) + MpcCmd (/auv/control/mpc_cmd)
        │
        ▼
Bridge Node (auv_bridge)
  └─ CommandArbiter (已实现 PC/JETSON_MPC 仲裁)
  └─ Protocol Encoder ($CKTH 二进制协议)
```

### 1.4 边界问题与拍板询问

**问题 A: 0xEF 模式 vs 现有 0xEE JETSON_PROTOCOL**

- 现有代码中 `ControlModeByte.JETSON_PROTOCOL = 0xEE` 已经被仲裁器和协议广泛使用
- 任务要求使用 `0xEF` 作为新的"劫持标记"
- **拍板方案**：在 `common/enums.py` 中新增 `JETSON_HYBRID = 0xEF`，作为混合控制器专用模式字节。`0xEE` 保留给传统模式。在 controller node 中根据 ROS2 param 决定使用哪个值。

**问题 B: 控制器输出路径**

- 当前 controller node 直接输出 Twist (`/cmd_vel`)，不经过 arbiter
- MPC 模式下的输出应该走 `MpcCmd` → `auv_bridge/arbiter` → 协议编码
- **拍板方案**：controller node 增加一个 MpcCmd 发布者。当 `use_mpc=true` 时，MPC 输出发往 `/auv/control/mpc_cmd`（桥接节点仲裁器消费）；当 `use_mpc=false` 时，PID 输出直接发 `/cmd_vel`（保持现有兼容）。

**问题 C: AMD 闭环透传的语义**

- 任务要求横/垂向"透传给 AMD 闭环"
- 当前 AMD（实物端）有自己的 PID 闭环，它期望收到舵角指令
- **拍板方案**：PID 模式下，纵向推力由 Jetson PID 计算，横/垂向舵角从 Setpoint 的 `target_heading_rad` 和 `target_depth_m` 直接写入输出字典（不做 PID 计算），标记为 `guidance_heading` 和 `guidance_depth` 字段。桥接节点或下游模块会将这些 guidance 值转为 AMD 期望的舵角协议。

**问题 D: MPC 的 casadi 依赖**

- MPC 控制器需要 `casadi` 库进行优化计算
- **拍板方案**：MPC 占位类中不实际引入 casadi 依赖，只在注释中标注集成点。casadi 的安装和 MPC 实际实现作为后续任务。

## 2. 实施计划

### Phase 1: 物理映射层 (`mappers.py`)

**文件**: `brain_linux/src/auv_controller/auv_controller/mappers.py`（新建）

**功能**:

```python
# 1. 舵机映射：angle_deg → protocol_value (int16)
def rudder_deg_to_protocol(angle_deg: float, config: dict) -> int:
    """
    包含:
    - center_bias (Trim 偏移，单位 deg)
    - gain (灵敏度，范围 0.5~2.0)
    - flip (极性翻转，bool)
    输出: 协议要求的 int16 舵角值（通常 -100~100 映射为协议值）
    """

# 2. 推进器线性化：thrust_percent → RPM (int16)
def thrust_to_rpm(thrust_percent: float, config: dict, *,
                  feedback_voltage: float | None = None) -> int:
    """
    包含:
    - deadzone (死区阈值，如 5%)
    - voltage_compensation (基于回传电压的增益补偿)
    - 死区跳过：1% 推力 → 直接输出 150 RPM 而非 15 RPM
    输出: 协议要求的 int16 RPM 值
    """

# 3. 单位强制转换工具
def clamp_int16(value: float) -> int:
    """将浮点数钳位到 int16 范围 [-32768, 32767]"""
```

**配置来源**: 从 `params.yaml` 的 `mappers` 段读取，示例：

```yaml
mappers:
  rudder:
    center_bias: 0.0   # Trim 偏移 (deg)
    gain: 1.0          # 灵敏度
    flip: false        # 极性
  thrust:
    deadzone_percent: 5.0      # 死区百分比
    rpm_per_percent: 15.0      # 每 1% 对应的 RPM 线性斜率
    voltage_nominal: 24.0      # 标称电压 (V)
    voltage_compensation: true # 是否启用电压补偿
```

### Phase 2: 控制器基类接口 (`base_controller.py`)

**文件**: `brain_linux/src/auv_controller/auv_controller/base_controller.py`（新建）

**功能**:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class ControlOutput:
    """控制器统一输出结构"""
    thrust_percent: float        # [-100, 100]
    right_fin_deg: float         # 舵面角度
    top_fin_deg: float
    left_fin_deg: float
    bottom_fin_deg: float
    guidance_heading: float | None  # None = 透传/不干预
    guidance_depth: float | None
    debug: dict[str, Any]

class BaseController(ABC):
    @abstractmethod
    def compute(self, state: dict, setpoint: dict) -> ControlOutput:
        """
        Args:
            state: 当前状态 {x, y, z, u, v, w, roll, pitch, yaw, p, q, r, ...}
            setpoint: 目标 {target_depth_m, target_heading_rad, target_speed_mps, ...}
        Returns:
            ControlOutput
        """
        ...
```

### Phase 3: PID 控制器封装 (`pid_controller.py`)

**文件**: `brain_linux/src/auv_controller/auv_controller/pid_controller.py`（新建）

**功能**:

```python
class PIDController(BaseController):
    def __init__(self, ctrl_cfg: dict, lim_cfg: dict, mapper_cfg: dict):
        # 内部包装已有的 AUVPIDController
        self._pid = AUVPIDController(ctrl_cfg, lim_cfg)
        self._mapper_cfg = mapper_cfg

    def compute(self, state: dict, setpoint: dict) -> ControlOutput:
        # 1. 速度 PID: 使用 AUVPIDController 的速度环计算 thrust
        pid_cmd, debug = self._pid.compute(state, target)

        # 2. 横/垂向：透传 guidance（不干预 AMD 闭环）
        thrust = pid_cmd[4]  # 推力来自 PID
        right_deg = None     # 舵角透传
        top_deg = None
        left_deg = None
        bottom_deg = None

        return ControlOutput(
            thrust_percent=thrust,
            right_fin_deg=right_deg,
            top_fin_deg=top_deg,
            left_fin_deg=left_deg,
            bottom_fin_deg=bottom_deg,
            guidance_heading=setpoint.get('target_heading_rad'),
            guidance_depth=setpoint.get('target_depth_m'),
            debug=debug,
        )
```

**关键改动**：现有 `AUVPIDController` 已经实现了完整的五通道输出，但本次 PID 模式只使用其**速度环**计算推力，横/垂向舵面标记为 `None`（透传），确保不干扰 AMD 本地 PID。

### Phase 4: MPC 控制器占位 (`mpc_controller.py`)

**文件**: `brain_linux/src/auv_controller/auv_controller/mpc_controller.py`（新建）

**功能**:

```python
class MPCController(BaseController):
    def __init__(self, ctrl_cfg: dict, lim_cfg: dict, mapper_cfg: dict):
        # TODO: 在此处接入基于 casadi 的预测控制逻辑
        # - 构建状态空间模型 (x, y, z, u, v, w, phi, theta, psi)
        # - 配置 prediction_horizon, control_horizon
        # - 初始化 casadi.Opti 或 casadi.SX 变量
        self._config = ctrl_cfg
        self._state_history = []

    def compute(self, state: dict, setpoint: dict) -> ControlOutput:
        # TODO: 在此处接入基于 casadi 的预测控制逻辑
        #
        # 解包输入状态量:
        #   x, y, z: 位置
        #   u, v, w: 体轴速度
        #   phi, theta, psi: 欧拉角 (roll, pitch, yaw)
        #   p, q, r: 体轴角速度
        #
        # 解包 setpoint:
        #   target_depth_m
        #   target_heading_rad
        #   target_speed_mps
        #   target_x_m, target_y_m (可选)
        #
        # 调用 casadi 优化器:
        #   result = self._solver.solve(state, setpoint)
        #
        # 返回控制指令:
        #   thrust_percent, fin_degrees

        # 占位实现：输出零指令
        return ControlOutput(
            thrust_percent=0.0,
            right_fin_deg=0.0,
            top_fin_deg=0.0,
            left_fin_deg=0.0,
            bottom_fin_deg=0.0,
            guidance_heading=None,
            guidance_depth=None,
            debug={'mpc_status': 'placeholder', 'note': 'MPC not yet implemented'},
        )
```

### Phase 5: 控制器节点重构 (`auv_controller_node.py`)

**文件**: `brain_linux/src/auv_controller/auv_controller/auv_controller_node.py`（修改）

**改动清单**:

#### 5.1 新增 ROS2 参数

```python
self.declare_parameter('use_mpc', False)
self.declare_parameter('control_mode_byte', 0xEF)  # 新增劫持标记
self.declare_parameter('heading_ramp_limit_deg', 30.0)  # 指令平滑器阈值
self.declare_parameter('heading_ramp_rate_deg_s', 10.0)  # 斜坡速率
```

#### 5.2 引入控制器切换逻辑

```python
class AUVControllerNode(Node):
    def __init__(self):
        # ... 现有初始化 ...

        # 加载控制器类
        from .base_controller import BaseController
        from .pid_controller import PIDController
        from .mpc_controller import MPCController

        self._pid_controller = PIDController(ctrl_cfg, lim_cfg, mapper_cfg)
        self._mpc_controller = MPCController(ctrl_cfg, lim_cfg, mapper_cfg)
        self._active_controller: BaseController = self._pid_controller
        self._use_mpc = False

        # 指令平滑器状态
        self._last_heading_cmd = 0.0
        self._heading_ramp_active = False
        self._heading_ramp_start = 0.0
        self._heading_ramp_target = 0.0

    def _on_parameters_changed(self, params):
        for param in params:
            if param.name == 'use_mpc':
                self._use_mpc = bool(param.value)
                if self._use_mpc:
                    self._active_controller = self._mpc_controller
                    self.get_logger().info('控制器切换为 MPC 模式')
                else:
                    self._active_controller = self._pid_controller
                    self.get_logger().info('控制器切换为 PID 模式')
```

#### 5.3 控制周期主循环修改

```python
def _on_timer(self):
    if self.latest_setpoint is None:
        return

    # 1. 组装 state 和 setpoint (保持现有逻辑)
    state = {...}
    setpoint = {...}

    # 2. 调用当前活跃控制器
    ctrl_output = self._active_controller.compute(state, setpoint)

    # 3. 指令平滑器：heading 跳变超过 30° 时生成斜坡信号
    target_heading = setpoint.get('target_heading_rad', 0.0)
    smoothed_heading = self._apply_heading_ramp(target_heading, now=time.time())

    # 4. 构建输出命令
    if self._use_mpc:
        # MPC 模式：发布 MpcCmd 消息（供 auv_bridge/arbiter 消费）
        mpc_msg = MpcCmd()
        mpc_msg.header.stamp = self.get_clock().now().to_msg()
        mpc_msg.source = 'JETSON_MPC'
        mpc_msg.valid = True
        mpc_msg.healthy = True
        mpc_msg.thrust_percent = float(ctrl_output.thrust_percent)
        mpc_msg.right_fin_deg = float(ctrl_output.right_fin_deg or 0.0)
        mpc_msg.top_fin_deg = float(ctrl_output.top_fin_deg or 0.0)
        mpc_msg.left_fin_deg = float(ctrl_output.left_fin_deg or 0.0)
        mpc_msg.bottom_fin_deg = float(ctrl_output.bottom_fin_deg or 0.0)
        mpc_msg.note = str(ctrl_output.debug.get('note', ''))
        self._mpc_cmd_pub.publish(mpc_msg)
    else:
        # PID 模式：直接发布 Twist + guidance 信息
        tw = Twist()
        tw.linear.x = float(ctrl_output.thrust_percent)
        # 舵角为 None 时标记为"透传"，不干扰 AMD
        tw.angular.x = float(ctrl_output.right_fin_deg or 0.0)
        tw.angular.y = float(ctrl_output.top_fin_deg or 0.0)
        tw.angular.z = float(ctrl_output.left_fin_deg or 0.0)
        tw.linear.z = float(ctrl_output.bottom_fin_deg or 0.0)
        self.cmd_pub.publish(tw)

    # 5. 发布 debug (保持现有逻辑，增加控制器模式信息)
    self.latest_debug_payload = {
        'mode': 'MPC' if self._use_mpc else 'PID',
        'control_mode_byte': self._control_mode_byte,
        'thrust_cmd': ctrl_output.thrust_percent,
        'guidance_heading': smoothed_heading,
        'guidance_depth': setpoint.get('target_depth_m', 0.0),
        ...  # 现有 debug 字段
    }
```

#### 5.4 新增指令平滑器方法

```python
def _apply_heading_ramp(self, target_rad: float, now: float) -> float:
    """
    如果 target_heading 跳变超过 30°，自动生成斜坡信号。
    防止 AMD 侧 PID 产生过大的冲击电流。
    """
    target_deg = math.degrees(target_rad)
    delta = abs(target_deg - self._last_heading_cmd)

    if delta > self._heading_ramp_limit_deg:
        # 启动斜坡
        self._heading_ramp_active = True
        self._heading_ramp_start = now
        self._heading_ramp_target = target_deg
        self._get_logger().info(
            f'Heading ramp activated: {self._last_heading_cmd:.1f}° -> {target_deg:.1f}°'
        )

    if self._heading_ramp_active:
        elapsed = now - self._heading_ramp_start
        max_delta = self._heading_ramp_rate_deg_s * elapsed
        actual_delta = min(max_delta, abs(self._heading_ramp_target - self._last_heading_cmd))
        direction = 1 if self._heading_ramp_target > self._last_heading_cmd else -1
        result = self._last_heading_cmd + direction * actual_delta

        if abs(result - self._heading_ramp_target) < 0.1:
            self._heading_ramp_active = False
            result = self._heading_ramp_target

        return math.radians(result)

    self._last_heading_cmd = target_deg
    return target_rad
```

#### 5.5 新增 MpcCmd 发布者

```python
from auv_interfaces.msg import MpcCmd
...
self._mpc_cmd_pub = self.create_publisher(MpcCmd, '/auv/control/mpc_cmd', 20)
```

#### 5.6 控制模式字节强制设置

在所有发往 auv_bridge 的消息中强制设置 `control_mode_byte = 0xEF`：

```python
# 在 PID 模式的 Setpoint 输出中
goal_dict['control_mode_byte'] = int(self.get_parameter('control_mode_byte').value)  # 0xEF
```

### Phase 6: 枚举和配置更新

#### 6.1 `common/enums.py` 更新

```python
class ControlModeByte(IntEnum):
    ...
    JETSON_PROTOCOL = 0xEE  # 现有
    JETSON_HYBRID = 0xEF    # 新增：混合控制器劫持标记
```

#### 6.2 `brain_linux/config/params.yaml` 更新

```yaml
auv_controller_node:
  ros__parameters:
    use_mpc: false
    control_mode_byte: 0xEF
    heading_ramp_limit_deg: 30.0
    heading_ramp_rate_deg_s: 10.0
    # ... 现有参数 ...

    mappers:
      rudder:
        center_bias: 0.0
        gain: 1.0
        flip: false
      thrust:
        deadzone_percent: 5.0
        rpm_per_percent: 15.0
        voltage_nominal: 24.0
        voltage_compensation: true
```

## 3. 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `brain_linux/src/auv_controller/auv_controller/mappers.py` | 物理映射层：舵机/推进器映射 |
| 新建 | `brain_linux/src/auv_controller/auv_controller/base_controller.py` | BaseController 接口定义 |
| 新建 | `brain_linux/src/auv_controller/auv_controller/pid_controller.py` | PID 控制器封装（包装 AUVPIDController） |
| 新建 | `brain_linux/src/auv_controller/auv_controller/mpc_controller.py` | MPC 占位控制器（预留 casadi） |
| 新建 | `brain_linux/src/auv_controller/auv_controller/__init__.py` | 包初始化（导出新类） |
| 修改 | `brain_linux/src/auv_controller/auv_controller/auv_controller_node.py` | 引入控制器切换逻辑、指令平滑器、MpcCmd 发布 |
| 修改 | `common/enums.py` | 新增 `ControlModeByte.JETSON_HYBRID = 0xEF` |
| 修改 | `brain_linux/config/params.yaml` | 新增 use_mpc、control_mode_byte、mappers 配置 |
| 修改 | `brain_linux/src/auv_controller/setup.py` | 如有需要，确保新模块被包含 |

## 4. 验收标准

### 4.1 代码产物验证

1. **PID 模式**：
   - `ros2 param set /auv_controller_node use_mpc false`
   - 发布 `/auv/control/setpoint` 含 `target_speed_mps: 1.0`
   - 监控 `/auv/controller/debug` 中 `thrust_cmd` 随 DVL 反馈动态调整
   - 舵角字段为 `None` 或 `0.0`（透传标记）

2. **死区补偿**：
   - 下发 1% 推力时，`thrust_to_rpm(1.0, config)` 输出应 ≥ 150 RPM（跳过死区）
   - 验证 `mappers.py` 的 deadzone 逻辑

3. **MPC 占位**：
   - `ros2 param set /auv_controller_node use_mpc true`
   - 监控 `/auv/control/mpc_cmd` 收到 MpcCmd 消息
   - `thrust_percent=0.0`（占位值），`note` 包含 "placeholder"

4. **指令平滑**：
   - 发送 heading 跳变 60° 的 Setpoint
   - 验证 debug 输出中 `guidance_heading` 呈斜坡上升而非阶跃

### 4.2 仲裁一致性

- `use_mpc=false` 时：输出舵角字段 = `None` 或标记为"透传"
- `use_mpc=true` 时：输出走 MpcCmd → auv_bridge/arbiter → 协议编码

### 4.3 调试命令

```bash
# 验证 PID 模式下的速度闭环
ros2 topic pub /auv/control/setpoint auv_interfaces/msg/Setpoint \
  "{target_speed_mps: 1.0, target_depth_m: 2.0}"

# 监控输出的 RPM 是否在随 DVL 反馈动态调整
ros2 topic echo /auv/controller/debug | jq '.thrust_cmd'

# 切换到 MPC 模式
ros2 param set /auv_controller_node use_mpc true

# 监控 MPC 输出
ros2 topic echo /auv/control/mpc_cmd
```

## 5. 实施顺序

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6
  ↓         ↓         ↓         ↓         ↓         ↓
mappers   base      PID       MPC       Node      Enums &
.py      .py       .py       .py       重构       Config
```

每个 Phase 完成后立即进行单元测试验证，最后进行集成测试。
