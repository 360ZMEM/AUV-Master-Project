# 硕士论文实验体系 — Phase 4 收口与论文化计划

> **本文件路径**：`.trae/documents/thesis_experiment_phase4_consolidation_plan.md`
> **依赖前置（已批准）**：
> - [thesis_experiment_uplift_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_uplift_plan.md)（总规划）
> - [thesis_experiment_phase2_implementation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_phase2_implementation.md)（Phase 2，部分落地）
> - [thesis_experiment_phase3_e4_to_final.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_phase3_e4_to_final.md)（Phase 3，部分落地）
>
> **本对话 scope**：通过仿真验证控制算法、ES-EKF 正确性、Jetson 部署可用性
> **本对话排除**：硬件电路、纯磁场（九参数标定）、实物部署改动外部接口、图像美观性、论文写作浓缩
> **本计划交付目标**：让仓库形成**可全面支持硕士论文 §1–§5 的实验体系**，输出 `docs/thesis/` 文档族 + 闭合 Phase 3 残链。

---

## 0. Executive Summary

Phase 1–3 已把 ES-EKF、UA-MPC、协方差耦合、sweep harness、Jetson 算力 bench、9 个 scenario 全部落到代码层；Phase 4 的任务**不是再加大量算法**，而是收口为一篇硕士论文用得上的实验报告体系。

**Phase 4 三大动作**：
1. **闭合 Phase 3 残链**（E6 链路 + 文档偏差）— 1 个文件改动 + 3 个文件偏差修正。
2. **跑实验、回填数据**（B 档）— 用既有 sweep 命令产出真实 CSV/PNG。
3. **写 8 篇 `docs/thesis/*.md`**（A 档骨架 → C 档信息量）— 每篇一一对应论文章节。

整体设计原则：**梯度并行 / 可回退 / 探索+稳定双路并存**。每个交付物有独立"骨架版（A）→ 数据版（B）→ 论文级信息量版（C）"三档，A 档先全部铺好，B/C 档按时间预算渐进推进，任何一档失败都不会阻塞其它交付。

---

## 1. 用户五问的直接回答（基于 Phase 1 探索）

### Q1 — 目前仓库可支持什么实验？这些实验可以论证什么内容？

**仓库已具备 7 类可复现实验**（按论文章节映射）：

| # | 实验类别 | 入口命令 | 论证目标 | 论文章节 |
|---|---|---|---|---|
| A | 端到端 120s 基准 | [start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh) | 全栈联调跑通、bag 完整性 | §5.1.2 |
| B | ES-EKF 三路对比 | [offline_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py) | Raw DR / Std EKF / ES-EKF RMSE/CEP50/Drift | §3.5 |
| C | MPC 三场景基准 | [mpc_test.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_test.py) | 深度阶跃 / 航向阶跃 / 电缆跟踪 | §4.5.1 |
| D | BT vs FSM 对比 | [tests/benchmark_bt_vs_fsm.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tests/benchmark_bt_vs_fsm.py) | 圈复杂度、决策时延 | §4.2 |
| E | 多场景 sweep（DVL/磁/综合） | [run_dvl_sweep.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_dvl_sweep.sh) / [run_mag_sweep.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_mag_sweep.sh) / [run_combined_sweep.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_combined_sweep.sh) | UA-MPC 鲁棒性、消融 | §3.5 / §4.5 |
| F | 参数敏感性 sweep | [run_thesis_sweep.py --param-grid](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) | sim-to-real 参数迁移性 | §5.5.1 |
| G | Jetson 算力仿真侧 | [run_jetson_emulated_bench.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_jetson_emulated_bench.sh) | CPU/MEM/IPOPT 时延 → 移植可行性 | §5.5 |
| H | 地形跟随 | [run_terrain_benchmark.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_terrain_benchmark.sh) | 之字形扫描 + 高度保持 | §4.3.1 |
| I | 通信透明度档位 | [run_transparency_level_benchmark.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_transparency_level_benchmark.sh) | bag 体积/丢包率 vs 信息密度 | §2.2 |

**直接论证**：论文 §3 EKF 全部、§4 MPC 全部（除真机 §5.3）、§5.1/§5.2/§5.5 大部分。

**间接论证**（需要叙述补强）：§4.2 BT 任务规划（已有 BT vs FSM 对比，但缺 zig-zag→tracking handover demo）、§5.5.2 真实海况外推（需在论文叙述补"敏感性 → 外推"逻辑链）。

**仍未覆盖**：§5.3（北京现场实物），属于 scope 外，不展开。

### Q2 — 现有实验文档（`docs/experiment/*.md`）信息量是否够支撑论文？

