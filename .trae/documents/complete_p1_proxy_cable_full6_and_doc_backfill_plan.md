# 完整 P1、代理电缆全量场景与论文回填计划

## Summary

本计划承接已经完成的“完整 P1 + 3 个核心代理电缆场景 smoke”工作，下一步目标分为两条线：

1. **第一类缺失实验闭环**：以过程导向补齐记录和论文证据链。重点不是继续扩大实验，而是把已经生成的 terrain PID 多 seed、P1 控制侧聚合、P1 NIS/R 聚合、H1 solve-time 重跑、代理电缆 smoke 等结果回填到实验 conduct plan、gap plan 和论文第 5 章。
2. **第二类多样环境扩展**：在现有 3 个代理电缆场景基础上，规划并实现 6 个全量代理电缆场景，继续保持低成本、可运行、可回滚。第一轮只跑 `30s x seed0 x baseline/ua` smoke，不把 n=1 结果写成统计结论。

用户已拍板：

- `docs/thesis/paper/05_experiments_and_discussion.md` 的处理方式：**两者都做**，即重建/新建 5.5.3 之后续写文件，同时对主文档做最小清理和链接说明。
- 第二类代理电缆环境：**规划扩展到 6 个全量场景**，但仍以低成本 smoke 起步。

## Current State Analysis

### 已完成且可引用的新增工具和配置

- `tools/run_terrain_pid_seed_sweep.py`
  - 已支持 `--terrains`、`--seeds`、`--duration`、`--label`、`--bag-finalize-s`。
  - 会基于 `config/bridge_params.protocol_udp.pvs.terrain_{low,mid,high}.yaml` 生成临时 seed config，并调用 `scripts/run_terrain_benchmark.sh`。

- `tools/aggregate_uncertainty_metrics.py`
  - 已支持从 sweep `results.csv` 批量调用 `tools/uncertainty_metrics.py`。
  - 已输出 P1 的 `per_run_uncertainty_results.csv`、`summary_by_scenario_mode.csv` 和 `aggregate_report.md`。

- `tools/run_proxy_cable_sweep.py`
  - 已支持 3 个核心代理场景：
    - `cable_s_curve_proxy`
    - `cable_slope_crossing_proxy`
    - `combined_cable_extreme_proxy`
  - 每个场景能绑定独立 `--bridge-cfg` 和 `--scenario`，弥补 `tools/run_thesis_sweep.py` 同一 sweep 不能逐场景切换 bridge config 的限制。

- 已有 3 个代理电缆 bridge config：
  - `config/bridge_params.protocol_udp.pvs.cable_s_curve_proxy.yaml`
  - `config/bridge_params.protocol_udp.pvs.cable_slope_crossing_proxy.yaml`
  - `config/bridge_params.protocol_udp.pvs.combined_cable_extreme_proxy.yaml`

### 已完成且可引用的结果路径

- Terrain PID 3 seed 主跑：
  - `results/control/terrain_pid_seed_sweep_20260613_162512_terrain_pid_3seed/`
  - 注意：该主跑中 low/mid 只有 1/3 ok，high 为 3/3 ok。

- Terrain retry：
  - `results/control/terrain_pid_seed_sweep_20260613_165856_terrain_pid_low_retry/`
  - `results/control/terrain_pid_seed_sweep_20260613_170630_terrain_pid_mid_retry/`
  - 文档回填时需要把主跑和 retry 合并叙述，不能只引用主跑 summary 误写为 low/mid 3/3。

- P1 sensor/chaos 3 seed：
  - `log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv`
  - `results/thesis_sweep_aggregates/20260612_170618_p1_sensor_3seed/`

- P1 控制侧聚合：
  - `results/control_aggregates/20260612_170618_p1_sensor_3seed/control_summary_by_scenario_mode.csv`
  - `results/control_aggregates/20260612_170618_p1_sensor_3seed/control_aggregate_report.md`

- P1 NIS/R 聚合：
  - `results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/summary_by_scenario_mode.csv`
  - `results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/aggregate_report.md`

- 3 个核心代理电缆 smoke：
  - `log/proxy_cable_sweep/20260613_171423_cable_proxy_smoke/results.csv`
  - `results/control_aggregates/20260613_171423_cable_proxy_smoke/control_summary_by_scenario_mode.csv`
  - 初次聚合中 `cable_slope_crossing_proxy + ua` 为 0/1，需要合并 retry。

