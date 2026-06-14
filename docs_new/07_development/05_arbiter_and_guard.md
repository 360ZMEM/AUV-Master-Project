# 05 - 仲裁与安全状态机 (Arbiter & Guard)

> 本文件定义了 AUV 系统中的"保命红线"——所有可能触发紧急动作的守卫条件与降级路径。  
> 仿真环境中这些守卫通常被禁用或阈值宽松；实机部署时必须收紧所有阈值，假设硬件是"不可信"的。

---

## 1. 命令仲裁器架构 (Command Arbiter)

### 1.1 系统角色

```
┌──────────────────────────────────────────────────────────────────┐
│                        上位机 PC (操作界面)                        │
│          发送 $CKTH 遥控指令 / 任务取消 / 清除故障                  │
└──────────────────┬───────────────────────────────────────────────┘
                   │ Zenoh: rt/pc/cmd_raw
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                     CommandArbiter (arbiter.py)                   │
│                                                                   │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────────────┐  │
│  │  PC 指令接收 │───▶│  模式判定    │───▶│  AUTONOMOUS 模式      │  │
│  │  update_pc_  │    │  control_   │    │  使用 Jetson MPC 输出  │  │
│  │  raw_command │    │  mode_byte  │    │  丢弃 PC 推力字段      │  │
│  └─────────────┘    │  = 0xEE?    │    └──────────────────────┘  │
│                     └──────┬──────┘              │                │
│                            │ REMOTE              ▼                │
│                            ▼           ┌──────────────────────┐  │
│                    ┌──────────────┐    │  REMOTE 模式          │  │
│                    │ 透明路由 PC  │    │  原封不动转发 PC 指令   │  │
│                    │ 原始指令      │    │  透明路由，零干预      │  │
│                    └──────────────┘    └──────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
              ┌─────────────────────────┐
              │   安全守卫层 (Guard)     │
              │   电压 / 置信度 / 超时   │
              └────────────┬────────────┘
                           ▼
              最终下行指令 → $CKTH → AUV 固件
```

### 1.2 仲裁模式切换逻辑

在 `arbiter.py:update_pc_raw_command`（line 116-135）中：

```python
# 工作指令优先级最高
if work_instruction in {TASK_CANCEL, CLEAR_FAULT}:
    self._mode = ArbiterMode.REMOTE       # 强制切回遥控
    self.reset_all_buffers()
elif control_mode_byte == JETSON_PROTOCOL: # 0xEE
    self._mode = ArbiterMode.AUTONOMOUS   # 进入自主
else:
    self._mode = ArbiterMode.REMOTE       # 默认遥控
```

**模式切换真值表**：

| `work_instruction` | `control_mode_byte` | 结果模式 | 说明 |
|:---:|:---:|:---:|:---|
| TASK_CANCEL (0x02) | 任意 | **REMOTE** | 操作员主动收回控制权 |
| CLEAR_FAULT (0x03) | 任意 | **REMOTE** | 故障清除后回到遥控 |
| 任意其他 | 0xEE (JETSON_PROTOCOL) | **AUTONOMOUS** | Jetson 协议标识，进入自主 |
| 任意其他 | 0x01 (REMOTE_CONTROL) | **REMOTE** | 默认遥控模式 |

> **仿真默认**：`protocol_control_mode_byte: 238` (0xEE) → 仿真中默认自主模式  
> **实机可能范围**：初始应为 `0x01`（遥控），由操作员确认后切换为自主

---

## 2. 分层超时机制 (Tiered Watchdog)

### 2.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机建议值 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `arbiter.mpc_timeout_s` | float | `0.5` | `0.3 ~ 0.5` | `params.yaml:26` |
| `arbiter.guard_max_uplink_age_ms` | float | `200.0` | `100.0 ~ 300.0` | `params.yaml:29` |
| `arbiter.pc_soft_warning_s` | float | `1.0` | `0.8 ~ 1.5` | `arbiter.py:85` |
| `arbiter.pc_timeout_s` | float | `1.5` | `1.0 ~ 2.0` | `arbiter.py:84` |
| `controller.control_rate_hz` | float | `20.0` | `10.0 ~ 50.0` | `params.yaml:43` |

在 `arbiter.py` 中（line 104-114）：

