# 完整 P1 与代理电缆场景实验计划

## Summary

本轮目标分两类推进：

1. **第一类缺失实验：完整 P1 补齐**  
   以过程导向为主，补齐已有软件实验链路中仍缺的统计、控制侧与不确定性量化证据，包括 terrain PID 多 seed、H1 solve time 重跑、DVL/chaos 控制侧聚合、NIS/R 自适应触发率聚合。

2. **第二类缺失实验：可运行代理电缆环境**  
   不做大规模后端重构，优先基于现有 `bridge_params.protocol_udp.pvs.terrain_*.yaml`、`cable_path`、`digital_twin`、`perception`、`pvs.current_speed_mps` 和 `start_experiment.sh --bridge-cfg` 创建可运行代理场景。第一步只建 3 个核心场景并做低成本 smoke：`cable_s_curve_proxy`、`cable_slope_crossing_proxy`、`combined_cable_extreme_proxy`。通过后再扩展到 6 个全量场景。

用户已拍板：

- 第一类范围：**完整 P1**
- 第二类路线：**可运行代理**
- 新场景数量：**2 步推进，先 3 个核心，后 6 个**
- 第一轮实验预算：**低成本，30s × seed0 smoke**

## Current State Analysis

### 已有实验与工具

- `tools/run_thesis_sweep.py`
  - 已支持 `--scenarios`、`--seeds`、`--mpc-modes`、`--duration`、`--param-grid`。
  - 场景解析固定走 `scenarios/scenario_<id>.yaml` 或显式 YAML 路径。
  - 可通过 `--start-arg` 透传参数给 `scripts/start_experiment.sh`，但同一次 sweep 的 `--start-arg` 对所有场景共享，不适合逐场景绑定不同 `--bridge-cfg`。

- `scripts/start_experiment.sh`
  - 支持 `--scenario PATH`、`--seed N`、`--mpc-mode MODE`、`--bridge-cfg PATH`。
  - 会把 `AUV_SCENARIO_FILE`、`AUV_SCENARIO_SEED`、`AUV_MPC_MODE` 透传给运行时。

- `scripts/run_terrain_benchmark.sh`
  - 支持 `bash scripts/run_terrain_benchmark.sh 30 pid terrain low|mid|high|<bridge_cfg.yaml>`。
  - 当前 terrain low/mid/high 只有 `results/control/pid_terrain_ablation_20260610_summary.csv`，每档 n=1。
  - bridge YAML 中 `digital_twin.terrain_seed` 固定为 42，因此 3 seed 需要生成临时 bridge config 或新增种子化配置。

- `tools/aggregate_control_metrics.py`
  - 已能从 sweep `results.csv` 或单 bag 聚合 lateral RMSE、solve time、fallback rate、control rate RMS、安全违规率。
  - H1 旧 bag 的 `solve_time_ms` 为 `nan`，原因是旧 bag 缺 debug payload 字段；后续重跑可补。

- `tools/uncertainty_metrics.py`
  - 已能对单个 bag 输出 `uncertainty_timeseries.csv`、NIS 图、P trace 图、`r_scale`。
  - 当前缺批量聚合入口，不能直接对 sweep 的 24 个 P1 bag 产出 scenario/mode 级 mean±std 表。

- `docs/thesis/paper/pvs_extreme_cable_scenarios.md`
  - 已有 6 类极端电缆巡检场景设计。
  - 目前还没有对应可运行 YAML/config 和 sweep 输出。

### 现有可运行环境表达能力

- `config/bridge_params.protocol_udp.pvs.terrain_low.yaml` / `mid` / `high`
  - 已包含 `digital_twin`、`cable_path.points_ned`、`perception.noise`、`perception.sonar`、`pvs.current_speed_mps`。
  - 这些字段足以做“代理电缆场景”：改变 cable polyline、地形强度、坡度、声呐噪声、磁噪声、流速。