- 代理电缆 UA retry：
  - `log/proxy_cable_sweep/20260613_180210_cable_slope_crossing_ua_retry/results.csv`
  - `results/control_aggregates/20260613_180210_cable_slope_crossing_ua_retry/control_summary_by_scenario_mode.csv`

- H1 solve-time 重跑：
  - `log/thesis_sweep/20260613_173559_h1_uampc_main_ablation_solvetime/results.csv`
  - `results/thesis_sweep_aggregates/20260613_173559_h1_uampc_main_ablation_solvetime/`
  - `results/control_aggregates/20260613_173559_h1_uampc_main_ablation_solvetime/control_summary_by_scenario_mode.csv`
  - 注意：`mpc_solve_time_*` 字段可用计数为 3，但值为 `0`，文档中必须写成“debug 字段已补录但计时语义仍需确认”，不能写成真实求解耗时为 0 ms。

### 当前文档状态

- `docs/experiment/experiment_gap_conduct_plan.md`
  - 已记录到 C0-C5、P1 3 seed、H1 主消融和旧 H1 控制侧聚合。
  - 尚未追加本轮 terrain retry、P1 控制侧、P1 NIS/R、代理电缆 smoke、H1 solve-time 重跑记录。

- `docs/thesis/paper/experiment_gap_and_next_plan.md`
  - P1 表仍有 `Terrain 重复统计`、`UA-MPC 控制侧消融`、`NIS/R 自适应触发率聚合` 等待补/旧状态。
  - 需要同步为“已完成/有边界”，并新增第二类代理电缆场景 3 核心已完成、6 全量待执行。

- `docs/thesis/paper/05_experiments_and_discussion.md`
  - 5.5 后半段存在污染内容，例如 `/dev/`、`SystemExit raise--------`、路径列表碎片等。
  - 不能在不清理的情况下继续追加正式论文内容。

- `docs/thesis/paper/05_experiments_and_discussion_continued.md`
  - 当前不存在，需要按用户此前要求重建为 5.5.3 之后续写文件。

## Proposed Changes

### 1. 回填 conduct plan 执行记录

**文件**：`docs/experiment/experiment_gap_conduct_plan.md`

**修改内容**：

- 追加“完整 P1 补齐执行记录”小节，包含：
  - terrain PID 3 seed 主跑 + low/mid retry 的命令、路径、成功情况和合并解释。
  - P1 控制侧聚合命令和输出路径。
  - P1 NIS/R 聚合命令和输出路径。
  - H1 solve-time 重跑命令、输出路径、`solve_time=0` 的边界说明。
  - 3 个核心代理电缆场景 smoke 命令、输出路径、初次失败和单条 retry 说明。

**写法约束**：

- `n=1` proxy cable smoke 只写“可运行性和控制指标链路 smoke”，不进入 mean±std 主结论。
- terrain low/mid 的 retry 要明确说明是为了补齐 bag/analysis，不把主跑 summary 误当最终 3/3。

### 2. 同步 gap plan 状态

**文件**：`docs/thesis/paper/experiment_gap_and_next_plan.md`

**修改内容**：

- P1 表状态更新：
  - `Terrain 重复统计`：改为“已完成，主跑 + retry 合并达到 low/mid/high 3 seed；需引用合并口径”。
  - `DVL dropout sweep`、`Mag/Sonar/Combined sweep`：保持 3 seed 已完成，并补充控制侧聚合已完成。
  - `UA-MPC 控制侧消融`：改为“已完成一轮，solve-time 字段补录但计时语义待确认”。
  - `NIS/R 自适应触发率聚合`：改为“已完成 P1 批量聚合”。
- 新增或更新第二类场景真实性条目：
  - 3 核心代理场景已完成 smoke。
  - 6 全量代理场景待扩展，计划仍为低成本 `30s x seed0 x baseline/ua`。
  - 代理场景结论边界：可作为控制性能和稳定性压力场景，不等价于真实海试。

### 3. 重建 05 章续写文件

**文件**：`docs/thesis/paper/05_experiments_and_discussion_continued.md`

**修改内容**：

