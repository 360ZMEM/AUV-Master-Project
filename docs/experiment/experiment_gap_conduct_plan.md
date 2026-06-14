# 实验缺口 Conduct 计划

**阅读边界**: 本文件是执行计划和命令手册，用来把 `docs/thesis/paper/experiment_gap_and_next_plan.md` 中的缺口转成可运行实验。论文正文结论仍以 `docs/thesis/paper/05_experiments_and_discussion.md` 和后续结果汇总表为准。

## 1. 执行原则

本轮实验按“低成本、少调试、可回滚”的顺序推进。每个阶段只扩大一个维度：先验证命令契约，再跑单场景短时 smoke，再跑低成本重复统计，最后进入多场景、UA-MPC 和硬件实验。任何单阶段如果连续调试超过 30 分钟仍未产出可用结果，应先落盘失败原因和下一步假设，不在同一问题上无限纠结。

所有实验都必须保留命令、输出路径、样本量和失败状态。`n=1` 只能写成 smoke 或单次结果；只有 3–5 seed 聚合后才能写 mean±std。emulated Jetson 不能写成真机 Jetson，PVS chaos 不能写成完整海缆巡检海试，MPC 不能写成全面优于 PID/LOS。

## 2. 命令契约

### 2.1 PVS/ES-EKF thesis sweep

入口：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline,dvl_dropout_60 \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --duration 30 \
  --label <label>
```

默认输出：

```text
log/thesis_sweep/<timestamp>_<label>/
  manifest.json
  results.csv
  failures.log
  logs/*.log
  benchmarks/*/benchmark_results.md
```

脚本内部已默认追加低层契约参数：`--bridge-backend protocol_udp`、`--arbiter-profile`、`--auto-activate`。这三项不能随意去掉，否则 bag 可能缺 IMU/DVL/depth，导致 `offline_ekf_benchmark.py` 报 No IMU samples。

### 2.2 Terrain-following benchmark

入口：

```bash
bash scripts/run_terrain_benchmark.sh 30 pid terrain low
bash scripts/run_terrain_benchmark.sh 30 pid terrain mid
bash scripts/run_terrain_benchmark.sh 30 pid terrain high
```

默认输出：

```text
results/control/terrain_following_<timestamp>/
  pid_terrain/
  pid_terrain_log.txt
```

该脚本会修改 `brain_linux/config/feature_flags.yaml`，并在退出时恢复。若中途被强杀，必须检查 `.feature_flags_backup.yaml` 和 `feature_flags.yaml` 是否恢复。

### 2.3 Sweep 聚合

新增聚合入口：

```bash
python3 tools/aggregate_thesis_sweep.py \
  --input log/thesis_sweep/<run>/results.csv \
  --output-dir results/thesis_sweep_aggregates/<run>
```

输出：

```text
summary_by_scenario_mode.csv
status_counts.csv
aggregate_report.md
```

该脚本只读 `results.csv`，成本很低，适合每次 sweep 后立即运行。

## 3. 低成本优先顺序

### C0：命令契约 dry-run

目的：确认场景名、seed、输出路径和参数展开正确，不启动仿真。

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline \
  --seeds 0 \
  --mpc-modes ua \
  --duration 10 \
  --label c0_contract \
  --dry-run
```

验收：生成 `log/thesis_sweep/*_c0_contract/manifest.json` 和 `results.csv`，`status=dry_run`。

### C1：单场景短时 smoke

目的：用最小真实 PVS 成本确认 `start_experiment.sh`、MCAP 录制和 `offline_ekf_benchmark.py` 仍可闭环。

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline \
  --seeds 0 \
  --mpc-modes ua \
  --duration 20 \
  --label c1_baseline_smoke
```

验收：`results.csv` 至少有一行 `status=ok`，并生成 `benchmark_results.md`。若失败，先看 `failures.log`，不要立即扩大实验。

### C2：baseline 低成本重复统计

目的：把最基础的 n=1 结果提升到 3 seed。

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --duration 30 \
  --label c2_baseline_3seed
```

随后聚合：

```bash
python3 tools/aggregate_thesis_sweep.py \
  --input log/thesis_sweep/<run>/results.csv \
  --output-dir results/thesis_sweep_aggregates/<run>
```

验收：至少 2/3 run 为 `ok`；如果低于 2/3，先停在 C2 修复命令链。

### C3：terrain PID 低成本重复统计

目的：优先补论文最稳的 terrain PID 主线。

```bash
bash scripts/run_terrain_benchmark.sh 30 pid terrain low
bash scripts/run_terrain_benchmark.sh 30 pid terrain mid
bash scripts/run_terrain_benchmark.sh 30 pid terrain high
```

验收：每档都有 `pid_terrain/analysis`，且 `seabed_clearance_min_m > 1.5m`。如果某档失败，保留日志并只重跑失败档。

## 4. 中成本阶段

C4 用 `run_thesis_sweep.py` 跑 DVL dropout 的 10/30/60/90 单 seed 或 3 seed。建议先单 seed 验证四档都能跑通，再扩到 3 seed。

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios dvl_dropout_10,dvl_dropout_30,dvl_dropout_60,dvl_dropout_90 \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label c4_dvl_1seed
```

C5 跑 mag distortion、sonar clutter 和 combined stress。这里更容易暴露感知或 benchmark 失败，应保持 30s、单 seed 起步。

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios mag_distortion_light,mag_distortion_heavy,sonar_clutter,combined_stress \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label c5_sensor_1seed
```

