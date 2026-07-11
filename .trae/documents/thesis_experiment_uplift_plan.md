# 硕士论文实验体系提升与实施计划（Thesis Experiment Uplift Plan）

> **本计划文件路径**：`.trae/documents/thesis_experiment_uplift_plan.md`  
> **最终交付目录**：`docs/thesis/*.md`（多份文档）  
> **本对话 scope**：仿真验证控制算法、ES-EKF 正确性、Jetson 部署可用性  
> **本对话排除**：硬件电路、纯磁场内容（如九参数标定）、部署到实物（接口不变）、图像美观性（计划固定，本次不实施）、论文写作浓缩（计划固定，本次不实施）

---

## 0. Executive Summary（一句话版）

把现有"benchmark 一键跑通"型仿真，提升为**多场景 × 多种子 × 双 MPC 模式**的可复现 sweep 体系，并把 ES-EKF 的不确定性量化、UA-MPC 的不确定性耦合、Jetson 上算力开销验证三条论文主链路落地为可一键复现的实验+文档。

---

## 1. 现状分析（Pre-Snapshot）

### 1.1 仓库当前能支持的实验

| 论文章节 | 当前可支持 | 当前不足 |
|---|---|---|
| §3.5 ES-EKF 验证 | ✅ `tools/offline_ekf_benchmark.py` 一键产 ES-EKF / Std-EKF / DR 三路对比 | ❌ 无多种子 sweep；❌ DVL 丢包/磁畸变需手动改配置；❌ 无 NIS 残差白化检验 |
| §4.5 控制鲁棒性 | ✅ `algorithm/auv_mpc_controller.py` 已含置信度自适应权重骨架（`low_conf_scale`、`low_conf_ctrl_scale`） | ❌ 阶跃门限 → 平滑 sigmoid 未做；❌ EKF P 协方差未耦合到 MPC；❌ 无 baseline vs UA 消融对比；❌ 无控制平滑度指标 |
| §5.2 数字孪生 sim 验证 | ✅ HoloOcean + PVS 双后端；✅ `mock_amd_chaos.py` 已有 dvl_freeze/imu_drift/depth_spike/mag_saturation 注入 | ❌ 无标准化场景配方（已建 9 个 yaml，但驱动器缺）；❌ 无 sweep 结果汇总 CSV |
| §5.5 Sim-to-Real 迁移 | ❌ Jetson 算力开销验证缺失 | ❌ 无 Jetson 仿真侧的延迟/CPU/MEM 基准脚本 |

### 1.2 既有实验文档充分性评估

参考 `docs/experiment/`：
- `benchmark_test_log.md`：单次 120s baseline 完整跑通日志，含 RMSE/CEP50/Max Drift 表格 → **覆盖 §3.5.1 baseline，但缺 §3.5.1 鲁棒性（多丢包率）和 §3.5.2 磁畸变两章节**
- `experiment_modes_validation.md`：MCAP 录制问题排查日志 → 工程价值高，论文不直接用
- `rosbag_analysis_validation.md`：分析工具一致性日志 → 工程价值高，论文不直接用

**结论**：现有文档支撑度仅约 30%，需要新增 6+ 篇 thesis 实验文档，覆盖论文 §3.5 / §4.5 / §5.2 / §5.5。

### 1.3 Phase 1 探索暴露的代码 bug（已通过 Step 0 修复）

| # | 文件 | 问题 | 状态 |
|---|---|---|---|
| B1 | `algorithm/es_ekf.py` L173-195 | IMU 加速度计偏置预标定符号约定错（`b_a = mean_acc - g_n`）—— 偏置方向与 `predict()` 公式不一致 | ✅ Step 0 已修 |
| B2 | `tools/offline_ekf_benchmark.py` L638 | ES-EKF 深度被双重取负（外部传 `-depth_m`，内部又转 NED 取负） | ✅ Step 0 已修 |
| B3 | `tools/offline_ekf_benchmark.py` L532-572 | Std-EKF 四元数 `state[6:10]` 加法后未归一化 | ✅ Step 0 已修 |
| B4 | `tools/offline_ekf_benchmark.py` L1118-1182 | `event_ts in truth_timestamps_ns`（list 查找）O(N²) | ✅ Step 0 已修（改 set） |

