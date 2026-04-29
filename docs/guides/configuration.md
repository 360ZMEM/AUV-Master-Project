# ⚙️ 配置参数详解

本文档详细说明 AUV_Master_Project 中所有可配置的 YAML 参数。

---

## 配置文件位置

所有配置文件位于 `config/` 目录：

| 文件 | 用途 | 覆盖策略 |
|------|------|--------|
| **sim_params.yaml** | 仿真与控制参数 | 基础配置，可被其他文件覆盖 |
| **sim_params.pvs.yaml** | PVS 仿真专用参数 | 当使用 `--sim-backend pvs` 时覆盖基础配置 |
| **real_params.yaml** | 实物参数 | 当使用 `--backend protocol_udp` 时覆盖基础配置 |
| **bridge_params.yaml** | Zenoh 桥接参数 | Zenoh 连接与协议配置 |
| **bridge_params.protocol_udp.*.yaml** | 二进制协议桥接配置 | Protocol UDP 专用配置 |

---

## sim_params.yaml 详解

### 仿真基础设置

```yaml
stage:
  name: auv_project_new_stack          # 项目名称（用于日志识别）

simulation:
  backend: holoocean                   # 仿真后端：holoocean / pvs
  world: Dam                           # 仿真场景
  ticks_per_sec: 30                    # 仿真 FPS（Hz）
  dt: 0.0333                           # 每步时间间隔 = 1 / ticks_per_sec
  max_steps: 4500                      # 最大仿真步数（总时长 = max_steps * dt）
  log_level: INFO                      # 日志级别：DEBUG/INFO/WARNING/ERROR
  
  # 仿真环境相关
  vehicle: TorpedoAUV                  # 车型
  num_agents: 1                        # 同时仿真的车数量
  sensors:
    - PoseSensor                       # 车体位置感知
    - DepthSensor                      # 深度传感器
    - IMUSensor                        # IMU
    - DVLSensor                        # Doppler Velocity Logger
```

### 控制参数

```yaml
control:
  target_u: 1.1                        # 目标前进速度（m/s）
  
  # 深度环 PID 参数
  depth:
    kp: 0.30                           # 比例增益
    ki: 0.01                           # 积分增益
    kd: 0.0                            # 微分增益
    integral_limit: 10.0               # 积分限幅
  
  # 俯仰角环 PID 参数（由深度环驱动）
  pitch:
    kp: 6.5
    ki: 0.0
    kd: 0.0
  
  # 航向角环 PID 参数（由轨迹导引驱动）
  yaw:
    kp: 9.0
    ki: 0.0
    kd: 0.0
    integral_limit: 30.0
  
  # 前进速度环 PID 参数
  speed:
    kp: 0.5
    ki: 0.0
    kd: 0.0
```

### 轨迹参数

```yaml
trajectory:
  kind: cable_like_3d                  # 轨迹类型：cable_like_3d / straight / circle
  duration: 150.0                      # 轨迹总时长（秒）
  
  # 直线与蛇形参数
  surge_speed: 1.1                     # 前进速度（m/s）
  lateral_wavenumber: 0.25             # 横向波动的波数（影响蛇形频率）
  lateral_amplitude: 20.0              # 横向摆幅（米）
  
  # 圆形轨迹参数（若 kind = circle）
  radius: 50.0                         # 圆形半径（米）
  period: 60.0                         # 圆周期（秒）
  
  # 路径约束
  depth_setpoint: 25.0                 # 目标深度（米，正向下）
  depth_tolerance: 0.5                 # 深度容差（米）
  
  # 起始位置（NED 坐标系）
  start_position:
    north: 0.0
    east: 0.0
    depth: 1.0
```

### 控制限幅

```yaml
limits:
  # 舵面限幅（度数）
  fin_deg_max: 30.0                    # 最大舵角
  fin_deg_min: -30.0                   # 最小舵角
  
  # 推力限幅（百分比，-100~100）
  thrust_min: -100.0
  thrust_max: 100.0
  
  # 速度限幅
  speed_min: 0.0
  speed_max: 3.0                       # 最大速度（m/s）
  
  # 深度限幅
  depth_min: 0.5                       # 防止浮出水面
  depth_max: 100.0
```

### 输出和日志

```yaml
output:
  log_dir: log/                        # 日志保存目录
  save_trajectory: true                # 是否保存轨迹数据
  plot_results: false                  # 实验后是否自动绘图
  
logging:
  file_level: INFO                     # 文件日志级别
  console_level: INFO                  # 控制台日志级别
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

---

## controller_params.yaml 详解（ROS2 侧）

```yaml
controller:
  # 与 sim_params.yaml 中的 control 部分相同
  target_u: 1.1
  
  depth:
    kp: 0.30
    ki: 0.01
    kd: 0.0
    integral_limit: 10.0
  
  # 其他环...
  
  # 控制频率
  update_rate: 30.0                    # 控制更新率（Hz）
  cmd_timeout: 1.0                     # 命令超时（秒）
