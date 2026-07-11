# docs/thesis + docs/experiment 重整、paper 正文层与实验拾遗计划

## Summary

本计划用于下一轮执行：先整理 `docs/thesis` 与 `docs/experiment` 中阅读负担较重、夹杂 debug 过程的文档，再新增 `docs/thesis/paper/` 作为直接面向毕设写作的正文材料层，最后基于当前实际存在的实验结果梳理“已完成 / 缺失 / 需新增消融 / 需更多环境验证”的实验矩阵，并专门评估 PVS 后端场景是否足以支撑“海底电缆巡检”和“水下极端工况”的论文叙事。

用户已确认本轮执行偏好：

* 优先级：旧文档优先；

* `docs/thesis/paper/` 第一批范围：覆盖 1–5 章全目录骨架；

* 实验缺口判据：按论文充分性，而不是最低可答辩标准。

执行时仍以“当前实际存在的结果”为准，不把计划中 pending 或 future work 写成已完成实验。

## Current State Analysis

### 1. 文档结构现状

已确认的主要文档入口：

* `docs/thesis/INDEX.md`：当前 thesis 文档索引，列出 T1–T11。

* `docs/thesis/00_overview.md`：实验体系总览。

* `docs/thesis/01_baseline_repro_log.md`：baseline n=1 复现与定位/控制/决策基准。

* `docs/thesis/02_es_ekf_validation.md`：ES-EKF 状态估计验证，明确多 seed 与多扰动 pending。

* `docs/thesis/03_uncertainty_quantification.md`：不确定性、NIS、自适应 R 与 UA-MPC 耦合。

* `docs/thesis/04_mpc_robustness_ablation.md`：MPC/UA-MPC 鲁棒性和调参过程，内容较长且混有阶段性结论。

* `docs/thesis/05_scenario_recipes.md`：9 个 PVS chaos 场景配方和 sweep 计划。

* `docs/thesis/06_jetson_deploy_emulated.md`：Jetson emulated 算力文档。

* `docs/thesis/07_drift_log_and_known_issues.md`：已知偏差总账，包含大量 debug 历史。

* `docs/thesis/08_terrain_following_pid_mpc_status.md`：terrain PID/MPC 与 MPC x/y/yaw 支线结论。

* `docs/thesis/09_terrain_following_figures.md`：地形跟随图像生成与 caption。

* `docs/thesis/10_figure_review_and_offset_diagnosis.md`：图像审查和偏移诊断。

* `docs/experiment/benchmark_test_log.md`：2026-06-08 端到端基准测试日志。

* `docs/experiment/terrain_benchmark_log.md`：terrain、MPC 深度调参、x/y/yaw 支线实验日志。

* `docs/experiment/experiment_modes_validation.md`：实验运行器模式验证。

* `docs/experiment/rosbag_analysis_validation.md`：rosbag 分析工具链验证。

* `docs/experiment/real_deployment/*.md`：真实部署 dry-run 日志。

用户指出的问题与抽样结果一致：部分 thesis 与 experiment 文档承担了“工程 debug 总账 + SOP + 论文材料 + 中间失败过程”的多重角色，阅读时需要穿过大量调试细节，影响毕设正文写作。

### 2. 当前已存在的实验结果

已确认存在并可引用的结果包括：

* `docs/experiment/benchmark_test_log.md` 中的 baseline n=1：ES-EKF / Std-EKF / Raw DR、MPC 离线测试、BT vs FSM。

* `/auv_data/results/control/mpc_test/*/report.md`：多次 MPC 离线测试报告，其中 `20260610_154407`、`20260610_170426` 等为近期调参产物。

* `results/control/terrain_following_20260610_175154/*/analysis/summary_statistics.csv`：PID/MPC × baseline/terrain 四组 60s terrain benchmark。

* `results/control/pid_terrain_ablation_20260610_summary.csv`：PID terrain low/mid/high 地形强度消融。

* `/auv_data/results/control/mpc_xy_yaw_extreme/20260610_204314/summary_metrics.csv` 与 `best_comparison.csv`：MPC x/y/yaw 极端路径支线。

* `docs/thesis/figures/terrain_following/`：terrain 相关论文图像。

* `docs/thesis/figures/architecture/`：系统架构、ROS2 拓扑、数据流、安全仲裁等图像。

### 3. 当前明确缺失或不足的实验

以“论文充分性”判据看，当前明显缺口包括：

* 多 seed mean±std：多数实验仍是 n=1 或少量 smoke，缺少 5 seed 统计。

* ES-EKF 鲁棒性：DVL dropout、磁畸变、声呐杂波、多源 combined stress 的多 seed 结果仍 pending。

