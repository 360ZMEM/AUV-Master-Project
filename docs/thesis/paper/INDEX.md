# paper 正文层索引

## 定位与使用说明

`docs/thesis/paper/` 是直接面向毕业设计正文写作的材料层。它不替代 `docs/thesis/` 的工程证据，也不替代 `docs/experiment/` 的运行日志，而是在二者之上形成更接近论文章节的叙述版本。本文档层尽量减少调试过程、命令流水和代码细节，保留实验设计背景、条件控制、指标解释、结果表格、结论边界和后续补实验计划。

当前正文材料必须遵守一个基本原则：已经有结果的内容可以写成实验结论，尚未形成结果的内容只能写成待补、设计方案或未来工作。尤其不能把 `n=1` 单次实验写成多种子统计，不能把 emulated Jetson 写成真机时延，不能把 MPC 写成全面优于 PID/LOS，也不能把当前 9 个 PVS chaos 场景写成完整海缆巡检数字孪生。

## 章节映射与导航

按毕设 1–5 章组织的正文材料：

| 文件 | 对应章节 | 核心内容 |
|---|---|---|
| [01_background_and_significance.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/01_background_and_significance.md) | 第 1 章 | 研究背景、技术现状、研究内容与创新点 |
| [02_system_design.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/02_system_design.md) | 第 2 章 | 任务需求、双脑架构、通信协议、声磁建模与标定框架 |
| [03_state_estimation.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/03_state_estimation.md) | 第 3 章 | 异步同步、ES-EKF、声磁协同、自适应不确定性 |
| [04_decision_and_control.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/04_decision_and_control.md) | 第 4 章 | 行为树、failsafe、PID/PVS、MPC/UA-MPC 与控制边界 |
| [05_experiments_and_discussion.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/05_experiments_and_discussion.md) | 第 5 章 | 实验平台、指标、结果表、讨论与 Sim-to-Real 边界 |

按论文写作支撑用途组织的补充文档：

| 文件 | 用途 |
|---|---|
| [experiment_gap_and_next_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/experiment_gap_and_next_plan.md) | 当前实验缺口、优先级和补实验计划 |
| [pvs_extreme_cable_scenarios.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/pvs_extreme_cable_scenarios.md) | PVS 场景真实性、极端电缆巡检设计和 discrepancy 收敛 |

## 与工程证据层的关系

三层文档体系的关系如下：

| 层级 | 路径 | 职责 | 适用场景 |
|---|---|---|---|
| 论文正文层 | `docs/thesis/paper/` | 面向毕设 1–5 章写作，段落式叙述，减少代码细节 | 先读本章写论文 |
| 工程证据层 | `docs/thesis/` | 实验依据、代码符号对照、已知偏差和边界约束 | 回到本章查证据 |
| 原始运行日志 | `docs/experiment/` | 单次实验执行命令、输出、坑点和复现入口 | 追溯原始执行 |

写作时建议先阅读本目录，再按需要回到 `docs/thesis/` 查证据，最后才进入 `docs/experiment/` 查原始命令和运行日志。

## 当前不能声称的事项清单

| 事项 | 原因 | 正确写法 |
|---|---|---|
| MPC 深度控制全面优于 PID | terrain benchmark 结果 PID 更优 | 写成对照算法和回退理由 |
| UA-MPC 主消融已完成 | baseline vs UA 多场景多种子未闭环 | 写成已实现框架和待补消融 |
| Jetson 真机绝对时延 | 当前为 emulated 模拟 | 标注 emulated，写真机待补 |
| 硬件磁标定和 10A 电缆台 | 实物实验未执行 | 写成设计方案和未来工作 |
| 9 个 PVS chaos = 完整海缆巡检 | 缺电缆几何、声磁耦合和横流 | 写成不确定性感知验证基础 |
| n=1 实验 = 多种子统计 | 缺少 mean±std | 表格标题标注 n=1 |