- 新建 5.5.3 之后的续写 Markdown，建议章节：
  - `## 5.5.4 完整 P1 多场景鲁棒性补齐`
  - `## 5.5.5 控制侧指标聚合与 UA-MPC 边界`
  - `## 5.5.6 NIS 与自适应 R 触发统计`
  - `## 5.5.7 Terrain PID 多 seed 复验`
  - `## 5.6 代理电缆巡检环境与低成本 smoke`
  - `## 5.7 极端电缆巡检场景全量扩展计划`
  - `## 5.8 当前实验闭环与剩余缺口`
- 内容保持原论文详细风格，表格优先引用稳定结果路径。
- 对污染主文档中的 5.7 旧内容不直接照搬；重新组织成干净、可读、可引用的章节。

### 4. 最小清理 05 主文档并加入续写链接

**文件**：`docs/thesis/paper/05_experiments_and_discussion.md`

**修改内容**：

- 在 5.5.3 后保留已有有效内容的边界，不大规模重写前文。
- 删除或替换明显污染碎片：
  - `/dev/`
  - `SystemExit raise--------`
  - 根目录路径列表碎片
  - 与论文正文无关的脚本错误残片
- 在 5.5.3 后加入指向 `05_experiments_and_discussion_continued.md` 的说明：
  - 主文档作为前半章。
  - 续写文件承载 5.5.4 之后补充实验和讨论。

**风险控制**：

- 如果主文档污染范围超过 5.5.3 后半段，只做最小可审阅修复，不重排前文。
- 不删除用户可能仍在写的有效段落，遇到无法判断的段落保留并在续写文件中给出干净版本。

### 5. 扩展 6 个全量代理电缆场景配置

**新增文件**：

- `config/bridge_params.protocol_udp.pvs.cable_hairpin_proxy.yaml`
- `config/bridge_params.protocol_udp.pvs.cable_buried_gap_proxy.yaml`
- `config/bridge_params.protocol_udp.pvs.cable_cross_current_proxy.yaml`

**已有文件继续使用**：

- `config/bridge_params.protocol_udp.pvs.cable_s_curve_proxy.yaml`
- `config/bridge_params.protocol_udp.pvs.cable_slope_crossing_proxy.yaml`
- `config/bridge_params.protocol_udp.pvs.combined_cable_extreme_proxy.yaml`

**6 个场景定义**：

- `cable_s_curve_proxy`
  - 已有配置。
  - S 形连续反向转弯，横流 0.2 m/s，地形轻扰动。

- `cable_hairpin_proxy`
  - 新增配置。
  - 使用近 180 deg 掉头 polyline，例如 `[0,0,12] -> [10,0,12] -> [16,5,12] -> [10,10,12] -> [0,10,12]`。
  - 地形中等扰动，横流 0.2 m/s。

- `cable_slope_crossing_proxy`
  - 已有配置。
  - 斜坡穿越，路径深度逐步变化，坡度 5 deg。

- `cable_buried_gap_proxy`
  - 新增配置。
  - 以“感知弱化代理”表达埋设间断：降低 `perception.sonar.peak_gain`，增大 `base_noise_sigma` 和 `magnetic_sigma`，路径保持可运行。
  - 不声称真实埋深反演，只表示观测置信度下降压力测试。

- `cable_cross_current_proxy`
  - 新增配置。
  - 直线或轻微弯曲电缆，`pvs.current_speed_mps = 0.5`，`current_direction_deg = 90.0`，用于纯控制横流补偿。

- `combined_cable_extreme_proxy`
  - 已有配置。
  - 组合急弯、坡度、强横流、磁/声呐噪声和 combined stress scenario。

### 6. 更新代理电缆 runner 场景映射

**文件**：`tools/run_proxy_cable_sweep.py`

**修改内容**：

- 在 `SCENARIOS` 中加入：
  - `cable_hairpin_proxy`
  - `cable_buried_gap_proxy`
  - `cable_cross_current_proxy`
- 绑定规则：
  - hairpin、buried_gap、cross_current 默认使用 `scenarios/scenario_baseline.yaml`。
  - combined extreme 继续使用 `scenarios/scenario_combined_stress.yaml`。
- 不改变已有 CLI 契约，仍使用：

```bash
python3 tools/run_proxy_cable_sweep.py \
  --scenarios cable_s_curve_proxy,cable_hairpin_proxy,cable_slope_crossing_proxy,cable_buried_gap_proxy,cable_cross_current_proxy,combined_cable_extreme_proxy \
  --seeds 0 \
  --mpc-modes baseline,ua \
  --duration 30 \
  --label cable_proxy_full6_smoke
```

