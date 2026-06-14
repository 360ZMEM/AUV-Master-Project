# 硕士论文实验体系 — 文档总览（thesis 板块）

> **板块路径**：`docs/thesis/`
> **定位**：把仓库内"通过仿真验证控制算法 / ES-EKF 正确性 / Jetson 部署可用性"全部成果整理为可直接服务于硕士论文 §1–§5 写作的文档族。
> **写作模板**：参考 [docs/experiment/benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md) 的"新手 SOP + 真实日志 + 已知陷阱"风格。

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
| 多种子统计 (mean/std) | ⏳ smoke 待跑 | T3/T5 中标 TBD |
| 多场景消融 (UA vs baseline) | ⏳ smoke 待跑 | T5 中标 TBD |
| 参数敏感性 | ⏳ smoke 待跑 | T7 中标 TBD |
| Jetson IPOPT 时延 | ⏳ 重跑 5 min | T7 中标 TBD |
| EKF P 时序图 | ⏳ 离线后处理 | T4 中标 TBD |
| NIS 时序+卡方阈值带 | ⏳ 离线后处理 | T4 中标 TBD |

⏳ 标记的项可由后续会话或外部环境跑数据后回填到对应 md，骨架已就绪。