## 5. 硬骨头阶段

H1 是 UA-MPC 主消融：`baseline,dvl_dropout_60,combined_stress × seeds 0,1,2 × mpc_modes baseline,ua`。只有 C1–C5 稳定后再跑。

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline,dvl_dropout_60,combined_stress \
  --seeds 0,1,2 \
  --mpc-modes baseline,ua \
  --duration 60 \
  --label h1_uampc_main_ablation
```

H2 是 UA-MPC 参数灵敏度，用 `--param-grid` 控制一次只扫 2–3 个值，避免组合爆炸。

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios combined_stress \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --duration 60 \
  --param-grid 'low_conf_scale:1.5,3.0,5.0' \
  --label h2_uampc_low_conf_scale
```

H3 是电缆真实性场景和硬件实验。当前只落盘设计，不直接跑：`scenario_cable_s_curve`、`scenario_cable_hairpin`、`scenario_cable_slope_crossing`、`scenario_cable_buried_gap`、`scenario_cross_current_near_bottom` 和 `scenario_combined_cable_extreme` 需要先新增 YAML、指标解析和论文表格，再进入实验。

## 6. 本轮先执行

本轮先做三件事：

1. 新增 `tools/aggregate_thesis_sweep.py`。
2. 执行 C0 dry-run，确认命令契约。
3. 若 C0 正常，执行 C1 baseline 20s smoke；若 C1 成功，立刻聚合并记录结果。

如果 C1 失败，本轮不继续 C2/C3，而是把失败日志路径和原因写回本文件或 `docs/experiment/benchmark_test_log.md` 的新小节。

## 7. 执行记录：2026-06-12

### C0：命令契约 dry-run

命令：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline \
  --seeds 0 \
  --mpc-modes ua \
  --duration 10 \
  --label c0_contract \
  --dry-run
```

结果：

```text
log/thesis_sweep/20260612_162825_c0_contract/results.csv
results/thesis_sweep_aggregates/20260612_162825_c0_contract/
```

结论：命令契约通过，展开命令包含 `--bridge-backend protocol_udp`、`--arbiter-profile` 和 `--auto-activate`。新增聚合脚本能读取 dry-run `results.csv` 并生成 `summary_by_scenario_mode.csv`、`status_counts.csv` 和 `aggregate_report.md`。

### C1：baseline 20s smoke

命令：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline \
  --seeds 0 \
  --mpc-modes ua \
  --duration 20 \
  --label c1_baseline_smoke
```

结果：

```text
log/thesis_sweep/20260612_162841_c1_baseline_smoke/results.csv
results/thesis_sweep_aggregates/20260612_162841_c1_baseline_smoke/
```

聚合结果：

| scenario | mpc_mode | ok/total | XY RMSE | Z RMSE | CEP50 |
|---|---|---:|---:|---:|---:|
| baseline | ua | 1/1 | 0.7930m | 1.0630m | 1.3260m |

结论：第一条真实 PVS + MCAP + offline EKF benchmark 闭环成功。由于 `runs_ok=1`，该结果只能作为 smoke，不进入 mean±std 论文表。

### C2：baseline 3 seed 低成本重复统计

命令：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --duration 30 \
  --label c2_baseline_3seed
```

结果：

```text
log/thesis_sweep/20260612_163001_c2_baseline_3seed/results.csv
results/thesis_sweep_aggregates/20260612_163001_c2_baseline_3seed/
```

聚合结果：

| scenario | mpc_mode | ok/total | XY RMSE mean±std | Z RMSE mean±std | CEP50 mean±std |
|---|---|---:|---:|---:|---:|
| baseline | ua | 3/3 | 1.1303±0.0474m | 0.8083±0.1285m | 1.3913±0.1056m |

单次结果：

| seed | status | XY RMSE | Z RMSE | CEP50 | Max Drift | bag |
|---:|---|---:|---:|---:|---:|---|
| 0 | ok | 1.120m | 0.881m | 1.425m | 0.982m | `/auv_data/bags/20260612_163002/rosbag/rosbag_0.mcap` |
| 1 | ok | 1.182m | 0.884m | 1.476m | 0.993m | `/auv_data/bags/20260612_163113/rosbag/rosbag_0.mcap` |
| 2 | ok | 1.089m | 0.660m | 1.273m | 0.911m | `/auv_data/bags/20260612_163225/rosbag/rosbag_0.mcap` |

结论：baseline/ua 已从 n=1 提升到 3 seed，可作为第 3 章/第 5 章的低成本重复统计材料。下一步不要直接进入 UA-MPC 大消融，优先跑 C3 terrain PID low/mid/high 或 C4 DVL dropout 单 seed，继续验证低成本路径。

### C3：terrain PID low/mid/high 低成本验证

命令：

```bash
AUV_BENCHMARK_SKIP_PREBUILD=1 bash scripts/run_terrain_benchmark.sh 30 pid terrain low
AUV_BENCHMARK_SKIP_PREBUILD=1 bash scripts/run_terrain_benchmark.sh 30 pid terrain mid
AUV_BENCHMARK_SKIP_PREBUILD=1 bash scripts/run_terrain_benchmark.sh 30 pid terrain high
```

结果：

| terrain | result_dir | duration | clearance RMSE to 3m | clearance mean | clearance std | clearance min | <1.5m ratio |
|---|---|---:|---:|---:|---:|---:|---:|
| low | `results/control/terrain_following_20260612_164020` | 29.843s | 0.1657m | 3.1655m | 0.0090m | 3.1268m | 0.0 |
| mid | `results/control/terrain_following_20260612_164141` | 29.749s | 0.1727m | 3.1727m | 0.0023m | 3.1690m | 0.0 |
| high | `results/control/terrain_following_20260612_164331` | 28.044s | 0.1643m | 3.1631m | 0.0192m | 3.0815m | 0.0 |

结论：三档 terrain PID 低成本验证全部通过，没有 `<1.5m` 安全违规；结果与前序 60s/ablation 结论一致，可作为“低成本复验”写入实验拾遗。注意本轮每档仍是单次运行，不等价于每档 3 seed mean±std。

### C4：DVL dropout 四档单 seed

命令：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios dvl_dropout_10,dvl_dropout_30,dvl_dropout_60,dvl_dropout_90 \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label c4_dvl_1seed
```