- `scenarios/scenario_*.yaml`
  - 目前 9 个场景覆盖 baseline、DVL dropout、mag distortion、sonar clutter、combined stress。
  - 这些 scenario YAML 更偏 chaos/perception/flow，不表达复杂 cable path。

### 主要限制

- 现有 `run_thesis_sweep.py` 不适合一组场景绑定不同 `--bridge-cfg`，因此代理电缆环境需要一个新的轻量 runner，直接调用 `start_experiment.sh`。
- 代理场景能支撑“控制性能与稳定性”的 smoke 证据，但不能声称为完整海缆巡检海试。
- 第一轮代理场景只跑 seed0 smoke，不进入 mean±std 主表；通过后再扩展 seed。

## Proposed Changes

### 1. 新增 terrain PID 多 seed 执行与聚合工具

**文件**：`tools/run_terrain_pid_seed_sweep.py`

**目的**：把 terrain low/mid/high 从 n=1 补到 n=3，并保留每次运行的配置、bag、分析输出和聚合表。

**实现方式**：

- 读取基础 bridge config：
  - `config/bridge_params.protocol_udp.pvs.terrain_low.yaml`
  - `config/bridge_params.protocol_udp.pvs.terrain_mid.yaml`
  - `config/bridge_params.protocol_udp.pvs.terrain_high.yaml`
- 对每个 terrain 档位和 seed 生成临时 bridge config 到：
  - `results/control/terrain_pid_seed_sweep_<timestamp>/configs/<terrain>_seed<seed>.yaml`
- 只改临时 config 中的：
  - `digital_twin.terrain_seed = seed`
  - `stage.name = <原名>_seed<seed>`
- 逐个调用：

```bash
bash scripts/run_terrain_benchmark.sh 30 pid terrain <generated_bridge_cfg>
```

- 从每个运行的 `pid_terrain/analysis/summary_statistics.csv` 或现有 terrain analysis 输出中抽取：
  - `seabed_clearance_rmse_to_3m`
  - `seabed_clearance_mean_m`
  - `seabed_clearance_std_m`
  - `seabed_clearance_min_m`
  - `seabed_clearance_safety_violation_ratio_1p5m`
  - duration / samples / bag path
- 输出：
  - `results/control/terrain_pid_seed_sweep_<timestamp>/results.csv`
  - `results/control/terrain_pid_seed_sweep_<timestamp>/summary_by_terrain.csv`
  - `results/control/terrain_pid_seed_sweep_<timestamp>/aggregate_report.md`

**验收**：

- low/mid/high × seeds 0,1,2 共 9 行 results。
- 每档至少 2/3 ok；理想 3/3 ok。
- 每档输出 mean±std，可回填论文 5.5.3。

### 2. H1 UA-MPC solve time 补录

**不新增代码，执行现有命令**：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline,dvl_dropout_60,combined_stress \
  --seeds 0,1,2 \
  --mpc-modes baseline,ua \
  --duration 60 \
  --label h1_uampc_main_ablation_solvetime
```

随后聚合定位指标：

```bash
python3 tools/aggregate_thesis_sweep.py \
  --input log/thesis_sweep/<run>/results.csv \
  --output-dir results/thesis_sweep_aggregates/<run>
```

再聚合控制指标：

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/thesis_sweep/<run>/results.csv \
  --output-dir results/control_aggregates/<run>
```

**验收**：

- 18/18 或至少 15/18 ok。
- `control_summary_by_scenario_mode.csv` 中 `mpc_solve_time_mean_ms_available_count > 0`。
- 若 solve time 仍为 `nan`，立刻检查 `/auv/controller/debug` payload，而不是继续扩大实验。

### 3. DVL/chaos 控制侧聚合

**不优先重跑，先复用已有 P1 bag**：

输入：

```text
log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv
```

命令：

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv \
  --output-dir results/control_aggregates/20260612_170618_p1_sensor_3seed
