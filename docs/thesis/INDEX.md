# 硕士论文实验体系 — 文档总览（thesis 板块）

> **板块路径**：`docs/thesis/`
> **定位（工程证据层 / 本树为"主"）**：把仓库内"通过仿真验证控制算法 / ES-EKF 正确性 / Jetson 部署可用性"全部成果整理为可直接服务于硕士论文 §1–§5 写作的文档族。
> **写作模板**：参考 [docs/experiment/benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) 的"新手 SOP + 真实日志 + 已知陷阱"风格。
> **与 paper 树的主从关系（P2-b）**：本树（`docs/thesis/`）为**工程证据层（主，存放代码符号对照、真实数据、已知偏差）**；[docs/thesis/paper/INDEX.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/INDEX.md) 为**论文正文层（从，段落式叙述）**。写作先读 paper 树、查证回本树。

| T16 | [16_cable_dlt1278_scoring_and_operator_products.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/16_cable_dlt1278_scoring_and_operator_products.md) | §5 / 工业部署附录 | DL/T 1278 风格评分实现、ready/pass 与扣分项关系、自动产物链和面向运维人员的 operator_view 图像 |

---

## 文档列表

| # | 文件 | 论文章节映射 | 内容定位 |
|---|---|---|---|
| T1 | [00_overview.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/00_overview.md) | §1.4 / §5.1 | 实验体系全图、术语、命令索引、创新点对照表 |
| T2 | [01_baseline_repro_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/01_baseline_repro_log.md) | §3.5 baseline / §5.1.2 | baseline 端到端 SOP + RMSE/CEP50 |
| T3 | [02_es_ekf_validation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/02_es_ekf_validation.md) | §3.5.1 / §3.5.2 / §3.6 | ES-EKF 三路对比 + DVL 丢包 + 磁畸变 |
| T4 | [03_uncertainty_quantification.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/03_uncertainty_quantification.md) | §3.4 / §4.4.2 | NIS 白化 + EKF P 时序 + UA-MPC 耦合 |
| T5 | [04_mpc_robustness_ablation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/04_mpc_robustness_ablation.md) | §4.5 | baseline-MPC vs UA-MPC 多场景多种子消融 |
| T6 | [05_scenario_recipes.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/05_scenario_recipes.md) | §5.2 | 9 个 scenario yaml 物理含义 + 覆盖矩阵 |
| T7 | [06_jetson_deploy_emulated.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/06_jetson_deploy_emulated.md) | §5.5 | Jetson 仿真侧 CPU/MEM/IPOPT 时延 + 敏感性 |
| T8 | [07_drift_log_and_known_issues.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md) | 全文附录 | 文档偏差闭环 + 已知问题 + 未来工作 |
| T9 | [08_terrain_following_pid_mpc_status.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/08_terrain_following_pid_mpc_status.md) | §5.5 控制 | 地形跟随 PID/MPC 状态 + §8 自洽闭环（datum 修复、真口径重跑、solve_time、WP-C、WP-E 公平口径、P1/P2 声明） |
| T10 | [09_terrain_following_figures.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/09_terrain_following_figures.md) | §5.5 图像 | 地形跟随 6 图清单/caption + §0 真口径重生成更新（WP-D） |
| T11 | [10_figure_review_and_offset_diagnosis.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/10_figure_review_and_offset_diagnosis.md) | §5.5 诊断 | 图像审查与轨迹偏移诊断 |
| T12 | [11_transition_experiments_F1_F2_F3.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/11_transition_experiments_F1_F2_F3.md) | §2 / §3 | 三组过渡实验：F1 三相螺旋漏磁 / F2 标定敏感度 / F3 网络抖动边界 |
| T13 | [12_cable_mag_dlt1278_fullflow.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/12_cable_mag_dlt1278_fullflow.md) | §5 / 工业部署附录 | 声磁电缆探测全流程、DL/T 1278 风格产物、指标有效性和工业结论边界 |
| T14 | [14_cable_acceptance_multirun.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/14_cable_acceptance_multirun.md) | §5 / 工业部署附录 | 声磁电缆探测多次运行验收口径、单次报告字段和 pass ratio 聚合方法 |
| T15 | [15_cable_zigzag_amplitude_tuning.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/15_cable_zigzag_amplitude_tuning.md) | §5 / 工业部署附录 | zig-zag 探针幅值动力学边界、有效巡检窗口、burial window30 调优和 120 s ready/pass 验收 run |
| T16 | [16_cable_dlt1278_scoring_and_operator_products.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/16_cable_dlt1278_scoring_and_operator_products.md) | §5 / 工业部署附录 | DL/T 1278 风格评分实现、ready/pass 与扣分项关系、自动产物链和面向运维人员的 operator_view 图像 |
| T16 | [16_cable_dlt1278_scoring_and_operator_products.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/16_cable_dlt1278_scoring_and_operator_products.md) | §5 / 工业部署附录 | DL/T 1278 风格评分实现、ready/pass 与扣分项关系、自动产物链和面向运维人员的 operator_view 图像 |
| T16 | [16_cable_dlt1278_scoring_and_operator_products.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/16_cable_dlt1278_scoring_and_operator_products.md) | §5 / 工业部署附录 | DL/T 1278 风格评分实现、ready/pass 与扣分项关系、自动产物链和面向运维人员的 operator_view 图像 |

---

## 阅读顺序建议

| 角色 | 入口 | 路径 |
|---|---|---|
| **论文写作（你自己）** | T1 → T8 → 按章节按需跳转 | T1 给全图，T8 列已知坑，T2–T7 按论文章节抓素材 |
| **审阅者 / 答辩老师** | T1 → T6 → T2/T3/T5 | 总览 → 实验设计 → 关键结果 |
| **新手复现** | T2 → T6 → T3/T4/T5/T7 | 先跑 baseline → 看场景 → 按需跑各类实验 |