结果：

```text
log/thesis_sweep/20260612_164528_c4_dvl_1seed/results.csv
results/thesis_sweep_aggregates/20260612_164528_c4_dvl_1seed/
```

聚合结果：

| scenario | ok/total | XY RMSE | Z RMSE | CEP50 | Max Drift |
|---|---:|---:|---:|---:|---:|
| dvl_dropout_10 | 1/1 | 3.249m | 0.219m | 3.256m | 3.253m |
| dvl_dropout_30 | 1/1 | 1.369m | 0.222m | 1.387m | 1.365m |
| dvl_dropout_60 | 1/1 | 3.331m | 0.190m | 3.337m | 3.334m |
| dvl_dropout_90 | 1/1 | 4.298m | 0.207m | 4.303m | 4.297m |

结论：四档 DVL dropout 均能完成 PVS + MCAP + offline EKF benchmark 闭环，说明场景配置与命令链路可跑通。由于每档仍是 `n=1`，目前只能写成单次场景可行性验证；下一步若要进入论文鲁棒性曲线，需要扩展到 3–5 seed。

### C5：mag/sonar/combined 单 seed

命令：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios mag_distortion_light,mag_distortion_heavy,sonar_clutter,combined_stress \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label c5_sensor_1seed
```

结果：

```text
log/thesis_sweep/20260612_164908_c5_sensor_1seed/results.csv
results/thesis_sweep_aggregates/20260612_164908_c5_sensor_1seed/
```

聚合结果：

| scenario | ok/total | XY RMSE | Z RMSE | CEP50 | Max Drift |
|---|---:|---:|---:|---:|---:|
| mag_distortion_light | 1/1 | 3.539m | 0.221m | 3.545m | 3.536m |
| mag_distortion_heavy | 1/1 | 4.264m | 0.187m | 4.268m | 4.259m |
| sonar_clutter | 1/1 | 4.031m | 0.234m | 4.038m | 4.024m |
| combined_stress | 1/1 | 2.448m | 0.242m | 2.460m | 2.449m |

结论：mag、sonar 和 combined stress 四类场景均能完成闭环。当前结果只说明场景和命令可运行，不解释扰动强度排序；例如 combined stress 的单次 XY RMSE 低于部分单因素场景，可能与随机种子、轨迹片段和观测时序有关，需要 3–5 seed 后才能写趋势结论。

## 8. 下一阶段建议

低成本阶段已经完成 `C0–C5`。下一步建议优先把 C4/C5 扩成 3 seed，而不是马上进入 H1 UA-MPC 主消融：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios dvl_dropout_10,dvl_dropout_30,dvl_dropout_60,dvl_dropout_90,mag_distortion_light,mag_distortion_heavy,sonar_clutter,combined_stress \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --duration 30 \
  --label p1_sensor_3seed
```

若该 8 场景 3 seed sweep 成功率达到 80% 以上，再进入 H1：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline,dvl_dropout_60,combined_stress \
  --seeds 0,1,2 \
  --mpc-modes baseline,ua \
  --duration 60 \
  --label h1_uampc_main_ablation
```

## 9. 执行记录：P1 sensor/chaos 3 seed

命令：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios dvl_dropout_10,dvl_dropout_30,dvl_dropout_60,dvl_dropout_90,mag_distortion_light,mag_distortion_heavy,sonar_clutter,combined_stress \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --duration 30 \
  --label p1_sensor_3seed
```

结果：

```text
log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv
results/thesis_sweep_aggregates/20260612_170618_p1_sensor_3seed/
```

聚合结果：