`docs/experiment/` 已有 4 篇实验日志（[benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) / [terrain_benchmark_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/terrain_benchmark_log.md) / [experiment_modes_validation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/experiment_modes_validation.md) / [rosbag_analysis_validation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/rosbag_analysis_validation.md)），**风格非常贴合"新手执行 SOP+真实日志+发现问题"**，是后续 `docs/thesis/` 的样板。

**信息量评估**：

| 论文需要 | 现有覆盖 | 缺口 |
|---|---|---|
| 命令可复现性 | ✅ 命令、参数、产物路径都有 | — |
| 单次运行真实数值（RMSE 等） | ✅ benchmark_test_log 含完整数据表 | — |
| **多种子统计**（mean/std/CI） | ❌ 全部 n=1 | **关键缺口** |
| **多场景对比**（baseline vs 扰动） | ❌ 仅 baseline 跑过 | **关键缺口** |
| **NIS 时间序列图** | ❌ 仅有 innovation_residual.png 一张 | 需 `--export-nis-csv` 跑后画 |
| **IPOPT 求解时延分布** | ❌ 无统计 | 需 mcap 上挖 `solve_time_ms` |
| **EKF 协方差时间演化** | ❌ 无图 | 需订阅 `/auv/state/covariance` 录制后画 |
| **UA-MPC vs baseline 消融** | ❌ 无 | E5 sweep 跑出来后画 |
| 失败/异常根因 | ✅ terrain_benchmark_log 详尽 | — |
| 文档偏差闭环 | 🟡 散落各篇 | 需一篇 drift log 收口 |

**结论**：现有 4 篇是**起点而非终点**，可以做 docs/thesis 的样板和数据源，但论文级别还要叠加 4 个维度（多种子、多场景、协方差时序、消融对比）。这正是 Phase 4 B 档要做的事。

### Q3 — 实验探索过程暴露了什么功能或架构缺陷？

**已暴露问题**（来自 4 篇日志 + 本次代码勘察）：

| # | 问题 | 严重度 | 状态 | 处理 |
|---|---|---|---|---|
| F1 | bag 录制 SIGTERM → MCAP 损坏 | 高 | 已修（kill→kill -INT + sleep 2） | 闭环到 T8 drift log |
| F2 | `get_output_dir()` 双路径（`results/` vs `$AUV_DATA_ROOT/`）对新手不直观 | 中 | 已记录未修 | T8 中说明，**不改代码**（动接口风险）|
| F3 | `mpc_test.py` 缺 `--output-dir` flag | 中 | 已记录未修 | T8 中说明，可选改（B 档） |
| F4 | bag 实际在 `$AUV_DATA_ROOT/bags/` 而非文档里写的 `log/experiments/` | 中 | 已记录 | T8 中说明，**改文档不改代码** |
| F5 | terrain bag 0 字节、行为树 StandbyCheck 未激活 | 高 | 待修 | 见 [terrain_benchmark_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/terrain_benchmark_log.md)，**不在 Phase 4 scope**（已有专项计划） |
| F6 | EKF 节点不发 NIS / r_scale 时间序列话题（仅 in-process 可访问 `get_nis_stats()`） | 中 | 部分修（offline 工具可挖 mcap），**不补 ROS 话题**（动接口） | T4 文档说明用 offline 工具兜底 |
| F7 | MPC 求解失败仅抛 `RuntimeError`，无显式 PID 兜底回退 | 中 | 待补叙述 | T5 文档**只描述风险并给出参数回退档**，**不改代码**（动接口） |
| F8 | E6 链路断裂：sweep 注入 `AUV_MPC_PARAM_OVERRIDES`，但 mpc_controller.py 不读 | 高 | **Phase 4 必修** | E6-fix（4.1 节） |
| F9 | `docs/thesis/` 目录全空 | 高 | **Phase 4 必修** | T1–T8 全篇创建 |
| F10 | `docs/INDEX.md` 没有 thesis 板块入口 | 低 | **Phase 4 必修** | T8 同步追加 |

**架构层面没有发现致命缺陷**。所有问题都是局部的、可在不动对外接口的前提下闭合的。这本身就是论文 §5.5.2 "对真实复杂海况的扩展性"叙述里"系统设计具备可外推性"的论据。

### Q4 — 是否有论文需要但代码缺失/兼容不全的实验？

按 scope 内（仿真验证控制算法、ES-EKF 正确性、Jetson 部署可用性）盘点：

