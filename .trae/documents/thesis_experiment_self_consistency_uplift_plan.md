# 实验深入挑刺与自洽性提升 — 综合实施计划 v2

> 状态：计划（Plan Mode）。本计划基于对全部实验产物、论文文档、源代码的**批判性通读 + 离线探针实测**，已逐项核对磁盘真实状态。
> 语言约定：正文中文，技术标识符/路径/代码英文。
> **v2 关键变更**：通读 + 实测**推翻了 v1 的核心诊断**（详见第二节）。原 v1 把"图像怪异"归因于控制器发散；实测证明**控制器其实正常工作**，真根因是**度量/分析层的 datum（基准面）bug 与 provenance 不一致**。本 v2 据此重排优先级，并纳入用户三项新决策。
> 用户三项决策（本轮 AskUserQuestion）：①MPC terrain"空转 + depth_error 7m 失真"=**彻查并真修复**；②solve_time 0ms 佐证=**轻量微基准 + 系统级重跑两者都做**；③范围边界=**全部纳入分级修（P0 本轮修，P1/P2 写明确待办 + 诚实边界声明）**。

---

## 一、Summary（目标）

让全部图、表、数值、结论可审计、自洽、可复现，达到中期答辩与毕设 Ready 标准。本计划解决三类问题：

1. **度量/分析层 datum bug（v2 新认定的真根因，P0）**：localization 用**常值 `seabed_depth_m=15.0`** 算 clearance、用 `target_depth=4.0` 算 depth_error，污染了所有下游 summary/图像，制造出"2D 平直海底 vs 3D 起伏"矛盾与"伪 6.6m 深度误差"。
2. **软件实现缺口的"数据佐证"补齐（P0）**：`solve_time` 代码已真实计时（WP-B 落盘），但 `analyze_bag` 从未把它抽进 summary → 论文仍显示 0ms。需补抽取 + 轻量微基准双佐证；并回查 WP-C 是否在"修一个 datum 误导出的假漂移"。
3. **物理建模与实验脱节 + 自洽性遗留项（P1/P2）**：第 2 章（三相螺旋漏磁、杆臂/安装角标定、网络抖动）仅理论无实验 → 补 3 组过渡实验；以及 truth-topic 不一致、磁通道空、extrinsics 2/3 seed、n=1、双 INDEX 树等 → 分级修 + 诚实边界声明。

---

## 二、Current State Analysis（v2：批判性通读 + 实测推翻 v1 诊断）

### A. 决定性诊断推翻（本轮最大成果，基于 rerun bag `terrain_following_20260619_222639` 离线探针实测）

**结论：控制器正常工作；"怪异"主要来自度量/分析层。**

