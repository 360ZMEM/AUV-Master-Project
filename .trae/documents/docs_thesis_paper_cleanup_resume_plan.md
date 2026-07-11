# docs/thesis paper 层续接清理与实验拾遗执行计划

## Summary

本计划用于续接 `docs/thesis` 与 `docs/experiment` 的文档重整任务。当前仓库已经完成了一部分前序工作：`docs/thesis/archive/` 已存在，`04_mpc_robustness_ablation.md` 与 `07_drift_log_and_known_issues.md` 已有归档副本，`docs/experiment/terrain_benchmark_log.md` 已添加阅读边界，`benchmark_test_log.md` 等实验日志也已开始区分 raw log 与论文正文材料。

但只读抽样发现，前序批量写入仍在部分文档中留下污染片段，例如 `state" error`、`state error` 和 `--------`。因此正式执行必须先修复已污染的当前入口文档，再创建 `docs/thesis/paper/` 正文层，并把实验缺口、PVS 极端电缆巡检场景与索引更新全部落盘。

本轮不运行新的长实验，不新增实际 YAML 场景，不把 pending 实验写成已完成。所有结论以当前仓库和已有结果路径为准。

## Current State Analysis

### 已确认存在的文件与目录

`docs/thesis/` 当前包含：

- `archive/`
- `00_overview.md`
- `01_baseline_repro_log.md`
- `02_es_ekf_validation.md`
- `03_uncertainty_quantification.md`
- `04_mpc_robustness_ablation.md`
- `05_scenario_recipes.md`
- `06_jetson_deploy_emulated.md`
- `07_drift_log_and_known_issues.md`
- `08_terrain_following_pid_mpc_status.md`
- `09_terrain_following_figures.md`
- `10_figure_review_and_offset_diagnosis.md`
- `INDEX.md`

`docs/experiment/` 当前包含：

- `benchmark_test_log.md`
- `experiment_modes_validation.md`
- `rosbag_analysis_validation.md`
- `terrain_benchmark_log.md`
- `real_deployment/`

`docs/thesis/paper/` 当前不存在，需要新建。

`scenarios/` 当前实际存在 9 个 PVS 场景：

- `scenario_baseline.yaml`
- `scenario_dvl_dropout_10.yaml`
- `scenario_dvl_dropout_30.yaml`
- `scenario_dvl_dropout_60.yaml`
- `scenario_dvl_dropout_90.yaml`
- `scenario_mag_distortion_light.yaml`
- `scenario_mag_distortion_heavy.yaml`
- `scenario_sonar_clutter.yaml`
- `scenario_combined_stress.yaml`

### 已确认的实验结果边界

可以引用为“当前已存在结果”的材料包括：

- `docs/experiment/benchmark_test_log.md` 中的 baseline n=1、ES-EKF/Std-EKF/Raw DR、MPC 离线测试、BT vs FSM 单次结果。
- `docs/experiment/terrain_benchmark_log.md` 中的 60s terrain benchmark、PID terrain low/mid/high ablation、MPC 深度调参、MPC x/y/yaw 支线。
- `docs/thesis/08_terrain_following_pid_mpc_status.md` 中的 terrain PID/MPC 结论和深度 MPC 回退理由。
- `/auv_data/results/control/mpc_xy_yaw_extreme/20260610_204314/` 中的 MPC 平面极端路径支线结果。
- `docs/thesis/figures/terrain_following/` 与 `docs/thesis/figures/architecture/` 中的论文图像。

当前不能写成已完成实验的材料包括：

- ES-EKF 多扰动多 seed sweep。
- baseline-MPC vs UA-MPC 多场景多 seed 主消融。
- NIS/R 自适应触发率的论文级聚合。
- Jetson 真机算力与真网络时延。
- 北京现场硬件集成、转台磁标定、10A 电缆台、HSF-500 埋深反演。
- PVS 中真实电缆路由几何、半掩埋、悬跨、坡面横穿、三相漏磁抵消和声呐漏检闭环。

### 已确认的污染残留

只读扫描确认以下入口文件仍需要修复：

- `docs/thesis/04_mpc_robustness_ablation.md`
  - 第 9 行出现 `--------的 MPC...`
  - 第 38、40、46 行出现 `state" error` 或 `state error` 污染片段。
- `docs/thesis/07_drift_log_and_known_issues.md`
  - 第 9 行出现 `# state error...` 污染片段。
