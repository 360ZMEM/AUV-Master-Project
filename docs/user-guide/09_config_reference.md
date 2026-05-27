# 配置文件速查

列出所有主线配置文件，说明每个文件的用途和关键参数。

---

## 配置文件地图

| 文件路径 | 用途 | 使用场景 |
|----------|------|----------|
| config/sim_params.yaml | HoloOcean仿真主配置 | `--sim-backend holoocean` |
| config/sim_params.pvs.yaml | PVS仿真配置 | `--sim-backend pvs` |
| config/bridge_params.yaml | Zenoh桥接配置(HoloOcean) | 默认仿真 |
| config/bridge_params.pvs.yaml | Zenoh桥接配置(PVS) | PVS+zenoh_json |
| config/bridge_params.protocol_udp.yaml | UDP协议桥接(HoloOcean) | 真机协议仿真 |
| config/bridge_params.protocol_udp.pvs.yaml | UDP协议桥接(PVS) | PVS+protocol_udp |
| config/real_params.yaml | 真机覆盖参数(预留) | 实物部署 |
| brain_linux/config/params.yaml | ROS2节点参数(仿真) | 默认Launch |
| brain_linux/config/params.protocol_udp_arbiter.yaml | ROS2节点参数(真机) | --arbiter-profile |
| brain_linux/config/feature_flags.yaml | 功能开关 | 所有模式 |
| console_soft/.../console_config.yaml | 上位机配置 | Console启动 |

---

## 主线配置（绝对必须关心的4个文件）

1. **config/sim_params.pvs.yaml** — 仿真实验的核心参数（PID增益、轨迹定义、评估阈值）
2. **brain_linux/config/params.protocol_udp_arbiter.yaml** — 真机部署的核心参数
3. **brain_linux/config/feature_flags.yaml** — 功能开关（决策/控制/桥接各层使能）
4. **console_soft/auv_console_pyside6/console_config.yaml** — 上位机通信参数

---

## 各配置核心参数说明

### config/sim_params.pvs.yaml

| 参数 | 默认值 | 含义 | 调整建议 |
|------|--------|------|----------|
| controller.depth_kp | 1.0 | 深度PID比例增益 | 增大加快响应，过大会振荡 |
| controller.heading_kp | 40.0 | 航向PID比例增益 | 仿真中偏大，真机需降低 |
| controller.speed_kp | 5.0 | 速度PID比例增益 | 配合前馈项调整 |
| trajectory.type | cable_like_3d | 轨迹类型 | 可选circle_3d等 |
| trajectory.speed_mps | 1.5 | 目标航速(m/s) | 根据实验需求调整 |
| evaluation.rmse_threshold | 5.0 | RMSE通过阈值(m) | 越小越严格 |
| ocean_current.enabled | false | 是否启用洋流扰动 | 鲁棒性测试时开启 |
| ocean_current.velocity | [0,0,0] | 洋流速度矢量(m/s) | 弱流[0.1,0.05,0]，强流[0.5,0.3,0] |
| duration_s | 120 | 仿真时长(秒) | 长时测试设为300-600 |
| pvs.dt | 0.1 | PVS积分步长(秒) | 通常无需修改 |

### brain_linux/config/params.protocol_udp_arbiter.yaml

| 参数 | 默认值 | 含义 | 调整建议 |
|------|--------|------|----------|
| protocol_udp.remote_host | 127.0.0.1 | AMD目标IP | 真机时改为实际IP |
| protocol_udp.remote_port | 52364 | AMD监听端口 | 与AMD端配置一致 |
| protocol_udp.bind_port | 52364 | Jetson监听端口 | 确保不冲突 |
| controller.depth_kp | 0.30 | 真机深度Kp | 已针对实物调优 |
| controller.heading_kp | 9.0 | 真机航向Kp | 已针对实物调优 |
| controller.speed_kp | 28.0 | 真机速度Kp | 已针对实物调优 |
| controller.speed_feedforward | [2.497,27.730,0.547] | 速度前馈系数 | 水池标定获得 |
| arbiter.estop_timeout_ms | 2000 | ESTOP超时 | 通信不稳定时可适当增大 |
| guard.min_total_voltage_v | 22.0 | 最低电池电压 | 匹配电池组规格 |
| ekf.imu_acc_is_linear | true | IMU输出是否已去重力 | 视具体IMU型号而定 |

### brain_linux/config/feature_flags.yaml

| 参数 | 默认值 | 含义 | 调整建议 |
|------|--------|------|----------|
| enable_behavior_tree | true | 决策层BT使能 | false时不发布setpoint |
| bypass_to_manual_setpoint | false | 跳过BT直接转发手动setpoint | 调试时使用 |
| bypass_zero_effort | false | 控制层输出零推力 | 安全测试时使用 |
| depth_mode | CONSTANT | 深度控制模式 | CONSTANT/SINE_WAVE/TERRAIN_FOLLOWING |
| heading_mode | CONSTANT | 航向控制模式 | CONSTANT/TRAJECTORY/MAGNETIC_TRACKING |
| passive_mode | false | 被动模式(不发送控制) | 观察模式/安全调试 |

### console_soft/auv_console_pyside6/console_config.yaml

| 参数 | 默认值 | 含义 | 调整建议 |
|------|--------|------|----------|
| udp.target_host | 127.0.0.1 | 目标主机IP | 真机时改为Jetson/AMD IP |
| udp.target_port | 52364 | 目标端口 | 与桥接/AMD配置一致 |
| udp.bind_port | 52365 | 本机监听端口 | 确保不冲突 |
| zenoh.router | tcp/127.0.0.1:7447 | Zenoh路由地址 | 远程时改为Jetson IP |
| gui.refresh_rate_hz | 10 | 界面刷新率 | 性能不足时降低 |
| gui.map_update_interval_ms | 200 | 地图更新间隔 | 带宽有限时增大 |

---

## feature_flags 完整说明

| 参数 | 默认值 | 影响范围 |
|------|--------|----------|
| enable_behavior_tree | true | 决策层：false时不发布setpoint |
| bypass_to_manual_setpoint | false | 决策层：true时跳过BT，直接转发手动setpoint |
| bypass_zero_effort | false | 控制层：true时输出零推力 |
| depth_mode | CONSTANT | 控制层：CONSTANT/SINE_WAVE/TERRAIN_FOLLOWING |
| heading_mode | CONSTANT | 控制层：CONSTANT/TRAJECTORY/MAGNETIC_TRACKING |
| passive_mode | false | 桥接层：true时不发送实际控制命令 |

---

## 历史遗留配置（可忽略）

- config/bridge_params.bak-20260401.yaml — 旧备份
- brain_linux/config/params.yaml.bak-20260401 — 旧备份
