# AUV 硕士毕设项目 — 文档总入口

本项目是一套面向自主水下机器人（AUV）的完整研发平台，集成了仿真环境、ROS 2 决策控制栈和 PySide6 上位机系统，支持从算法开发到真机部署的全流程工作。

---

## 推荐阅读路径

| 读者角色 | 起点 | 说明 |
|----------|------|------|
| **Jetson 新接手 / AI 协作** | [JETSON_DEPLOYMENT_CONTEXT.md](JETSON_DEPLOYMENT_CONTEXT.md) | Jetson Orin NX 主线、仿真电缆巡检、全链路仿真测试、依赖与性能边界 |
| **新用户 / 实验操作者** | 明线 `user-guide/` | 了解系统由哪些模块构成、每个模块怎么用、前置条件和操作步骤 |
| **开发者 / 维护者** | 暗线 `internals/` | 深入系统内部原理、数据流架构、各子系统协作机制 |

---

## 文档目录

### 明线 — 使用者指南

> 路径：[user-guide/INDEX.md](user-guide/INDEX.md)

- [quick_start.md](user-guide/quick_start.md) — 5 分钟启动第一次仿真实验
- [experiment_runner.md](user-guide/experiment_runner.md) — start_experiment.sh 完整实验录制与参数详解
- [console.md](user-guide/console.md) — 上位机（PySide6）：遥控、自主授权、ESTOP
- [rosbag_analysis.md](user-guide/rosbag_analysis.md) — MCAP 数据回放与离线分析工具链
- [benchmarks.md](user-guide/benchmarks.md) — 基准测试：PID/MPC 对比、BT/FSM 对比、EKF 性能
- [foxglove.md](user-guide/foxglove.md) — Foxglove 实时可视化：布局生成与导入
- [experiments_catalog.md](user-guide/experiments_catalog.md) — 实验目录：已完成/可复现/待开展的仿真实验清单
- [real_hardware_sop.md](user-guide/real_hardware_sop.md) — 真机迁移 SOP：从仿真到实物的完整操作流程
- [config_reference.md](user-guide/config_reference.md) — 配置文件速查：主线配置地图与参数含义

### 暗线 — 开发者内幕

> 路径：[internals/INDEX.md](internals/INDEX.md)

- 系统架构总览与节点拓扑
- ROS 2 数据流与话题/服务映射
- 决策层（行为树 / 有限状态机）内部实现
- 控制层（PID / MPC）算法细节
- 状态估计（EKF）与传感器融合
- 仿真后端接口与物理引擎对接
- 上位机通信协议与前后端交互

### 论文向 — 硕士毕业设计实验体系

> 路径：[thesis/INDEX.md](thesis/INDEX.md)（Phase 4 收口产物）

- [paper/INDEX.md](thesis/paper/INDEX.md) — 毕设正文层：按 1–5 章组织背景、系统、估计、控制、实验讨论和缺口计划
- [00_overview.md](thesis/00_overview.md) — 实验体系总览 + 5 大创新点对照表
- [01_baseline_repro_log.md](thesis/01_baseline_repro_log.md) — baseline 复现日志（§5.4）
- [02_es_ekf_validation.md](thesis/02_es_ekf_validation.md) — ES-EKF 15 维状态 + 6 通道观测验证（§3.4 / §5.4）
- [03_uncertainty_quantification.md](thesis/03_uncertainty_quantification.md) — 不确定性量化与 EKF→MPC 耦合链路（§3.5 / §4.4）
- [04_mpc_robustness_ablation.md](thesis/04_mpc_robustness_ablation.md) — UA-MPC 消融与灵敏度（§4.5 / §5.5 / §5.5.1）
- [05_scenario_recipes.md](thesis/05_scenario_recipes.md) — 9 个 yaml 场景配方与三维强度覆盖（§5.2）
- [06_jetson_deploy_emulated.md](thesis/06_jetson_deploy_emulated.md) — Jetson 算力部署 emulated 文档（§5.5）
- [07_drift_log_and_known_issues.md](thesis/07_drift_log_and_known_issues.md) — 文档/代码偏差闭环 + 已知问题（§5.6）

`thesis/paper/` 面向论文正文写作，`thesis/` 根目录保留工程证据和实验依据，`experiment/` 保留单次运行日志。

> 入口与上下文：参见 Phase 4 计划 [thesis_experiment_phase4_consolidation_plan.md](../.trae/documents/thesis_experiment_phase4_consolidation_plan.md)。

### 实物部署 — 从仿真到真机的工程化路径

> 路径：[real_deployment/INDEX.md](real_deployment/INDEX.md)（SOP 体系，预先规约）+ [experiment/real_deployment/INDEX.md](experiment/real_deployment/INDEX.md)（事后日志）

明线 `08_real_hardware_sop.md` 是 6 步速记表，便于现场对照；本节给出**多 Level 实施路径**：S1 链路审计 → S2 静态执行器极性 → S3 影子导航 → S4 单点闭环 → S5 全自主，每阶段独立 shell 入口、独立通过判据、独立失败回退。

- [00_principles.md](real_deployment/00_principles.md) — 三战术 + 三架构智慧 + 三铁律
- [01_stage1_link_audit.md](real_deployment/01_stage1_link_audit.md) — 协议字节对齐与时延 p95 测量
- [02_stage2_static_actuator.md](real_deployment/02_stage2_static_actuator.md) — 5 路推力极性与死区
- [03_stage3_shadow_navigation.md](real_deployment/03_stage3_shadow_navigation.md) — passive_mode 影子模式（不夺权）
- [04_stage4_closed_loop_single.md](real_deployment/04_stage4_closed_loop_single.md) — 首次单点闭环（Kp 取仿真 50%）
- [05_stage5_full_autonomy.md](real_deployment/05_stage5_full_autonomy.md) — 行为树释放 + ros2 bag 黑匣子
- [06_kill_switch.md](real_deployment/06_kill_switch.md) — 急停双保险与释放顺序
- [07_param_diff_sim_vs_real.md](real_deployment/07_param_diff_sim_vs_real.md) — 仿真 vs 真机参数差异速查
- [10_sim_vs_real_link_and_wrapper_map.md](real_deployment/10_sim_vs_real_link_and_wrapper_map.md) — 仿真 / 真机链路区别、配置分层、fan-out 与 wrapper 接入图

---

## 最小启动命令

```bash
cd scripts && bash start_experiment.sh --sim-backend pvs --duration 120
```

该命令将使用 PVS 仿真后端启动一次时长 120 秒的实验。