- `docs/thesis/05_scenario_recipes.md`
  - 第 213、214、216 行出现 `state" error`、`state error` 和 `--------` 污染片段。

这说明后续执行不能再依赖未经验证的批量大段写入。必须采用“单文件、可审查、写后立即扫描”的补丁方式。

## Proposed Changes

### Phase 1: 修复已污染入口文档

目标是先恢复当前已暴露的污染残留，使 `docs/thesis` 入口文件重新可读。

处理文件：

- `docs/thesis/04_mpc_robustness_ablation.md`
- `docs/thesis/07_drift_log_and_known_issues.md`
- `docs/thesis/05_scenario_recipes.md`

具体做法：

- 对 `04_mpc_robustness_ablation.md` 做小范围重写：
  - 第 9 行改为正常段落，说明 MPC 是 guidance-level reference generator。
  - 第 38 行改为论文可用表述。
  - 第 40 行改为“不能写成”的边界句。
  - 第 46 行删除污染残句，使后续补实验建议从编号列表直接开始。
- 对 `07_drift_log_and_known_issues.md` 做小范围重写：
  - 第 9 行改为正常事实边界段落。
  - 保留数据统计偏差表、模型与场景偏差、算法结论边界和写作避雷清单。
- 对 `05_scenario_recipes.md` 的第 8 节做局部重写：
  - 保留“现有 9 个 PVS 场景只能覆盖传感/通信/感知不确定性”的判断。
  - 删除污染标题和污染前缀。
  - 用 2–3 段说明真实电缆巡检还需要短波长 S 弯、U 型急转、局部悬跨、半掩埋、坡面横穿、声呐不可见、三相交流漏磁抵消等场景。
  - 链接到即将新增的 `docs/thesis/paper/pvs_extreme_cable_scenarios.md`。

执行方式约束：

- 优先使用 `apply_patch` 做单文件局部编辑。
- 不使用 shell heredoc 写长中文正文。
- 每改完一批立刻用 `Grep` 扫描 `state" error|state error|nodes block|\.DS_Store|�|/dev/null`。
- 对 `--------` 只在目标 thesis/experiment 文档正文中扫描；Markdown 表格分隔线 `|---|` 不算污染，水平分割线 `---` 也不算污染。

### Phase 2: 建立 `docs/thesis/paper/` 正文层

新增目录：

- `docs/thesis/paper/`

新增 8 个文件：

- `docs/thesis/paper/INDEX.md`
- `docs/thesis/paper/01_background_and_significance.md`
- `docs/thesis/paper/02_system_design.md`
- `docs/thesis/paper/03_state_estimation.md`
- `docs/thesis/paper/04_decision_and_control.md`
- `docs/thesis/paper/05_experiments_and_discussion.md`
- `docs/thesis/paper/experiment_gap_and_next_plan.md`
- `docs/thesis/paper/pvs_extreme_cable_scenarios.md`

写作原则：

- 这是面向毕设正文的 paper 层，不是工程 debug 层。
- 语言以段落为主，减少碎片化分点。
- 允许保留必要表格，但表格服务于论文写作，不堆命令流水。
- 当前已有结果写成“已完成”；未跑实验写成“待补”或“建议补充”；不混淆两者。
- 所有实验表都标注数据来源和样本量，尤其 n=1。

### Phase 3: paper 层文件内容设计

`docs/thesis/paper/INDEX.md`：

- 说明 paper 层用途。
- 给出用户提供的 1–5 章目录映射。
- 区分三层文档关系：
  - `docs/thesis/paper/`：毕设正文材料。
  - `docs/thesis/`：工程证据和实验依据。
  - `docs/experiment/`：原始运行日志。
- 明确当前不能声称的事项：
  - MPC 深度控制全面优于 PID。
  - UA-MPC 主消融已完成。
  - Jetson 真机时延已完成。
  - 硬件电缆台和 HSF-500 埋深反演已完成。

`docs/thesis/paper/01_background_and_significance.md`：

- 覆盖 1.1–1.5。
- 以海上风电、海缆生命线、ROV/人工巡检/AUV 对比为主线。
- 写出本文研究内容和创新点的可用表述。
- 对外部文献和行业标准引用留出 `TODO: cite`，不伪造具体来源。

`docs/thesis/paper/02_system_design.md`：