### 1.4 已落地的实施进度

- ✅ **Step 0**：4 个 bug 全部修完
- ✅ **S1**：`scripts/start_experiment.sh` 加固完成（新增 5 个 CLI flag、cleanup 改为轮询 finalize、scenario/seed/mpc_mode 注入为环境变量）
- ✅ **S2 前半**：`scenarios/*.yaml`（9 个）+ `scenarios/README.md` 完成

### 1.5 文档与实际描述差异（顺手记录）

- `docs/experiment/benchmark_test_log.md` Step 2 提到 "已修复 kill → kill -INT"，实际在 S1 后改为基于 finalize 轮询 + SIGTERM 兜底 → **Final 阶段同步该日志**
- `docs/experiment/rosbag_analysis_validation.md` 提到的 Std-EKF 在某些场景"误差异常"现象部分可被 Step 0 B3 解释（四元数未归一化）→ **Final 阶段补一句根因说明**
- `docs/user-guide/05_benchmarks.md` 与新 sweep 体系需建立交叉链接 → **Final 阶段加链接**

---

## 2. 核心决策（已用户拍板）

| # | 决策 | 选项 | 影响 |
|---|---|---|---|
| D1 | 磁观测代码范围 | **B：仿真观测最小钩**（不做实测九参数标定） | E1 仅在 ES-EKF 加 `correct_mag()` + 仿真侧最小生成路径 |
| D2 | UA-MPC 改造深度 | **B：平滑 sigmoid + EKF 协方差耦合 + 消融开关** | E3+E4 联动 |
| D3 | Bug 修复策略 | **A：Step 0 全部修复 + 重跑全部已有基准** | benchmark 重跑落 `01_baseline_repro_log.md` |

---

## 3. 交付物清单（最终是这些）

### 3.1 代码与配置（按梯度顺序，可独立回退）

| 阶段 | 路径 | 类型 | 状态 | 论文章节映射 |
|---|---|---|---|---|
| Step 0 | `algorithm/es_ekf.py` | 修 | ✅ 已落 | §3.3 ES-EKF 正确性前提 |
| Step 0 | `tools/offline_ekf_benchmark.py` | 修 | ✅ 已落 | §3.5 / §5.2 公平基准前提 |
| S1 | `scripts/start_experiment.sh` | 增强 | ✅ 已落 | §5.2 实验入口 |
| S2a | `scenarios/*.yaml`（9 个）+ `scenarios/README.md` | 新建 | ✅ 已落 | §3.5 / §4.5 / §5.2 配方 |
| S2b | `tools/run_thesis_sweep.py` | 新建 | ⏳ 待做 | §3.5 / §4.5 / §5.2 sweep 驱动 |
| S3 | `tools/uncertainty_metrics.py` + `offline_ekf_benchmark.py --export` | 新建/增强 | ⏳ 待做 | §3.4 / §4.5 度量 |
| S4 | `scripts/run_jetson_emulated_bench.sh` | 新建 | ⏳ 待做 | §5.5 Sim-to-Real |
| E1 | `algorithm/es_ekf.py::correct_mag()` + ROS 桥订阅钩 + `feature_flags` 开关 | 新增 | ⏳ 待做 | §3.3.3 磁观测模型 |
| E2 | `algorithm/es_ekf.py` NIS 滑动窗口 + 自适应 R | 新增 | ⏳ 待做 | §3.4.1 SNR 自适应 |
| E3 | `algorithm/auv_mpc_controller.py` 阶跃→sigmoid + (1-conf)^α 跟踪权重 | 改 | ⏳ 待做 | §4.4.2 不确定性代价 |
| E4 | `ekf_covariance_publisher.py`（ROS2 节点）+ MPC 订阅 + `--mpc-mode` 接通 | 新建 | ⏳ 待做 | §4.4 EKF→MPC 耦合 |
| E5 | DVL 丢包 + 磁畸变 + 综合应力 sweep 命令脚本（不重复创建 yaml，直接用 S2a） | 新建脚本 | ⏳ 待做 | §3.5.1 / §3.5.2 / §4.5 |
| E6 | sweep 加参数扰动循环 + ANOVA 风格分解 | 新增 | ⏳ 待做 | §5.5 敏感性 |

