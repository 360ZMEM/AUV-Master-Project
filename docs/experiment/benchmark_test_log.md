# 基准测试端到端验证日志

**日期**: 2026-06-08  
**目的**: 以新手视角按照文档契约执行完整流程，验证命令正确性并发现潜在问题。

**阅读边界**: 本文件是 2026-06-08 的端到端执行日志，保留当时命令、路径偏差和问题定位。它不是最终论文结果表；正文引用请优先使用 `docs/thesis/paper/05_experiments_and_discussion.md` 与 `docs/thesis/paper/experiment_gap_and_next_plan.md`。


---

## Step 1: 编译项目

```bash
source /opt/ros/humble/setup.bash
cd brain_linux
colcon build --cmake-clean-cache \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3 -DPYTHON_EXECUTABLE=/usr/bin/python3
```

**结果**: 9 个包全部编译通过（4.55 秒），无错误。

**注意事项**:
- 必须先 `conda deactivate`（如果当前在 conda 环境中），否则 conda 的 python 会干扰 ROS2 接口生成（缺少 `em` 模块）
- `start_lin_brain.sh` 内部已包含 colcon build 且会自动 deactivate conda，但首次手动编译可以提前暴露依赖问题
- `--cmake-clean-cache` 会清除缓存重新构建，日常迭代可去掉此参数加速

---

## Step 2: 运行 120s PVS+Zenoh 全量实验

```bash
cd scripts
bash start_experiment.sh --sim-backend pvs --bridge-backend zenoh_json --duration 120
```

**结果**: 实验正常运行 120 秒后自动停止。

**实际录制路径**: `/auv_data/bags/20260608_172454/rosbag/rosbag_0.mcap` (1.7GB)

**关键发现 — MCAP 文件损坏**:
录制的 MCAP 文件**无法被 mcap 库解析**。错误信息：
```
mcap.exceptions.RecordLengthLimitExceeded: unknown (opcode 54) record has length 
12338244732438562096 that exceeds limit 4294967296
```

**根因**: `start_experiment.sh` 在 duration 超时后通过 `kill` 终止 `ros2 bag record` 进程。该进程被强制杀死时未能写入 MCAP footer（summary section），导致文件格式不完整。

**规避方法**: 
1. 使用 `--duration` 时，应在脚本中使用 `SIGINT`（等效于 Ctrl+C）而非 `SIGTERM/SIGKILL` 来停止 recorder，让其正常 flush
2. 或者手动运行实验（不使用 `--duration`），手动 Ctrl+C 停止
3. 已有的 `log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap`（507MB）是正常关闭的完整文件，可用于基准测试

**已修复**: `scripts/start_experiment.sh` 第 176 行 `kill` 改为 `kill -INT`，并加入 `sleep 2` 等待 recorder flush。

---

## Step 3: 运行 ES-EKF 基准测试

使用已有完整 MCAP 文件（绕过 Step 2 的损坏文件）：

```bash
python3 tools/offline_ekf_benchmark.py \
    --input log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap \
    --output-dir results/localization/验证运行_20260608 \
    --verbose
```

**结果**: 成功。输出到项目内 `results/localization/验证运行_20260608/`。

**产出**:
- `benchmark_results.md` — Markdown 报告
- `trajectory_xy.png` — XY 轨迹对比图
- `error_time.png` — 误差随时间演变
- `error_components.png` — XYZ 各轴误差分量
- `innovation_residual.png` — 滤波器新息/残差

**性能数据**:

| 算法 | XY RMSE | Z RMSE | CEP50 | Max Drift |
|------|---------|--------|-------|-----------|
| Raw DR | 4.305 m | 0.030 m | 4.062 m | 6.557 m |
| Std EKF | 4.378 m | 0.005 m | 4.106 m | 6.703 m |
| ES-EKF | 4.375 m | 0.005 m | 4.102 m | 6.697 m |

**注意**: ES-EKF 未显著优于 Dead Reckoning，这是因为此 MCAP 中 ground truth 来自 `/auv/visual/truth_marker`（10Hz），与 DVL 存在系统性初始偏移，导致 EKF 校正反而引入误差。

> **⚠️ 负结果注记（禁止引入学位论文正文）**：早先用作"修复参照"的 `dvl_fixed_final` 结果（Std/ES-EKF XY≈0.9 m、"改善 95%"）**不可作学术结论**——该 bag 三算法 Z RMSE 均约 12 m（深度维全崩被隐藏）、数据不同源、单 bag 无种子，且"改善 95%"实为三引擎初始化口径不一致（DR 用 truth 起点、ES-EKF 首帧自对齐并手动翻 Z）造成的脚手架伪影。可信结论以公平口径重算（`tools/run_tri_estimator_fair_benchmark.py`）为准：统一初始化后 24 次运行水平 RMSE 三者统计等价（3.197/3.196/3.200 m，属结构性可观性边界），深度 12 m 恒偏伪影已消除。

