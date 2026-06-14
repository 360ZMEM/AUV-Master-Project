# 地形跟随论文图像生成指引

**日期**: 2026-06-10  
**定位**: 给毕业设计/论文中“地形跟随控制实验”提供可直接引用的图像清单、caption、生成依据、分析脚本位置和 benchmark 命令契约。  
**图像目录**: `docs/thesis/figures/terrain_following/`  
**统一生成脚本**: `tools/plot_terrain_following_figures.py`

---

## 1. 统一生成命令

所有地形跟随论文图像统一由以下脚本生成：

```bash
python3 tools/plot_terrain_following_figures.py
```

可选参数：

```bash
python3 tools/plot_terrain_following_figures.py \
  --main-result results/control/terrain_following_20260610_175154 \
  --ablation-summary results/control/pid_terrain_ablation_20260610_summary.csv \
  --terrain-config config/bridge_params.protocol_udp.pvs.terrain.yaml \
  --output-dir docs/thesis/figures/terrain_following \
  --target-clearance-m 3.0
```

说明：

- `--main-result` 指向 PID/MPC 四组对比结果目录，默认使用 `results/control/terrain_following_20260610_175154`。
- `--ablation-summary` 指向 low/mid/high 三档 PID terrain 消融汇总，默认使用 `results/control/pid_terrain_ablation_20260610_summary.csv`。
- `--terrain-config` 用于 3D 图的确定性地形重建，默认使用 `config/bridge_params.protocol_udp.pvs.terrain.yaml`。
- 若 bag 中存在 `/auv/visual/seabed_cloud` 或 `/auv/visual/seabed_cloud_throttled` 点云，3D 图优先使用 bag 点云；若 bag 未记录点云，则根据 bridge YAML 中 `digital_twin` 参数离线重建地形曲面。

---

## 2. 已生成图像清单

 6 组论文图像，每组均提供 `png` 和 `pdf` 两种格式。

| 图号建议 | 文件名 stem | 推荐章节 | 数据源 | 分析脚本位置 |
|---|---|---|---|---|
| Fig. 5-1 | `terrain_clearance_rmse_pid_mpc` | 控制算法对比实验 | `results/control/terrain_following_20260610_175154/*/analysis/summary_statistics.csv` | `tools/plot_terrain_following_figures.py::plot_clearance_rmse` |
| Fig. 5-2 | `terrain_clearance_safety_margin` | 安全性与地形跟随性能分析 | 同 Fig. 5-1 | `tools/plot_terrain_following_figures.py::plot_clearance_safety` |
| Fig. 5-3 | `pid_terrain_low_mid_high_ablation` | 地形强度消融实验 | `results/control/pid_terrain_ablation_20260610_summary.csv` | `tools/plot_terrain_following_figures.py::plot_ablation` |
| Fig. 5-4 | `terrain_benchmark_command_contract` | 实验设计/SOP 附图 | `scripts/run_terrain_benchmark.sh` | `tools/plot_terrain_following_figures.py::plot_command_contract` |
| Fig. 5-5 | `terrain_tz_tracking_pid_mpc` | 深度跟踪动态过程分析 | `pid_terrain` 与 `mpc_terrain` 的 MCAP bag diagnostics | `tools/plot_terrain_following_figures.py::plot_tz_tracking` |
| Fig. 5-6 | `terrain_3d_pid_terrain_trajectory` | 三维地形跟随效果展示 | `pid_terrain` bag trajectory + bag point cloud 或 deterministic terrain YAML | `tools/plot_terrain_following_figures.py::plot_3d_terrain_trajectory` |

输出文件：

```text
docs/thesis/figures/terrain_following/
 terrain_clearance_rmse_pid_mpc.png
 terrain_clearance_rmse_pid_mpc.pdf
 terrain_clearance_safety_margin.png
 terrain_clearance_safety_margin.pdf
 pid_terrain_low_mid_high_ablation.png
 pid_terrain_low_mid_high_ablation.pdf
 terrain_benchmark_command_contract.png
 terrain_benchmark_command_contract.pdf
 terrain_tz_tracking_pid_mpc.png
 terrain_tz_tracking_pid_mpc.pdf
 terrain_3d_pid_terrain_trajectory.png
 terrain_3d_pid_terrain_trajectory.pdf
```

---

## 3. 图像说明与 Caption

### 3.1 PID/MPC 四组 RMSE 对比

**文件**: `terrain_clearance_rmse_pid_mpc.pdf/png`  
**分析脚本位置**: `tools/plot_terrain_following_figures.py::plot_clearance_rmse`  
**数据源**: `results/control/terrain_following_20260610_175154/*/analysis/summary_statistics.csv`

 caption：

> 图 X 地形跟随任务中 PID 与 MPC 在固定深度和地形跟随模式下的离底高度 RMSE 对比。结果表明，固定深度 baseline 无法稳定保持 3m 离底高度；terrain-following 模式显著降低离底误差。其中 PID terrain 的 RMSE 为 0.175m，是当前最优方案；MPC terrain 相比 MPC baseline 有改善，但仍弱于 PID terrain。