---

## 与其它文档的关系

- **`docs/experiment/`**：单次实验执行日志（n=1），是 thesis 文档的数据源之一；thesis 文档在 `docs/experiment/` 基础上叠加多种子统计、消融、敏感性、IPOPT 时延等论文级维度。
- **`docs/INDEX.md`**：项目顶层 INDEX，已追加 thesis 板块入口。
- **Phase 1–4 实施计划**：见 `.trae/documents/`，记录每一阶段的 Pre/Post-Snapshot：
  - [thesis_experiment_uplift_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_uplift_plan.md)
  - [thesis_experiment_phase2_implementation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_phase2_implementation.md)
  - [thesis_experiment_phase3_e4_to_final.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_phase3_e4_to_final.md)
  - [thesis_experiment_phase4_consolidation_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_phase4_consolidation_plan.md)
  - thesis_experiment_phase4_postsnapshot.md（全部交付完成时回填）

---

## 数据档案位置约定

| 数据集类别 | 默认落盘路径 | 备注 |
|---|---|---|
| 单次实验 mcap | `$AUV_DATA_ROOT/bags/<TS>/rosbag/rosbag_*.mcap` | `start_experiment.sh` 默认 |
| EKF 三路对比 | `$AUV_DATA_ROOT/results/localization/<TS>/` | `offline_ekf_benchmark.py` |
| MPC 三场景基准 | `$AUV_DATA_ROOT/results/control/mpc_test/<TS>/` | `mpc_test.py` |
| BT vs FSM | `$AUV_DATA_ROOT/results/decision/bt_vs_fsm/<TS>/` | `tests/benchmark_bt_vs_fsm.py` |
| sweep 结果 | `$AUV_DATA_ROOT/results/sweeps/<NAME>_<TS>/` | `tools/run_thesis_sweep.py` |
| Jetson 算力 bench | `$AUV_DATA_ROOT/results/jetson/<TS>/` | `scripts/run_jetson_emulated_bench.sh` |

**`$AUV_DATA_ROOT` 默认 = `/auv_data`**（详见 [start_experiment.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/start_experiment.sh)）。

---

## 当前数据状态摘要

> 完整状态见 [thesis_experiment_phase4_consolidation_plan.md §2](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_phase4_consolidation_plan.md)

| 维度 | 数据已就位？ | 来源 |
|---|---|---|
| baseline 单次 RMSE/CEP50 | ✅ | [docs/experiment/benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) |
| MPC 三场景单次 | ✅ | 同上 |
| BT vs FSM 单次 | ✅ | 同上 |
| 地形跟随四相（真口径，n=1） | ✅ | `results/control/terrain_following_20260619_222639/`；T9 §8.2 |
| 真 solve_time（系统级 + 微基准） | ✅ | T9 §8.3；`tools/mpc_solve_microbench.py` |
| MPC x/y/yaw 公平口径 | ✅ | `results/control/mpc_xy_yaw_extreme/20260620_011831/`；T9 §8.7 |
| F1 三相螺旋漏磁 | ✅ | `results/perception/helical_cable_magnetic_scan/20260620_013450/`；T12 |
| F2 标定敏感度（3 seed） | ✅ | `results/es_ekf_extrinsics/20260620_012952/`；T12 |
| F3 网络抖动边界（3 seed） | ✅ | `results/es_ekf_jitter_boundary/20260620_014529/`；T12 |
| 声磁电缆探测全流程 + DL/T 1278 产物 | ✅ 初步链路；工业结论 limited | `/auv_data/bags/20260705_213816/`；`results/cable_ops_report/fullflow_20260705_213816/`；T13 |
| 声磁电缆探测多次验收聚合 | ⏳ 工具与口径已就绪，待 3 次 fullflow | `tools/aggregate_cable_acceptance_runs.py`；T14 |
| 声磁电缆 zig-zag 幅值调优 | ✅ 1.5 m 推荐默认；window30 + preflight-clean 后 120 s 验收 ready/pass | `/auv_data/bags/20260705_235221/`；`results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/`；T15 |
| 声磁电缆 DL/T 1278 评分与运维图像 | ✅ ready/pass run 已生成评分文档、CSV/JSON/Markdown 报告、工程诊断图和 operator_view 运维图像 | `tools/dlt1278_cable_report.py`；`tools/plot_cable_operator_products.py`；T16 |
| 声磁电缆 DL/T 1278 评分与运维图像 | ✅ ready/pass run 已生成评分文档、CSV/JSON/Markdown 报告、工程诊断图和 operator_view 运维图像 | `tools/dlt1278_cable_report.py`；`tools/plot_cable_operator_products.py`；T16 |
| 多种子统计 (mean/std) | ⏳ smoke 待跑 | T3/T5 中标 TBD |
| 多场景消融 (UA vs baseline) | ⏳ smoke 待跑 | T5 中标 TBD |
| 参数敏感性 | ⏳ smoke 待跑 | T7 中标 TBD |
| Jetson IPOPT 时延 | ⏳ 重跑 5 min | T7 中标 TBD |
| EKF P 时序图 | ⏳ 离线后处理 | T4 中标 TBD |
| NIS 时序+卡方阈值带 | ⏳ 离线后处理 | T4 中标 TBD |
| 地形跟随多次重复（≥3，统计置信） | ⏳ 待补（当前 n=1） | T9 §8.2 诚实边界 |

⏳ 标记的项可由后续会话或外部环境跑数据后回填到对应 md，骨架已就绪。