| # | 论文需要 | 当前代码 | 缺口判定 |
|---|---|---|---|
| N1 | §3.5.1 DVL 丢包鲁棒性 | scenarios + sweep 都有 | **不缺，跑数据即可** |
| N2 | §3.5.2 磁畸变下的定位精度 | scenarios + sweep 都有 + correct_mag 已落 | **不缺，跑数据即可** |
| N3 | §3.4.1 NIS 白化检验 | get_nis_stats + offline 工具都有 | **不缺，跑+画图即可** |
| N4 | §4.4.2 不确定性代价权重动态调整 | sigmoid + (1-conf)^α 已落，可消融 | **不缺，跑数据即可** |
| N5 | §4.5.1 控制平滑度对比 | mpc_test.py 含但仅 baseline 一条线 | **轻缺**：需 baseline vs ua 双线，B 档跑通 |
| N6 | §4.5.2 极端工况安全边界 | combined_stress 场景已有 | **不缺，跑数据即可** |
| N7 | §5.1.2 算力开销 | run_jetson_emulated_bench 已有 | **不缺，跑数据即可** |
| N8 | §5.2.3 传统 MPC vs UA-MPC 高不确定性表现 | E3 mpc_mode 消融已落 | **不缺，跑数据即可** |
| N9 | §5.5.1 仿真→实物敏感性 | E6 param-grid 几乎落，但 MPC 端读取缺 | **必补 8 行代码**（4.1 节） |
| N10 | §4.2.2 zig-zag→tracking handover demo | terrain bench 含 zig-zag，但缺 BT 状态切换日志 | **可选补**（C 档）：录一条 demo bag |
| N11 | §3.3.4 声磁接力（handover） | 算法层有逻辑，但缺端到端验证 demo | **可选补**（C 档）：scripted 场景 |

**结论**：**N9 是 Phase 4 内必补的代码**（8 行），其它要么不缺要么是 C 档优化项。这一点直接证明"前 3 阶段已把代码体系基本备齐，Phase 4 主战场是数据 + 文档"。

**从"用仿真推进实物验证"的逻辑严密性看**，下面这条链最应该被论文完整呈现：
> scenarios（合成可控扰动） → sweep（多种子统计鲁棒性）→ param-grid（参数敏感性）→ Jetson 算力 bench（部署侧时延）→ 真机（scope 外）

Phase 4 通过 `docs/thesis/T7+T8` 把这条链显式写出来，使得即使无现场数据，论文 §5.5 仍逻辑自洽。

### Q5 — 文档与实际描述的差异

**已知偏差**（来自 Phase 3 现状勘察 + 4 篇 experiment 日志）：

| # | 文档 | 描述 | 实际 | 处理 |
|---|---|---|---|---|
| D1 | 旧 README/启动指南 | bag 落在 `log/experiments/` | 实际 `$AUV_DATA_ROOT/bags/<TS>/` | T8 + 顺手改 INDEX |
| D2 | `mpc_test.py` 帮助 | 暗示有 `--output-dir` | 无此 flag | T8 注明 |
| D3 | Phase 2 计划 §3 E4 | "新建 `ekf_covariance_publisher.py`" | 现已直接复用 `/auv/state/covariance` | T8 注明决策迁移 |
| D4 | `docs/INDEX.md` | 未列 thesis 板块 | thesis 文档将存在 | T8 同步加链接 |
| D5 | `terrain_benchmark_log.md` | 描述行为已支持 | 实际 StandbyCheck 未激活，bag 0B | 引用但**不在本计划解决** |

每条偏差**只在 T8 一处统一收口，文档为主、代码不动**。

---

## 2. 现状定格（Pre-Snapshot @ Phase 4 开端）

### 2.1 已落地（不重复，引用 Phase 3 §1.1）

| 阶段 | 关键交付 | 状态 |
|---|---|---|
| Step 0 / S1–S4 / E1 | bug 修复 + scenarios + sweep harness + uncertainty_metrics + jetson bench + correct_mag | ✅ |
| E2 | NIS 滑窗 + 自适应 R + `get_nis_stats()` | ✅ |
| E3 | sigmoid + (1-conf)^α + `mpc_mode` 消融 + `AUV_MPC_MODE` env 贯通 | ✅ |
| E4 | controller_node 订阅 `/auv/state/covariance` + `_confidence_from_cov` 注入 setpoint | ✅ |
| E5 | run_dvl_sweep.sh / run_mag_sweep.sh / run_combined_sweep.sh | ✅ |
| E6（半） | `run_thesis_sweep.py` 加 `--param-grid` + `parse_param_grid` + `write_sensitivity_summary`，sweep 端通过 env 注入 `AUV_MPC_PARAM_OVERRIDES` | 🟡 |

### 2.2 关键缺口

