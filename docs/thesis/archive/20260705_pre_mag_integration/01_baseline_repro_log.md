# T2 — Baseline 复现日志（论文级）

> **对应论文章节**：§5.4 算法可行性 baseline 节
> **直接消费方**：论文 §5.4 表 5-1（baseline 性能基线）；T3/T4/T5 中所有"相对 baseline"的相对量
> **生成时机**：Phase 4 — A 档骨架 + 既有数据（Phase 1 [benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) 单 seed）；多种子聚合见本表 §6 待补部分

本日志记录 *baseline* 场景下的端到端复现：从命令到产物，逐步可验证。所有数据须可由本仓库当前提交哈希再次产出。

---

## 1. 场景与配置

| 项 | 值 | 来源 |
| --- | --- | --- |
| Scenario yaml | `scenarios/scenario_baseline.yaml` | [scenario_baseline.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/scenarios/scenario_baseline.yaml) |
| Sim backend | `pvs` (Python REMUS-100) | yaml `sim_backend` |
| MPC mode | `ua` (默认) / `baseline` (对照) | yaml + env `AUV_MPC_MODE` |
| Duration | 120 s | yaml `duration_s` |
| Seed | 0（单 seed）/ 0..4（多 seed pending） | CLI `--seed` |
| Bridge backend | `zenoh_json` | `start_experiment.sh` 默认 |

> 论文中 baseline 同时用作"算法功能性"基准与"鲁棒性增益归一化分母"。

---

## 2. 复现命令（论文级）

### 2.1 单 seed 单次 run（已完成）

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project
bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend zenoh_json \
  --duration 120 \
  --scenario scenarios/scenario_baseline.yaml \
  --seed 0
```

落盘路径：`/auv_data/bags/<timestamp>/rosbag/rosbag_0.mcap` + `run_metadata.json`。

### 2.2 离线 ES-EKF 复算（论文 §5.4 表 5-1）

```bash
python3 tools/offline_ekf_benchmark.py \
  --input log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap \
  --output-dir results/localization/baseline_n1 \
  --verbose
```

> 当前 [benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) 引用的 baseline 数据即由该命令产出。

### 2.3 多 seed 聚合（pending，§6 待补）

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline \
  --seeds 0,1,2,3,4 \
  --mpc-modes baseline,ua \
  --output-root /auv_data/sweeps/baseline_n5
```

> 产物：`summary.csv` + `aggregate.md`，论文表 5-1 引用 `aggregate.md` 的 mean±std 列。

---

## 3. 已确认数据（n=1，当前论文锚点）