```python
def check_pc_link_health(self, *, now: float | None = None) -> str:
    dt = stamp - self._last_pc_ts
    if dt > self.pc_timeout_s:         # 1.5s → LOST (Hard ESTOP)
        return "LOST"
    if dt > self.pc_soft_warning_s:    # 1.0s → WEAK (Soft Warning)
        return "WEAK"
    return "OK"
```

### 2.2 失联降级路径流程图

```
                    ┌────────────────────┐
                    │  Jetson 正常运行    │
                    │  MPC 20Hz 输出     │
                    └──────┬─────────────┘
                           │
                    ┌──────▼─────────────┐
                    │ MPC 指令是否新鲜？  │  mpc_timeout_s = 0.5s
                    │ (now - last_mpc_ts │
                    │  < 0.5s ?)         │
                    └──┬───────────┬─────┘
                       │ 是         │ 否
               ┌───────▼──────┐  ┌──▼────────────────┐
               │ MPC 指令有效？ │  │ 安全回退路径       │
               │ (valid+healthy)│ │ SAFETY_FALLBACK    │
               └──┬──────┬─────┘ │ thrust=0, fins=0   │
                  │ 是    │ 否   │ 所有执行器归零      │
          ┌───────▼──┐ ┌─▼────┐└──────────┬─────────┘
          │ 自主模式  │ │安全  │            │
          │ 使用 MPC │ │回退  │     ┌──────▼────────┐
          │ 输出      │ │      │     │ PC 链路健康？  │
          └──────┬───┘ └──┬───┘     │ check_pc_link │
                 │         │        └──┬──────┬─────┘
                 │         │      是   │      │ LOST
          ┌──────▼──────┐  │    ┌──────▼┐ ┌──▼────────────┐
          │ 最终下行指令 │  │    │ REMOTE│ │ 强制安全模式   │
          │ → $CKTH 帧  │  │    │ 模式  │ │ 全部执行器归零 │
          └─────────────┘  │    │转发PC │ │ + 告警日志     │
                           │    │指令   │ └───────────────┘
                           └────┴──────┘
```

### 2.3 超时层级详解

| 层级 | 超时阈值 | 触发条件 | 降级动作 | 严重级别 |
|:---|:---:|:---|:---|:---:|
| **L0: 正常** | - | MPC 新鲜 + 有效 | 使用 MPC 输出 | ✅ 绿色 |
| **L1: MPC 过期** | > 0.5s | MPC 节点挂掉或延迟 | 安全回退（推力=0, 舵面=0） | ⚠️ 黄色 |
| **L2: PC 弱** | > 1.0s | PC 与 Jetson 通信延迟 | 状态标记 WEAK，继续当前模式 | ⚠️ 黄色 |
| **L3: PC 丢失** | > 1.5s | PC 与 Jetson 完全断联 | 强制 REMOTE 模式，所有指令归零 | 🔴 红色 (ESTOP) |
| **L4: 上行超时** | > 200ms | 上行遥测数据不新鲜 | 降低置信度，可能触发状态切换 | ⚠️ 黄色 |

> **仿真默认**：所有超时阈值宽松，因为仿真中所有节点在同一进程内  
> **实机暗病**：若网络拥塞导致 Jetson-MPC 通信延迟 > 0.5s，仲裁器会认为 MPC 失效 → 切换到安全回退 → AUV 突然失去推力。**建议**：在实机上缩短到 `0.3s`，让降级更早触发，避免使用过期控制指令。

---

## 3. 电压压降补偿 (Voltage Drop Compensation)

### 3.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机可能范围 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `arbiter.guard_min_total_voltage_v` | float | `47.0` | `44.0 ~ 50.0` (V) | `params.yaml:27` |
| `battery_low_voltage_threshold` | float | `44.8` | `42.0 ~ 46.0` (V) | `auv_localization_node.py:144` |
| `nominal_voltage_v` | float | `48.0` | `46.0 ~ 50.4` (V) | `auv_localization_node.py:145` |
| `mappers.thrust.voltage_nominal` | float | `24.0` | `22.0 ~ 26.0` (V) | `params.yaml:61` |

### 3.2 压降干扰问题

当主推进器启动瞬间（从 0% → 50%），电池内阻导致总电压出现瞬时跌落：