```

**验收**：

- 8 场景 × 3 seed 的 control rows 能生成。
- 可用指标至少包含 lateral RMSE、fallback rate、control rate RMS、安全违规率。
- solve time 若为 `nan`，按旧 bag 字段缺失处理，在报告中标注，不作为失败。

### 4. 新增 NIS/R 自适应触发率批量聚合

**文件**：`tools/aggregate_uncertainty_metrics.py`

**目的**：把 `tools/uncertainty_metrics.py` 的单 bag 输出扩展成 sweep 级别聚合，支撑完整 P1 的不确定性量化表。

**输入**：

```bash
python3 tools/aggregate_uncertainty_metrics.py \
  --sweep-results log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv \
  --output-dir results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed
```

**实现方式**：

- 读取 sweep `results.csv`，仅处理 `status=ok` 且 `mcap` 存在的行。
- 每行调用：

```bash
python3 tools/uncertainty_metrics.py \
  --input <mcap> \
  --output-dir <output-dir>/per_run/<scenario>__seed<seed>__<mode>
```

- 解析 `uncertainty_timeseries.csv`，计算：
  - `nis_real_mean`
  - `nis_real_p95`
  - `nis_dvl_proxy_mean`
  - `nis_depth_proxy_mean`
  - `r_scale_mean`
  - `r_scale_max`
  - `r_scale_trigger_ratio`：`r_scale > 1.0 + 1e-6` 的比例
  - `p_trace_xy_mean`
  - `p_trace_z_mean`
- 输出：
  - `per_run_uncertainty_results.csv`
  - `summary_by_scenario_mode.csv`
  - `aggregate_report.md`

**验收**：

- P1 24 个 bag 能批量处理；失败行写明原因，不中断全局。
- 每个 scenario/mode 输出 mean±std。
- 可回填论文 3.4/5.5 的 NIS/R 表，且清楚标注 NIS proxy 与 real NIS 的区别。

### 5. 创建 3 个核心代理电缆场景配置

**文件**：

- `config/bridge_params.protocol_udp.pvs.cable_s_curve_proxy.yaml`
- `config/bridge_params.protocol_udp.pvs.cable_slope_crossing_proxy.yaml`
- `config/bridge_params.protocol_udp.pvs.combined_cable_extreme_proxy.yaml`

**基线来源**：

- 从 `config/bridge_params.protocol_udp.pvs.terrain_mid.yaml` 复制结构。

**场景 1：`cable_s_curve_proxy`**

- `digital_twin.terrain_noise_amplitude_m = 1.0`
- `digital_twin.terrain_slope_deg = 1.5`
- `pvs.current_speed_mps = 0.2`
- `pvs.current_direction_deg = 90.0`
- `cable_path.points_ned` 设为短波长 S 弯 polyline，例如：

```yaml
cable_path:
  points_ned:
    - [0.0, 0.0, 12.0]
    - [8.0, 4.0, 12.0]
    - [16.0, -4.0, 12.0]
    - [24.0, 4.0, 12.0]
    - [32.0, -4.0, 12.0]
    - [40.0, 0.0, 12.0]
```

**场景 2：`cable_slope_crossing_proxy`**

- `digital_twin.terrain_noise_amplitude_m = 2.0`
- `digital_twin.terrain_slope_deg = 5.0`
- `pvs.current_speed_mps = 0.2`
- `pvs.current_direction_deg = 45.0`
- `cable_path.points_ned` 设为带深度变化的坡面横穿：

```yaml
cable_path:
  points_ned:
    - [0.0, -8.0, 11.5]
    - [10.0, -4.0, 12.0]
    - [20.0, 0.0, 12.8]
    - [30.0, 4.0, 13.6]
    - [40.0, 8.0, 14.2]