| scenario | ok/total | XY RMSE mean±std | Z RMSE mean±std | CEP50 mean±std |
|---|---:|---:|---:|---:|
| dvl_dropout_10 | 3/3 | 2.9723±1.4092m | 0.2030±0.0255m | 2.9817±1.4020m |
| dvl_dropout_30 | 3/3 | 3.3733±0.1340m | 0.2020±0.0092m | 3.3793±0.1340m |
| dvl_dropout_60 | 3/3 | 2.8863±0.4556m | 0.2203±0.0105m | 2.8950±0.4545m |
| dvl_dropout_90 | 3/3 | 3.5483±0.2261m | 0.1927±0.0405m | 3.5537±0.2268m |
| mag_distortion_light | 3/3 | 2.7580±0.3413m | 0.1807±0.0075m | 2.7640±0.3395m |
| mag_distortion_heavy | 3/3 | 3.4160±0.1027m | 0.2220±0.0213m | 3.4233±0.1023m |
| sonar_clutter | 3/3 | 3.2670±1.0586m | 0.2003±0.0297m | 3.2743±1.0540m |
| combined_stress | 3/3 | 3.2720±1.0894m | 0.2037±0.0232m | 3.2790±1.0873m |

结论：8 个 PVS chaos 场景全部达到 3 seed，成功率 100%，可以进入论文 mean±std 表格。结果趋势仍需谨慎解释：不同场景的 XY RMSE 不严格按扰动强度单调变化，说明 30s 片段、seed 和观测时序仍有显著影响。下一步可以进入 H1 UA-MPC 主消融，但主消融结论仍需单独聚合，不能直接由 UA mode 的 P1 结果推出。

## 10. 执行记录：H1 UA-MPC 主消融

命令：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline,dvl_dropout_60,combined_stress \
  --seeds 0,1,2 \
  --mpc-modes baseline,ua \
  --duration 60 \
  --label h1_uampc_main_ablation
```

结果：

```text
log/thesis_sweep/20260612_172535_h1_uampc_main_ablation/results.csv
results/thesis_sweep_aggregates/20260612_172535_h1_uampc_main_ablation/
```

聚合结果：

| scenario | mode | ok/total | XY RMSE mean±std | Z RMSE mean±std | CEP50 mean±std |
|---|---|---:|---:|---:|---:|
| baseline | baseline-MPC | 3/3 | 4.6180±0.6107m | 0.2960±0.0026m | 4.6277±0.6093m |
| baseline | UA-MPC | 3/3 | 4.4007±1.0071m | 0.2970±0.0044m | 4.4110±1.0048m |
| dvl_dropout_60 | baseline-MPC | 3/3 | 3.4857±0.9488m | 0.2913±0.0006m | 3.4983±0.9456m |
| dvl_dropout_60 | UA-MPC | 3/3 | 3.5517±0.4957m | 0.2960±0.0056m | 3.5640±0.4932m |
| combined_stress | baseline-MPC | 3/3 | 4.1070±0.1146m | 0.2947±0.0042m | 4.1177±0.1150m |
| combined_stress | UA-MPC | 3/3 | 3.6800±0.5014m | 0.2940±0.0020m | 3.6920±0.4988m |

相对 baseline-MPC 的 XY RMSE 变化：

| scenario | UA-MPC 相对变化 |
|---|---:|
| baseline | 改善约 4.7% |
| dvl_dropout_60 | 变差约 1.9% |
| combined_stress | 改善约 10.4% |

结论边界：H1 已经完成 `baseline/dvl_dropout_60/combined_stress × baseline/ua × 3 seed`，成功率 100%，可以写成“UA-MPC 主消融命令链和三场景统计已闭环”。但当前 `tools/run_thesis_sweep.py` 聚合的是 offline EKF 的 XY/Z/CEP50 指标，不是完整控制侧 lateral RMSE、fallback rate 或 control smoothness。因此论文中不能把这张表单独写成“UA-MPC 控制性能显著优于 baseline-MPC”。更稳妥的写法是：UA mode 在 baseline 与 combined_stress 下对定位相关指标有轻微改善，在 dvl_dropout_60 下无优势；控制侧 UA-MPC 结论还需要补充 lateral/fallback/control-effort 指标解析。

下一步需要补的代码不是再调参，而是扩展分析链路：从 bag 或控制诊断中解析 lateral RMSE、MPC solve time、fallback rate、控制量变化率和安全违规率，并加入 `results.csv` 或单独的 control aggregate 表。

## 11. 执行记录：H1 控制侧指标聚合

新增工具：

```text
tools/aggregate_control_metrics.py
docs/user-guide/11_control_aggregate.md
```

命令：

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/thesis_sweep/20260612_172535_h1_uampc_main_ablation/results.csv \
  --output-dir results/control_aggregates/20260612_172535_h1_uampc_main_ablation
```

结果：

```text
results/control_aggregates/20260612_172535_h1_uampc_main_ablation/control_metrics_by_run.csv
results/control_aggregates/20260612_172535_h1_uampc_main_ablation/control_summary_by_scenario_mode.csv
results/control_aggregates/20260612_172535_h1_uampc_main_ablation/control_status_counts.csv
results/control_aggregates/20260612_172535_h1_uampc_main_ablation/merged_control_results.csv
results/control_aggregates/20260612_172535_h1_uampc_main_ablation/control_aggregate_report.md
```

状态计数：

```text
generated,18
```

控制侧聚合摘要：