* UA-MPC 主消融：baseline-MPC vs UA-MPC 多场景多 seed 未完成；`04_mpc_robustness_ablation.md` 已将其标注为 future work。

* 不确定性量化：NIS 时序、卡方阈值带、自适应 R 触发率还缺论文级聚合。

* `sigma_xy_ref`、权重、控制惩罚、置信度映射灵敏度：工具链部分支持，但结果不足。

* Jetson 真机算力：目前偏 emulated，不能宣称真机绝对延迟。

* 硬件集成/北京现场/转台磁标定/10A 大电流模拟电缆实验台：大纲中要求，但当前仓库内未看到完整实测结果。

* 电缆巡检闭环场景：已有 chaos 场景偏“传感/通信故障”，terrain 场景偏“近底跟随”，x/y/yaw 支线偏“极端路径”；三者与真实“海缆巡检”的目标、磁/声观测和路径约束仍有 discrepancy，需要文档中明确并提出补实验。

### 4. PVS 场景覆盖现状

`docs/thesis/05_scenario_recipes.md` 和 `scenarios/*.yaml` 显示，当前 PVS 场景包括：

* `scenario_baseline.yaml`

* `scenario_dvl_dropout_10.yaml`

* `scenario_dvl_dropout_30.yaml`

* `scenario_dvl_dropout_60.yaml`

* `scenario_dvl_dropout_90.yaml`

* `scenario_mag_distortion_light.yaml`

* `scenario_mag_distortion_heavy.yaml`

* `scenario_sonar_clutter.yaml`

* `scenario_combined_stress.yaml`

这些场景能覆盖传感器丢包、磁饱和、声呐噪声、深度毛刺、IMU 漂移和均匀海流，但还不足以完全模拟海底电缆巡检中的极端几何与环境：

* 缺少电缆路由几何变化：急弯、S 弯、交叉、局部绕障、断续可见。

* 缺少地形与电缆耦合：电缆贴底、半掩埋、悬跨、沟槽边缘、坡面横穿。

* 缺少海流空间变化：剪切流、横流、近底涡、流向突变。

* 缺少磁场物理变化：三相抵消、埋深变化、铠装屏蔽、局部强干扰源。

* 缺少声呐成像极端：遮挡、多径、底质变化导致的漏检/误检。

## Proposed Changes

### Phase A：建立可重复的文档打补丁方式

目标：先从一个文档验证“低成本、稳定、不污染”的文档修复方式。

首选试点文件：

* `docs/experiment/terrain_benchmark_log.md`

原因：

* 该文件近期已被重写成相对干净的实验日志；

* 范围适中，包含命令、结果、坑点和论文建议；

* 可用于验证“保留事实表 + 删除 debug 流水 + 提取论文结论”的编辑模式。

具体做法：

1. 只读检查该文件中的：

   * 标题层级是否清楚；

   * 是否仍混有中间 debug 过程；

   * 是否有重复、过期、与当前实际结果冲突的内容；

   * 是否能被 `docs/thesis/paper/` 引用。
2. 小范围补丁：

   * 保留“命令、结果、坑点、结论”；

   * 删除任何与最终结论无关的失败路径细节；

   * 添加“本文件为实验执行日志，正文引用请看 paper 层”的提示。
3. 验证：

   * `Grep` 检查是否仍有明显污染词，如 `nodes block`、`state" error`、`.DS_Store`、`/dev/null`；

   * `Read` 抽查开头、中段、结尾。

若该方式稳定，再推广到其他文档；若文档过长或混乱严重，则采用“归档重写”：

* 原文保留为 `docs/thesis/archive/<原文件名>` 或 `docs/experiment/archive/<原文件名>`；

* 新文件只保留当前事实、结果表、论文可引用结论和指向 archive 的链接。

### Phase B：重整 docs/thesis 与 docs/experiment

#### B1. 新增归档目录

新增：

* `docs/thesis/archive/`

* `docs/experiment/archive/`

归档原则：

* 对于 `07_drift_log_and_known_issues.md`、`04_mpc_robustness_ablation.md` 这类历史调试信息密集文档，优先归档原文，并重写当前版摘要。

* 对于 `09_terrain_following_figures.md`、`08_terrain_following_pid_mpc_status.md` 这类已经比较结构化的文件，只做局部清理。

* 对于 `docs/experiment/*.md`，保留其“实验执行日志”身份，不强行改成论文正文。

#### B2. 重写或瘦身文件清单

建议第一批处理：