```

**场景 3：`combined_cable_extreme_proxy`**

- `digital_twin.terrain_noise_amplitude_m = 3.0`
- `digital_twin.terrain_noise_scale_m = 4.5`
- `digital_twin.terrain_noise_octaves = 5`
- `digital_twin.terrain_slope_deg = 6.0`
- `pvs.current_speed_mps = 0.4`
- `pvs.current_direction_deg = 90.0`
- `perception.noise.magnetic_sigma = [5.0e-8, 5.0e-8, 5.0e-8]`
- `perception.sonar.base_noise_sigma = 0.05`
- `perception.sonar.peak_gain = 0.5`
- `cable_path.points_ned` 设为大曲率 + 深度变化：

```yaml
cable_path:
  points_ned:
    - [0.0, 0.0, 11.5]
    - [10.0, 6.0, 12.0]
    - [20.0, 8.0, 13.0]
    - [26.0, 0.0, 13.8]
    - [20.0, -8.0, 14.0]
    - [8.0, -8.0, 13.2]
    - [0.0, 0.0, 12.4]
```

**说明**：

- 这三个 config 是“可运行代理场景”，不是完整后端语义扩展。
- 论文表述必须写成“复杂电缆环境代理场景”或“高保真仿真增强”，不能写成真实海试等价。

### 6. 新增代理电缆场景低成本 runner

**文件**：`tools/run_proxy_cable_sweep.py`

**目的**：解决 `run_thesis_sweep.py` 无法逐场景绑定不同 `--bridge-cfg` 的问题。

**CLI**：

```bash
python3 tools/run_proxy_cable_sweep.py \
  --scenarios cable_s_curve_proxy,cable_slope_crossing_proxy,combined_cable_extreme_proxy \
  --seeds 0 \
  --mpc-modes baseline,ua \
  --duration 30 \
  --label cable_proxy_smoke
```

**内部映射**：

- `cable_s_curve_proxy`：
  - bridge cfg：`config/bridge_params.protocol_udp.pvs.cable_s_curve_proxy.yaml`
  - thesis scenario：`scenarios/scenario_baseline.yaml`
- `cable_slope_crossing_proxy`：
  - bridge cfg：`config/bridge_params.protocol_udp.pvs.cable_slope_crossing_proxy.yaml`
  - thesis scenario：`scenarios/scenario_baseline.yaml`
- `combined_cable_extreme_proxy`：
  - bridge cfg：`config/bridge_params.protocol_udp.pvs.combined_cable_extreme_proxy.yaml`
  - thesis scenario：`scenarios/scenario_combined_stress.yaml`

**每个 run 调用**：

```bash
bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --bridge-cfg <bridge_cfg> \
  --scenario <scenario_yaml> \
  --seed <seed> \
  --mpc-mode <mode> \
  --record-format mcap \
  --duration <duration> \
  --arbiter-profile \
  --auto-activate