| scenario | mode | ok/total | lateral RMSE mean±std | solve mean ms | fallback rate | control rate RMS | safety violation |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline | baseline-MPC | 3/3 | 0.003803±0.000392m | nan | 0.0000±0.0000 | 0.1443±0.0133 | 0.0000±0.0000 |
| baseline | UA-MPC | 3/3 | 0.003730±0.000329m | nan | 0.0000±0.0000 | 0.4380±0.2670 | 0.0000±0.0000 |
| dvl_dropout_60 | baseline-MPC | 3/3 | 0.003335±0.000257m | nan | 0.0000±0.0000 | 0.1292±0.0631 | 0.0000±0.0000 |
| dvl_dropout_60 | UA-MPC | 3/3 | 0.003871±0.001301m | nan | 0.0000±0.0000 | 0.1863±0.2150 | 0.0000±0.0000 |
| combined_stress | baseline-MPC | 3/3 | 0.003500±0.000226m | nan | 0.0000±0.0000 | 0.1383±0.0737 | 0.0000±0.0000 |
| combined_stress | UA-MPC | 3/3 | 0.002947±0.000438m | nan | 0.0000±0.0000 | 0.0301±0.0038 | 0.0000±0.0000 |

结论边界：H1 旧 bag 能补齐 lateral RMSE、fallback rate、控制量变化率和安全违规率。MPC solve time 在旧 bag 中为 `nan`，原因是 `/auv/controller/debug` 当时没有发布 `solve_time_ms` 字段；已在 `brain_linux/src/auv_controller/auv_controller/auv_controller_node.py` 补充 debug payload，使后续新 bag 能记录 `solve_time_ms`、`solver_status` 和 `fallback_reason`。因此当前 H1 控制表可用于“已有 bag 的控制侧回填”，但 solve-time 对比需要重跑 H1 或后续 H2 时再补。

## 12. 执行记录：完整 P1 补齐与代理电缆 smoke

本轮按“第一类过程导向补充、第二类多样环境低成本 smoke”的原则推进。第一类重点是补齐已有 P1/H1 证据链；第二类重点是先证明代理电缆场景可运行和控制指标可聚合，不把 `n=1` smoke 写成统计结论。

关键新增产物：

```text
results/control/terrain_pid_seed_sweep_20260613_162512_terrain_pid_3seed/
results/control/terrain_pid_seed_sweep_20260613_165856_terrain_pid_low_retry/
results/control/terrain_pid_seed_sweep_20260613_170630_terrain_pid_mid_retry/
results/control_aggregates/20260612_170618_p1_sensor_3seed/
results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/
log/proxy_cable_sweep/20260613_171423_cable_proxy_smoke/results.csv
results/control_aggregates/20260613_171423_cable_proxy_smoke/
log/proxy_cable_sweep/20260613_180210_cable_slope_crossing_ua_retry/results.csv
results/control_aggregates/20260613_180210_cable_slope_crossing_ua_retry/
log/thesis_sweep/20260613_173559_h1_uampc_main_ablation_solvetime/results.csv
results/control_aggregates/20260613_173559_h1_uampc_main_ablation_solvetime/
```

Terrain PID 合并口径：主跑中 high 为 3/3 ok，low 和 mid 各只有 1/3 ok；随后仅重跑失败 seed，最终 low/mid/high 均达到 3/3。合并后的 clearance RMSE 分别为 low `0.5868±0.1116 m`、mid `0.7094±0.0015 m`、high `0.6102±0.0810 m`，三档 `<1.5 m` 安全违规率均为 0。论文中必须注明 low/mid 采用主跑 + retry 合并口径。

P1 控制侧聚合：`results/control_aggregates/20260612_170618_p1_sensor_3seed/control_status_counts.csv` 显示 `generated,24`。旧 bag 的 solve time 仍为 `nan`，但 lateral RMSE、fallback rate、control rate RMS 和 safety violation 可用；所有 P1 场景 fallback rate 与 safety violation rate 均为 0。

P1 NIS/R 聚合：`results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/summary_by_scenario_mode.csv` 中 8 个场景均为 3/3 ok，`r_scale_max` 均达到 5，`r_scale_trigger_ratio` 约为 0.2355-0.3610。该表可用于论文中的 NIS/R 触发统计，但必须区分 real NIS 与 DVL/depth proxy NIS。

H1 solve-time 重跑：`log/thesis_sweep/20260613_173559_h1_uampc_main_ablation_solvetime/results.csv` 为 18/18 ok，控制聚合也为 18/18 generated。`mpc_solve_time_*` 字段可用但当前值为 0 ms，说明 debug payload 字段已补录，但控制器填充的计时语义仍需确认，不能据此声称真实求解耗时为 0 ms。

三个核心代理电缆场景 smoke：`cable_s_curve_proxy`、`cable_slope_crossing_proxy`、`combined_cable_extreme_proxy` 的 seed0 x baseline/ua 运行链路可用。初次控制聚合中 `cable_slope_crossing_proxy + ua` 缺 estimated-state samples，单条 retry 后补齐。该结果只作为 `n=1` smoke，不进入 mean±std 主结论。

## 13. 下一步：6 个全量代理电缆场景

第二类场景真实性缺口下一步扩展为 6 个全量代理场景：

```text
cable_s_curve_proxy
cable_hairpin_proxy
cable_slope_crossing_proxy
cable_buried_gap_proxy
cable_cross_current_proxy
combined_cable_extreme_proxy
```

第一轮仍执行低成本 smoke：

```bash
python3 tools/run_proxy_cable_sweep.py \
  --scenarios cable_s_curve_proxy,cable_hairpin_proxy,cable_slope_crossing_proxy,cable_buried_gap_proxy,cable_cross_current_proxy,combined_cable_extreme_proxy \
  --seeds 0 \
  --mpc-modes baseline,ua \
  --duration 30 \
  --label cable_proxy_full6_smoke
```