1. `docs/thesis/07_drift_log_and_known_issues.md`

   * 归档原文；

   * 新文件改为“当前仍影响论文写作的偏差清单”；

   * 删除大量已解决 debug 叙事，只保留状态、影响、论文规避、补实验路径。

2. `docs/thesis/04_mpc_robustness_ablation.md`

   * 归档原文；

   * 新文件分为：MPC 定位、已完成结果、已失败/冻结原因、仍需补的消融、正文可写结论；

   * 避免继续在该文件内追加长调参流水。

3. `docs/thesis/05_scenario_recipes.md`

   * 保留为工程场景配方；

   * 增加“与电缆巡检真实性的差距”小节；

   * 链接到新建的 paper 缺口文档。

4. `docs/experiment/benchmark_test_log.md`

   * 保留 raw log；

   * 添加顶部摘要，明确这是 2026-06-08 单次执行，不是最终论文结果；

   * 将 MCAP 损坏等历史问题压缩为“已修复/仍需注意”。

5. `docs/experiment/experiment_modes_validation.md`

   * 保留执行验证；

   * 压缩中间失败细节；

   * 单列“当前仍有效的模式验证结论”。

6. `docs/experiment/rosbag_analysis_validation.md`

   * 保留工具链验证；

   * 将输出格式不一致、录制分析链问题整理为当前状态。

#### B3. 更新索引

更新：

* `docs/thesis/INDEX.md`

* `docs/experiment/real_deployment/INDEX.md` 如有必要；

* `docs/INDEX.md` 如 paper 层需要顶层入口。

索引中新增说明：

* `docs/thesis/`：工程证据、实验依据、代码符号对照；

* `docs/thesis/paper/`：面向毕设正文；

* `docs/experiment/`：单次运行日志和工具链验证；

* `archive/`：历史 debug 与中间过程，仅供追溯。

### Phase C：新增 docs/thesis/paper 正文层

新增目录：

* `docs/thesis/paper/`

新增第一批文件：

1. `docs/thesis/paper/INDEX.md`

   * 说明 paper 层用途：减少工程细节，直接服务毕设写作；

   * 给出章节映射和数据来源；

   * 明确“已完成 / 待补 / 不宜声称”的边界。

2. `docs/thesis/paper/01_background_and_significance.md`

   * 覆盖 1.1–1.5；

   * 包含海上风电、海缆生命线、ROV/人工巡检/AUV 对比；

   * 只写论文式段落，不堆代码路径。

3. `docs/thesis/paper/02_system_design.md`

   * 覆盖 2.1–2.5；

   * 承接双脑架构、Jetson/AMD/VxWorks、UDP 协议、电气隔离、磁/声几何建模；

   * 数据来源包括 `docs/internals/01_architecture.md`、`docs/internals/05_binary_protocol.md`、`docs/real_deployment/00_principles.md`、`docs/user-guide/03_console.md`。

4. `docs/thesis/paper/03_state_estimation.md`

   * 覆盖 3.1–3.6；

   * 写 ES-EKF、异步时空同步、自适应 R/NIS、DVL 丢包与磁畸变实验；

   * 明确当前多 seed 和多扰动仍不足。

5. `docs/thesis/paper/04_decision_and_control.md`

   * 覆盖 4.1–4.6；

   * 写 BT、failsafe、PID/PVS、MPC/UA-MPC、terrain-following 和 x/y/yaw 支线；

   * 明确“深度/terrain 主线用 PID，MPC 作为复杂路径制导扩展”。

6. `docs/thesis/paper/05_experiments_and_discussion.md`

   * 覆盖 5.1–5.6；

   * 包含实验设计背景、实验条件控制、指标定义、表格本体、结论和缺口；

   * 这是最重要的汇总正文。

7. `docs/thesis/paper/experiment_gap_and_next_plan.md`

   * 汇总所有缺失实验；

   * 按论文充分性给出优先级；

   * 说明每个补实验的目标、指标、预期表格、运行条件。

8. `docs/thesis/paper/pvs_extreme_cable_scenarios.md`

   * 专门回答 PVS 后端场景是否足以模拟水下极端电缆巡检；

   * 提出新增极端场景设计；

   * 明确如何缩小仿真场景与真实电缆巡检任务的 discrepancy。

写作风格：

* 减少列表，更多段落叙述；

* 每个文件保留少量必要表格；

* 不沉浸在函数名、行号、debug 命令；

* 关键数据表只引用当前实际存在结果；

* pending 实验必须明确写成“待补”，不能写成已验证。

### Phase D：实验充分性评估与补实验计划

新增或回填到：

* `docs/thesis/paper/experiment_gap_and_next_plan.md`