```

---

## localization_params.yaml 详解（ROS2 侧）

```yaml
localization:
  # ES-EKF 滤波器参数
  
  # 过程噪声（Process Noise Covariance Q）
  process_noise:
    position: [0.01, 0.01, 0.01]      # 位置过程噪声（北东地）
    velocity: [0.1, 0.1, 0.1]         # 速度过程噪声
    attitude: [0.01, 0.01, 0.01]      # 姿态过程噪声
  
  # 测量噪声（Measurement Noise Covariance R）
  measurement_noise:
    imu_acc: [0.1, 0.1, 0.1]          # IMU 加速度测量噪声
    imu_gyro: [0.01, 0.01, 0.01]      # IMU 角速度测量噪声
    dvl: [0.05, 0.05, 0.05]           # DVL 速度测量噪声
    depth: 0.1                        # 深度传感器噪声
  
  # 初始状态估计
  initial_position: [0.0, 0.0, 0.0]
  initial_velocity: [0.0, 0.0, 0.0]
  initial_attitude: [0.0, 0.0, 0.0]
  
  # 滤波器更新率
  update_rate: 30.0                    # Hz
```

---

## bridge_params.yaml 详解

```yaml
zenoh:
  # Zenoh 连接模式
  mode: peer                           # peer / client / router
  
  # 传输协议（多协议支持）
  transport:
    - tcp                              # TCP 传输
    - udp                              # UDP 传输（低延迟）
    - ws                               # WebSocket（用于浏览器）
  
  # 性能参数
  batch_size: 65536                    # 批处理大小（字节）
  batch_timeout_ms: 100                # 批处理超时（毫秒）
  
  # 主题映射（Zenoh ↔ ROS2）
  topic_mapping:
    # 仿真 → ROS2
    rt/auv/sensors/imu: /imu
    rt/auv/sensors/dvl: /dvl
    rt/auv/telemetry: /auv/telemetry
    
    # ROS2 → 仿真
    /cmd_vel: rt/auv/control/cmd_vel

# Protocol UDP（若使用二进制协议）
protocol:
  port: 12345                          # UDP 端口
  host: 127.0.0.1                      # 本地绑定地址
  remote_host: 127.0.0.1               # 远端地址（若有）
  remote_port: 54321
  
  # 协议版本
  version: 1
  
  # 消息编码（big_endian / little_endian）
  byte_order: little_endian
```

---

## 参数修改示例

### 场景 1：提高控制响应速度（实验室调试）

```yaml
# 修改 sim_params.yaml
simulation:
  ticks_per_sec: 60         # 提高到 60 FPS
  max_steps: 1800           # 保持总时长 60 秒

control:
  depth:
    kp: 0.50               # 提高深度环 Kp
  yaw:
    kp: 12.0               # 提高航向环 Kp
```

### 场景 2：长时间实验（120+ 秒）

```yaml
simulation:
  max_steps: 3600          # 120 秒实验
  ticks_per_sec: 30        # 保持默认速度

trajectory:
  duration: 150.0          # 增加轨迹时长
  lateral_wavenumber: 0.15 # 降低蛇形频率以覆盖更多循环
```

### 场景 3：与实物通信（协议 UDP）

```yaml
# 在启动时指定
# bash scripts/start_lin_sim.sh both --backend protocol_udp

# 或编辑配置
simulation:
  backend: holoocean       # 还是使用仿真

# 同时启动 bridge_params.protocol_udp.*.yaml
protocol:
  port: 12345              # 与实物通信端口保持一致
  byte_order: little_endian
```

---

## 常见参数调整建议

### 若控制不稳定（振荡）
- **降低** Kp（比例增益）
- **降低** Ki（积分增益）或增加 integral_limit
- **检查** 采样频率（ticks_per_sec）是否足够高

### 若控制响应慢（延迟大）
- **提高** Kp
- **提高** ticks_per_sec（增加计算负荷）
- **检查** udp/tcp 延迟

### 若轨迹执行不准确
- **调整** lateral_wavenumber 改变蛇形频率
- **调整** surge_speed 改变前进速度
- **检查** trim_angle（若有）是否需要调整

### 若与实物不同步
- **检查** byte_order（大小端）
- **检查** protocol_control_mode_byte 是否与实物一致
- **检查** 时间戳精度（毫秒 vs 微秒）

---

## 验证配置

### 查看当前配置

```bash
# 打印当前加载的配置
python -c "from sim_holoocean.apps.main import load_config; import yaml; cfg = load_config('config/sim_params.yaml'); print(yaml.dump(cfg))"

# 或查看文件本身
cat config/sim_params.yaml
```

### 验证参数合理性

```bash
# 检查约束
max_time = max_steps * dt
# 应该大约等于 trajectory.duration 或稍长
```

---

## 下一步

- 📝 修改参数后，测试运行：[仿真启动指南](simulation_startup.md)
- 🔧 若需要更细粒度的调整，查看源代码中的默认值
- 📊 若需要长期调参，考虑使用参数扫描脚本（`tools/sweep_params.py`，若有）

---

**更新日期**：2026-04-25
