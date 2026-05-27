# 04 - Zenoh实时通信桥接

## 为什么用Zenoh

Zenoh被选为系统通信中间件，基于以下考量：

| 需求 | Zenoh优势 |
|------|-----------|
| 跨平台 | 原生支持Windows/Linux/macOS，无需额外移植 |
| 低延迟 | 基于共享内存和零拷贝的发布/订阅，亚毫秒级延迟 |
| 零配置发现 | 自动对等发现，无需中心broker |
| 序列化简单 | 直接传输JSON字符串，无需IDL编译 |
| 轻量级 | 单库依赖，无ROS2在Windows端的部署困难 |

典型场景：Windows上运行HoloOcean仿真器，Linux上运行ROS2决策栈，两者通过Zenoh局域网通信。

---

## 架构位置

```
┌─────────────────┐         Zenoh (UDP/TCP)         ┌─────────────────┐
│   Windows PC    │ ◄══════════════════════════════► │   Linux PC      │
│                 │                                  │                 │
│  HoloOcean     │    rt/auv/sensors/*  ──────►     │  ROS2节点       │
│  ZenohBridge   │    ◄──────  rt/auv/control/*     │  zenoh_bridge   │
│                 │                                  │  _node          │
└─────────────────┘                                  └─────────────────┘
```

也支持同机通信（开发调试时Linux上同时运行PVS + ROS2）。

---

## Topic设计

### 上行Topic（仿真→决策栈）

| Topic Key | 数据内容 | 频率 |
|-----------|----------|------|
| `rt/auv/sensors/ground_truth` | 位置(x,y,z) + 姿态(roll,pitch,yaw) + 电缆距离 | 50 Hz |
| `rt/auv/sensors/imu` | 加速度(ax,ay,az) + 角速度(gx,gy,gz) | 100 Hz |
| `rt/auv/sensors/dvl` | 对地速度(vx,vy,vz) + 底部跟踪有效标志 | 6 Hz |
| `rt/auv/sensors/depth` | 深度(z) + 温度 | 50 Hz |
| `rt/auv/sensors/magnetic` | 磁场(mx,my,mz) | 20 Hz |
| `rt/auv/perception/sonar` | 声纳距离数组 + 方位角 | 10 Hz |

### 下行Topic（决策栈→仿真）

| Topic Key | 数据内容 | 频率 |
|-----------|----------|------|
| `rt/auv/control/cmd_vel` | 5元控制命令 [surge, sway, heave, yaw_rate, pitch_rate] | 50 Hz |

### 侧通道

| Topic Key | 数据内容 | 用途 |
|-----------|----------|------|
| `rt/pc/cmd_raw` | PC上位机原始$CKTH二进制包 | 上位机直接控制绕过ROS2 |
| `rt/auv/telemetry` | 仲裁器状态、当前控制源、安全标志 | 监控/调试 |

---

## ZenohBridge类接口

核心API：

```python
class ZenohBridge:
    def open(self, config: dict) -> None:
        """初始化Zenoh会话，声明所有publisher和subscriber"""
        
    def publish(self, topic: str, data: dict) -> None:
        """将字典序列化为JSON并发布到指定topic"""
        
    def get_latest_cmd(self) -> Optional[dict]:
        """获取最近收到的控制命令（非阻塞）"""
        
    def close(self) -> None:
        """关闭会话，释放资源"""
```

生命周期：
1. `open()` 时建立Zenoh session，根据配置声明所有topic的pub/sub
2. 主循环中反复调用 `publish()` 发送传感器数据
3. 主循环中调用 `get_latest_cmd()` 获取最新控制命令
4. 退出时调用 `close()` 确保优雅断开

---

## HoloOceanPhysicsZenohBridge

这是Zenoh桥接中最关键的组件，负责将原始HoloOcean传感器数据处理为"真实感"传感器输出。

**处理流水线**：

```
HoloOcean原始输出
       │
       ▼
  坐标变换 (UE4左手系 → NED右手系)
       │
       ▼
  噪声注入 (高斯噪声 + 偏置)
       │
       ▼
  DVL降采样 (50Hz → 6Hz)
       │
       ▼
  多Topic发布
    ├── rt/auv/sensors/ground_truth
    ├── rt/auv/sensors/imu
    ├── rt/auv/sensors/dvl
    ├── rt/auv/sensors/depth
    └── rt/auv/sensors/magnetic
```

**噪声模型参数**：
| 传感器 | 噪声类型 | 参数 |
|--------|----------|------|
| IMU加速度 | 高斯白噪声 | σ = 0.01 m/s² |
| IMU角速度 | 高斯白噪声 + 偏置随机游走 | σ = 0.001 rad/s |
| DVL | 高斯白噪声 | σ = 0.02 m/s |
| 深度 | 高斯白噪声 | σ = 0.01 m |
| 磁力计 | 高斯白噪声 + 硬铁偏置 | σ = 0.5 μT |

---

## ROS2侧桥接

`zenoh_json_bridge_node` 是ROS2端的桥接节点，职责为Zenoh与ROS2消息系统之间的双向转换。

**上行路径**（Zenoh → ROS2）：
```
Zenoh subscriber
       │
       ▼
  JSON反序列化
       │
       ▼
  构建ROS2消息 (sensor_msgs/Imu, geometry_msgs/PoseStamped, ...)
       │
       ▼
  ROS2 publisher
```

**下行路径**（ROS2 → Zenoh）：
```
ROS2 subscriber (geometry_msgs/Twist → cmd_vel)
       │
       ▼
  提取5元命令
       │
       ▼
  JSON序列化
       │
       ▼
  Zenoh publisher → rt/auv/control/cmd_vel
```

---

## 配置

在 `bridge_params.yaml` 的 `bridge` 段：

```yaml
bridge:
  type: zenoh  # zenoh | mock_amd | direct
  zenoh_topics:
    sensors:
      ground_truth: "rt/auv/sensors/ground_truth"
      imu: "rt/auv/sensors/imu"
      dvl: "rt/auv/sensors/dvl"
      depth: "rt/auv/sensors/depth"
      magnetic: "rt/auv/sensors/magnetic"
      sonar: "rt/auv/perception/sonar"
    control:
      cmd_vel: "rt/auv/control/cmd_vel"
    side_channel:
      cmd_raw: "rt/pc/cmd_raw"
      telemetry: "rt/auv/telemetry"
  zenoh_config:
    mode: "peer"  # peer | client
    connect: []   # 手动指定对端地址（空则自动发现）
    listen: []
  publish_rate_hz: 50
  noise:
    enabled: true
    imu_accel_std: 0.01
    imu_gyro_std: 0.001
    dvl_std: 0.02
    depth_std: 0.01
    mag_std: 0.5
```