按用户给出的毕设目录，建立章节到证据的覆盖矩阵（部分实验不被本代码库覆盖，因此简要提及即可，例如软试验台等）：

| 章节              | 当前证据                               | 缺口                          | 补充优先级          |
| --------------- | ---------------------------------- | --------------------------- | -------------- |
| 1.1–1.3 背景与现状   | 主要依赖外部文献，仓库内证据少                    | 需要行业损失、DL/T 标准、ROV/AUV 对比引用 | 高              |
| 2.1 标准对齐        | 标准文档存在，但未系统摘录                      | 0.05 nT、0.2 m 埋深误差需来源说明     | 高              |
| 2.2 双脑架构        | docs/internals、real\_deployment 已有 | 需转成论文段落和架构图说明               | 高              |
| 2.3 磁场模型        | 仓库内未见完整论文式推导                       | 三相交流、螺旋漏磁、屏蔽因子需补理论文档        | 高              |
| 2.4 声呐与标定       | 工程文档不足                             | 侧扫声呐几何与 lever-arm 模型需补      | 中高             |
| 3.5 状态估计验证      | baseline n=1，DVL/mag/sonar pending | 多 seed、多扰动、NIS/R 触发率        | 高              |
| 4.5 决策控制鲁棒性     | terrain、MPC x/y/yaw、BT/FSM 有部分结果   | UA-MPC 多场景消融、多 seed、极端安全边界  | 高              |
| 5.2 数字孪生        | PVS chaos + terrain 存在             | 与电缆巡检真实性差距需要补场景             | 高              |
| 5.3 硬件集成        | real\_deployment SOP 多，实测少         | 北京现场、转台标定、故障注入结果            | 中高             |
| 5.4 实验室电缆       | 当前结果不足                             | 10A 电缆台、HSF-500、埋深反演        | 高，out of scope |
| 5.5 Sim-to-Real | emulated Jetson 有文档                | 真 Jetson、真网络、真 AMD 延迟       | 中高             |

补实验优先级建议：

1. P0：文档充分性与证据边界，不跑新实验也必须完成。
2. P1：多 seed baseline + terrain PID low/mid/high 重复统计。
3. P2：DVL dropout、mag distortion、sonar clutter、combined stress 的 3–5 seed sweep。
4. P3：PVS 电缆巡检极端场景：急弯/坡面/横流/局部遮挡/磁畸变组合。
5. P4：UA-MPC 与 PID/LOS 的复杂路径和不确定性对照。
6. P5：硬件/实物相关：Jetson 真机、AMD UDP 时延、转台磁标定、10A 电缆实验台。

### Phase E：PVS 极端电缆巡检场景设计

新增或回填到：

* `docs/thesis/paper/pvs_extreme_cable_scenarios.md`

* `docs/thesis/05_scenario_recipes.md`

拟新增场景类别：

1. `scenario_cable_s_curve.yaml`

   * 短波长 S 弯电缆路径；

   * 目标：测试 AUV 路径预瞄和横向误差；

   * 对应当前 x/y/yaw 支线，但需接入 PVS/ROS benchmark。

2. `scenario_cable_hairpin.yaml`

   * 180° 掉头或 U 型路由；

   * 目标：测试 LOS/PID 与 MPC 预瞄的边界。

3. `scenario_cable_slope_crossing.yaml`

   * 电缆横穿斜坡/沟槽；

   * 目标：耦合 terrain-following 与 cable tracking。

4. `scenario_cable_buried_gap.yaml`

   * 电缆局部掩埋或声呐不可见，仅磁信号可用；

   * 目标：测试声磁接力和置信度衰减。

5. `scenario_cross_current_near_bottom.yaml`

   * 近底横流或流向突变；

   * 目标：测试路径跟踪、速度规划和安全离底。

6. `scenario_combined_cable_extreme.yaml`

   * 急弯 + 地形起伏 + DVL dropout + 磁饱和 + 声呐杂波 + 横流；

   * 目标：作为“水下极端电缆巡检”综合压力测试。

每个场景文档必须回答：

* 是否直接服务电缆巡检；

* 它模拟的真实风险是什么；

* 观测链路中声、磁、DVL、深度各自扮演什么角色；

* 评价指标是什么；

* 与现有场景相比新增了什么困难；

* 是否能通过当前 PVS 后端真实实现，还是只作为 future work。

### Phase F：指标与表格体系

在 `docs/thesis/paper/05_experiments_and_discussion.md` 中建立统一指标解释：

* 定位指标：XY RMSE、Z RMSE、CEP50、Max Drift、NIS mean/阈值越界率。