论文中应强调：

- 主指标是 `seabed_clearance_rmse_to_3m`。
- `depth_error_rmse_m` 不作为 terrain-following 主指标，因为地形跟随目标深度随海底起伏动态变化。
- MPC 在本文中是 guidance-level reference generator，不是底层舵面控制器。

### 3.2 离底高度安全裕度图

**文件**: `terrain_clearance_safety_margin.pdf/png`  
**分析脚本位置**: `tools/plot_terrain_following_figures.py::plot_clearance_safety`  
**数据源**: `results/control/terrain_following_20260610_175154/*/analysis/summary_statistics.csv`

 caption：

> 图 X 地形跟随任务中四组控制策略的离底高度统计分布。圆点和误差棒表示离底高度均值及标准差，倒三角表示最小离底高度，虚线表示 3m 目标离底高度，点线表示 1.5m 安全阈值。所有策略均未触发安全违规，但 PID terrain 最接近目标离底高度且波动最小。

论文中应强调：

- 安全结论：四组 `clearance < 1.5m ratio = 0`。
- 性能结论：PID terrain 最贴近 3m 目标离底高度。
- baseline 安全但不贴底，不能说明地形跟随成功。

### 3.3 Low/Mid/High 地形消融图

**文件**: `pid_terrain_low_mid_high_ablation.pdf/png`  
**分析脚本位置**: `tools/plot_terrain_following_figures.py::plot_ablation`  
**数据源**: `results/control/pid_terrain_ablation_20260610_summary.csv`

 caption：

> 图 X PID/PVS 地形跟随控制器在 low、mid、high 三档地形强度下的离底高度保持性能。三档实验均无小于 1.5m 的安全违规，且离底高度 RMSE 均低于 0.18m，说明所设计的地形跟随链路在不同地形强度下具有稳定性和安全裕度。

消融结果：

| terrain | RMSE to 3m | mean | std | min | <1.5m ratio |
|---|---:|---:|---:|---:|---:|
| low | 0.0709m | 3.0218m | 0.0675m | 2.8612m | 0.0 |
| mid | 0.1735m | 3.1735m | 0.0028m | 3.1634m | 0.0 |
| high | 0.0586m | 2.9932m | 0.0582m | 2.8765m | 0.0 |

### 3.4 命令契约图

**文件**: `terrain_benchmark_command_contract.pdf/png`  
**分析脚本位置**: `tools/plot_terrain_following_figures.py::plot_command_contract`  
**数据源**: `scripts/run_terrain_benchmark.sh`

 caption：

> 图 X 地形跟随 benchmark 的命令参数契约。脚本通过 controller、mode 和 terrain level 三个维度组合生成实验矩阵，并将每个 phase 的 bag、summary statistics 和图像结果落盘到 `results/control/terrain_following_<timestamp>/`。

### 3.5 2D t-z 深度跟踪曲线

**文件**: `terrain_tz_tracking_pid_mpc.pdf/png`  
**分析脚本位置**: `tools/plot_terrain_following_figures.py::plot_tz_tracking`  
**数据源**: `results/control/terrain_following_20260610_175154/pid_terrain/bag_path.txt` 与 `results/control/terrain_following_20260610_175154/mpc_terrain/bag_path.txt`

 caption：

> 图 X PID terrain 与 MPC terrain 在地形跟随任务中的 `t-z` 深度跟踪曲线。横轴为实验时间，纵轴为向下为正的深度，棕色曲线表示海底深度，绿色虚线表示由 3m 目标离底高度换算得到的目标深度，蓝色曲线表示 AUV 实际深度。结果显示 PID terrain 能更稳定地贴近动态目标深度，而 MPC terrain 存在更明显的参考跟踪滞后和误差。

坐标说明：

- 图中 `depth` 使用 NED 约定，向下为正。
- `seabed_depth = depth + seabed_clearance`。
- `target_depth = seabed_depth - target_clearance_m`。
- 绘图时反转 y 轴，使“更深”显示在图像下方，符合深度曲线直觉。

### 3.6 3D 地形曲面与 AUV 轨迹图

**文件**: `terrain_3d_pid_terrain_trajectory.pdf/png`  
**分析脚本位置**: `tools/plot_terrain_following_figures.py::plot_3d_terrain_trajectory`  
**数据源**: `results/control/terrain_following_20260610_175154/pid_terrain/bag_path.txt` + `config/bridge_params.protocol_udp.pvs.terrain.yaml`

 caption：

> 图 X PID terrain 实验中的三维地形曲面与 AUV 轨迹。蓝色曲线表示 AUV 在显示坐标系下的三维运动轨迹，绿色虚线表示基于 3m 目标离底高度得到的目标深度轨迹，海底曲面颜色表示向下为正的海底深度。由于当前 bag 未记录可直接读取的 seabed point cloud，本图根据完整 bridge 配置中的 deterministic terrain 参数离线重建海底曲面，并叠加 bag 中记录的 AUV 轨迹。