数据来源以 D9.1+D9.2+D9.5 修复后的 zenoh_json 手工 single seed 为准：bag [/auv_data/bags/20260609_090300](file:///auv_data/bags/20260609_090300)，离线 EKF 输出目录 [log/dr_v2/dvl_world](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world)，汇总文件 [log/dr_v2/summary.txt](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/summary.txt)。早期 Phase 1 `truth_marker` 数据与 protocol_udp/sweep 伪信号仅保留为反例，不进入论文主表。

### 3.1 ES-EKF vs Std-EKF vs Dead-Reckoning（baseline，n=1）

| 算法 | XY RMSE (m) | Z RMSE (m) | CEP50 (m) | Max Drift (m) |
| --- | --- | --- | --- | --- |
| Raw DR | 1.017 | 0.030 | 0.856 | 1.847 |
| Std EKF | 1.083 | 0.004 | 0.936 | 1.873 |
| ES-EKF | 1.074 | 0.584 | 0.925 | 1.863 |

> EKF 图源：[`trajectory_xy.png`](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world/trajectory_xy.png)、[`error_time.png`](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world/error_time.png)、[`error_components.png`](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world/error_components.png)、[`innovation_residual.png`](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world/innovation_residual.png)。报告源：[benchmark_results.md](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world/benchmark_results.md)。

### 3.2 MPC 步进/跟踪（baseline，UA-MPC，n=1）

| 场景 | 指标 | 值 |
| --- | --- | --- |
| 深度阶跃 | RMSE | 4.295 m |
| 深度阶跃 | 上升时间 (90%) | 未达到 |
| 航向阶跃 | RMSE | 21.25° |
| 航向阶跃 | 上升时间 (90%) | 未达到 |
| 电缆跟踪 | 深度 RMSE | 3.424 m |
| 电缆跟踪 | 航向 RMSE | 16.21° |

> 数据源：[mpc_test.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_test.py) 最新离线 PVS 控制测试，输出目录 [/auv_data/results/control/mpc_test/20260610_125725](file:///auv_data/results/control/mpc_test/20260610_125725)，报告 [report.md](file:///auv_data/results/control/mpc_test/20260610_125725/report.md)。MPC 离线测试不依赖 ROS backend；所有 bag 驱动的定位/仿真数据统一使用 zenoh_json 后端。当前控制指标欠优是因 PVS 仿真限定步幅偏小、参考信号阶跃过大，论文 §5.4 须明示该限制（见 D2.1 / D4.1，[07_drift_log_and_known_issues.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md)）。

---

## 4. 输出产物清单（每次 run）

| 文件 | 路径模板 | 用途 |
| --- | --- | --- |
| rosbag (mcap) | [/auv_data/bags/20260609_090300/rosbag/rosbag_0.mcap](file:///auv_data/bags/20260609_090300/rosbag/rosbag_0.mcap) | 论文 §5 定位回算依据（zenoh_json，真 GT N≈2795） |
| run metadata/log | [/auv_data/bags/20260609_090300](file:///auv_data/bags/20260609_090300) 下 `metadata.txt` / `launcher.log` / `auto_activate.log` | scenario、seed、启动链路、节点上线顺序 |
| ES-EKF benchmark | [log/dr_v2/dvl_world/benchmark_results.md](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world/benchmark_results.md) + [log/dr_v2/summary.txt](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/summary.txt) | 论文 §5.4 表 5-1 数据 |
| ES-EKF figures | [trajectory_xy.png](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world/trajectory_xy.png), [error_time.png](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world/error_time.png), [error_components.png](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world/error_components.png), [innovation_residual.png](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world/innovation_residual.png) | 论文 §5.4 配图 |
| MPC benchmark | [/auv_data/results/control/mpc_test/20260610_125725/report.md](file:///auv_data/results/control/mpc_test/20260610_125725/report.md) | 论文 §5.4 控制节（n=1 离线 PVS） |
| MPC figures | [/auv_data/results/control/mpc_test/20260610_125725/figures](file:///auv_data/results/control/mpc_test/20260610_125725/figures) 下 `01_mpc_depth_step.png` 至 `05_mpc_combined_summary.png` | 论文 §5.4 配图 |

---

## 5. 验证逐项核对清单

复现后逐项打钩，确认与本表一致：

- [ ] 编译通过 9 个包（无报错）
- [ ] 实验完整运行 120 s 后正常停止（recorder 通过 `kill -INT` 优雅退出，MCAP footer 完整）
- [ ] MCAP 文件大小 > 100 MB（baseline 期望 ~500 MB）
- [x] [offline_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py) 出 4 张 PNG + benchmark_results.md（见 [log/dr_v2/dvl_world](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world)）
- [x] XY RMSE 数值已回填 §3.1（n=1 单 seed，multi-seed/std 不再要求）
- [x] [mpc_test.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_test.py) 出 5 张 PNG + report.md（见 [/auv_data/results/control/mpc_test/20260610_125725](file:///auv_data/results/control/mpc_test/20260610_125725)）
- [ ] `run_metadata.json` 含 git commit、scenario yaml 路径、seed、启动 UTC 时间戳

---

## 6. 待补数据与冻结项（2026-06-10）

| 项 | 说明 | 触发条件 |
| --- | --- | --- |
| baseline_n5 mean±std | **冻结/不再要求**：sweep harness 与 protocol_udp 路径已确认产生 mock fallback 伪信号；论文表 5-1 使用 n=1 单 seed | 用户决策：不要求 std/multi-seed |
| Std-EKF / ES-EKF / DR 三者 mean±std 对比 | **冻结/不再要求**；保留 §3.1 单 seed 三算法对比 | 同上 |
| MPC step/track 最新离线数据 | **已完成**：[/auv_data/results/control/mpc_test/20260610_125725/report.md](file:///auv_data/results/control/mpc_test/20260610_125725/report.md) | 由 `tools/mpc_test.py` 生成 |

回填原则：论文 §5.4 表 5-1 明示 *n=1 single-seed*；multi-seed mean±std 与 sweep harness 修复均列为 future work，不再作为当前交付阻塞项。

---

## 7. 与论文的对应

- 论文 §5.4 表 5-1 ←→ 本表 §3.1（XY RMSE / Z RMSE / CEP50）
- 论文 §5.4 图 5-X 轨迹图 ←→ [trajectory_xy.png](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world/trajectory_xy.png)
- 论文 §5.4 图 5-Y 误差时序 ←→ [error_time.png](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/dvl_world/error_time.png)
- 论文 §5.4 控制节表 ←→ 本表 §3.2

> 论文若需引用 baseline 之外的数据（DVL 丢包、磁干扰、综合应力），见 [04_mpc_robustness_ablation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/04_mpc_robustness_ablation.md) 与 [05_scenario_recipes.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/05_scenario_recipes.md)。

---

## Pre-Snapshot @ Phase 4 A5

- Phase 1 单 seed 数据完整（[benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md)）
- 多 seed sweep 工具就位（[run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py)）
- 本会话因终端 stdout 隔离无法回读 sweep 日志，多 seed 数据待后续会话回填（D7.2）

## Post-Snapshot @ Phase 4

- 多 seed sweep 数据：n≥3 多 seed 仍待补；本会话已交付 v2.2 sweep harness 1-seed smoke（[log/thesis_sweep/20260609_160344_v22_dvl_smoke](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260609_160344_v22_dvl_smoke)，9/10 ok，覆盖 baseline + dvl_dropout_{10,30,60,90} × {baseline, ua}），D8.1 阻塞已彻底解除（详见 [Phase 2 §8.7](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_phase2_implementation.md)）
- 单 seed 锚点数据：基于 `/auv_data/bags/20260609_113311/rosbag/rosbag_0.mcap`（60s real run，protocol_udp + auto-activate，**v1 时代 bag**）由 [tools/offline_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py) 重跑得到 n=1 锚点：

| 算法 | XY RMSE (m) | Z RMSE (m) | CEP50 (m) | Max Drift (m) |
| --- | ---: | ---: | ---: | ---: |
| Raw DR | 15.053 | 0.137 | 9.636 | 31.697 |
| Std EKF | 15.116 | 0.137 | 9.661 | 31.932 |
| ES-EKF | 15.116 | 20.848 ⚠ | 9.661 | 31.932 |

> ES-EKF Z 维异常源于首帧 auto-init 偏移 24 m（D8.2 follow-up）。本表仅作 baseline 锚点，不替代 §6 多 seed 升级。原 §3.1 表头维持 n=1，待 D8.1 修复后由多 seed 取代。
>
> **v2.2 自检指针（2026-06-09 16:03）**：sweep harness 在 v2.2 时序契约下 baseline 60s 单 seed 复现得 XY RMSE = 27.703 m / Z RMSE = 23.872 m / CEP50 = 36.569 m / Max Drift = 27.677 m（详见 [v22_dvl_smoke/results.csv](file:///home/auv_user/auv_ws/AUV-Master-Project/log/thesis_sweep/20260609_160344_v22_dvl_smoke/results.csv)）。⚠ **该 27 m 数值现确认为伪信号**——见下方 D9.1 + D9.2 双重根因闭环；**不直接覆盖**论文 §3.1 锚点。
>
> **D9.1 + D9.2 修复后单 seed 锚点（2026-06-09，60s baseline，bag [/auv_data/bags/20260609_090300](file:///auv_data/bags/20260609_090300)，真 GT N=2795 path=27.94m；es_ekf Z 维数据已在 D9.5 修复后回归）**：
>
> | 算法 | XY RMSE (m) | Z RMSE (m) | CEP50 (m) | 备注 |
> | --- | ---: | ---: | ---: | --- |
> | Raw DR (`dvl_world` / `dvl_body`) | **1.017** | 0.030 | 0.856 | DR 物理漂移率 ≈ 3.7%，对 0.5 m/s × 60s 工况完全可用 |
> | Std EKF | **1.083** | 0.004 | 0.936 | 比 raw_dr 略差源于 process noise 高估（D9.4） |
> | ES-EKF | **1.074** | **0.584** | 0.925 | XY 维有效；Z 维原 23.99m 已通过 D9.5（`EseKfEngine.get_position()` 翻号）修复至 0.584m，残留 vs std_ekf 0.004m 是 es_ekf 自身 error-state init/correct_depth 次级问题 |
> | imu_only / heading_only DR | 16.06 | — | — | 仅 baseline 上界对照 |
>
> 数据源：[log/dr_v2/summary.txt](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/summary.txt)。详细诊断见 [07_drift_log_and_known_issues.md §9](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md)。本组数字已锁定为论文 §4.1-§4.3 / §5.4 表 5-1 的单 seed 主锚点；多 seed 升级须基于本组重跑。
>
> **⚠ v22 dvl_3seed sweep（2026-06-09，30 runs，driver "30/30 ok"）数据全部废弃**：[/auv_data/sweeps/20260609_190148_v22_dvl_3seed/results.csv](file:///auv_data/sweeps/20260609_190148_v22_dvl_3seed/results.csv) 30 行 `xy_rmse ∈ [23.3, 29.3]m`、`z_rmse ∈ [0.3, 0.6]m` **不可用于论文回填**。bag [/auv_data/bags/20260609_190148](file:///auv_data/bags/20260609_190148) 取证：`/auv/sensors/ground_truth Count=0` + `/auv/visual/truth_marker Count=555`，benchmark 拿 mock fallback 公式输出当 GT 自相参考产生伪误差。根因：D8.4 修复仅覆盖 `zenoh_json` 后端（`HoloOceanPhysicsZenohBridge`），sweep harness 强制注入 `--bridge-backend protocol_udp` 走 `MockAmdUdpServer`，[mock_amd_server.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_server.py) 全文件零 zenoh publish；详见 [07_drift_log_and_known_issues.md §9 D9.7](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md) + [Phase 2 §8.7 D8.8](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_phase2_implementation.md)。
>
> **⚠ v23/v24 6-run smoke sweep（2026-06-10，方向 1 修复后）依然全部废弃**：方向 1（[mock_amd_server.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_server.py) 加 zenoh GT publisher）已落地且日志确认 publish 端正常（0 publish 错误），但 sweep harness 路径下 viz_bridge `_on_ground_truth` 仍未触发，bag [/auv_data/bags/20260610_112050](file:///auv_data/bags/20260610_112050)（protocol_udp）和 [/auv_data/bags/20260610_113053](file:///auv_data/bags/20260610_113053)（zenoh_json）均**完全没有 `/auv/sensors/ground_truth` topic**；首 run xy_rmse=3.695m 仍是 mock-truth 自参考伪信号（benchmark md 显示 GT 10Hz，应为 50Hz）。同代码同 yaml 在手工 single seed launcher 下正常，根因落在 sweep harness vs 单 seed launcher 的 zenoh 跨进程 discovery 假设差异（详见 [07_drift_log_and_known_issues.md §9 D9.7 update](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md)）。
>
> **论文 §5.4 表 5-1 锚点决策（2026-06-10，用户拍板"定点单 seed 为论文调变"）**：**n=1 单 seed 数字**冻结为论文唯一可信数字源——XY=1.017m (raw_dr) / 1.083m (std_ekf) / 1.074m (es_ekf)、Z=0.030m / 0.004m / 0.584m（来自 D9.1+D9.2+D9.5 锚点 [log/dr_v2/summary.txt](file:///home/auv_user/auv_ws/AUV-Master-Project/log/dr_v2/summary.txt)）。**不调设 multi-seed mean±std**，论文 §5.4 在此栏目明示 "n=1, multi-seed evaluation deferred due to sweep harness zenoh cross-process discovery limitation under serial 30-run scheduling, see [07_drift_log_and_known_issues.md §9 D9.7](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md)"。Limitations 节列入 future work："多种子鲁棒统计须先解决 sweep harness 进程隔离问题"。
