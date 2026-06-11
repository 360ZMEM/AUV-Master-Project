# 地形跟随（Terrain Following）

本文档介绍地形跟随基准的运行方式、配置切换、关键 KPI 与已知约束。
适用对象：希望对比 **恒深控制** 与 **自适应地形跟随** 的实验操作者。

> 想了解算法原理（前瞻预测 + LPF 平滑 + 安全仲裁），请阅读 [`docs/internals/`](../internals/INDEX.md) 中地形相关章节。
> 本页只关心"如何跑起来 / 看什么 / 出问题怎么办"。

---

## 1. 一句话理解

地形跟随让 AUV 维持一个**恒定的离底高度**（如 3.0 m）而不是恒定的绝对深度。
仿真侧的 [`VirtualEnvironment`](../../sim_holoocean/interfaces/synthetic_sensors.py) 用 Perlin 噪声生成起伏海床，
[`mock_amd_server`](../../sim_holoocean/interfaces/mock_amd_server.py) 与 [`holoocean_physics_bridge`](../../sim_holoocean/interfaces/holoocean_physics_bridge.py) 把动态的离底高度（altitude）和前向斜率（forward sonar slope）发到 brain；
[`TerrainFollower`](../../brain_linux/src/auv_controller/auv_controller/terrain_engine.py) 据此输出动态的深度目标，下发给 AMD。

---

## 2. 仿真链路全景

```
                ┌────────────────────────────────────────┐
                │  VirtualEnvironment.terrain_height_at  │  Perlin 噪声 + 线性斜坡
                └────────────────┬───────────────────────┘
                                 │ z = f(x, y)
              ┌──────────────────┴──────────────────┐
              ▼                                     ▼
   sim_holoocean/.../mock_amd_server.py     sim_holoocean/.../holoocean_physics_bridge.py
        (protocol_udp 链路)                          (zenoh_json 链路)
              │                                     │
              │  AMD 报文 spare 字段：               │  JSON 包：
              │   • altitude → param_values[?]      │   • packets["altitude"]
              │   • forward_slope ×10000            │   • packets["forward_sonar"]
              │     → param_values[10]              │
              ▼                                     ▼
   brain_linux/src/auv_bridge/.../bridge_node.py（双路径解析）
              │
              ├─► /auv/sensors/altitude               (Float32, 米)
              └─► /auv/sensors/forward_sonar_slope    (Float32, tan α)
                                 │
                                 ▼
       brain_linux/src/auv_controller/.../auv_controller_node.py
            ├─► VirtualSonarWrapper.update_slope(...)
            └─► TerrainFollower.compute_depth_target(altitude, slope, target_alt)
                                 │
                                 ▼
                    /auv/setpoint/depth → AMD
```

---

## 3. 五分钟运行

### 3.1 一键基准

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project
bash scripts/run_terrain_benchmark.sh 120
```

参数：传入每个 phase 的录制时长（秒），默认 120。

脚本自动执行三阶段：

| Phase | 模式 | feature_flags |
|-------|------|---------------|
| 1 | Baseline（恒深 CONSTANT） | `feature_flags.yaml`（默认） |
| 2 | Terrain Following | `feature_flags_terrain.yaml`（脚本临时切换） |
| 3 | Analysis | `tools/analyze_bag.py` 对两段 bag 出图 |

输出位置：`results/control/terrain_following_<YYYYMMDD_HHMMSS>/`

```
terrain_following_20260608_191052/
├── baseline_log.txt           # 阶段 1 stdout 全量记录
├── baseline/
│   ├── bag_path.txt           # 指向 $AUV_DATA_ROOT/bags/<ts>/
│   └── analysis/              # analyze_bag.py 产物
├── terrain_log.txt
└── terrain/
    ├── bag_path.txt
    └── analysis/
```

> **bag_path.txt 由来**：脚本只**记录** bag 路径而不**移动** bag，因为 `$AUV_DATA_ROOT` 通常挂载只读子树，移动会失败。要查找原始 mcap：`cat results/control/terrain_following_*/terrain/bag_path.txt`。

### 3.2 单独跑一次地形跟随

如果只想跑一次地形阶段（不需要 baseline 对照）：

```bash
cp brain_linux/config/feature_flags.yaml brain_linux/config/.feature_flags_backup.yaml
cp brain_linux/config/feature_flags_terrain.yaml brain_linux/config/feature_flags.yaml

bash scripts/start_experiment.sh \
    --sim-backend pvs \
    --bridge-backend protocol_udp \
    --arbiter-profile \
    --duration 120 \
    --record-bag

