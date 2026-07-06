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
| [05_experiments_and_discussion.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/05_experiments_and_discussion.md) | 第 5 章 | 实验平台、指标、结果表、讨论与 Sim-to-Real 边界（5.1–5.8 全章，单文件） |

> **05 章单文件说明（P2-b，已合并）**：原 `05_experiments_and_discussion.md`（主）+ `..._continued.md`（续写）双文件结构已合并为**单一主文件**。续写文件中的新增结果已按主题并入主文件对应子节——terrain PID 3 seed → §5.5.3、P1 NIS/R 聚合 → §5.5.5、P1 控制侧聚合与 H1 solve-time 重跑 → §5.5.7、代理电缆 6 场景 smoke → §5.7.7。主文件 §5.5.x 编号保持不变（03/04 章及 e2e 计划文档均按此编号交叉引用），不再存在双文件编号重叠问题。
> **三组过渡实验（F1/F2/F3）证据**见工程证据层 [docs/thesis/11_transition_experiments_F1_F2_F3.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/11_transition_experiments_F1_F2_F3.md)，对应第 2/3 章。

按论文写作支撑用途组织的补充文档：

| 文件 | 用途 |
|---|---|
| [experiment_gap_and_next_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/experiment_gap_and_next_plan.md) | 当前实验缺口、优先级和补实验计划 |
| [pvs_extreme_cable_scenarios.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/pvs_extreme_cable_scenarios.md) | PVS 场景真实性、极端电缆巡检设计和 discrepancy 收敛 |
| [e2e_distorted_prior_next_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/e2e_distorted_prior_next_plan.md) | 端到端 distorted-prior 电缆探测验证专项计划（§5.5.11 第 (5) 条引用），闭合"clean-prior 端到端已闭环、distorted-prior 仅算法级验证"的缺口 |

> **§5.5.10/§5.5.11 电缆探测证据分层（P2-c）**：`05_experiments_and_discussion.md` §5.5.10 为主仓 DL/T 1278 数字孪生验收（clean prior，3/3 ready/pass）；§5.5.11 把端到端电缆探测证据显式分层——主仓端到端运行的是同源 `AuvMagTrackingPipeline`（非代理），但只在 clean prior 下被激励，distorted-prior 失效/恢复边界为专用仓库 `AUV-Master-Mag` docs 28-30 的**算法级、n=1、纯仿真**证据（仅引用，不迁移）。写作时严禁把算法级 distorted-prior 结论表述为主仓端到端实测。

> **上位机操作员工作流演示视频（答辩/附录）**：§5.5.10 末尾附上位机操作员工作流演示视频，由 [tools/record_console_operator_video.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/record_console_operator_video.py) 在 headless（`xvfb-run` + `QT_QPA_PLATFORM=offscreen`）下驱动真实 PySide6 `MainWindow`，用 run1 真实遥测 `tracking.jsonl` 逐帧回放电缆巡检监控面板并 `window.grab()` 后经 ffmpeg 编码 MP4（PIL 作 GIF 回退），产物在 `docs/thesis/figures/console_operator_video/`。**边界：真实遥测的离线回放演示（非现场实时会话），仅执行安全操作员动作、停用外发定时器不发包，末帧对应全程离窗后的 `NOT READY/FAIL` 状态。**

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
| 主仓端到端已验证 distorted-prior 鲁棒性 | 主仓端到端只跑 clean prior（`max_route_offset≈0`），无先验扰动 knob | 写成 clean-prior 端到端已闭环 + 引用 docs 28-30 算法级边界，见 §5.5.11 |
| DL/T 1278 数字孪生验收 = 现场海试验收 | 确定性电缆先验、非真实检测噪声 | 写成 preliminary_acceptance_ready，见 §5.5.10 边界 |
| 海缆 DL/T ready/pass = 全程通过 | 判定限有效巡检窗口，全程 readiness=limited | 写成"有效巡检窗口内通过"，见 §5.5.10 边界 3 |
