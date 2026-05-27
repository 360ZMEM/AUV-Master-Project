# 主线实验脚本

详细说明 `start_experiment.sh` 及其调用的子脚本链。

---

## 脚本调用链

```
start_experiment.sh
│
├─→ start_foxglove_holoocean_ros.sh
│       │
│       ├─→ Foxglove WebSocket Bridge
│       ├─→ HoloOcean / PVS 仿真引擎
│       └─→ ROS2 Bag 录制
│
├─→ start_lin_sim.sh          # 仿真层（传感器模拟、物理模型）
│
└─→ start_lin_brain.sh        # 决策层（行为树、路径规划、控制器）
```

**执行顺序**：`start_experiment.sh` 先启动基础设施（Foxglove + 仿真环境 + ROS），再依次拉起仿真层和决策层。

---

## start_experiment.sh 完整参数表

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--sim-backend` | 枚举 | `holoocean` | 仿真后端选择：`holoocean`（完整3D）或 `pvs`（纯虚拟轻量） |
| `--bridge-backend` | 枚举 | `zenoh_json` | 通信桥接方式：`zenoh_json`（Zenoh JSON序列化）或 `protocol_udp`（UDP二进制协议，模拟真机） |
| `--duration` | 整数(秒) | `300` | 实验持续时间，单位秒 |
| `--record-bag` | 标志 | 启用 | 启用 ROS2 Bag 录制 |
| `--no-record-bag` | 标志 | — | 禁用 ROS2 Bag 录制 |
| `--bag-storage` | 枚举 | `mcap` | Bag 存储格式：`mcap` 或 `sqlite3` |
| `--arbiter-profile` | 字符串 | 无 | 启用仲裁器并指定 profile 名称 |
| `--protocol-control-mode-byte` | 十六进制 | `0xEE` | 协议控制模式字节，`0xEE` = 自主模式 |
| `--brain-mode` | 字符串 | 自动推导 | 决策层运行模式，覆盖自动推导 |
| `--sim-mode` | 字符串 | 自动推导 | 仿真层运行模式，覆盖自动推导 |
| `--sim-cfg` | 路径 | 自动推导 | 仿真层配置文件路径，覆盖自动推导 |
| `--bridge-cfg` | 路径 | 自动推导 | 桥接层配置文件路径，覆盖自动推导 |

---

## 配置自动推导规则

当未显式指定 `--sim-cfg` / `--bridge-cfg` 时，脚本根据 `sim-backend × bridge-backend` 组合自动选择配置文件：

| sim-backend | bridge-backend | sim 配置文件 | bridge 配置文件 |
|-------------|---------------|-------------|----------------|
| `holoocean` | `zenoh_json` | `sim_params.yaml` | `bridge_params.yaml` |
| `holoocean` | `protocol_udp` | `sim_params.yaml` | `bridge_params.protocol_udp.yaml` |
| `pvs` | `zenoh_json` | `sim_params.pvs.yaml` | `bridge_params.pvs.yaml` |
| `pvs` | `protocol_udp` | `sim_params.pvs.yaml` | `bridge_params.protocol_udp.pvs.yaml` |

配置文件位于 `config/` 目录下，可直接编辑以调整仿真参数。

---

## 输出产物

### Bags 目录结构

```
$AUV_DATA_ROOT/bags/YYYYMMDD_HHMMSS/
├── metadata.txt                # 运行参数快照
├── rosbag2_YYYYMMDD_HHMMSS_0.mcap   # ROS2 Bag 录制
└── rosbag2_YYYYMMDD_HHMMSS_0.mcap.yaml  # Bag 元信息
```

### metadata.txt 内容

```
experiment_start: 2026-05-27T14:30:22
sim_backend: pvs
bridge_backend: zenoh_json
duration: 120
sim_cfg: config/sim_params.pvs.yaml
bridge_cfg: config/bridge_params.pvs.yaml
bag_storage: mcap
record_bag: true
arbiter_profile: none
protocol_control_mode_byte: 0xEE
```

---

## 典型使用场景

### 场景 1：快速 120 秒 PVS 实验

最轻量的仿真方式，适合算法快速验证：

```bash
bash start_experiment.sh --sim-backend pvs --duration 120
```

### 场景 2：HoloOcean 完整 3D 仿真

启动完整水下 3D 渲染环境，适合视觉算法和环境交互测试：

```bash
bash start_experiment.sh --sim-backend holoocean --duration 300
```

### 场景 3：Protocol UDP 模式（模拟真机通信）

使用 UDP 二进制协议桥接，模拟与真实硬件通信，适合通信层联调：

```bash
bash start_experiment.sh --sim-backend pvs --bridge-backend protocol_udp --duration 120
```

### 场景 4：启用仲裁器的自主模式

启用仲裁器进行多任务优先级管理，自主模式运行：

```bash
bash start_experiment.sh \
  --sim-backend holoocean \
  --arbiter-profile default \
  --protocol-control-mode-byte 0xEE \
  --duration 300
```

### 场景 5：不录制 Bag（调试用）

调试时可跳过 Bag 录制以减少 I/O 开销：

```bash
bash start_experiment.sh --sim-backend pvs --no-record-bag --duration 60
```