**注意事项**:
- `--output-dir` 传相对路径时输出到项目内（如 `results/localization/...`）
- 若不传 `--output-dir`，脚本使用 `get_output_dir()` 会输出到 `$AUV_DATA_ROOT/results/localization/...`
- 需要安装 `mcap` 和 `mcap-ros2-support` pip 包

---

## Step 4: 运行 MPC 基准测试

```bash
python3 tools/mpc_test.py
```

**结果**: 成功。

**实际输出路径**: `/auv_data/results/control/mpc_test/20260608_173429/`

> ⚠️ **路径偏差**: 脚本内部使用 `get_output_dir('results/control/mpc_test')`，实际路径为
> `$AUV_DATA_ROOT/results/control/mpc_test/TIMESTAMP/`。
> 此脚本**无** `--output-dir` 参数，无法覆盖。

**产出**:
- `report.md` — 完整性能报告
- `figures/01_mpc_depth_step.png`
- `figures/02_mpc_heading_step.png`
- `figures/03_mpc_cable_tracking_depth.png`
- `figures/04_mpc_cable_tracking_heading.png`
- `figures/05_mpc_combined_summary.png`

**性能数据**:

| 场景 | 指标 | 值 |
|------|------|-----|
| 深度阶跃 | RMSE | 3.968 m |
| 深度阶跃 | 上升时间(90%) | 未达到 |
| 航向阶跃 | RMSE | 21.25° |
| 航向阶跃 | 上升时间(90%) | 未达到 |
| 电缆跟踪 | 深度 RMSE | 4.770 m |
| 电缆跟踪 | 航向 RMSE | 15.74° |

**注意事项**:
- 依赖 `/root/PythonVehicleSimulator/src`（硬编码路径，line 24）
- 依赖 CasADi + IPOPT（`pip install casadi`）
- 此测试无需 rosbag 输入，完全独立运行

---

## Step 5: 运行 BT vs FSM 基准测试

```bash
python3 tests/benchmark_bt_vs_fsm.py
```

**结果**: 成功。

**实际输出路径**: `/auv_data/results/decision/bt_vs_fsm/20260608_173806/`

> ⚠️ **路径偏差**: 同 MPC，使用 `get_output_dir` 输出到 `$AUV_DATA_ROOT` 下。
> 此脚本**无** `--output-dir` 参数。

**产出**:
- `decision_architecture_benchmark.md` — 报告
- `figures/01_reaction_latency_distribution.png`
- `figures/02_chattering_timeline.png`
- `figures/03_complexity_comparison.png`
- `figures/04_expansion_cost.png`
- `figures/05_monte_carlo_survival.png`

**性能数据**:

| 维度 | BT | FSM | BT 优势 |
|------|-----|-----|---------|
| 响应延迟 | 100 ms | 100 ms | 等价 |
| 振荡频率 | 0 Hz | 4.77 Hz | BT 无振荡 |
| 圈复杂度 V(G) | 15 | 40 | ↓62% |
| 扩展成本 | ~8 行/状态 | ~28 行/状态 | ↓71% |
| 蒙特卡洛存活率 | 100% | 100% | 等价 |

**注意事项**:
- 依赖 `brain_linux/src/auv_decision/` 下的引擎模块（需 colcon build 后 PYTHONPATH 正确）
- 依赖 `mccabe` 包（`pip install mccabe`）
- 此测试无需 rosbag 输入，纯内存计算

---

## 发现的文档偏差与修正项

### 1. MCAP 录制损坏问题（严重）

文档未提及 `--duration` 自动停止时 rosbag 可能损坏。需在文档中加入警告。

### 2. `get_output_dir` 实际路径 vs 文档描述

文档 `05_benchmarks.md` 描述输出路径为项目内 `results/control/`、`results/decision/` 等。但实际上：
- 使用 `get_output_dir('results/control/mpc_test')` 时，真实路径 = `$AUV_DATA_ROOT/results/control/mpc_test/TIMESTAMP/`
- 仅当显式传 `--output-dir results/...` 参数时，才会输出到项目内相对路径

**修正**：文档需明确说明双路径机制（显式指定 vs 默认行为）。

### 3. BT 和 MPC 脚本无 `--output-dir` 参数

文档写了 `--output-dir` 用法，但 `mpc_test.py` 和 `benchmark_bt_vs_fsm.py` 实际上没有 argparse 接受此参数。需修正文档或给脚本添加参数。

### 4. 实验录制路径

文档说输出到 `log/experiments/YYYYMMDD_HHMMSS/`，实际输出到 `$AUV_DATA_ROOT/bags/YYYYMMDD_HHMMSS/`（本机为 `/auv_data/bags/...`）。

---

## 产物汇总

| 基准 | 实际输出路径 | 产物 |
|------|-------------|------|
| ES-EKF | `results/localization/验证运行_20260608/` | 4 PNG + 1 MD |
| MPC | `/auv_data/results/control/mpc_test/20260608_173429/` | 5 PNG + 1 MD |
| BT vs FSM | `/auv_data/results/decision/bt_vs_fsm/20260608_173806/` | 5 PNG + 1 MD |