### 7. 运行低成本验证和聚合

**静态检查**：

```bash
python3 -m py_compile \
  tools/run_proxy_cable_sweep.py \
  tools/run_terrain_pid_seed_sweep.py \
  tools/aggregate_uncertainty_metrics.py \
  tools/aggregate_control_metrics.py
```

**6 场景 smoke**：

```bash
python3 tools/run_proxy_cable_sweep.py \
  --scenarios cable_s_curve_proxy,cable_hairpin_proxy,cable_slope_crossing_proxy,cable_buried_gap_proxy,cable_cross_current_proxy,combined_cable_extreme_proxy \
  --seeds 0 \
  --mpc-modes baseline,ua \
  --duration 30 \
  --label cable_proxy_full6_smoke
```

**控制侧聚合**：

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/proxy_cable_sweep/<run>/results.csv \
  --output-dir results/control_aggregates/<run>
```

**验收标准**：

- runner 能识别 6 个场景。
- 12 个 run 中至少 10 个生成非空 MCAP；失败项记录原因，不进行长时间调试。
- 控制聚合至少生成：
  - `control_metrics_by_run.csv`
  - `control_summary_by_scenario_mode.csv`
  - `control_status_counts.csv`
  - `control_aggregate_report.md`
- 若某单条失败且原因类似“缺 estimated-state samples”，允许一次单条 retry；若仍失败，文档中保留为待修复，不拖延整体闭环。

## Assumptions & Decisions

- 不扩展 PVS 后端物理模型；本轮只用现有 `digital_twin`、`cable_path`、`perception`、`pvs.current_speed_mps/current_direction_deg` 表达代理场景。
- 代理场景用于控制性能和稳定性压力测试，不等价于真实海缆巡检或海试。
- `n=1` smoke 只说明“场景和指标链路可运行”，不写成统计显著结论。
- terrain PID 的最终文档口径必须合并主跑与 retry，避免把主跑 low/mid 的 1/3 当作最终状态。
- H1 solve-time 重跑中的 `mpc_solve_time_* = 0` 只说明字段已补录，不能解释为求解器真实耗时为 0 ms。
- 05 主文档采取最小清理；主要新增论文正文写入续写文件，降低污染文档造成的反复编辑风险。

## Verification Steps

1. 只读核对新增/修改文件：

```bash
git diff -- docs/experiment/experiment_gap_conduct_plan.md \
  docs/thesis/paper/experiment_gap_and_next_plan.md \
  docs/thesis/paper/05_experiments_and_discussion.md \
  docs/thesis/paper/05_experiments_and_discussion_continued.md \
  tools/run_proxy_cable_sweep.py \
  config/bridge_params.protocol_udp.pvs.cable_hairpin_proxy.yaml \
  config/bridge_params.protocol_udp.pvs.cable_buried_gap_proxy.yaml \
  config/bridge_params.protocol_udp.pvs.cable_cross_current_proxy.yaml
```

2. Python 静态检查：

```bash
python3 -m py_compile tools/run_proxy_cable_sweep.py
```

3. Runner 场景识别检查：

```bash
python3 tools/run_proxy_cable_sweep.py --help
```

4. 6 场景低成本 smoke：

```bash
python3 tools/run_proxy_cable_sweep.py \
  --scenarios cable_s_curve_proxy,cable_hairpin_proxy,cable_slope_crossing_proxy,cable_buried_gap_proxy,cable_cross_current_proxy,combined_cable_extreme_proxy \
  --seeds 0 \
  --mpc-modes baseline,ua \
  --duration 30 \
  --label cable_proxy_full6_smoke
```

5. smoke 控制聚合：

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/proxy_cable_sweep/<run>/results.csv \
  --output-dir results/control_aggregates/<run>
```

6. 文档一致性核对：

```bash
rg -n "待补|最高|nan|solve time|代理|cable_proxy|terrain_pid|NIS|自适应 R" \
  docs/experiment/experiment_gap_conduct_plan.md \
  docs/thesis/paper/experiment_gap_and_next_plan.md \
  docs/thesis/paper/05_experiments_and_discussion.md \
  docs/thesis/paper/05_experiments_and_discussion_continued.md
```