### 3.2 文档（`docs/thesis/*.md`，**8 篇**）

| # | 文件名 | 论文章节映射 | 内容要点 |
|---|---|---|---|
| T1 | `docs/thesis/00_overview.md` | §1 / §5.1 | 实验体系全图、术语表、命令脚手架索引、Pre/Post-Snapshot |
| T2 | `docs/thesis/01_baseline_repro_log.md` | §3.5 baseline / §5.1.2 评价指标 | Step 0 修复后的 baseline 重跑日志（覆盖 `benchmark_test_log.md` 数据） |
| T3 | `docs/thesis/02_es_ekf_validation.md` | §3.5.1 / §3.5.2 / §3.6 | ES-EKF 正确性 + DVL 丢包鲁棒性 + 磁畸变扰动验证 |
| T4 | `docs/thesis/03_uncertainty_quantification.md` | §3.4 / §4.4.2 | NIS 白化检验 + EKF P 协方差落 ROS 话题 + UA-MPC 耦合验证 |
| T5 | `docs/thesis/04_mpc_robustness_ablation.md` | §4.5 | baseline-MPC vs UA-MPC 在 7 个场景 × 5 种子下的消融对比 |
| T6 | `docs/thesis/05_scenario_recipes.md` | §5.2 | 9 个 yaml 场景的物理含义、覆盖矩阵、新手运行 SOP |
| T7 | `docs/thesis/06_jetson_deploy_emulated.md` | §5.5 | Jetson 模拟侧的延迟/CPU/MEM 基准（不实物） |
| T8 | `docs/thesis/99_repo_doc_drift_log.md` | — | 1.5 节差异修订日志（顺手解决） |

每篇文档都包含：**新手命令清单 + 期望产出 + 实验结果摘要 + 错误处理（提及不展开）**，风格仿照 `docs/experiment/benchmark_test_log.md`。

---

## 4. 实施路线（按梯度顺序，可并行/可回退）

### Step 0 — 阻断式 bug 修复 ✅（已完成）

仅作记录，不再展开。

### S1 — 录制工作流加固 ✅（已完成）

仅作记录。

### S2 — 标准化场景配方（部分完成）

- ✅ S2a：9 个 yaml + README
- ⏳ **S2b**：`tools/run_thesis_sweep.py`
  - CLI：`--scenarios baseline,dvl_dropout_30,... --seeds 0,1,2,3,4 --mpc-modes ua,baseline --duration 120`
  - 三层循环：`for scenario in scenarios: for seed in seeds: for mpc_mode in mpc_modes:`
  - 每个 (scenario, seed, mpc_mode)：`bash scripts/start_experiment.sh --sim-backend pvs --scenario <yaml> --seed <int> --mpc-mode <mode> --duration <N> --record-format mcap`
  - 完成后调 `tools/offline_ekf_benchmark.py --input <bag>` 产出 RMSE/CEP50；额外提取控制平滑度（控制差分均方根）
  - 汇总：`log/thesis_sweep/<timestamp>/results.csv`，列：scenario,seed,mpc_mode,xy_rmse,z_rmse,cep50,ctrl_smooth,duration
  - 失败兜底：单个 run 失败不中断 sweep，记录到 `failures.log`

### S3 — 不确定性度量与图导出（待做）

- `tools/uncertainty_metrics.py`：从 bag 提取 EKF P trace、新息、NIS 时间序列；输出 CSV + matplotlib 图
- `tools/offline_ekf_benchmark.py --export {pdf,png,both}` + `--export-tex`：把现有 4 张 PNG 改为同时落 PDF（论文用），并可选导 TeX 表（RMSE/CEP50）

### S4 — Jetson 算力侧基准（待做）

- `scripts/run_jetson_emulated_bench.sh`：在 `brain_linux` 节点上启用 `--ros-args --remap __ns:=/jetson_emu`，套 `tegrastats`/`top` 风格采样脚本（在仿真主机上模拟 5 分钟），产 CPU%/MEM/100ms 滚动延迟分布
- 不需要真实 Jetson；本次只验证"在算力受限场景下软件栈仍可工作"

### E1 — ES-EKF 磁观测最小钩（待做，对应决策 D1=B）