1. **控制器其实在跟随海底**。实测 rerun bag 的真实 DVL 离底高度 `/auv/sensors/altitude`：n=2786、mean=**2.83m**（≈3m 目标）、起伏 1.4–4.3m。证明 MPC/PID terrain **确实在收紧 clearance 到 ~3m**，并非"空转"。
2. **`solve_time` 已真实，只是没被抽进 summary**。实测 `/auv/controller/debug` 的 `solve_time_ms`：mean=**10.59ms**（9.3–12.7），WP-B 修复已生效。但 [analyze_bag.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py) 的 `export_statistics_tables`（L1163-1175）与 `compute_summary_metric_rows`（L1092-1144）**无任何 solve_time 字段**，故论文 05 章仍呈 0ms。
3. **真根因①：常值海底 datum bug**。[auv_localization_node.py:142](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_localization/auv_localization/auv_localization_node.py#L142) declare `seabed_depth_m=15.0`（[L171](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_localization/auv_localization/auv_localization_node.py#L171) read），[L331-332](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_localization/auv_localization/auv_localization_node.py#L331-L336) `seabed_clearance_m = seabed_depth_m - depth_m`（常值 datum，忽略真实起伏地形）；该节点[未订阅 `/auv/sensors/altitude`](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_localization/auv_localization/auv_localization_node.py#L208-L211)（真 DVL clearance 未用于 clearance 计算）。后果：派生海底 `seabed_depth_derived = depth + clearance = depth + (15−depth) ≡ 15`，恒为常值 → **这就是"2D 平直海底 / 3D 起伏"矛盾的真根因**（同一物理量两套数据源）。实测 diag clearance mean=**4.39m**（失真，与真 altitude 2.83m 差 1.5m）。
4. **真根因②：depth_error 度量口径错**。[auv_localization_node.py:353-354](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_localization/auv_localization/auv_localization_node.py#L353-L354) `depth_error = current_depth - target_depth`，其中 `target_depth` 来自 setpoint depth（BT 决策的定深目标，实测恒 **4.0m**）。在 **altitude-follow / terrain 模式**下，AUV 跟的是离底高度而非绝对深度 4.0m，故此口径产生**伪 6.6m"深度误差"**（实测 diag.depth_error_m mean=6.613 / diag.target_depth_m mean=4.000）。`depth_error_rmse≈6.4-7.3m` 完全是这个口径 bug，**不是控制误差**。
5. **WP-C 可能是误诊（需回查）**。v1 WP-C（`buoyancy_term=-0.5` + `ki_z=0.1` 积分补偿，[params.yaml:118-129](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.yaml#L116-L129)）针对的"深度 12m→9.3m 上漂"，实测在 baseline（CONSTANT，target=4.0）模式是**正常缓慢收敛**而非发散；terrain 模式 altitude≈2.83m 本就达标。`buoyancy_term` 注释里"观测上漂≈0.02m/s"很可能是 datum 误导出的**假象**。→ 需回查，必要时回退。

### B. 数据流佐证（analyze_bag 为何用了污染值而非真值）

- [synthesize_diagnostics_from_odometry](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py#L687-L752) 会用真点云 `nearest_terrain_depths(...)` 派生 clearance，**但仅在 `/auv/diagnostics` 缺失时触发**。实跑时 `/auv/diagnostics` 存在（596 msg，由 [decision_node.py:123](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros/decision_node.py#L123) 发布、内含 localization 算出的常值 datum clearance + 4.0 口径 depth_error）→ analyze_bag 实际取的是**污染值**。
- `compute_summary_metric_rows`（[L1112-1137](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py#L1112-L1137)）的 clearance/depth_error 全部从 `diagnostics.seabed_clearance_m`/`depth_error_m` 取 → 全链路继承污染。
- 真点云 `data.terrain_points_xyz`（[read_bag_data L536-539](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py#L536)，topic `/auv/visual/seabed_cloud`）与真 `/auv/sensors/altitude` **都在 bag 里可用**，只是没被 summary 通路使用 → 这正是修复抓手。

### C. v1 已确认仍成立的问题（保留）

1. **warm-up 污染**：旧 run（如 `terrain_following_20260610_175154/pid_terrain`）`seabed_clearance_std≈0.001` 而 `min` 偏离均值上百倍 std = 初始化过渡段污染。WP-A 的 warm-up 过滤（默认 skip 10s）已在 rerun 生效。
2. **平面路径钝化**：[mpc_xy_yaw_extreme_benchmark.py:82](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_xy_yaw_extreme_benchmark.py#L82) `s_turn_short_wave` 波长 11m/幅值 4.8m，对欠驱动 AUV 转弯极限过苛 → 两控制器"切弯"（WP-E 已加 `s_turn_long_wave`，待运行验证）。
3. **`best_comparison` yaw-RMSE reduction = -8141%**（近零分母爆炸，WP-E 已加 `safe_reduction_pct`，待验证）。
4. **"开挂真值"是误判**（v1 已澄清，仍成立）：[auv_controller_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py) 仅用 `/auv/state/filtered`（ES-EKF），真值仅离线评分 → 闭环系统，文档澄清即可，不改控制代码。

### D. v2 新审计发现（用户已批"全部纳入分级修"）

1. **truth-topic 不一致**：baseline 相用 `/auv/visual/truth_marker`，terrain 相用 `/auv/sensors/ground_truth` → 跨相 RMSE 口径不齐（P0：统一）。
2. **磁通道从未填充**：summary `magnetic_sample_count=0`、`magnetic_peak_t=nan`（P1：补采集或诚实声明）。
3. **extrinsics 仅 2/3 seed OK**：`extrinsics_main_3seed` 低于报告自定阈值（P1：补 seed 或调阈值 + 声明）。
4. **n=1 baseline 冻结**：单次实验无统计置信（P2：声明边界 / 后续补重复）。
5. **双 INDEX 树**：`docs/thesis/INDEX.md` vs `docs/thesis/paper/INDEX.md`，05 章拆 base+_continued（P2：合并或标注主从）。
6. **05 章 0ms vs 08 章非零 solve time 矛盾**：[08_terrain_following_pid_mpc_status.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/08_terrain_following_pid_mpc_status.md) 已有 13.62/9.82/18.59ms，与 05 章 0ms 自相矛盾（P0：solve_time 抽取后统一）。

---

## 三、Proposed Changes（按工作包，v2 重排优先级）

> **执行顺序**：P0-1（度量 datum 修复）→ P0-2（solve_time 抽取 + 微基准）→ P0-3（WP-C 回查）→ P0-4（truth-topic 统一）→ 统一重分析/必要时重跑 → WP-D（图像）→ WP-E 运行验证 → WP-F（3 组新实验）→ P1/P2 分级处理 → WP-G（文档闭环）。
> 已落盘的 WP-A/B/C 代码改动**保留**（除 WP-C 待回查），rerun bag `terrain_following_20260619_222639` 已具备真 altitude/真点云/真 solve_time，故 P0 多数为**离线重分析**，未必需要再次实时重跑。

### P0-1：度量 datum 修复（analyze_bag 用真 altitude / 真点云重算 clearance + 修 depth_error 口径）★核心

- 文件：[tools/analyze_bag.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py)
- What/How：
  1. **新增订阅真 altitude**：在 `read_bag_data`（L445+）读取 `/auv/sensors/altitude`（真 DVL 离底高度）为 `data.altitude`（新 `ScalarSeries`）。
  2. **clearance 优先用真值重算**：`compute_summary_metric_rows`（L1112-1137）与图像通路改为——若 `data.altitude` 可用，`seabed_clearance := altitude`（真 clearance）；否则若真点云 `terrain_points_xyz` 可用，用 `nearest_terrain_depths(est_xy)` 派生 `clearance = seabed_depth_pc − depth`；二者皆缺才回退 diagnostics 常值（并在 summary 标 `clearance_source` 字段：`real_altitude` / `terrain_cloud` / `diag_constant_datum`）。
  3. **修 depth_error 口径（altitude-follow 模式自适应）**：summary 新增 `clearance_error_to_target_m`（=`altitude − 3.0`，terrain 模式真正的"跟踪误差"）作为主指标；保留 `depth_error_rmse_m` 但**改为对真 target 评分**或在 terrain 模式标 `N/A (altitude-follow)`，避免伪 6.6m 误导。新增 `control_mode_detected` 字段（从 diagnostics.mode 推断 CONSTANT/TERRAIN）。
  4. 派生海底 `seabed_depth` 在图像通路改为真点云重建（而非 `depth + 常值 clearance`），消除"恒为 15"的平直假象。
- Why：这是 v2 认定的真根因。修复后"2D 平直海底"矛盾、伪 6.6m depth_error 同时消除，clearance≈3m 跟随真相浮现。
- 风险控制：保留旧字段、新增带 `_source` 标注的新字段，**不破坏既有列**，便于跨 run 对比与审计。

### P0-2：solve_time 数据佐证（抽取进 summary + 轻量微基准）★用户决策"两者都做"

- **系统级佐证（抽取）**：[tools/analyze_bag.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py)
  - `read_bag_data` 新增读取 `/auv/controller/debug`（JSON String）的 `solve_time_ms` + `solve_time_source` → `data.solve_time`（ScalarSeries）。
  - `export_statistics_tables`（L1163-1175）summary 新增 `solve_time_mean_ms`、`solve_time_p95_ms`、`solve_time_max_ms`、`solve_time_sample_count`、`solve_time_source`。
  - 预期 rerun bag 抽出 mean≈10.59ms（实测已确认）。
- **微基准（确定数值）**：新文件 `tools/mpc_solve_microbench.py`
  - 直接构造 `AUVMPCOptimizer`（[algorithm/auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py)），对典型 setpoint 跑 N=200 次 `solve()`，`perf_counter` 统计 mean/p50/p95/max + warm-start vs cold-start 对比，导出 CSV + 直方图。
- Why：消除"0ms 求解非线性优化"学术硬伤，给确定的台架数值 + 系统级闭环佐证两条独立证据；并解决 05 章 0ms vs 08 章非零的矛盾。

### P0-3：回查 WP-C（buoyancy_term / ki_z 是否误诊 datum 假漂移）★用户决策"彻查并真修复"

- 文件：[brain_linux/config/params.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.yaml)（L118-129）、[mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py)（C2 积分块 L257-270）
- How：
  1. 用 P0-1 修复后的真口径，**重新评估 baseline depth 行为**：确认 12m→9.3m 是 CONSTANT(target=4.0) 下的正常收敛还是真发散。
  2. 做 **A/B 离线对照**：`buoyancy_term=-0.5,ki_z=0.1`（现状）vs `buoyancy_term=0.0,ki_z=0.0`（回退），比较 terrain 模式真 altitude 跟踪误差与 baseline depth 收敛。
  3. 结论二选一并落档：
     - 若 WP-C 是对 datum 假象的过度补偿 → **回退**（恢复 `buoyancy_term=0.0`、`ki_z=0.0`），保持模型诚实。
     - 若 WP-C 确有改善真 clearance 跟踪 → **保留**，并把注释里"≈0.02m/s 上漂"换成基于真 altitude 的物理依据。
- Why：避免"用一个补偿器去修一个度量 bug 制造的假漂移"，这本身是更深的学术硬伤。

### P0-4：truth-topic 统一

- 文件：[tools/analyze_bag.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py)（`candidate_truth_topics` L347 / `DEFAULT_TRUTH_TOPICS` L54-58）、[scripts/run_terrain_benchmark.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_terrain_benchmark.sh)
- How：四相统一用同一 truth topic（优先 `/auv/sensors/ground_truth`，缺失回退 `/auv/visual/truth_marker`）；summary 已有 `truth_topic_used`（L1167）字段做审计，确保四相一致。
- Why：消除跨相 RMSE 口径不齐，使 baseline/terrain 可比。

### 统一重分析（P0 就绪后）

- **首选离线重分析**（无需重跑实时）：对已存在的 `results/control/terrain_following_20260619_222639/` 四相 bag，用修复后的 `analyze_bag.py` 重新生成 summary（真 clearance + 真 solve_time + 修正 depth_error 口径 + 统一 truth-topic）。
- **仅当**回查 WP-C 决定回退控制参数时，才需 `bash scripts/run_terrain_benchmark.sh 60 both both_modes default` 实时重跑一轮。
- 记录最终结果路径，供 WP-D 做图与 WP-G 文档引用。

### WP-D：图像自洽性修复（用修复后真口径数据）

- 文件：[tools/plot_terrain_following_figures.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/plot_terrain_following_figures.py)（v1 已改 6 处：默认 20260619_222639、`--warmup-skip-s`、动态 RMSE 参考线、y 轴自适应、t-z warm-up 裁剪 + provenance 注释）
- v2 增量：
  1. **2D 海底数据源改用真口径**：t-z / clearance 图用 P0-1 修复后的真 altitude / 真点云（不再用常值 datum），使 2D 海底起伏与 3D 图一致 → 彻底消除"2D 平、3D 起伏"矛盾。
  2. clearance 安全裕度图用真 clearance≈3m 重绘，RMSE 参考线从修复后 summary 动态读取。
  3. 图注统一标注数据 provenance（真 altitude / 真点云 / deterministic terrain 重建）。
- Why：图像数值与修复后 summary 一致，矛盾消除。

### WP-E：平面路径"适度极端"运行验证

- 文件：[tools/mpc_xy_yaw_extreme_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_xy_yaw_extreme_benchmark.py)（编辑已落盘：`s_turn_long_wave` 波长 60m/幅值 7m + `safe_reduction_pct` + 双基线）
- How：运行 `python3 tools/mpc_xy_yaw_extreme_benchmark.py`，确认 `s_turn_long_wave` 出图（MPC 贴合弦波、横向误差 < PID）、`best_comparison` 无 -8141% 爆炸值、保留 `s_turn_short_wave` 作诚实失败反例。
- Why：长波长展示 MPC 预瞄优势，短波长保留为动力学饱和边界。

### WP-F：3 组强解说力过渡实验（混合形态）

- **F1 三相螺旋漏磁空间扫面（对应 2.3.2）**：新文件 `tools/helical_cable_magnetic_scan.py`。复用 [perception_engine.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/perception_engine.py) 的 `MU0`/`CablePath`/`compute_biot_savart_hvdc`，新增三相绞合（3 导体螺旋、相位差 120°、螺距 1.2m）。AUV 恒高 2m 沿轴向直线 10m。输出对比曲线：单芯平直 vs 三相 pitch=1.2m 周期波浪。CSV+PNG。
- **F2 标定敏感度消融（对应 2.4.2）**：扩展 [tools/es_ekf_extrinsics_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/es_ekf_extrinsics_benchmark.py)。新增 `no_lever_arm`（DVL translation 置 0）、`no_mounting_angle`（5° 安装角偏差），baseline=`calibrated`。输出三组 XY/Z RMSE 对比表。
- **F3 网络抖动边界测试（对应 2.5.1 / 3.2.1）**：新文件 `tools/jitter_boundary_ekf_benchmark.py`。复用 [mock_amd_delay.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/mock_amd_delay.py) `TransportDelayQueue` + [es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py)（先加 `self.last_K` 暴露 Kalman 增益）。jitter 50→500ms，记录增益范数/误差/NIS 找发散临界点。输出曲线 + 临界 jitter 表。

### P1/P2 分级处理（用户决策"全部纳入分级修"）

- **P1-a 磁通道空**：核查 bag 是否含 `/auv/sensors/magnetic`；若实验未走电缆磁场场景则在文档**诚实声明**"地形跟随实验不含磁采集，磁指纹见 F1/第 3 章"；若应有而漏采则修采集链路。
- **P1-b extrinsics 2/3 seed**：补第 3 个 seed 重跑或调整报告阈值，并在结论标注 seed 数与方差。
- **P2-a n=1**：在结论显式声明"地形基准为单次运行，统计置信有限，后续补 ≥3 次重复"的诚实边界。
- **P2-b 双 INDEX 树**：合并 `docs/thesis/INDEX.md` 与 `docs/thesis/paper/INDEX.md`，或明确标注主/从，05 章 base/_continued 标注关系。

### WP-G：文档闭环

- 文件：[08_terrain_following_pid_mpc_status.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/08_terrain_following_pid_mpc_status.md)、[09_terrain_following_figures.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/09_terrain_following_figures.md)、[terrain_benchmark_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/terrain_benchmark_log.md)、INDEX
- How：
  1. **记录 datum 修复始末**：旧常值 datum bug 的发现、真 clearance≈2.83m 的实测、depth_error 口径修正、修复前后 summary/图对比。
  2. 记录真 solve_time 数值（系统级 ≈10.6ms + 微基准），统一 05/08 章口径。
  3. WP-C 回查结论（保留/回退）落档。
  4. 闭环 vs 开挂真值澄清；truth-topic 统一说明。
  5. 三组新实验各一节（方法/图表/学术价值/对应章节）。
  6. P1/P2 诚实边界声明（磁通道、seed 数、n=1、INDEX 合并）。
  7. INDEX 数据状态表刷新 ✅/⏳。

---

## 四、Assumptions & Decisions

- **D1（v2 核心）**：真根因是**度量/分析层 datum bug**，非控制器发散；P0 优先离线修分析层 + 重分析既有 rerun bag，**优先不重跑实时**。
- **D2**：solve_time **两者都做**（analyze_bag 抽取 + `mpc_solve_microbench.py` 微基准）。
- **D3**：WP-C **彻查回查**；若判定为对 datum 假象的过补偿则**回退** `buoyancy_term/ki_z`，保持模型诚实。
- **D4**：clearance 真值优先级 `real_altitude > terrain_cloud > diag_constant_datum`，summary 带 `clearance_source` 审计字段。
- **D5**：terrain 模式主跟踪指标改为 `clearance_error_to_target_m`（altitude−3.0）；`depth_error` 在 altitude-follow 模式标 N/A 或对真 target 评分。
- **D6**：truth-topic 四相统一（优先 `/auv/sensors/ground_truth`）。
- **D7**：三组新实验混合形态（F1/F2 离线确定性脚本，F3 离线注入抖动）；螺距 1.2m / 相位 120°；杆臂 0.8m / 安装角 5°（用户大纲指定）。
- **D8**："开挂真值"为误解，仅文档澄清，不改控制器状态来源。
- **D9**：warm-up 默认 10s（`AUV_WARMUP_SKIP_S`，`--warmup-mode time`）。
- **D10**：新发现自洽问题**全部纳入分级修**——P0 本轮修（datum/solve_time/WP-C/truth-topic），P1（磁通道、extrinsics seed）写明确待办 + 声明，P2（n=1、双 INDEX）诚实边界声明。

---

## 五、Verification（验证步骤）

1. **P0-1**：修复后 `python3 tools/analyze_bag.py results/control/terrain_following_20260619_222639/<phase> --stats-only` → summary 出现 `clearance_source=real_altitude`、`seabed_clearance_mean_m≈2.8-3.0`（不再 4.39）、`clearance_error_to_target_m` 小、terrain 模式 `depth_error` 标 N/A 或合理。
2. **P0-2**：summary 出现 `solve_time_mean_ms≈10.6`、`solve_time_source`；`mpc_solve_microbench.py` 出确定 mean/p95/max + 直方图。
3. **P0-3**：A/B 对照表落档，WP-C 保留/回退结论明确，模型注释与真物理依据一致。
4. **P0-4**：四相 summary `truth_topic_used` 一致。
5. **WP-D**：2D 海底起伏与 3D 图一致，clearance 安全裕度图≈3m，RMSE 参考线与 summary 一致，无"平直矛盾"。
6. **WP-E**：`s_turn_long_wave` 出图 MPC 贴合、横向误差 < PID；`best_comparison` 无爆炸值。
7. **WP-F**：F1 单芯 vs 三相双曲线；F2 三组 XY/Z RMSE 表；F3 jitter 50→500ms 曲线 + 临界时延，`es_ekf.last_K` 可访问。
8. **P1/P2**：磁通道核查结论；extrinsics seed 补齐/声明；n=1、双 INDEX 边界声明落档。
9. **WP-G**：文档闭环，datum 修复始末 + 真 solve_time + WP-C 结论 + 三组新实验 + 诚实边界 + INDEX 刷新全部到位。

---

## 六、里程碑

- **M1（P0-1/P0-2/P0-4）**：度量 datum 修复 + solve_time 抽取/微基准 + truth-topic 统一；离线重分析 rerun bag。
- **M2（P0-3）**：WP-C 回查结论（保留/回退）。
- **M3（WP-D/WP-E）**：图像自洽 + 平面路径验证。
- **M4（WP-F）**：三组新实验出图出表。
- **M5（P1/P2 + WP-G）**：分级修 + 文档闭环。

---

## 七、执行进度与续跑状态（Resume State，2026-06-19 v2 更新）

> 本节记录已落盘并经只读复核/实测的进度。**注意：v2 推翻了 v1 对"图像怪异"的控制器发散诊断**——以下 WP-A/B/C 代码改动多数仍有效，但 WP-C 列入 P0-3 回查、WP-D 的数据源需按 P0-1 真口径重做。

### 已完成并已验证（代码层）
- **WP-A（✅）**：[aggregate_control_metrics.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/aggregate_control_metrics.py) 修复（`import os`、`--warmup-skip-s` 注入/透传）；[run_terrain_benchmark.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_terrain_benchmark.sh) 加 `AUV_WARMUP_SKIP_S`（默认 10）；[analyze_bag.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py) warm-up 链路复核 OK。
- **WP-B（✅）**：[auv_mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/auv_mpc_controller.py) `perf_counter` 计时 + `solve_time_source`；brain [mpc_controller.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_controller/auv_controller/mpc_controller.py) 透传。**实测 rerun bag solve_time mean=10.59ms（已确认生效）**。
- **WP-C（✅ 代码落盘，⚠️ 列入 P0-3 回查）**：[params.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.yaml) `ki_z=0.1`/`z_integral_clamp_m=2.0`/`buoyancy_term=-0.5`；mpc_controller C2 积分块。**v2 存疑：可能在修 datum 误导的假漂移，待 P0-3 A/B 对照定夺去留。**
- **统一实时重跑（✅）**：rerun 结果 **`results/control/terrain_following_20260619_222639/`**（四相 summary 齐全、带 warm-up 字段）。实测含真 `/auv/sensors/altitude`（mean=2.83m）、真 `/auv/controller/debug` solve_time（mean=10.59ms）、真点云 → 为 P0 离线重分析提供完整数据。
- **WP-E（部分，编辑落盘待运行）**：[mpc_xy_yaw_extreme_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_xy_yaw_extreme_benchmark.py) 加 `s_turn_long_wave`（60m/7m）+ `safe_reduction_pct` + 双基线，`ast.parse` OK，**尚未运行**。
- **WP-D（部分，落盘待重做）**：[plot_terrain_following_figures.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/plot_terrain_following_figures.py) 已改 6 处。**但因 datum bug 推翻，2D 海底数据源需按 P0-1 真口径在 WP-D 重做**。

### P0 已完成（本会话续跑落盘 + 验证）
- **P0-1（✅）**：[analyze_bag.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py) 度量 datum 修复——读 `/auv/sensors/altitude` 真 clearance + 真点云回退；修 depth_error 口径（terrain 模式标 N/A）；加 `clearance_source` 审计字段（`real_altitude`/`terrain_cloud`/`diag_constant_datum`）；`--control-mode` 入参。
- **P0-2（✅）**：① analyze_bag 系统级抽取 `/auv/controller/debug.solve_time_ms` + `solve_time_source` 进 summary（实测 mean≈10.6ms）；② 新建 [tools/mpc_solve_microbench.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_solve_microbench.py) 微基准——默认稳态 100% 成功，cold solver_internal mean≈10.77ms/p95≈11.35ms、warm≈4.88ms/p95≈5.0ms，与系统级 ≈10.6ms 互证；导出 summary CSV + raw CSV + 直方图 PNG；`--start-depth 8.0` 可复现约束驱动 fallback。
- **P0-3（✅，决策：保留 + 重写注释）**：新建 [tools/wp_c_depth_ab.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/wp_c_depth_ab.py) 离线 A/B——现实浮力（−0.5~−2.0）A/B 均 sub-mm、plant 中性 A 不引入偏置、仅 8× 失配（−4.0）B 退化~14mm 而 A 保持 <1mm → **WP-C 良性鲁棒裕度**。真 bag depth 探针证明"12m→9.3m"是真实物理（terrain-following + baseline 缓慢收敛，与 datum bug 无关），原"≈0.02m/s 上漂"依据被推翻。**参数值不变**（buoyancy_term=-0.5/ki_z=0.1/clamp=2.0），仅重写 [params.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.yaml#L116-L134) L116-134 注释为基于 A/B 实证的诚实物理依据。
- **P0-4（✅）**：[analyze_bag.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py) `DEFAULT_TRUTH_TOPICS` 改 ground_truth 优先；`read_bag_data` 重构 per-topic 收集 + 优先级选择（消除多 topic 混入 + first-arrived bug）；[run_terrain_benchmark.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_terrain_benchmark.sh) `analyze_phase` 透传 `--control-mode`。四相离线重分析全部统一到 `/auv/sensors/ground_truth`。

### 新发现（已纳入 WP-G 文档闭环）
- **solver_fallback 14.3%（P0-1 副产物）**：mpc_terrain 相 14.3% 步触发 `FALLBACK_LAST_OUTPUT`，根因为 z_band=4.0m/delta_z_max_per_step=1.0m 等带宽/速率约束在起始深度与目标差距过大（8m→3m）时求解不可行 → 与微基准 `--start-depth 8.0` 复现一致。需在 WP-G 诚实记录。

### 续跑顺序（剩余，按 v2 优先级）
1. ~~**WP-E**~~：✅ 已完成（见下"WP-E 已完成"小节）。
2. ~~**WP-F**~~：✅ 已完成（F1 三相螺旋漏磁 / F2 标定敏感度 / F3 网络抖动边界，见下"WP-F 已完成"小节）。
3. ~~**P1/P2**~~：✅ 已完成（见下"P1/P2 调查结论"小节，P1-b 代码修复 + 其余诚实声明已落档）。
4. ~~**WP-G**~~：✅ 已完成（见下"WP-G 已完成"小节）。

> **计划 v2 全部工作包（WP-A~G + P0~P2）已交付。自洽性提升阶段收尾完成。**

### 离线重分析 + WP-D 已完成（本会话）
- **离线重分析（✅，已持久化）**：四相 `results/control/terrain_following_20260619_222639/<phase>/analysis/summary_statistics.csv` 用 P0 真口径重生成并落盘（此前磁盘上为 pre-P0 stale 值）。验证：`clearance_source=real_altitude`，`seabed_clearance_mean_m`=pid_baseline 2.699 / pid_terrain 1.954 / mpc_baseline 2.657 / mpc_terrain 2.647（不再 4.5m 常值 datum）；terrain 相 `depth_error_rmse_m=nan`（altitude-follow 口径修正）、`depth_error_rmse_diag_m` 保留审计；`truth_topic_used` 四相统一 `/auv/sensors/ground_truth`；`solve_time_mean_ms` mpc_baseline 12.93 / mpc_terrain 10.59；`solver_fallback_ratio` mpc_terrain=0.1429（与 P0-1 发现 14.3% 自洽）。
- **WP-D（✅）**：[plot_terrain_following_figures.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/plot_terrain_following_figures.py) 修复——`load_bag_for_phase` 补 `altitude_topic`/`controller_debug_topic` 新参（P0-1/P0-2 后原已坏）；`diagnostics_arrays` 改用 `resolve_clearance_series` 真 altitude/点云口径，`seabed_depth=depth+real_clearance` 现随真地形起伏（pid_terrain std=0.443/range[12.29,14.11]、mpc_terrain std=0.882/range[10.63,15.13]）→ 彻底消除"2D 平 vs 3D 起伏"矛盾；t-z 标题/图例标 clearance source；新增 `provenance_note` 在 clearance RMSE 柱状图与安全裕度图标注数据来源（real DVL altitude / warm-up trimmed / truth=ground_truth）。6 张图全部重生成无误（docs/thesis/figures/terrain_following/）。

### WP-E 已完成（本会话，用户决策"两者都做"）
- **机械修复（✅）**：`safe_reduction_pct` 加 `cap_pct=1000` 守卫——除近零分母外，对 |reduction|>1000% 也返回字符串 sentinel（如 `N/A (ratio=82.4x, not comparable)`），消除 yaw-only 切线基线 yaw-RMSE 近完美导致的 -8141% 爆炸；`s_turn_long_wave`（60m/7m）成功出图、success=1.0。
- **harness 公平性排查（✅，发现真实 bug 并修复）**：`run_mpc` 参考构建原为 `s_values[idx] + 2.0 + k*v*dt`（[mpc_xy_yaw_extreme_benchmark.py L312](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_xy_yaw_extreme_benchmark.py)），其中 `+2.0` 常值下游偏置把**整条参考（含 k=0）**整体推到最近点下游，迫使 MPC 切弯、人为放大其横向 RMSE；而 yaw-only 基线读 `path[idx,3]` 精确最近切线、LOS 基线从当前位置做前瞻 → 两基线无此偏置，对比不公平。修正：删除 `+2.0` 常值偏置，保留 `k*v*dt` 真正的预瞄项（k=0 锚定最近点）。**这是真实的 harness bug 而非偏向 MPC 的调参**。
- **公平口径复跑结果（✅，`20260620_011831/best_comparison.csv`）**：MPC 不再被冤枉，且结论稳健（非单 variant 偶然，5 个 variant 全部一致）——
  - `s_turn_long_wave`：MPC best **0.055m**（5 variant 0.055–0.066）vs yaw-only 0.093 / LOS 1.047 → **MPC 全胜**（−41% vs yaw-only，−95% vs LOS）。**计划原定"长波展示 MPC 预瞄优势"现被数据支持**。
  - `hairpin_180deg`：MPC best **2.277m**（5 variant 2.28–2.96 全部优于两基线 4.69）→ **MPC 全胜**（−51%）。
  - `s_turn_short_wave`：MPC best 1.655 vs yaw-only 2.597 / LOS 1.657 → MPC −36% vs yaw-only、与 LOS 持平。
  - `chicane_90deg`：LOS **0.659m** 最优，MPC best 1.452、yaw-only 3.596 → **诚实边界：直角折线 chicane 上 LOS 前瞻基线最优**（路径由直段+直角拐点构成，LOS 固定前瞻天然贴合；MPC 受 `psi_band`/`delta_psi` 速率约束在硬拐点处略逊）。
- **诚实结论（供 WP-G 引用）**：在公平口径下 **MPC 在长波 S 弯、急转 hairpin、短波 S 弯三类工况均优于或持平基线**；唯一基线占优的是直角 chicane（LOS 前瞻更贴合分段直线）。早先"MPC 不普遍优于基线"的判断源自 harness 的 +2.0m 偏置 bug，修复后已被推翻——但 chicane 这一诚实边界予以保留记录，不做过度宣称。

### WP-F 已完成（本会话，3 组强解说力过渡实验）
- **F1 三相螺旋漏磁（✅，`results/perception/helical_cable_magnetic_scan/20260620_013450/`）**：新建 [tools/helical_cable_magnetic_scan.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/helical_cable_magnetic_scan.py)，复用 `perception_engine.compute_biot_savart_hvdc` 对比单芯电缆 vs 三相平衡螺旋（120° 相位、螺距 1.2m、三相电流和=0）。AUV 在海床上方 2m 沿 x 扫场。**结果**：单芯 mean=4.97e+04 nT、ripple **0.1%**（准均匀）；三相 mean=34.4 nT（远场抵消 ~1400× 弱）、ripple **81.6%**（螺距周期起伏）。**关键陷阱已修**：每段仅一个中点电流元，单芯必须细分到与 helix 同段数（6000）否则出现伪 ripple（首跑 263% 系 2 点粗糙线积分近似，非物理）。出 magnetic_scan.csv + ripple_metrics.csv + PNG/PDF（标螺距周期竖线）。
- **F2 标定敏感度消融（✅，`results/es_ekf_extrinsics/20260620_012952/`）**：扩展 [tools/es_ekf_extrinsics_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/es_ekf_extrinsics_benchmark.py)，加 `no_lever_arm`（杆臂置零）与 `no_mounting_angle`（安装角注入 +5° yaw 误差）两消融 mode。medium profile × 3 seed。**结果**：calibrated XY RMSE 22.67m / no_lever_arm 22.03m（**杆臂可忽略**）/ no_mounting_angle 30.06m（**安装角误差 +33% 漂移**）；Z RMSE 三者均 ~0.003m（深度通道不受机体平面外参影响）。出 summary_by_error_level.csv + extrinsics_report.md。**物理合理**：DVL 速度方向对安装角敏感、对小杆臂不敏感。
- **F3 网络抖动边界（✅，`results/es_ekf_jitter_boundary/20260620_014529/`）**：新建 [tools/jitter_boundary_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/jitter_boundary_ekf_benchmark.py)，复用 `mock_amd_delay.TransportDelayQueue` 对 DVL 流注入 base_delay=20ms + jitter（0→500ms）扫描，DVL 经队列取陈旧包喂 `correct_dvl_sensor`。为支撑诊断在 [algorithm/es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L157-L163) 暴露 `last_K`/`last_S`/`last_innov`（最近一次观测更新的 Kalman 增益/创新协方差/创新向量）。**边界指标选型（关键诚实记录）**：①XY 位置不可观（DVL 仅机体速度、depth 仅 z）→ XY RMSE 由 dead-reckoning 漂移主导、掩盖 jitter，弃用；②velocity RMSE 噪声大（adaptive-R 保护状态）→ 仅作旁证；③**最终采用 DVL NIS（归一化创新平方）作主边界指标**——它直接度量观测-预测一致性，正是 jitter 破坏的量。**结果**（3 seed）：DVL NIS 0.125（0ms）→ 1.554（500ms）严格单调 ~12× 上升，**临界 jitter=150ms**（NIS 首超 2× nominal）；Kalman 增益范数 8.38→4.52 单调下降（滤波器渐进折扣陈旧 DVL，与 adaptive-R 自洽）。三witness（NIS↑/gain↓/vel 噪声）相互印证。出 jitter_results.csv + jitter_summary.csv + critical_jitter.csv + 三子图 PNG/PDF。

### P1/P2 调查结论（本会话，决策"全部纳入分级修"）
> P1-b 已落地代码修复；其余 P1-a/P2-a/P2-b 为诚实声明型，文案在 WP-G 文档闭环统一落档（避免重复编辑同批文档）。
- **P1-a 磁通道空（→ 诚实声明）**：核查确认 terrain benchmark **无磁场采集链路**——[run_terrain_benchmark.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_terrain_benchmark.sh) grep "magnetic" 零命中、未传 `--topic-magnetic`；四相 `analysis/summary_statistics.csv` 的 `magnetic_sample_count=0`/`magnetic_peak_t=nan`（[analyze_bag.py L64](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py) 始终输出该列）。**结论：地形跟随实验不含磁采集（设计如此），磁指纹见 F1/第 3 章——WP-G 文档诚实声明，无需补采集。**
- **P1-b extrinsics seed（✅ 代码修复）**：[es_ekf_extrinsics_benchmark.py L58](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/es_ekf_extrinsics_benchmark.py) `--seeds` 默认由 `"0"`（单 seed）改为 `"0,1,2"`，使 3-seed 复验成为内建默认（此前 20260620_012952 run_count=3 系显式传参）；结论需标注 seed 数与方差（summary 已含 *_std 列）。
- **P2-a n=1（→ 诚实声明）**：[run_terrain_benchmark.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_terrain_benchmark.sh) 执行循环仅 controllers×modes，每相单次运行、无重复/平均循环 → 地形基准为 n=1，WP-G 声明"单次运行、统计置信有限、后续补 ≥3 次重复"。
- **P2-b 双 INDEX 树（→ 标注主从 + 刷新）**：`docs/thesis/INDEX.md`（工程证据层，列 T1-T8 即 00-07，**漏 08/09/10**）与 `docs/thesis/paper/INDEX.md`（论文正文层，列 ch.1-5，**漏 05_..._continued.md**）为两棵平行树；另 `05_experiments_and_discussion.md` 与 `05_experiments_and_discussion_continued.md` 存在 5.5.4-5.8 重叠编号。WP-G：两 INDEX 各补漏项 + 标注主/从定位，05 base/_continued 标注续写关系。

### WP-G 已完成（本会话，文档闭环 4 子任务）
> 把 P0/WP-D/WP-E/WP-F 真口径结果与 P1/P2 诚实边界固化进三层文档体系，旧污染表加 stale 警示，刷新双 INDEX。
- **WP-G/1（✅）doc 08 自洽闭环**：[08_terrain_following_pid_mpc_status.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/08_terrain_following_pid_mpc_status.md) 旧 §2/§5.4 表头加 stale 警示（指向 §8.2/§8.7）；追加 §8「自洽性提升闭环（2026-06-20）」含 8.1 datum bug 发现修复、8.2 P0 真口径重跑表（clearance_mean pid_baseline 2.699/pid_terrain 1.954/mpc_baseline 2.657/mpc_terrain 2.647；terrain 相 depth_error_rmse N/A；n=1 警示）、8.3 真 solve_time（mpc_baseline 12.93/mpc_terrain 10.59ms）、8.4 solver_fallback 14.3%、8.5 WP-C 回查结论、8.6 开挂真值澄清、8.7 WP-E 公平口径表、8.8 P1/P2 诚实声明汇总。
- **WP-G/2（✅）doc 09 图像口径**：[09_terrain_following_figures.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/09_terrain_following_figures.md) 头部加 §0「2026-06-20 真口径重生成更新（WP-D）」——6 图改用 `20260619_222639`、clearance=real_altitude、2D 海底起伏修复（pid_terrain std=0.443/mpc_terrain std=0.882）、provenance 标注、n=1 边界。
- **WP-G/3（✅）三组新实验文档**：新建 [11_transition_experiments_F1_F2_F3.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/11_transition_experiments_F1_F2_F3.md)（10 已被 10_figure_review 占用）——F1 三相螺旋漏磁（单芯 0.1% vs 三相 81.6% ripple + 远场抵消 1400× + 细分陷阱方法学）、F2 标定敏感度（安装角 +33%/杆臂可忽略，3 seed mean±std）、F3 网络抖动边界（DVL NIS 表 + critical 150ms + 指标选型表）+ 复现命令。
- **WP-G/4（✅）双 INDEX 刷新 + 主从标注**：[thesis/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/INDEX.md) 补 T9-T12（08/09/10/11）、加「本树工程证据层为主、paper 树为从」说明、数据状态表追加真口径/真 solve_time/MPC 公平口径/F1/F2/F3/地形多次重复待补 等行；[paper/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/INDEX.md) 章节表 05 标「主」+ 新增 05_..._continued「续写」行（标注 5.5.4-5.8 编号重叠主从）+ F1/F2/F3 证据指向 doc 11；[terrain_benchmark_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/terrain_benchmark_log.md) 末尾追加「2026-06-20 真口径重跑闭环」运行级条目（真口径目录、真测高、真 solve_time、solver_fallback 14.3%、n=1 边界、复现命令）。