```
时间轴:  ... | t-10ms | t-5ms | t=0ms | t+5ms | t+10ms | t+50ms |
电压:    ... | 48.0V  | 47.8V | 42.0V | 44.0V | 46.5V  | 47.8V  |
                ▲ 稳定     ▲ 启动瞬间      ▲ 恢复中     ▲ 恢复稳定
```

### 3.3 剔除瞬时压降的策略

在 `arbiter.py` 中，`guard_min_total_voltage_v` 用于守卫决策：

```python
# 伪代码逻辑（基于 params.yaml:27 的定义）
if total_voltage_v < guard_min_total_voltage_v:
    # 触发低电压守卫
    force_remote_mode()
    log_warning("低电压告警")
```

**策略建议**：

| 方法 | 实现 | 优点 | 缺点 |
|:---|:---|:---|:---|
| **滑动窗口平均** | 取最近 10 帧电压均值 | 平滑瞬时压降 | 延迟响应真实低电 |
| **压降率检测** | `dV/dt > 阈值` 判定为启动压降 | 快速区分启动 vs 低电 | 需要额外计算 |
| **双阈值** | 低电压告警阈值 < 压降检测阈值 | 简单可靠 | 需要精确标定 |

**推荐双阈值方案**：

```
guard_min_total_voltage_v: 47.0V   # 压降检测线（启动时可能短暂跌破）
battery_low_voltage_threshold: 44.8V  # 真正低电告警线（持续低于此值才触发）
```

- 电压在 44.8V ~ 47.0V 之间：标记警告，不触发紧急动作
- 电压低于 44.8V：触发紧急上浮

**配置命令**：
```bash
# 设置电压守卫阈值（剔除启动压降干扰）
ros2 param set /auv_bridge_node guard_min_total_voltage_v 47.0

# 设置真正的低电告警阈值
ros2 param set /auv_localization_node battery_low_voltage_threshold 44.8
```

> **仿真默认**：电压恒为 `48.0V`（无电池模型）  
> **实机暗病**：6S LiPo 满电 `25.2V`（半系统）或 `50.4V`（全系统），欠压截止 `21.6V`（6S）或 `43.2V`（12S）。若阈值设得太高（如 50V），正常启动也会触发误告警。

---

## 4. 置信度守卫 (Confidence Guard)

### 4.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机建议值 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `arbiter.guard_min_confidence` | float | `0.5` | `0.4 ~ 0.7` | `params.yaml:28` |
| `mpc_weights.confidence_threshold` | float | `0.6` | `0.5 ~ 0.8` | `params.yaml:138` |
| `mpc_weights.low_confidence_scale` | float | `3.0` | `2.0 ~ 5.0` | `params.yaml:139` |
| `mpc_weights.low_confidence_control_scale` | float | `0.3` | `0.1 ~ 0.5` | `params.yaml:140` |

### 4.2 置信度驱动的行为切换

在 `fsm_baseline.py` 中（line 113-138）：

```python
# 高置信度 → 并行跟踪（精细巡检）
if sensor.confidence > self.confidence_threshold:
    return PARALLEL_TRACKING  # speed=0.6, sine_amp=0.15, period=12s

# 低置信度 → 之字形搜索（广域覆盖）
else:
    return ZIGZAG_SEARCH      # speed=0.4, sine_amp=0.35, period=8s
```

在 MPC 控制器中，低置信度会放大跟踪权重、缩小控制权重：

```python
# 伪代码
if confidence < confidence_threshold:
    tracking_weights *= low_confidence_scale      # 放大 3x → 更激进跟踪
    control_weights /= low_confidence_control_scale  # 缩小 → 控制更保守
```

### 4.3 置信度阈值对照

| `confidence` 值 | 行为模式 | 速度 | 正弦扰动 | 说明 |
|:---|:---|:---:|:---|:---|
| **≥ 0.7** | PARALLEL_TRACKING | 0.6 m/s | 幅值 0.15m, 周期 12s | 精细巡检，紧贴海缆 |
| **0.5 ~ 0.7** | PARALLEL_TRACKING | 0.6 m/s | 同上 | 边界状态，勉强可信 |
| **0.3 ~ 0.5** | ZIGZAG_SEARCH | 0.4 m/s | 幅值 0.35m, 周期 8s | 扩搜索范围 |
| **< 0.3** | ZIGZAG_SEARCH | 0.4 m/s | 最大扰动 | 几乎丢失目标 |