- `algorithm/es_ekf.py`：新增 `correct_mag(mag_body, ts_ns, R_mag)`，按线性化的毕奥-萨伐尔最近距离反演埋深；保留 `feature_flags["enable_mag_correction"]` 开关，默认 `False`
- ROS 桥仅订阅，不接入主线 fallback；论文用为额外章节

### E2 — NIS 滑动窗口 + 自适应 R（待做）

- `algorithm/es_ekf.py`：在 `correct_dvl_world` / `correct_depth` 完成后记录 NIS = innovation^T S^-1 innovation；滑动窗 N=50；当 NIS 均值 > 阈值时按倍率放大 R

### E3 — MPC 平滑置信度 + 消融开关（待做，对应决策 D2=B）

- `algorithm/auv_mpc_controller.py`：把 L210-235 的阶跃门限改为 sigmoid（参数 `confidence_smoothness_k`）；权重缩放改为 `(1 - conf)^alpha`
- 新增 MPC 模式：`mode = "baseline"` 时全部置信度通路短路（等价旧 PID 风格权重），`mode = "ua"` 启用平滑通路
- 透出参数：`mpc_mode` 通过 `AUV_MPC_MODE` 环境变量从 `start_experiment.sh` 注入

### E4 — EKF→MPC 协方差耦合（待做）

- 新建 ROS2 节点 `ekf_covariance_publisher.py`：把 EKF P 矩阵关键对角分量发到 `/auv/ekf_covariance`
- MPC 控制器订阅，融合到 `confidence` 输入：`conf = exp(-trace_xy / sigma)`，sigma 可调
- `--mpc-mode ua` 启用此通路；`baseline` 走默认置信度（来自 `synthetic_sensors`）

### E5 — 三场景 sweep 命令脚本（待做）

- 不另建 yaml（用 S2a 已有的）
- 写 3 个一行脚本：`run_dvl_sweep.sh`、`run_mag_sweep.sh`、`run_combined_sweep.sh`
- 每个内部就是 `tools/run_thesis_sweep.py --scenarios ... --seeds 0..4 --mpc-modes baseline,ua`

### E6 — 参数扰动 sweep + 敏感性分解（待做）

- 在 `run_thesis_sweep.py` 加 `--param-grid` 选项，支持对 `low_conf_scale`、`confidence_smoothness_k` 进行网格扫描
- 输出 `sensitivity.csv`，主因素方差占比（不上完整 ANOVA，简化的 ratio-based 即可，论文叙述够用）

### Final — 文档撰写（待做）

按 §3.2 表格依次写 8 篇 `docs/thesis/*.md`，并：
- 更新 §1.5 的差异点（写入 T8 = `99_repo_doc_drift_log.md`）
- 在 `docs/INDEX.md` 加 thesis 板块链接
- 在 T1 内填写 Post-Snapshot：sweep 结果表 + 关键图链接 + Final 状态

---

## 5. 风险与回退矩阵

| 风险 | 影响 | 回退策略 | 回退点 |
|---|---|---|---|
| E1 磁观测在某些场景使估计发散 | 论文 §3.3.3 数据 | `feature_flags["enable_mag_correction"] = False`，仅论文截图 | E1 内部 |
| E3 sigmoid 平滑参数不合适导致 MPC 抖振 | §4.5 数据 | 保留 baseline 模式作为对照；`--mpc-mode baseline` 一键回退 | E3 内部 |
| E4 EKF→MPC 通路在 sim 抖动 | §4.5 / §3.4 | 通过 `--mpc-mode baseline` 完全短路 | E4 入口 |
| run_thesis_sweep 单次失败 | sweep 不完整 | 失败 run 写 `failures.log`，sweep 不中断；事后单跑补齐 | S2b 内部 |
| Jetson 算力 emulated 不准 | §5.5 信度 | 文档明确"emulated, not on-device"，避免过度声明 | S4 / T7 文档 |

并行性：E1/E2 可并行；E3/E4 串行（E3 先）；E5 依赖 E3/E4 全部就绪；E6 依赖 E5；Final 文档可逐个独立完成。

---

## 6. 验证步骤（每阶段完成后做）