验收口径：12 条 run 中至少 10 条生成非空 MCAP，并能通过 `tools/aggregate_control_metrics.py` 生成控制侧表。若个别 run 仍因 estimated-state samples 缺失导致聚合失败，只做一次单条 retry；若仍失败，保留为待修复，不展开长时间调试。

## 12. 执行记录：完整 P1 补齐与代理电缆 smoke

本轮按“第一类过程导向补充、第二类多样环境低成本 smoke”的原则推进。第一类重点是补齐已有 P1/H1 证据链；第二类重点是先证明代理电缆场景可运行和控制指标可聚合，不把 `n=1` smoke 写成统计结论。

### 12.1 Terrain PID 3 seed 与 retry 合并口径

主跑命令：

```bash
python3 tools/run_terrain_pid_seed_sweep.py \
  --terrains low,mid,high \
  --seeds 0,1,2 \
  --duration 30 \
  --label terrain_pid_3seed \
  --bag-finalize-s 90
```

结果路径：

```text
results/control/terrain_pid_seed_sweep_20260613_162512_terrain_pid_3seed/
results/control/terrain_pid_seed_sweep_20260613_165856_terrain_pid_low_retry/
results/control/terrain_pid_seed_sweep_20260613_170630_terrain_pid_mid_retry/
```

主跑中 high 为 3/3 ok，low 和 mid 各只有 1/3 ok，失败原因是部分 bag/analysis 没有稳定落盘。随后只重跑失败 seed，low 和 mid 各补齐 2 条，因此最终合并口径为 low/mid/high 均 3/3。

合并后的关键指标：

| terrain | ok/total | clearance RMSE mean±std | clearance mean±std | min clearance mean±std | violation < 1.5 m |
|---|---:|---:|---:|---:|---:|
| low | 3/3 | 0.5868±0.1116 m | 3.5461±0.1455 m | 3.2594±0.3881 m | 0.0000 |
| mid | 3/3 | 0.7094±0.0015 m | 3.7094±0.0015 m | 3.7083±0.0018 m | 0.0000 |
| high | 3/3 | 0.6102±0.0810 m | 3.5830±0.1117 m | 3.2283±0.2053 m | 0.0000 |

结论边界：该结果可以把 terrain PID 从 n=1/档推进到 3 seed mean±std，但 low/mid 的最终统计是“主跑 + retry”合并口径；论文中需要注明 retry 用于补齐落盘失败，不应把主跑 summary 单独当作最终表。

### 12.2 P1 sensor/chaos 控制侧聚合

命令：

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv \
  --output-dir results/control_aggregates/20260612_170618_p1_sensor_3seed
```

结果：

```text
results/control_aggregates/20260612_170618_p1_sensor_3seed/control_metrics_by_run.csv
results/control_aggregates/20260612_170618_p1_sensor_3seed/control_summary_by_scenario_mode.csv
results/control_aggregates/20260612_170618_p1_sensor_3seed/control_status_counts.csv
results/control_aggregates/20260612_170618_p1_sensor_3seed/control_aggregate_report.md
```

状态计数：

```text
generated,24
```

摘要：8 个 PVS chaos 场景 x 3 seed 的控制侧指标均生成成功。旧 bag 的 solve time 仍为 `nan`，但 lateral RMSE、fallback rate、control rate RMS、安全违规率可用。所有场景 fallback rate 和 safety violation rate 均为 0。

### 12.3 P1 NIS/R 自适应触发率聚合

命令：

```bash
python3 tools/aggregate_uncertainty_metrics.py \
  --sweep-results log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv \
  --output-dir results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed
```

结果：

```text
results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/per_run_uncertainty_results.csv
results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/summary_by_scenario_mode.csv
results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/aggregate_report.md
```

关键现象：8 个场景均为 3/3 ok。`r_scale_max` 均达到 5，`r_scale_trigger_ratio` 在约 0.238-0.361 之间，说明自适应 R 机制在 P1 chaos 场景中确实被触发。`nis_real_mean` 约为 3.36-4.51，`nis_real_p95` 约为 19.37-21.03。该表可用于论文中的 NIS/R 触发统计，但必须区分 real NIS 与 DVL/depth proxy NIS。

### 12.4 H1 solve-time 重跑

命令：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline,dvl_dropout_60,combined_stress \
  --seeds 0,1,2 \
  --mpc-modes baseline,ua \
  --duration 60 \
  --label h1_uampc_main_ablation_solvetime

python3 tools/aggregate_control_metrics.py \
  --sweep-results log/thesis_sweep/20260613_173559_h1_uampc_main_ablation_solvetime/results.csv \
  --output-dir results/control_aggregates/20260613_173559_h1_uampc_main_ablation_solvetime
```

结果：

```text
log/thesis_sweep/20260613_173559_h1_uampc_main_ablation_solvetime/results.csv
results/thesis_sweep_aggregates/20260613_173559_h1_uampc_main_ablation_solvetime/
results/control_aggregates/20260613_173559_h1_uampc_main_ablation_solvetime/
```