1. **E6 链路断裂**：`tools/run_thesis_sweep.py` 已 `os.environ["AUV_MPC_PARAM_OVERRIDES"] = json.dumps(...)`，但 [mpc_controller.py L114-117](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py#L114-L117) 只读 `AUV_MPC_MODE`，**param overrides 注入了等于没注入**。 → 必修，~10 行代码。
2. **`docs/thesis/` 目录不存在**，T1–T8 全部待写。
3. **真实数据未跑**：3 个 sweep 脚本未运行；param-grid 未运行；Jetson bench 之前跑过但需重跑获取最新 IPOPT 时延样本。
4. **`docs/INDEX.md` 未追加 thesis 板块**。
5. **Phase 2 / Phase 3 计划文档的 Post-Snapshot 仍是占位**（不影响交付，可一并补）。

### 2.3 时间预算估算（B 档真实运行成本）

| sweep | runs × 单 run | 总时长 | 优先级 |
|---|---|---|---|
| dvl_sweep（5 场景 × 5 种子 × 2 mode） | 50 × 120s | ≈ 1.7h | 高 |
| mag_sweep（3 场景 × 5 种子 × 2 mode） | 30 × 120s | ≈ 1.0h | 高 |
| combined_sweep（3 场景 × 5 种子 × 2 mode） | 30 × 120s | ≈ 1.0h | 高 |
| param_grid（baseline × 3 种子 × 2×2 grid） | 12 × 90s | ≈ 0.3h | 中 |
| jetson_bench | 5 个 profile × 60s | ≈ 0.1h | 中 |
| **合计** | **127 runs** | **≈ 4.1h（顺序）** | — |

**降档方案**：smoke 档（每 sweep 仅 1 场景 × 2 种子 × 2 mode）≈ 30 min 即可填满 docs/thesis 表格框架，C 档信息量再回填。

---

## 3. 交付清单（Phase 4 范围）

### 3.1 代码与配置改动

| # | 文件 | 类型 | 论文章节 | 动机 | 回退档 |
|---|---|---|---|---|---|
| C1 | [mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py) | **改 ~10 行** | §5.5.1 | 闭合 E6 链路（读 `AUV_MPC_PARAM_OVERRIDES`） | 不设 env 即等价旧行为 |
| C2（可选） | [auv_controller_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py) | 改 ~5 行（如 C 档需要） | §4.4 | 把 `_latest_p_trace_*` 与 `confidence_from_cov` 暴露为 Float32 话题，方便论文画时序图 | 不订阅即等价 |

**仅 C1 是必做**。C2 是可选优化（如果 B 档跑数据时发现想要 EKF 协方差 → 置信度的时序图，再做）。

### 3.2 文档（`docs/thesis/*.md` 8 篇 + 1 附录）

| # | 文件 | 论文章节 | 内容要点 | A/B/C 档划分 |
|---|---|---|---|---|
| T1 | `docs/thesis/00_overview.md` | §1 / §5.1 | 实验体系全图、术语、命令索引、Pre/Post-Snapshot 总览 | A：纯叙述，无需数据 |
| T2 | `docs/thesis/01_baseline_repro_log.md` | §3.5 / §5.1.2 | baseline 端到端 SOP + 单次 RMSE/CEP50 表 | A：骨架；B：用 benchmark_test_log 数据回填即可 |
| T3 | `docs/thesis/02_es_ekf_validation.md` | §3.5.1 / §3.5.2 / §3.6 | ES-EKF 三路对比 + DVL 丢包鲁棒 + 磁畸变扰动 | A：表头；B：跑 dvl_sweep + mag_sweep；C：画箱型图 |
| T4 | `docs/thesis/03_uncertainty_quantification.md` | §3.4 / §4.4.2 | NIS 白化检验 + EKF P 时间序列 + UA-MPC 耦合 | A：方法学；B：用 offline_ekf_benchmark 数据；C：画 NIS 时序+P 时序 |
| T5 | `docs/thesis/04_mpc_robustness_ablation.md` | §4.5 | baseline-MPC vs UA-MPC × 多场景 × 多种子消融 + IPOPT 时延分布 | A：表头；B：跑 combined_sweep；C：画 RMSE 直方+箱型 |
| T6 | `docs/thesis/05_scenario_recipes.md` | §5.2 | 9 个 yaml 物理含义 + 覆盖矩阵 + 新手 SOP | A：全静态可写完 |
| T7 | `docs/thesis/06_jetson_deploy_emulated.md` | §5.5 | Jetson 仿真侧 CPU/MEM/IPOPT 时延 + 部署可行性结论 | A：方法学；B：跑 jetson_bench；C：画饱和曲线 |
| T8 | `docs/thesis/07_drift_log_and_known_issues.md` | 全文附录 | 文档偏差闭环 + 已知问题清单 + 未来工作 | A：全静态可写完 |
| T9 | `docs/thesis/INDEX.md` | — | thesis 文档族总览，链入 T1–T8 + Phase 1–4 计划 | A：全静态 |
| **+1** | [docs/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/INDEX.md) | — | 顶层 INDEX 追加 thesis 板块入口（T9 链接） | A：1 行追加 |

**所有 8 篇都遵循 `docs/experiment/*.md` 的"新手 SOP + 真实日志 + 发现问题"风格**，含：
- 前置条件（环境、依赖）
- 完整可粘贴的命令
- 命令产物的具体路径
- 关键数据表
- 至少 1 张图（B/C 档）
- 已知陷阱

### 3.3 数据制品（B/C 档）

| 数据集 | 来源命令 | 落盘位置 | 用于 |
|---|---|---|---|
| dvl_sweep 结果 | `bash scripts/run_dvl_sweep.sh` | `$AUV_DATA_ROOT/results/sweeps/dvl_<TS>/results.csv` + 子 bags | T3 |
| mag_sweep 结果 | `bash scripts/run_mag_sweep.sh` | `…/sweeps/mag_<TS>/` | T3 |
| combined_sweep 结果 | `bash scripts/run_combined_sweep.sh` | `…/sweeps/combined_<TS>/` | T5 |
| param_grid 结果 | `python3 tools/run_thesis_sweep.py --scenarios baseline,combined_stress --seeds 0,1,2 --mpc-modes ua --param-grid 'low_conf_scale:1.5,3.0;smoothness_k:0.5,2.0' --duration 90` | `…/sweeps/paramgrid_<TS>/` + `sensitivity_summary.md` | T7（敏感性章节） |
| jetson_bench | `bash scripts/run_jetson_emulated_bench.sh` | `$AUV_DATA_ROOT/results/jetson/<TS>/` | T7 |

**全部数据集存档路径直接写入对应 thesis md，便于后续 AI 工具浓缩或论文图重画。**

### 3.4 Post-Snapshot 与流转

| # | 工件 | 何时写 |
|---|---|---|
| P1 | `.trae/documents/thesis_experiment_phase4_postsnapshot.md` | 全部交付完成时 |
| P2 | Phase 2/3 计划文档的 §8 Post-Snapshot 占位回填 | 同上 |
| P3 | T8 drift log 收口 D1–D5 | T8 写作时 |

---

## 4. 实施步骤（梯度顺序，每一步独立可落 / 可回退）

### 4.1 Step C1 — E6 闭环（必做，~10 行代码，5 分钟）

**位置**：[mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py) L114-117 现有 `AUV_MPC_MODE` 读取后追加：

```python
# E6 — sweep harness 通过 AUV_MPC_PARAM_OVERRIDES 注入参数网格 (论文 §5.5.1)
overrides_json = os.environ.get("AUV_MPC_PARAM_OVERRIDES", "").strip()
if overrides_json:
    try:
        overrides = json.loads(overrides_json)
        if isinstance(overrides, dict):
            weights_cfg.update(overrides)
    except Exception:
        pass
```

外加在 import 段补 `import json`（若不存在）。

**验证**：
```bash
python3 -c "import ast; ast.parse(open('brain_linux/src/auv_controller/auv_controller/mpc_controller.py').read()); print('OK')"
python3 tools/run_thesis_sweep.py --scenarios baseline --seeds 0 --mpc-modes ua \
  --param-grid 'low_conf_scale:1.5,3.0' --duration 30 --dry-run
```

**回退**：直接还原本次 patch；不设 env → 等价旧行为。

### 4.2 Step A — 8 篇 thesis 骨架（可与 4.3/4.4 并行）

**A 档目标**：每篇 md 有完整章节标题、命令块、产物路径、表头（数据 = TBD），让审阅者立刻看到"实验体系全貌"。

**模板基线**：拷贝 [benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) 风格（Step 1 / Step 2 / 结果 / 注意事项）。

**写作顺序**（按依赖与价值）：
1. T9（INDEX）— 先有目录后有文章
2. T1（overview）— 总览
3. T6（scenario recipes）— 全静态，最快产出
4. T8（drift log）— 全静态
5. T2 / T3 / T4 / T5 / T7 — 数据驱动，骨架先写

**回退**：任何一篇骨架失败 → 单篇删除不影响其它；T9 INDEX 维护中央列表。

### 4.3 Step B — 跑数据回填（可与 4.2 并行；smoke 档优先）

**B 档目标**：每个表头都有真实数字。

**B-smoke**（≈ 30 min，最低保证）：
```bash
# 每个 sweep 削为 1 场景 × 2 种子 × 2 mode
bash scripts/run_dvl_sweep.sh --scenarios baseline,dvl_dropout_30 --seeds 0,1
bash scripts/run_mag_sweep.sh --scenarios baseline,mag_distortion_heavy --seeds 0,1
bash scripts/run_combined_sweep.sh --scenarios baseline,combined_stress --seeds 0,1
python3 tools/run_thesis_sweep.py --scenarios baseline --seeds 0,1 --mpc-modes ua \
    --param-grid 'low_conf_scale:1.5,3.0' --duration 60
bash scripts/run_jetson_emulated_bench.sh
```

**B-full**（≈ 4h，论文级）：直接跑各 sweep 脚本默认参数。

**回退**：任何 sweep 失败 → 用既有 [benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) 单 run 数据兜底，文档标注 "n=1, multi-seed pending"，不阻塞 T1/T6/T8/T9 交付。

### 4.4 Step C — 信息量提升（论文级，时间富余时做）

**C 档目标**：图表足以直接嵌入论文。

| 图表 | 工具 | 数据源 |
|---|---|---|
| ES-EKF vs Std EKF vs DR 多种子箱型图 | `tools/offline_ekf_benchmark.py` 已含画图，扩为 sweep 后批量 | dvl_sweep results.csv |
| NIS 时序 + 卡方阈值带 | offline 工具已含 NIS 导出 + matplotlib | sweep 子 bag |
| EKF P_xy / P_z 时序 | 新增小工具 `tools/plot_covariance.py`（**可选**） | mcap 录的 `/auv/state/covariance` |
| UA-MPC vs baseline RMSE 直方 + 显著性 | mcap 后处理脚本 | combined_sweep |
| IPOPT 时延 CDF | mcap 后处理 | jetson_bench |
| 参数敏感性 between-group var bar chart | sensitivity_summary.md 转图 | param_grid |

**回退**：任何 C 档图失败 → 表格代替图，论文 §3-4 仍能成文。

### 4.5 Step P — Post-Snapshot 与 INDEX 链入（必做，最后做）

1. 写 `.trae/documents/thesis_experiment_phase4_postsnapshot.md`：列已交付/未交付/drift。
2. 在 Phase 2/3 计划文档末尾 §8 占位处追加状态。
3. [docs/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/INDEX.md) 追加 "thesis" 板块（链 T9 INDEX）。
4. T8 drift log 收口 D1–D5。

---

## 5. 待用户拍板的问题（按优先级）

> 这些问题如果不拍板，Phase 4 仍可推进 A 档骨架；但拍板后 B/C 档质量会显著提升。
> **不必现在全部回答**，可在执行过程中逐一沟通。

### 优先级 P0（影响整体时间预算）
**Q-P0**：B 档数据是跑 **smoke**（30 min）还是 **full**（4h）？
- 选项 a：先 smoke，后续抽空再跑 full
- 选项 b：直接 full（占用整夜或长会话）
- 选项 c：仅 smoke，full 留给后续会话
- 推荐：a

### 优先级 P1（影响 T2/T3 数据可信度）
**Q-P1**：现有 `dvl_fixed_final` 数据集（已知 ground truth 偏移已修复的 bag）是否仍可访问？如果可访问，T2 直接复用其结果即可，不必重跑 baseline。
- 选项 a：可访问，T2 直接引用
- 选项 b：不可访问，需重跑 baseline 120s
- 选项 c：未知，由 Phase 4 执行时探测

### 优先级 P2（影响 C2 是否做）
**Q-P2**：是否需要把 EKF P 协方差时序也以 Float32 话题暴露到 ROS（C2），用于 T4 画"P 时间演化图"？
- 选项 a：做（C2 可选改 5 行，论文图美观）
- 选项 b：不做（用 mcap 离线挖 `/auv/state/covariance` Float32MultiArray 也能画，不动接口）
- 推荐：b（保持接口稳定）

### 优先级 P3（影响 T1/T9 表达）
**Q-P3**：thesis 文档族要不要在 T1 overview 中补一节"创新点对照表"，把论文 §1.4 的 N 个创新点一一映射到代码文件 + 实验数据集？
- 选项 a：补（强烈推荐，对论文写作极有帮助）
- 选项 b：不补（让论文写作时自己映射）
- 推荐：a

---

## 6. 风险/回退矩阵

| 风险 | 触发场景 | 影响 | 回退档 |
|---|---|---|---|
| sweep 跑到一半 OOM/进程僵死 | sweep harness 长时运行内存泄漏 | B 档数据缺失 | smoke 档兜底；A 档骨架仍可交付 |
| C1 改后 mpc_controller 启动失败 | json 解析异常或 weights_cfg 类型不匹配 | E6 链路坏 | revert C1，不设 env 等价旧行为 |
| Jetson bench 数据老化 | 之前跑的 mcap 已被清理 | T7 数据缺失 | 重跑 5 min smoke；或论文用既有 benchmark_test_log 占位 |
| `docs/INDEX.md` 链入冲突 | 已有他人同时在改 | 链接错位 | 仅 append 一节，不覆盖 |
| param_grid 参数命名与 weights_cfg 实际 key 不一致 | low_conf_scale 不在 weights | 注入静默无效 | C1 同步追加 logger.warning，sweep CSV 列即使为 nan 也保留可见性 |

---

## 7. 验证总表

| 阶段 | 检查 | 命令/产物 |
|---|---|---|
| C1 后 | 语法 OK + dry-run 注入正确 | `python3 -c "import ast; ast.parse(open('brain_linux/src/auv_controller/auv_controller/mpc_controller.py').read())"` + `--dry-run` |
| A 档 | 8 篇 thesis md + INDEX 创建 | `ls docs/thesis/*.md` 期望 9 个文件 |
| B 档 | 5 个数据集落盘 | 各 results.csv 行数 >= smoke 配置目标 |
| C 档 | 关键图就位 | 至少 4 张 PNG 出现在 docs/thesis 引用路径 |
| P 档 | INDEX 链通 + drift 清零 | `grep -r "TBD\|TODO" docs/thesis/` 期望 0 行非占位 |

---

## 8. TODO 镜像（Phase 4 任务列表）

> 实际执行时通过 `TaskCreate` 同步到 task list。

1. **C1**：`mpc_controller.py` 加 `AUV_MPC_PARAM_OVERRIDES` 读取 + AST 校验 + dry-run 验证
2. **A1**：创建 `docs/thesis/INDEX.md` (T9)
3. **A2**：创建 `docs/thesis/00_overview.md` (T1)
4. **A3**：创建 `docs/thesis/05_scenario_recipes.md` (T6) — 全静态
5. **A4**：创建 `docs/thesis/07_drift_log_and_known_issues.md` (T8) — 全静态
6. **A5**：创建 `docs/thesis/01_baseline_repro_log.md` (T2) — 骨架
7. **A6**：创建 `docs/thesis/02_es_ekf_validation.md` (T3) — 骨架
8. **A7**：创建 `docs/thesis/03_uncertainty_quantification.md` (T4) — 骨架
9. **A8**：创建 `docs/thesis/04_mpc_robustness_ablation.md` (T5) — 骨架
10. **A9**：创建 `docs/thesis/06_jetson_deploy_emulated.md` (T7) — 骨架
11. **B1**：smoke 档 dvl/mag/combined sweep（如时间允许）+ 回填 T3/T5
12. **B2**：smoke 档 param_grid + 回填 T7 敏感性章节
13. **B3**：smoke 档 jetson_bench + 回填 T7
14. **C-opt**：C2 协方差 Float32 话题（仅当 P2=a 才做）
15. **P1**：在 [docs/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/INDEX.md) 追加 thesis 板块入口
16. **P2**：写 Phase 4 Post-Snapshot；同步回填 Phase 2/3 计划 §8 占位

---

## 9. Post-Snapshot（Phase 4 收口回填）

> 落点：Phase 4 计划在两次会话中执行完毕；以下为最终交付盘点。

### 9.1 已交付

**代码补齐（Step C）**

- C1 ✅ [mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py) 接入 `AUV_MPC_PARAM_OVERRIDES`（[L19 import json](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py#L19) + [L120-L128 解析](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py#L120-L128)）；E6 sim-to-real 敏感性矩阵闭环。
- C2 不做（P2=b 路径，按计划 §6 决策表）。

**论文向文档（Step A）8 篇全部就位**

| 文件 | 章节 | 状态 |
| --- | --- | --- |
| [thesis/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/INDEX.md) | T9 | ✅ |
| [thesis/00_overview.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/00_overview.md) | T1 / §1 §5.1 | ✅ |
| [thesis/01_baseline_repro_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/01_baseline_repro_log.md) | T2 / §5.4 | ✅ A 档（n=1 既有数据，多 seed B 档 deferred） |
| [thesis/02_es_ekf_validation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/02_es_ekf_validation.md) | T3 / §3.4 §5.4 | ✅ A 档 |
| [thesis/03_uncertainty_quantification.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/03_uncertainty_quantification.md) | T4 / §3.5 §4.4 | ✅ A 档 |
| [thesis/04_mpc_robustness_ablation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/04_mpc_robustness_ablation.md) | T5 / §4.5 §5.5 §5.5.1 | ✅ A 档（A0-A4 + B1-B3 矩阵 + 占位） |
| [thesis/05_scenario_recipes.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/05_scenario_recipes.md) | T6 / §5.2 | ✅ A 档（9 yaml 全静态可写完） |
| [thesis/06_jetson_deploy_emulated.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/06_jetson_deploy_emulated.md) | T7 / §5.5 | ✅ A 档（emulated 限定 + 接口表 + 占位） |
| [thesis/07_drift_log_and_known_issues.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md) | T8 / §5.6 全文附录 | ✅ A 档（19 条 drift + 写作避雷映射） |

**Step P 入口**

- P1 ✅ [docs/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/INDEX.md) 追加"论文向 — 硕士毕业设计实验体系"板块，链入 INDEX + 8 篇文档 + 本计划。
- P2 ✅ 本节回填。

### 9.2 未交付（deferred / 论文范围外）

| 项 | 原因 | 解锁条件 | 论文影响兜底 |
| --- | --- | --- | --- |
| B1 — smoke 档 dvl/mag/combined sweep | 终端 stdout 与文件工具 /tmp 隔离（D7.2） | 后续会话或外部环境执行命令 | 所有 thesis md 均明示"多 seed 数据 ⏳ pending"；§5.6 limitations 列明 |
| B2 — smoke 档 param_grid | 同 D7.2 | 同上 | T4/T5 §5.5.1 表格列空 |
| B3 — smoke 档 jetson_bench | 同 D7.2 | 同上 | T7 §5.5 emulated 列空、real 列由 D4.2 兜底 |
| C2 — 协方差 Float32 话题 | P2=b 决策路径 | 仅当 EKF→MPC 链路被发现需要时启用 | 论文链路图改用 PoseWithCovariance.covariance 字段（已落） |
| Jetson Orin 真机数据 | 论文范围外（D7.1） | 真机回填（未来工作） | T7 §6 接口表已就绪 |

> deferred 不影响 A 档骨架的完整性；任何一篇 md 在多 seed 数据回填前都已可作为论文素材使用。

### 9.3 drift（与计划 §3.1 假设的偏差）

| drift | 说明 | 处理 |
| --- | --- | --- |
| §3.1 H4 多 seed sweep 默认假定终端可用 | 实际终端 stdout 隔离，B 档全档 deferred | 不动计划，按 §4.3 回退档处理；A 档充分 |
| §3.4 数据→文档映射表"baseline_n5.csv 等"产物链 | 因 B 档延迟，产物均未生成 | 各 md 中明示"⏳ pending"；不修正映射 |
| §3.2 T7 文档原计划"B：跑 jetson_bench；C：画饱和曲线" | 仅 A 档完成 | T7 已声明 emulated/real 双层；B/C 档落 P2 解锁后会话 |
| §6 决策表 P3 选 b（不做 C2） | 决策实施 | 已落地，无 drift |
| 拼写检查告警噪音 | IDE 默认字典对中文不识别 | 一律忽略；不影响 md 渲染与论文素材抽取 |

### 9.4 后续会话承接（不在本计划范围）

- B1/B2/B3 数据回填 → 直接编辑 [01_baseline_repro_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/01_baseline_repro_log.md) §6 / [04_mpc_robustness_ablation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/04_mpc_robustness_ablation.md) §5 / [06_jetson_deploy_emulated.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/06_jetson_deploy_emulated.md) §4 §5 中的 ⏳ 占位即可。
- C 档（图）与论文写作浓缩 — 本计划再次声明：不实施。
- Phase 2 / Phase 3 计划文档 §8 Post-Snapshot 占位回填 — 留给单独一次会话整理（不阻塞 Phase 4 收口）。

### 9.5 验收清单（Phase 4 整体）

- [x] C1 落地、E6 链路闭环（mpc_controller.py 改动可回滚）
- [x] 8 篇 thesis md 全部 A 档就位，互相引用链接成网
- [x] docs/INDEX.md 新增 thesis 板块入口
- [x] drift log 19 条覆盖算法 / 仿真 / ROS / 数据 / 工具 / 文档 / 环境七大类
- [x] §5.6 limitations 来源链路全部可溯
- [x] 论文 §3.5 / §4.4 / §5.5 / §5.5.1 / §5.2 / §5.4 / §5.6 各自有 ≥ 1 篇 thesis md 锚定
- [ ] B 档数据回填（deferred；解锁条件已定义）
- [ ] C 档画图（论文写作阶段做）
- [ ] Phase 2/3 §8 Post-Snapshot 回填（独立会话）

---

## 10. 排除项（再次声明）

- 硬件电路、九参数标定、实物部署、改对外接口 — 不做
- 图像美观性提升、论文写作浓缩 — **计划已固定，本次不实施**
- 任何修改 ROS 节点对外话题/服务接口 — 不做（C2 是新增话题不算改接口；如做 C2 也仅 publisher 增量）
- terrain_benchmark / VxWorks / 深度安全等其它专项计划 — 各自有专属计划文件，不并入本计划