可追溯性说明：

- 轨迹来自 MCAP 中 `/auv/state/filtered`。
- 若 MCAP 中存在 `/auv/visual/seabed_cloud` 或 `/auv/visual/seabed_cloud_throttled`，脚本优先使用 bag point cloud。
- 当前正式结果 bag 未读到 point cloud，因此脚本读取 `config/bridge_params.protocol_udp.pvs.terrain.yaml` 的 `digital_twin` 参数。
- 地形重建公式复用 `sim_holoocean/interfaces/synthetic_sensors.py::berlin_noise_2d`，与仿真侧 deterministic terrain 生成逻辑一致。

---

## 4. Benchmark 命令契约

`run_terrain_benchmark.sh` 当前支持三档地形作为第 4 个位置参数：

```bash
bash scripts/run_terrain_benchmark.sh [DURATION_SECONDS] [pid|mpc|both] [baseline|terrain|both_modes] [default|low|mid|high|<bridge_cfg.yaml>]
```

参数说明：

| 参数 | 可选值 | 默认值 | 说明 |
|---|---|---|---|
| `DURATION_SECONDS` | 任意正数 | `120` | 每个 phase 的录包时长 |
| controller | `pid` / `mpc` / `both` | `both` | 使用 PID、MPC 或两者都跑 |
| mode | `baseline` / `terrain` / `both_modes` / `both` | `both_modes` | 固定深度、地形跟随或两者都跑 |
| terrain level | `default` / `low` / `mid` / `high` / `<bridge_cfg.yaml>` | `default` | 选择地形强度或自定义完整 bridge 配置 |

地形档位映射：

| terrain level | 配置文件 | 说明 |
|---|---|---|
| `default` | `config/bridge_params.protocol_udp.pvs.terrain.yaml` | 当前主 benchmark 配置，等价于论文主设置 |
| `low` | `config/bridge_params.protocol_udp.pvs.terrain_low.yaml` | 平缓地形 |
| `mid` | `config/bridge_params.protocol_udp.pvs.terrain_mid.yaml` | 中等起伏，论文主 ablation 档 |
| `high` | `config/bridge_params.protocol_udp.pvs.terrain_high.yaml` | 高起伏压力测试 |
| `<bridge_cfg.yaml>` | 任意完整 YAML | 必须是完整 bridge 配置，不是仅含 `digital_twin` 的 overlay |

环境变量覆盖规则：

```bash
TERRAIN_BRIDGE_CFG=/abs/path/to/bridge.yaml \
  bash scripts/run_terrain_benchmark.sh 60 pid terrain
```

说明：

- `TERRAIN_BRIDGE_CFG` 保留向后兼容，并且优先于第 4 个位置参数。
- 自定义 `<bridge_cfg.yaml>` 可以是绝对路径，也可以是相对于项目根目录的路径。
- 脚本会检查最终 bridge config 是否存在；不存在则退出并提示错误。

---

## 5. 推荐论文实验命令

### 5.1 正式 PID/MPC 四组对比

```bash
bash scripts/preflight_clean.sh --quiet
bash scripts/run_terrain_benchmark.sh 60 both both_modes default
```

预期输出结构：

```text
results/control/terrain_following_<TS>/
 pid_baseline/
 pid_terrain/
 mpc_baseline/
 mpc_terrain/
```

### 5.2 PID terrain 三档地形消融

```bash
bash scripts/preflight_clean.sh --quiet
bash scripts/run_terrain_benchmark.sh 60 pid terrain low
bash scripts/preflight_clean.sh --quiet
bash scripts/run_terrain_benchmark.sh 60 pid terrain mid
bash scripts/preflight_clean.sh --quiet
bash scripts/run_terrain_benchmark.sh 60 pid terrain high
```

 smoke：

```bash
bash scripts/run_terrain_benchmark.sh 30 pid terrain low
bash scripts/run_terrain_benchmark.sh 30 pid terrain mid
bash scripts/run_terrain_benchmark.sh 30 pid terrain high
```

### 5.3 MPC 单独复核

```bash
bash scripts/preflight_clean.sh --quiet
bash scripts/run_terrain_benchmark.sh 60 mpc terrain default
```

MPC 作为对照算法，不作为 terrain-following 主控制方案。主线采用 PID/PVS terrain，因为当前实验表明它在离底高度 RMSE、实时稳定性和工程可复现性上更适合作为毕设主结果。

---

## 6. 复现检查

已执行并通过：

```bash
python3 -m py_compile tools/plot_terrain_following_figures.py
python3 tools/plot_terrain_following_figures.py
```

验证结果：

- `tools/plot_terrain_following_figures.py` 无语法错误。
- 6 组图像均已生成 `png` 和 `pdf`。
- 3D 图在 bag 无 point cloud 的情况下可通过 `--terrain-config` 重建地形并正常输出。