```

**输出**：

```text
log/proxy_cable_sweep/<timestamp>_<label>/
  manifest.json
  results.csv
  failures.log
  logs/*.log
```

`results.csv` 字段：

- `scenario`
- `bridge_cfg`
- `thesis_scenario`
- `seed`
- `mpc_mode`
- `status`
- `duration_s_actual`
- `run_dir`
- `mcap`
- `error`

**验收**：

- 3 场景 × 1 seed × 2 mode = 6 rows。
- 至少 4/6 ok；若低于 4/6，停止扩展场景，先修命令链。
- 每个 ok run 都有非空 mcap。

### 7. 代理场景控制侧聚合

**命令**：

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/proxy_cable_sweep/<run>/results.csv \
  --output-dir results/control_aggregates/<run>
```

**验收**：

- 每个代理场景按 baseline/ua 输出：
  - lateral RMSE
  - solve time
  - fallback rate
  - control rate RMS
  - safety violation
- 这是 smoke 级控制稳定性结果，不写 mean±std。

### 8. 文档回填与状态更新

**文件**：

- `docs/experiment/experiment_gap_conduct_plan.md`
- `docs/thesis/paper/experiment_gap_and_next_plan.md`
- `docs/thesis/paper/05_experiments_and_discussion.md`
- 如 05 主文档仍因缓存只到 5.5.3，则同步更新：
  - `docs/thesis/paper/05_experiments_and_discussion_continued.md`

**更新内容**：

- 第一类：
  - terrain PID 3 seed 聚合结果。
  - H1 solve time 重跑结果。
  - DVL/chaos 控制侧聚合结果。
  - NIS/R 自适应触发率聚合结果。
- 第二类：
  - 新增 3 个代理电缆场景的设计、命令、数据源、smoke 成功率。
  - 明确“代理场景”“低成本 smoke”“尚未进入 mean±std”的边界。
- `experiment_gap_and_next_plan.md`：
  - 将完整 P1 已完成项标为完成。
  - 将第二类改为“代理场景第一步已完成 / 全量 6 场景待扩展”。

## Assumptions & Decisions

- terrain 多 seed 通过修改临时 bridge config 中的 `digital_twin.terrain_seed` 实现，不修改原始 low/mid/high YAML。
- 代理电缆场景不扩展 PVS 后端，只利用现有 config 字段表达复杂 cable path、terrain、flow、perception。
- 代理场景第一轮只跑 `seed=0`、`duration=30`、`mpc_modes=baseline,ua`，共 6 run。
- 第二步 6 场景扩展不在第一轮 smoke 之前执行；如果 3 个核心场景 smoke 失败，不继续扩展。
- solve time 的验收以新 H1 重跑 bag 中 `/auv/controller/debug` 的 `solve_time_ms` 可解析为准。
- NIS/R 批量聚合优先使用已有 P1 24 个 bag，不先重跑。
- 文档写法继续保持论文详细风格，但所有 smoke / n=1 / proxy 场景必须显式标注边界。

## Verification Steps

### 静态检查

```bash
python3 -m py_compile tools/run_terrain_pid_seed_sweep.py
python3 -m py_compile tools/aggregate_uncertainty_metrics.py
python3 -m py_compile tools/run_proxy_cable_sweep.py
```

### 第一类验证

```bash
python3 tools/run_terrain_pid_seed_sweep.py \
  --terrains low,mid,high \
  --seeds 0,1,2 \
  --duration 30 \
  --label terrain_pid_3seed
```

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline,dvl_dropout_60,combined_stress \
  --seeds 0,1,2 \
  --mpc-modes baseline,ua \
  --duration 60 \
  --label h1_uampc_main_ablation_solvetime
```

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/thesis_sweep/<h1_run>/results.csv \
  --output-dir results/control_aggregates/<h1_run>
```

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv \
  --output-dir results/control_aggregates/20260612_170618_p1_sensor_3seed
```

```bash
python3 tools/aggregate_uncertainty_metrics.py \
  --sweep-results log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv \
  --output-dir results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed
```

### 第二类验证

```bash
python3 tools/run_proxy_cable_sweep.py \
  --scenarios cable_s_curve_proxy,cable_slope_crossing_proxy,combined_cable_extreme_proxy \
  --seeds 0 \
  --mpc-modes baseline,ua \
  --duration 30 \
  --label cable_proxy_smoke
```

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/proxy_cable_sweep/<run>/results.csv \
  --output-dir results/control_aggregates/<run>
```

### 文档验收

- `docs/experiment/experiment_gap_conduct_plan.md` 有每组命令、输出路径和结果表。
- `docs/thesis/paper/05_experiments_and_discussion.md` 或续写文件包含第一类完整 P1 和第二类代理场景 smoke 的结果。
- `docs/thesis/paper/experiment_gap_and_next_plan.md` 状态与实际结果一致。
- 所有 `n=1`、`smoke`、`proxy`、`solve_time nan` 或失败项均明确标注，不混入主结论。
