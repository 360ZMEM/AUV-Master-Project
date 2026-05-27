# 03 - Mock AMD子系统

## 设计目标

Mock AMD（Acoustic Modem/Driver模拟器）的核心目标是让仿真环境尽可能逼近真实水下通信环境。真实的VxWorks AMD硬件具有以下特征：

- 非确定性传输延迟（声学通道+处理延迟）
- 偶发丢包和数据包重排序
- 各传感器以不同采样率工作
- 传感器可能出现故障（冻结、漂移、尖峰）

Mock AMD在软件层面模拟上述所有行为，使得上层决策算法在仿真阶段就必须处理这些非理想情况。

---

## 架构图

```
上位机/Jetson ←UDP→ [MockAmdServer] ←内部→ [PVS/HoloOcean仿真]
                         │
                         ├── TransportDelayQueue (通信延迟)
                         ├── SensorSampleCache (多速率采样)
                         └── ChaosInjector (故障注入)
```

数据流向：
- **下行**（上位机 → AUV）：控制命令经UDP到达MockAmdServer，解析后送入仿真器
- **上行**（AUV → 上位机）：仿真器输出经传感器缓存、延迟队列、混沌注入后打包回传

---

## 三大子模块

### 1. TransportDelayQueue (`mock_amd_delay.py`)

模拟声学通信信道的非确定性延迟。

**原理**：
```
实际延迟 = base_delay + uniform_random(-jitter, +jitter)
```

**实现细节**：
- FIFO有界队列，容量由 `max_queue_size` 配置
- 每个数据包入队时打上"到期时间戳"
- 主循环每帧检查队头是否到期，到期则出队发送
- 队列溢出时丢弃最旧的包（模拟缓冲区溢出）

**配置参数**：
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `base_delay_ms` | 基础延迟 | 200 |
| `jitter_ms` | 随机抖动范围 | 50 |
| `max_queue_size` | 队列容量 | 32 |

### 2. SensorSampleCache (`mock_amd_sensor_cache.py`)

模拟各传感器不同的采样频率。真实AUV中各传感器异步工作，不会每帧都有新数据。

**各传感器采样率**：
| 传感器 | 采样率 | 说明 |
|--------|--------|------|
| IMU | ~100 Hz | 加速度+角速度 |
| Depth | ~50 Hz | 压力传感器深度 |
| Magnetometer | ~20 Hz | 三轴磁场 |
| DVL | ~6 Hz | 对地速度（声学多普勒） |

**实现方式**：
- 每个传感器维护独立的"最后采样时间"
- 每帧检查：`current_time - last_sample_time >= sample_period`
- 满足条件则更新缓存值；否则返回旧值（hold）
- DVL额外模拟"底部跟踪丢失"场景

### 3. ChaosInjector (`mock_amd_chaos.py`)

故障注入引擎，模拟真实环境中的各种异常。

**传输层故障**：
| 故障类型 | 触发方式 | 效果 |
|----------|----------|------|
| 丢包 | 概率触发 (`drop_rate`) | 整包丢弃 |
| 重排序 | 概率触发 (`reorder_rate`) | 与前一包交换顺序 |

**传感器层故障**：
| 故障类型 | 触发方式 | 效果 |
|----------|----------|------|
| DVL冻结 | 持续时间窗口 | DVL输出锁定为最后有效值 |
| IMU漂移 | 缓慢累积 | 角速度偏置线性增长 |
| 深度尖峰 | 随机脉冲 | 深度值突变至异常值 |
| 磁力计饱和 | 幅度限制 | 磁场输出裁剪至极值 |

**上行链路故障**：
| 故障类型 | 触发方式 | 效果 |
|----------|----------|------|
| 周期性通信中断 | 定时器触发 | 一段时间内无上行数据 |

故障可通过配置文件启用/禁用，也支持运行时动态触发。

---

## Mock AMD Server主循环

每帧执行流程：

```
┌─────────────────────────────────────────┐
│ 1. UDP接收下行包                         │
│    └── parse_downlink_packet()          │
├─────────────────────────────────────────┤
│ 2. CommandGuard.sanitize()              │
│    └── 命令限幅、频率检查、合法性验证     │
├─────────────────────────────────────────┤
│ 3. PVS/HoloOcean仿真步进               │
│    └── sim_wrapper.tick(command)        │
├─────────────────────────────────────────┤
│ 4. 后处理                               │
│    ├── 坐标转换 (UE4→NED)              │
│    ├── SensorSampleCache.update()       │
│    └── ChaosInjector.inject()          │
├─────────────────────────────────────────┤
│ 5. 打包上行                             │
│    ├── build_uplink_packet()            │
│    ├── TransportDelayQueue.enqueue()    │
│    └── 检查到期包 → UDP发送             │
└─────────────────────────────────────────┘
```

---

## 配置入口

所有Mock AMD参数集中在 `bridge_params.yaml` 的 `mock_amd` 段：

```yaml
mock_amd:
  enabled: true
  udp_port: 5000
  delay:
    base_delay_ms: 200
    jitter_ms: 50
    max_queue_size: 32
  sensor_rates:
    imu_hz: 100
    dvl_hz: 6
    depth_hz: 50
    mag_hz: 20
  chaos:
    enabled: false
    drop_rate: 0.02
    reorder_rate: 0.01
    dvl_freeze_duration_s: 2.0
    imu_drift_rate: 0.001
    depth_spike_probability: 0.005
    comms_blackout_period_s: 30.0
    comms_blackout_duration_s: 3.0
```

---

## 与VxWorks真实AMD的7处已知偏差

以下为Mock AMD与真实硬件之间的已知差异（详见 `docs_old/mock_amd_hw/偏差分析.md`）：

| # | 偏差项 | Mock行为 | 真实行为 | 影响 |
|---|--------|----------|----------|------|
| 1 | 时钟源 | 系统时钟（μs精度） | 硬件RTC（ns精度） | 时间戳抖动更大 |
| 2 | UDP分片 | OS自动处理 | 自定义MTU拆包 | 大包行为不同 |
| 3 | 执行器反馈 | 无延迟 | 有CAN总线延迟 | 控制响应偏快 |
| 4 | 看门狗 | 软件模拟 | 硬件看门狗 | 超时行为宽松 |
| 5 | 电源监控 | 无 | 有电压/电流监测 | 缺少低电告警 |
| 6 | 多播支持 | 不支持 | 支持 | 仅点对点通信 |
| 7 | 加密 | 明文 | AES-128 | 安全层缺失 |