| 阶段 | 验证命令 | 通过条件 |
|---|---|---|
| Step 0 后 | 用现有 MCAP 重跑 `offline_ekf_benchmark.py`，对比修复前 | ES-EKF Z 维不再持续偏负；Std-EKF 不再因四元数发散 |
| S1 后 | `bash scripts/start_experiment.sh --duration 30 --record-format mcap` | 退出后 mcap 文件可被 `mcap` 库正常解析 |
| S2 后 | `python3 tools/run_thesis_sweep.py --scenarios baseline --seeds 0 --duration 30` | 产出 `results.csv` 1 行，无异常 |
| S3 后 | `--export both` | 同时产出 PNG + PDF |
| S4 后 | `bash scripts/run_jetson_emulated_bench.sh --duration 60` | 产出 `cpu_mem.csv` 与延迟分布图 |
| E1-E2 后 | 启 `enable_mag_correction=True` 跑 baseline | 不发散；NIS 时间序列落盘 |
| E3-E4 后 | sweep 跑 `mpc-modes baseline,ua` 各 5 种子 | UA-MPC 在高扰动场景 RMSE 改善 ≥ 阈值（具体数据由实验定） |
| E5-E6 后 | sweep 全 7 场景 × 5 种子 × 2 模式 = 70 runs | 无 critical failure；results.csv 全填 |
| Final | 8 个 thesis 文档完成 | 互链清晰；命令可被新手按图索骥跑通 |

---

## 7. TODO 状态镜像

| # | 任务 | 状态 |
|---|---|---|
| 1 | Pre-Snapshot 现状记录 | ✅ |
| 2 | Step 0 ES-EKF IMU bias fix | ✅ |
| 3 | Step 0 offline_ekf_benchmark depth fix | ✅ |
| 4 | Step 0 Std-EKF quaternion normalization | ✅ |
| 5 | Step 0 O(N²) optimization | ✅ |
| 6 | S1 start_experiment.sh hardening | ✅ |
| 7 | S2a scenarios/*.yaml + README | ✅ |
| 8 | S2b tools/run_thesis_sweep.py | ⏳ |
| 9 | S3 uncertainty_metrics + benchmark export | ⏳ |
| 10 | S4 run_jetson_emulated_bench.sh | ⏳ |
| 11 | E1 correct_mag() + 钩子 | ⏳ |
| 12 | E2 NIS + 自适应 R | ⏳ |
| 13 | E3 sigmoid + 消融开关 | ⏳ |
| 14 | E4 ekf_covariance_publisher + MPC 订阅 | ⏳ |
| 15 | E5 三场景 sweep 命令脚本 | ⏳ |
| 16 | E6 参数扰动 + 敏感性 | ⏳ |
| 17 | Final 8 篇 docs/thesis/*.md + drift log + INDEX 链接 | ⏳ |

---

## 8. Pre-Snapshot（实施前总结，定格）

- 仓库主线启动：`cd scripts && bash start_experiment.sh --sim-backend pvs --duration 120` 可跑
- ES-EKF 三路对比：`tools/offline_ekf_benchmark.py` 可跑（**Step 0 修复后**指标方有意义）
- 已存在的实验文档 3 篇：覆盖单次 baseline、MCAP 录制踩坑、分析工具一致性，**对论文支撑度 ~30%**
- 已落地：Step 0 + S1 + S2a；剩 S2b/S3/S4/E1-E6/Final
- MPC 已有"低置信度切换"骨架（阶跃形式）；EKF P 未发布；NIS 未度量；磁观测未接入；Jetson 算力侧无基准

## 9. Post-Snapshot（实施后总结，待 Final 阶段填写）

> 占位：Final 阶段完成后回填。
> 必填字段：
> - 8 篇文档清单 + 行数
> - sweep 70 runs 完成率
> - baseline vs UA-MPC 在高扰动场景的 RMSE 改善百分比
> - Jetson emulated 60s 跑下 100ms 滚动延迟 P95
> - 变化的代码文件清单（git diff --stat 概要）

---

## 10. 不在本次实施范围（明确排除）

- 图像美观性提升（统一字体/颜色/坐标轴样式）
- 论文写作浓缩（AI 工具加工正文段落）
- 实物部署（Jetson 真机；不改对外接口）
- 硬件电路、九参数标定相关代码

以上 4 项**计划已固定**，本次只交付支撑它们的代码与数据基础。