> **仿真默认**：置信度由算法稳定输出，通常在 0.7 ~ 1.0  
> **实机暗病**：浑浊水域中置信度可能在 0.3 ~ 0.8 间快速波动 → FSM 频繁切换状态 → 控制指令不连续。**建议**：在 FSM 中加入状态滞回（Hysteresis），避免乒乓切换。

---

## 5. 上行链路新鲜度守卫 (Uplink Freshness Guard)

### 5.1 参数定义

| 字段 | 类型 | 仿真默认值 | 实机建议值 | 代码位置 |
|:---|:---|:---:|:---:|:---|
| `arbiter.guard_max_uplink_age_ms` | float | `200.0` | `100.0 ~ 500.0` | `params.yaml:29` |

### 5.2 新鲜度计算

```python
telemetry_freshness_ms = (current_time - last_uplink_ts) * 1000.0

if telemetry_freshness_ms > guard_max_uplink_age_ms:
    # 上行数据过期，降级处理
    reduce_confidence()
    log_warning("上行遥测不新鲜")
```

### 5.3 超时来源分析

| 超时原因 | 典型延迟 | 应对策略 |
|:---|:---:|:---|
| 水声通信带宽限制 | 100ms ~ 2000ms | 增大 `guard_max_uplink_age_ms` |
| UDP 丢包 | 随机 | 使用 Zenoh 重传机制 |
| Jetson CPU 负载过高 | 10ms ~ 100ms | 降低控制频率 `control_rate_hz` |
| 传感器驱动阻塞 | 不定 | 设置传感器超时看门狗 |

**配置命令**：
```bash
# 水声通信场景（高延迟）
ros2 param set /auv_bridge_node guard_max_uplink_age_ms 500.0

# 有线/无线局域网场景（低延迟）
ros2 param set /auv_bridge_node guard_max_uplink_age_ms 100.0
```

---

## 6. 安全状态机完整守卫汇总

### 6.1 紧急上浮触发条件（或关系）

| 条件 | 检测代码 | 阈值 | 触发后动作 |
|:---|:---|:---:|:---|
| 漏水 | `sensor.is_leaking()` | `leak_level > 0` | EMERGENCY_SURFACE |
| 低电 | `sensor.battery_low` | `voltage < 44.8V` | EMERGENCY_SURFACE |
| 穿底 | `sensor.is_seabed_penetrated()` | `clearance < 0` | EMERGENCY_SURFACE |
| 翻滚 | `attitude_guard_active` | `roll > 120° 或 pitch > 45°` | 恢复推力 + 水平姿态 |

### 6.2 仿真 vs 实机守卫对照汇总

| 守卫项 | 仿真默认 | 实机建议 | 风险等级 |
|:---|:---:|:---:|:---:|
| `guard_min_total_voltage_v` | 47.0V | 44.0V ~ 50.0V | 🔴 |
| `guard_min_confidence` | 0.5 | 0.4 ~ 0.7 | 🟡 |
| `guard_max_uplink_age_ms` | 200ms | 100ms ~ 500ms | 🟡 |
| `mpc_timeout_s` | 0.5s | 0.3s ~ 0.5s | 🔴 |
| `pc_timeout_s` | 1.5s | 1.0s ~ 2.0s | 🔴 |
| `pc_soft_warning_s` | 1.0s | 0.8s ~ 1.5s | 🟡 |
| `attitude_guard.enable` | true | true | 🔴 |
| `attitude_guard.roll_deg_max` | 120.0° | 90.0° ~ 150.0° | 🔴 |
| `attitude_guard.pitch_deg_max` | 45.0° | 25.0° ~ 60.0° | 🔴 |

### 6.3 保命红线调试命令

```bash
# 紧急情况下强制切回遥控模式（通过发送特定工作指令）
# work_instruction=0x02 (TASK_CANCEL) 会触发 arbiter.force_remote()

# 调整电压守卫（防止启动压降误触发）
ros2 param set /auv_bridge_node guard_min_total_voltage_v 45.0

# 放宽上行新鲜度要求（水声高延迟环境）
ros2 param set /auv_bridge_node guard_max_uplink_age_ms 500.0

# 收紧姿态保护（浅水任务）
ros2 param set /auv_bridge_node pitch_deg_max 25.0

# 查看当前仲裁状态
ros2 topic echo /auv/arbiter/status --once
```