状态：18/18 ok，控制聚合 18/18 generated。`mpc_solve_time_*` 字段可用计数为 3/3，但当前值为 0 ms。结论边界必须写成：debug payload 字段已经补录并可解析，但控制器填充的计时语义仍需确认，不能据此声称真实求解耗时为 0 ms。

### 12.5 三个核心代理电缆场景 smoke

命令：

```bash
python3 tools/run_proxy_cable_sweep.py \
  --scenarios cable_s_curve_proxy,cable_slope_crossing_proxy,combined_cable_extreme_proxy \
  --seeds 0 \
  --mpc-modes baseline,ua \
  --duration 30 \
  --label cable_proxy_smoke

python3 tools/aggregate_control_metrics.py \
  --sweep-results log/proxy_cable_sweep/20260613_171423_cable_proxy_smoke/results.csv \
  --output-dir results/control_aggregates/20260613_171423_cable_proxy_smoke
```

结果：

```text
log/proxy_cable_sweep/20260613_171423_cable_proxy_smoke/results.csv
results/control_aggregates/20260613_171423_cable_proxy_smoke/
```

初次 run 为 6/6 ok。控制聚合中 `cable_slope_crossing_proxy + ua` 初次缺 estimated-state samples，因此做了单条 retry：

```bash
python3 tools/run_proxy_cable_sweep.py \
  --scenarios cable_slope_crossing_proxy \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label cable_slope_crossing_ua_retry
```

retry 结果：

```text
log/proxy_cable_sweep/20260613_180210_cable_slope_crossing_ua_retry/results.csv
results/control_aggregates/20260613_180210_cable_slope_crossing_ua_retry/
```

合并口径下 3 个核心代理场景 x baseline/ua 均有控制侧指标。该结果只作为 `n=1` smoke：说明代理电缆环境、runner 和控制聚合链路可运行；还不能写成多场景统计优势。

## 13. 下一步：6 个全量代理电缆场景

已决定把第二类场景真实性缺口从 3 个核心场景扩展到 6 个全量代理场景。场景集合为：

```text
cable_s_curve_proxy
cable_hairpin_proxy
cable_slope_crossing_proxy
cable_buried_gap_proxy
cable_cross_current_proxy
combined_cable_extreme_proxy
```

第一轮仍执行低成本 smoke：

```bash
python3 tools/run_proxy_cable_sweep.py \
  --scenarios cable_s_curve_proxy,cable_hairpin_proxy,cable_slope_crossing_proxy,cable_buried_gap_proxy,cable_cross_current_proxy,combined_cable_extreme_proxy \
  --seeds 0 \
  --mpc-modes baseline,ua \
  --duration 30 \
  --label cable_proxy_full6_smoke
```

验收口径：12 条 run 中至少 10 条生成非空 MCAP，并能通过 `tools/aggregate_control_metrics.py` 生成控制侧表。若个别 run 仍因 estimated-state samples 缺失导致聚合失败，只做一次单条 retry；若仍失败，保留为待修复，不展开长时间调试。

## 12. 执行记录：ES-EKF 杆臂/外参错位评估

新增/联动文件：

```text
common/sensor_extrinsics.py
tools/es_ekf_extrinsics_benchmark.py
tools/calibrate_sensor_extrinsics_sim.py
tools/aggregate_extrinsics_benchmark.py
scenarios/scenario_extrinsics_light.yaml
scenarios/scenario_extrinsics_medium.yaml
scenarios/scenario_extrinsics_heavy.yaml
```

纯脚本 smoke：

```bash
python3 tools/es_ekf_extrinsics_benchmark.py \
  --duration 30 \
  --seeds 0 \
  --true-profile light \
  --estimation-modes none,calibrated,online_lite \
  --output-dir results/es_ekf_extrinsics/smoke
```

结果路径：

```text
results/es_ekf_extrinsics/smoke/summary_by_error_level.csv
```

摘要：

| profile | mode | XY RMSE | Z RMSE | 3D RMSE |
|---|---|---:|---:|---:|
| light | none | 2.2571m | 0.0495m | 2.2576m |
| light | calibrated | 2.1947m | 0.0030m | 2.1947m |
| light | online_lite | 2.1900m | 0.0031m | 2.1900m |

标定联动：

```bash
python3 tools/calibrate_sensor_extrinsics_sim.py \
  --profile light \
  --seed 0 \
  --duration 120 \
  --output results/es_ekf_extrinsics/smoke/estimated_extrinsics.yaml

python3 tools/es_ekf_extrinsics_benchmark.py \
  --duration 60 \
  --seeds 0 \
  --true-profile light \
  --estimation-modes none,calibrated,calibrated_from_yaml \
  --estimated-extrinsics-yaml results/es_ekf_extrinsics/smoke/estimated_extrinsics.yaml \
  --output-dir results/es_ekf_extrinsics/calibration_smoke
```

聚合结果：

```text
results/es_ekf_extrinsics/calibration_smoke_aggregate/extrinsics_aggregate_report.md
```

| profile | mode | runs | 3D RMSE | improvement vs none |
|---|---|---:|---:|---:|
| light | none | 1 | 8.3584m | 0.0000% |
| light | calibrated | 1 | 7.9924m | 4.3793% |
| light | calibrated_from_yaml | 1 | 8.2549m | 1.2390% |

PVS smoke 修复记录：