- 覆盖 2.1–2.5。
- 将 `docs/internals/01_architecture.md` 的五层架构改写为论文式系统架构。
- 将 `docs/internals/05_binary_protocol.md` 的 `$CKTH` 72B 下行、`$AUV` 145B 上行和 UDP/VxWorks 偏差改写为双脑通信设计。
- 将 `docs/user-guide/03_console.md` 的 MANUAL/AUTONOMY/ESTOP 改写为上位机授权与安全闭环。
- 将 `docs/real_deployment/00_principles.md` 的真实部署原则作为 Sim-to-Real 安全约束来源。
- 对磁场模型、三相交流螺旋漏磁、侧扫声呐几何、lever-arm 标定只写当前理论框架和待补推导，不虚构实测。

`docs/thesis/paper/03_state_estimation.md`：

- 覆盖 3.1–3.6。
- 写异步传感器时间戳、安装偏差补偿、50Hz 磁信号噪声抑制、ES-EKF、声磁接力、自适应 R/NIS。
- 引用当前 baseline n=1 和工具链状态。
- 明确 DVL dropout、磁畸变、声呐杂波和 combined stress 的多 seed 仍待补。

`docs/thesis/paper/04_decision_and_control.md`：

- 覆盖 4.1–4.6。
- 写行为树任务调度、failsafe、PID/PVS terrain-following、MPC guidance-level reference generator、UA-MPC 设计边界。
- 重点写清：
  - terrain 主线采用 PID/PVS。
  - 深度 MPC 当前作为对照算法和扩展方向。
  - MPC x/y/yaw 支线说明复杂路径预瞄和速度规划潜力。
  - LOS 强 baseline 未被全面超过，因此不能写成 MPC 全面优于 PID/LOS。

`docs/thesis/paper/05_experiments_and_discussion.md`：

- 覆盖 5.1–5.6。
- 必须包含用户要求的六类内容：
  - 实验设计背景。
  - 实验条件控制。
  - 每个指标的解释和论文用途。
  - 表格本体。
  - 当前可写结论。
  - 缺少的实验、对比、更多环境需求。
- 建议表格：
  - 当前已完成实验总表。
  - terrain PID/MPC 主结果表。
  - PID terrain low/mid/high 消融表。
  - MPC x/y/yaw 支线表。
  - 缺失硬件/实物实验表。
- 所有 `n=1` 和 emulated 结果必须显式标注。

`docs/thesis/paper/experiment_gap_and_next_plan.md`：

- 按用户给出的毕设目录建立“章节-当前证据-缺口-补充方式-优先级”矩阵。
- P0：文档充分性与证据边界。
- P1：多 seed baseline 与 terrain PID low/mid/high 重复统计。
- P2：DVL dropout、mag distortion、sonar clutter、combined stress 的 3–5 seed sweep。
- P3：PVS 电缆巡检极端场景。
- P4：UA-MPC 与 PID/LOS 的复杂路径和不确定性对照。
- P5：Jetson 真机、AMD UDP 时延、转台磁标定、10A 电缆实验台、HSF-500 埋深反演。

`docs/thesis/paper/pvs_extreme_cable_scenarios.md`：

- 专门回答：现有 PVS 后端场景包含什么、选择是否正确、是否满足电缆巡检、如何缩小 discrepancy。
- 明确当前 9 个 YAML 偏向传感/通信不确定性，不完整模拟海底电缆巡检。
- 提出但不实际新增以下场景：
  - `scenario_cable_s_curve`
  - `scenario_cable_hairpin`
  - `scenario_cable_slope_crossing`
  - `scenario_cable_buried_gap`
  - `scenario_cross_current_near_bottom`
  - `scenario_combined_cable_extreme`
- 每个场景需说明：
  - 真实电缆巡检风险。
  - AUV 路径设计。
  - 环境/地形/流场设计。
  - 声、磁、DVL、深度观测角色。
  - 对应指标。
  - 当前 PVS 是否能直接实现，还是 future work。

### Phase 4: 更新索引

更新 `docs/thesis/INDEX.md`：

- 新增 `paper/` 作为“毕设正文层”入口。
- 保留 T1–T11 作为工程证据层。
- 修改阅读顺序：
  - 论文写作优先进入 `paper/INDEX.md`。
  - 需要证据和命令时再回到 T1–T11 与 `docs/experiment/`。

更新 `docs/INDEX.md`：

- 在“论文向”部分增加 `thesis/paper/INDEX.md`。
- 说明 `thesis/paper/` 面向正文，`thesis/` 面向工程证据。