# 跑完务必恢复
cp brain_linux/config/.feature_flags_backup.yaml brain_linux/config/feature_flags.yaml
rm brain_linux/config/.feature_flags_backup.yaml
```

`run_terrain_benchmark.sh` 的 `trap cleanup EXIT ERR INT TERM` 已经把这个备份/恢复封装好了，强烈建议直接走脚本。

---

## 4. 配置文件参考

### 4.1 [feature_flags_terrain.yaml](../../brain_linux/config/feature_flags_terrain.yaml)

```yaml
/**:
  ros__parameters:
    enable_behavior_tree: true
    bypass_to_manual_setpoint: false
    bypass_zero_effort: false
    depth_mode: 'TERRAIN_FOLLOWING'   # 关键：切换为地形跟随
    heading_mode: 'CONSTANT'
    constant_depth_m: 3.0             # 此处复用为目标离底高度（m）
    constant_heading_rad: 0.0
    passive_mode: false
```

> **注意**：`/**: ros__parameters:` 是 ROS 2 通配命名空间封装，缺少这两层会被 launch 系统忽略。

### 4.2 起伏地形参数（可选）

要让对比更显著，可临时把 `bridge_params.yaml`（或 `bridge_params_terrain.yaml`）中的 `digital_twin` 节调大：

```yaml
digital_twin:
  seabed_z_m: 15.0
  terrain_noise_amplitude_m: 2.0   # ±2m 起伏
  terrain_noise_scale_m: 6.0       # 缩短波长
  terrain_noise_octaves: 4
  terrain_seed: 42
  terrain_slope_deg: 3.0           # 3° 线性下坡
```

> Perlin 噪声从 `x = 10 m` 处开始线性叠加斜坡（参见 [synthetic_sensors.py#L234](../../sim_holoocean/interfaces/synthetic_sensors.py)），所以前 10 m 是平地。

---

## 5. 关键 KPI

由 [`tools/analyze_bag.py`](../../tools/analyze_bag.py) 自动产出，目标对比表：

| 指标 | Baseline (CONSTANT) | Terrain Following | 期望差异 |
|------|---------------------|-------------------|----------|
| `seabed_clearance_mean_m` | 接近 `15 - constant_depth_m`（地形不影响目标） | 接近 `constant_depth_m`（即 ~3.0 m） | TF 明显更稳 |
| `seabed_clearance_min_m` | 在地形高点会跌入危险区（< 1.5 m 触发警告） | 应始终 > 1.5 m | TF 安全裕度大 |
| `seabed_clearance_std_m` | 大（深度恒定但海床起伏） | 小（跟随海床） | TF 显著更小 |
| `depth_error_rmse_m` | 小（恒深目标下） | 较大（目标随海床动） | 此项 baseline 更优属正常 |

**判定准则**：
- 修复成功 ⇔ TF 模式下 `seabed_clearance_mean_m ≈ 3.0 ± 0.5 m`，且 `seabed_clearance_min_m > 1.5 m`
- 若 TF 模式 clearance 仍接近 baseline（地形被忽略），多半是 altitude 链路没打通（详见 §7）

---

## 6. 验证清单（修复确认）

地形跟随依赖 4 个修复点全部生效。可逐项验证：

| # | 修复点 | 验证方式 |
|---|--------|---------|
| 1 | `mock_amd_server` 接入动态地形 | 实验运行中 `cat $AUV_DATA_ROOT/bags/<ts>/.../altitude` 应随 AUV 移动起伏；`grep terrain_height_at sim_holoocean/interfaces/mock_amd_server.py` 应有调用 |
| 2 | Zenoh 路径 altitude 透传 | `ros2 topic hz /auv/sensors/altitude` 应有数据（zenoh_json 后端时） |
| 3 | 前视声呐 forward_slope | `ros2 topic echo /auv/sensors/forward_sonar_slope` 应有非零值（在斜坡区域）；`terrain_debug` JSON 中 `slope_source` 在斜率非零时切换为 `"sonar"` |
| 4 | 端到端基准 | `bash scripts/run_terrain_benchmark.sh 60` 能完整跑过两个 phase 并出 analysis 目录 |

快速一行命令（静态检查全部 4 个修复落地）：

```bash
grep -n "terrain_height_at" sim_holoocean/interfaces/synthetic_sensors.py \
                            sim_holoocean/interfaces/mock_amd_server.py \
                            sim_holoocean/interfaces/holoocean_physics_bridge.py
grep -n "altitude_pub\|forward_sonar_pub" brain_linux/src/auv_bridge/auv_bridge/bridge_node.py
grep -n "/\*\*:" brain_linux/config/feature_flags_terrain.yaml
```

---

## 7. 已知问题与排查

### 7.1 行为树卡在 `StandbyCheck`

**症状**：`baseline_log.txt` 全程 `mode=IDLE | behavior=StandbyCheck | depth=0.00m`，AUV 从不移动。

**伴随日志**：
```
[decision_node] Mock AMD time timeout: 5.00s > 5.0s, falling back to system time
```

**根因**：决策节点没收到 `mock_amd_timestamp`，`StandbyCheck` 守护条件不通过。

**临时缓解**：`run_terrain_benchmark.sh` 已传 `--arbiter-profile`，确保仲裁器进入 AUTONOMOUS。如仍卡死：
1. `pkill -9 -f "auv_bridge|holoocean|mock_amd|zenoh|decision_node"` 清残留进程
2. 确认 `mock_amd_server.py` 正在发送 `mock_amd_timestamp` 字段（grep 日志中 telemetry 是否包含）
3. 重跑

### 7.2 zenoh_json_bridge_node 端口冲突

**症状**：
```
OSError: [Errno 98] Address already in use
```

**根因**：上次实验残留进程仍占用端口。

**修复**：
```bash
pkill -9 -f "zenoh_json_bridge_node|holoocean_physics_bridge|mock_amd_server"
ss -tlnp | grep -E "5000|7447|8765"   # 确认端口空闲
```

### 7.3 mcap 录制损坏（RecordLengthLimitExceeded）

**症状**：`analyze_bag.py` 失败，提示 mcap 截断。

**根因**：实验进程被 `SIGKILL` 而非 `SIGINT`，rosbag2 没机会写入 footer。

**修复**：[`scripts/start_experiment.sh#L176`](../../scripts/start_experiment.sh) 已经改成 `kill -INT` + `sleep 2`，新录制不再损坏。如遇旧 bag 损坏，使用 [`log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap`](../../log/experiments/benchmark_120s/) 作为已知完好替代。

### 7.4 `feature_flags_terrain.yaml` 不生效

**症状**：切换到 terrain phase，但日志显示 `depth_mode=CONSTANT`。

**根因**：YAML 缺少 `/**: ros__parameters:` 顶层包装，被 launch 系统忽略。

**修复**：参见 [§4.1](#41-feature_flags_terrainyaml) 当前文件已是正确格式，请勿移除外层包装。

### 7.5 `/auv_data` 路径无法移动 bag

**症状**：`mv /auv_data/bags/... results/...` 报 read-only。

**根因**：容器内 `/auv_data` 是只读挂载子树。

**修复**：脚本已改为**记录路径**（见 [§3.1](#31-一键基准) 的 `bag_path.txt` 机制），分析时按 `cat bag_path.txt` 取路径。

---

## 8. 开发者扩展点

如果你打算改地形参数或新增地形场景：

| 想做的事 | 改哪里 |
|---------|--------|
| 改海床起伏强度/波长 | [`bridge_params.yaml#digital_twin`](../../config/bridge_params.yaml) 中 `terrain_noise_*` |
| 新增地形 preset | 复制 `bridge_params.yaml` 为 `bridge_params_<scene>.yaml`，再在 `start_experiment.sh` 中加 `--bridge-config` 参数 |
| 改前瞻距离 | [`holoocean_physics_bridge.py`](../../sim_holoocean/interfaces/holoocean_physics_bridge.py) 中 `lookahead_m` |
| 改控制器响应 | [`terrain_engine.py`](../../brain_linux/src/auv_controller/auv_controller/terrain_engine.py) 的 `lookahead_time_s`（默认 2.0）和 `lpf_alpha`（默认 0.2） |
| 验证地形采样 | 直接调用 `VirtualEnvironment(cfg).terrain_height_at(x, y)` 在 Python 中预览 |

---

## 9. 相关文档

- [05_benchmarks.md](05_benchmarks.md) — 全部基准测试的统一契约
- [02_experiment_runner.md](02_experiment_runner.md) — `start_experiment.sh` 完整参数
- [04_rosbag_analysis.md](04_rosbag_analysis.md) — `analyze_bag.py` 用法
- [09_config_reference.md](09_config_reference.md) — 配置文件速查
- [.trae/documents/terrain_following_fix_plan.md](../../.trae/documents/terrain_following_fix_plan.md) — 4 个修复点的设计与实现细节