- `log/thesis_sweep/20260613_161921_extrinsics_light_smoke/` 暴露 0 字节 MCAP，`offline_ekf_benchmark` 读包触发 EOF。
- 修复后 `run_thesis_sweep.py` 默认：
  - 跳过运行中 `colcon build`：`AUV_SKIP_BRAIN_BUILD=1`。
  - 录包前等待 `/auv/control/mpc_cmd` publisher。
  - 排除大体积 `/auv/visual/.*` topic，避免 recorder 被杀后 MCAP 损坏。
  - 对 0 字节 MCAP 写出 `bag_empty`，不再交给 benchmark 读。
- `scripts/start_experiment.sh` 增加 `--brain-ready-topic` 与 `--brain-ready-timeout`，支持命令行或环境变量等待 brain ready 后再录包。

PVS 回归命令：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label extrinsics_regression_baseline

python3 tools/run_thesis_sweep.py \
  --scenarios extrinsics_light \
  --seeds 0 \
  --mpc-modes ua \
  --duration 30 \
  --label extrinsics_light_smoke_lean
```

结果：

| run | status | XY RMSE | Z RMSE | MCAP |
|---|---|---:|---:|---|
| baseline smoke | ok | 1.144m | 0.827m | `/auv_data/bags/20260613_162742/rosbag/rosbag_0.mcap` |
| extrinsics_light smoke | ok | 1.215m | 0.044m | `/auv_data/bags/20260613_163029/rosbag/rosbag_0.mcap` |

PVS 主实验：

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios extrinsics_light,extrinsics_medium,extrinsics_heavy \
  --seeds 0,1,2 \
  --mpc-modes ua \
  --duration 60 \
  --label extrinsics_main_3seed
```

结果路径：

```text
log/thesis_sweep/20260613_163259_extrinsics_main_3seed/results.csv
results/thesis_sweep_aggregates/20260613_163259_extrinsics_main_3seed/aggregate_report.md
```

聚合摘要（仅 `status=ok`）：

| scenario | mode | ok/total | XY RMSE mean±std | Z RMSE mean±std | CEP50 mean±std |
|---|---|---:|---:|---:|---:|
| extrinsics_light | ua | 2/3 | 1.6145±0.7304m | 0.3360±0.4384m | 1.6625±0.7969m |
| extrinsics_medium | ua | 2/3 | 1.5480±0.7920m | 0.5145±0.0714m | 1.6485±0.7220m |
| extrinsics_heavy | ua | 2/3 | 1.9330±0.3055m | 0.6345±0.1549m | 2.0415±0.2411m |

结论边界：纯脚本和标定联动已经闭环，可以支撑“外参改正进入 ES-EKF 观测模型后能恢复部分性能”的有限结论。PVS 侧完成 light/medium/heavy 的低样本补充，但 seed2 的三个 MCAP 损坏，当前只能写成 `2/3` 可用的 smoke/补充证据；不能写成完整 `3 seed` 统计结论。`online_lite` 仍是 oracle-style 上限或小残差修正，不是完整在线外参状态增广。

## 12. 执行记录：ES-EKF 杆臂/外参第一阶段

新增/修正文件：

```text
common/sensor_extrinsics.py
tools/es_ekf_extrinsics_benchmark.py
tools/calibrate_sensor_extrinsics_sim.py
tools/aggregate_extrinsics_benchmark.py
scenarios/scenario_extrinsics_{light,medium,heavy}.yaml
```

关键修正：ES-EKF 使用左乘姿态误差注入，DVL 和 depth sensor 观测的姿态雅可比需要与该约定一致。修正后，纯脚本无噪声 smoke 中 `calibrated` 明显优于 `none`。

命令：

```bash
python3 tools/es_ekf_extrinsics_benchmark.py \
  --duration 30 \
  --seeds 0 \
  --true-profile light \
  --estimation-modes none,calibrated,online_lite \
  --output-dir results/es_ekf_extrinsics/smoke
```

```bash
python3 tools/calibrate_sensor_extrinsics_sim.py \
  --profile light \
  --seed 0 \
  --duration 120 \
  --output results/es_ekf_extrinsics/calibration_smoke/estimated_extrinsics.yaml
```

```bash
python3 tools/aggregate_extrinsics_benchmark.py \
  --results results/es_ekf_extrinsics/calibration_smoke/results.csv \
  --output-dir results/es_ekf_extrinsics/calibration_smoke_aggregate
```

当前 calibration smoke 聚合：

| profile | mode | runs | 3D RMSE | XY RMSE | Z RMSE | improvement vs none |
|---|---|---:|---:|---:|---:|---:|
| light | calibrated | 1 | 7.9924 | 7.9924 | 0.0035 | 4.3793% |
| light | calibrated_from_yaml | 1 | 8.2545 | 8.2545 | 0.0037 | 1.2433% |
| light | none | 1 | 8.3584 | 8.3583 | 0.0490 | 0.0000% |

结论边界：第一阶段已经验证“外参改正进入 ES-EKF 观测模型后能带来正收益”，并且仿真标定 YAML 能联动 benchmark。`online_lite` 当前仍是带 oracle 上限含义的小残差慢速靠近真值，不应写成完整在线标定。PVS 已接入 `sensor_extrinsics_truth` 和 light/medium/heavy 场景，但 PVS 主 sweep 还需要单独跑 smoke 与 3 seed 后再写最终统计。