不更新 `docs/experiment/real_deployment/INDEX.md`，除非执行时发现它直接引用了已经迁移的 paper 层内容。

### Phase 5: 验证

文件存在性验证：

- 确认 `docs/thesis/paper/` 下 8 个文件全部存在。
- 确认 `docs/thesis/archive/04_mpc_robustness_ablation_20260612_cleanup.md` 和 `docs/thesis/archive/07_drift_log_and_known_issues_20260612_cleanup.md` 仍存在。

污染扫描：

- 对以下范围扫描：
  - `docs/thesis/*.md`
  - `docs/thesis/paper/*.md`
  - `docs/experiment/*.md`
- 扫描关键词：
  - `state" error`
  - `state error`
  - `nodes block`
  - `.DS_Store`
  - `�`
  - `/dev/null`
- 对 `--------` 单独扫描，并人工区分 Markdown 合法表格分隔与污染片段。

可读性抽查：

- 读取 `docs/thesis/paper/INDEX.md`。
- 读取 `docs/thesis/paper/05_experiments_and_discussion.md`。
- 读取 `docs/thesis/paper/experiment_gap_and_next_plan.md`。
- 读取 `docs/thesis/paper/pvs_extreme_cable_scenarios.md`。
- 抽查被修复的 `04_mpc_robustness_ablation.md`、`07_drift_log_and_known_issues.md`、`05_scenario_recipes.md`。

事实边界检查：

- `n=1` 明确标注。
- pending/future work 不写成已完成。
- emulated Jetson 不写成真机 Jetson。
- MPC 不写成全面优于 PID/LOS。
- 当前 9 个 PVS 场景不写成完整电缆巡检数字孪生。

## Assumptions & Decisions

- 用户已明确偏好“旧文档优先”“paper 层覆盖全目录骨架”“按论文充分性判断实验缺口”。
- 本轮执行只做文档整理、paper 层落盘、缺口计划和场景设计，不跑长实验。
- 当前已有的污染残留必须先修复，否则 paper 层会引用不干净入口。
- `docs/thesis/paper/` 不替代 `docs/thesis/`，而是在其上方形成论文写作层。
- 新的极端电缆巡检场景先写成设计文档，不直接新增 `scenarios/*.yaml`。
- 外部标准、行业损失和文献引用只保留 `TODO: cite`，不伪造出处。

## Execution Order

1. 用 `apply_patch` 修复 `04_mpc_robustness_ablation.md`、`07_drift_log_and_known_issues.md`、`05_scenario_recipes.md` 的污染残留。
2. 扫描确认 `state" error|state error|nodes block|\.DS_Store|�|/dev/null` 在目标 docs 中无残留。
3. 创建 `docs/thesis/paper/` 和 8 个 paper 文档。
4. 先写 `INDEX.md` 与 `05_experiments_and_discussion.md`，确保 paper 层主入口和实验汇总成立。
5. 再写 `01_background_and_significance.md`、`02_system_design.md`、`03_state_estimation.md`、`04_decision_and_control.md`。
6. 写 `experiment_gap_and_next_plan.md`，按章节矩阵给出实验拾遗和补充优先级。
7. 写 `pvs_extreme_cable_scenarios.md`，回答 PVS 场景是否满足电缆巡检以及如何构造更刁钻场景。
8. 更新 `docs/thesis/INDEX.md` 与 `docs/INDEX.md`。
9. 执行文件存在性、污染扫描、可读性抽查和事实边界检查。

## Acceptance Criteria

- `docs/thesis/paper/INDEX.md` 能直接指导毕设 1–5 章写作。
- `docs/thesis/paper/05_experiments_and_discussion.md` 包含实验背景、条件控制、指标说明、表格本体、结论和缺口。
- `docs/thesis/paper/experiment_gap_and_next_plan.md` 能回答“目前哪些实验没做、缺什么对比、需要哪些消融和更多环境”。
- `docs/thesis/paper/pvs_extreme_cable_scenarios.md` 能回答“现有 PVS 场景是否足够模拟水下极端电缆巡检，以及如何缩小 discrepancy”。
- `04_mpc_robustness_ablation.md`、`07_drift_log_and_known_issues.md`、`05_scenario_recipes.md` 不再含污染残留。
- `docs/thesis/INDEX.md` 与 `docs/INDEX.md` 均能引导读者进入 paper 层。
- 所有未完成实验均明确标为待补，不被写成已完成结果。