* 控制指标：heading RMSE、depth RMSE、lateral RMSE、控制量平滑度、solve time、fallback rate。

* terrain 指标：seabed clearance mean/min/std/RMSE to 3m、clearance violation ratio。

* 电缆巡检指标：lateral cable offset RMSE、route completion、buried-depth inversion error、detection continuity。

* 系统指标：Jetson CPU/MEM、IPOPT solve time、UDP latency、packet loss、ESTOP response。

每个指标需写：

* 物理意义；

* 为什么适合电缆巡检；

* 当前是否已有结果；

* 来源文件/结果目录；

* 论文表格建议。

### Phase G：验证步骤

执行完成后必须验证：

1. 文件存在性：

   * `docs/thesis/paper/INDEX.md`

   * `docs/thesis/paper/01_background_and_significance.md`

   * `docs/thesis/paper/02_system_design.md`

   * `docs/thesis/paper/03_state_estimation.md`

   * `docs/thesis/paper/04_decision_and_control.md`

   * `docs/thesis/paper/05_experiments_and_discussion.md`

   * `docs/thesis/paper/experiment_gap_and_next_plan.md`

   * `docs/thesis/paper/pvs_extreme_cable_scenarios.md`

2. 污染词扫描：

   * 对 `docs/thesis/*.md`、`docs/experiment/*.md`、`docs/thesis/paper/*.md` 扫描：

     * `nodes block`

     * `state" error`

     * `.DS_Store`

     * `--------`

     * `/dev/null`

   * 若是代码块中的合法 shell 内容，需要人工确认；否则删除。

3. 引用一致性：

   * `docs/thesis/INDEX.md` 中新增 paper 层入口；

   * `docs/INDEX.md` 中新增 paper 层或 thesis 层说明；

   * paper 文档中引用的结果路径必须真实存在。

4. 事实边界：

   * 所有 n=1 结果必须标注 n=1；

   * pending / future work 不能写成已完成；

   * emulated Jetson 不能写成真机 Jetson；

   * MPC 不能写成全面优于 PID。

5. Markdown 可读性：

   * 抽查每个新 paper 文档开头、中段、结尾；

   * 表格列数正确；

   * 章节标题与用户给出的毕设目录对应。

## Assumptions & Decisions

* 不在本轮执行中直接跑长实验；本计划阶段只做文档重整和补实验计划硬化。

* 执行时以仓库和 `/auv_data/results` 中实际存在的结果为准。

* 旧文档不强制全部删除；对于历史 debug 价值高但不适合阅读的内容，采用 archive 保留。

* `docs/thesis/paper/` 是论文正文层，不替代 `docs/thesis/` 的工程证据层。

* `docs/experiment/` 继续作为 raw run log，不承担论文正文职责。

* 由于用户选择“论文充分性”，缺口清单会严格列出硬件、实测、多 seed、标准对齐、磁/声物理模型等当前不足，而不是只给最低可答辩版本。

## Execution Order

1. 试点清理 `docs/experiment/terrain_benchmark_log.md`。
2. 建立 `docs/thesis/archive/` 与 `docs/experiment/archive/`。
3. 归档并重写或瘦身 `07_drift_log_and_known_issues.md`、`04_mpc_robustness_ablation.md`。
4. 局部清理 `05_scenario_recipes.md`、`benchmark_test_log.md`、`experiment_modes_validation.md`、`rosbag_analysis_validation.md`。
5. 创建 `docs/thesis/paper/` 与 8 个第一批 paper 文档。
6. 将当前实验结果和缺口矩阵写入 `experiment_gap_and_next_plan.md`。
7. 将 PVS 极端电缆巡检场景设计写入 `pvs_extreme_cable_scenarios.md`，并在 `05_scenario_recipes.md` 加链接。
8. 更新 `docs/thesis/INDEX.md` 与 `docs/INDEX.md`。
9. 执行只读验证和污染词扫描。

## Acceptance Criteria

* 用户打开 `docs/thesis/paper/INDEX.md` 后，可以直接按毕设目录找到每章写作材料。

* `docs/thesis` 中 debug 总账型文档不再阻塞阅读；旧细节可通过 archive 追溯。

* `docs/experiment` 的定位明确为运行日志，不再被误认为论文正文。

* `experiment_gap_and_next_plan.md` 能回答“哪些实验已做、哪些没做、为什么不够、怎么补”。

* `pvs_extreme_cable_scenarios.md` 能回答“现有 PVS 场景是否满足电缆巡检、如何构造更刁钻水下极端场景、如何缩小 discrepancy”。

* 所有引用的结果路径都来自实际已存在文件或明确标注为待补。

