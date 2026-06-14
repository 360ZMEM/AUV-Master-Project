# 配置文件参考

本文档详细解释 `config/` 目录下所有配置文件的参数和含义。

---

## 配置文件列表

| 文件 | 说明 |
|------|------|
| `sim_params.yaml` | HoloOcean 仿真默认配置 |
| `sim_params.pvs.yaml` | PVS 仿真专用配置（推荐） |
| `bridge_params.yaml` | 桥接默认配置 |
| `bridge_params.pvs.yaml` | PVS 桥接配置 |
| `bridge_params.protocol_udp.yaml` | Protocol UDP 专用配置 |
| `real_params.yaml` | 实物对接配置 |

---

## sim_params.pvs.yaml 详解

这是 PVS（Python Vehicle Simulator）后端的主要配置文件。

### stage 配置

```yaml
stage:
  name: auv_project_new_stack_pvs
```
- **name**: 运行阶段的标识名称，用于日志和配置

### simulation 配置

```yaml
simulation:
  backend: pvs
  world: Dam
  package_name: Ocean
  agent_name: auv0
  show_viewport: false
  verbose: false
  ticks_per_sec: 30
  frames_per_sec: false
  dt: 0.0333333333
  max_steps: 6000
```

| 参数 | 说明 | 默认值 |
|------|------|-------|
| `backend` | 仿真后端选择 | `pvs` |
| `world` | 场景名称（HoloOcean） | `Dam` |
| `show_viewport` | 是否显示3D视图（HoloOcean） | `false` |
| `verbose` | 是否输出详细日志 | `false` |
| `ticks_per_sec` | 仿真帧率 | `30` |
| `dt` | 步长时间（秒） | 1/ticks_per_sec |
| `max_steps` | 最大步数（0为无限） | `6000` |

### agent 配置

```yaml
agent:
  type: TorpedoAUV
  control_scheme: 0
  location: [0.0, 0.0, -12.0]
  rotation: [0.0, 0.0, 0.0]
```

| 参数 | 说明 |
|------|------|
| `type` | AUV 类型 |
| `location` | 初始位置 (X, Y, Z)，负Z为向下 |
| `rotation` | 初始姿态 (Roll, Pitch, Yaw) (度) |

### limits 配置

```yaml
limits:
  fin_deg_max: 30.0
  thrust_min: -100.0
  thrust_max: 100.0
  env_min: [-200.0, -45.0, -35.0]
  env_max: [200.0, 45.0, -4.0]
  safety_margin_xy: 3.0
  safety_margin_z: 1.5
```

| 参数 | 说明 |
|------|------|
| `fin_deg_max` | 最大舵角（度） |
| `thrust_min/thrust_max` | 推力范围（%） |
| `env_min/env_max` | 环境边界安全限制 |

### control 配置

```yaml
control:
  target_u: 1.1
  u0: 1.0
  u_min: 0.6
  feedforward_trim_deg: -1.5
  depth:
    kp: 0.30
    ki: 0.01
    kd: 0.0
    integral_limit: 4.0
    target_pitch_deg_max: 15.0
    target_pitch_rate_limit_deg_s: 8.0
  pitch:
    kp: 6.5
    ki: 0.15
    kd: 2.2
    integral_limit: 45.0
  yaw:
    kp: 9.0
    ki: 0.12
    kd: 1.4
    integral_limit: 45.0
  speed:
    kp: 28.0
    ki: 1.4
    kd: 3.0
    integral_limit: 55.0
    feedforward:
      a: 2.497183
      b: 27.729751
      c: 0.546851
```

**PID 增益说明**:

| 参数 | 说明 |
|------|------|
| `kp` | 比例增益 |
| `ki` | 积分增益 |
| `kd` | 微分增益 |
| `integral_limit` | 积分限幅值 |

**外环**:
- `depth`：深度控制外环 → 输出目标俯仰角

**内环**:
- `pitch`：俯仰控制
- `yaw`：航向控制
- `speed`：速度控制

### pvs 配置

```yaml
pvs:
  control_mode: depthHeadingAutopilot
  initial_depth_m: 12.0
  initial_heading_deg: 0.0
  initial_speed_mps: 0.5
  initial_rpm: 0.0
  reference_rpm: 520.0
  reference_speed_rpm_slope: 581.0
  reference_speed_rpm_offset: -115.0
  reference_rpm_min: 300.0
  command_thrust_rpm_scale: 15.0
  max_command_rpm: 1525.0
  current_speed_mps: 0.5
  current_direction_deg: 0.0
```

**控制模式**:
- `depthHeadingAutopilot`：深度航向自动驾驶（推荐）
- `stepInput`：阶跃输入（用于协议测试）

---

## bridge_params.protocol_udp.yaml 详解

```yaml
bridge:
  backend: protocol_udp
  rate_hz: 50.0
  cmd_timeout_s: 0.5
  require_first_cmd: false
  default_command: [0.0, 0.0, 0.0, 0.0, 0.0]
  fin_abs_max: 30.0
  thrust_min: -100.0
  thrust_max: 100.0
  max_steps: 0
  protocol_udp:
    bind_host: 0.0.0.0
    bind_port: 52364
    remote_host: 127.0.0.1
    remote_port: 52365
    socket_timeout_s: 0.01
    recv_buffer_size: 2048
    auv_address: 1
    default_control_mode_byte: 238
    main_motor_rpm_scale: 15.0
    side_motor_rpm: 0
    telemetry_total_voltage_v: 48.0
    telemetry_total_current_a: 12.0
    telemetry_soc: 100
    telemetry_soh: 100
    sniffer_mirror_host: 127.0.0.1
    sniffer_mirror_port: 52366
    log_packets: true
    log_packet_hex: false
    log_ascii_format: true
    log_hex_bytes: 48
    log_every_n: 1
```

### protocol_udp 子配置

| 参数 | 说明 |
|------|------|
| `bind_host/bind_port` | 服务端绑定地址 |
| `remote_host/remote_port` | 客户端（决策侧）地址 |
| `auv_address` | AUV 地址标识 |
| `default_control_mode_byte` | 默认控制模式（238 = 自主） |
| `main_motor_rpm_scale` | 推力% 到 RPM 的缩放系数 |
| `telemetry_*` | 模拟遥测数据（电压、电流、SOC） |
| `log_packets` | 是否记录协议包日志 |
| `log_ascii_format` | 是否使用可读ASCII格式 |

---

## 配置文件选择

### 快速选择指南

| 场景 | 仿真配置 | 桥接配置 |
|------|---------|---------|
| **PVS + Zenoh (推荐)** | `sim_params.pvs.yaml` | `bridge_params.pvs.yaml` |
| **PVS + Protocol UDP** | `sim_params.pvs.yaml` | `bridge_params.protocol_udp.yaml` |
| **HoloOcean + Zenoh** | `sim_params.yaml` | `bridge_params.yaml` |

### 命令行指定配置

启动时可以直接指定配置文件：

```bash
# 启动 PVS 并使用指定配置
bash start_lin_sim.sh both --sim-backend pvs \
    --sim-cfg ../config/sim_params.pvs.yaml \
    --bridge-cfg ../config/bridge_params.pvs.yaml
```

---

## 下一步

- 了解 [PVS 架构](../02_architecture/02_pvs_architecture.md) 如何使用这些配置
- 学习 [模式切换](../05_operations/01_mode_switching.md) 的完整指导
