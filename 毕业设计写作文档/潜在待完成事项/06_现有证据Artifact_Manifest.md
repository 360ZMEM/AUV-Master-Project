# 06 现有证据 Artifact Manifest

## 1. 用途

本文件由 `tools/build_thesis_artifact_manifest.py` 从审核后的 catalog 生成。
JSON 是机器可读事实源，本 Markdown 只提供审阅摘要。校验值覆盖当前可访问
文件的路径、字节数与 SHA256；历史实验未记录的 Git commit 不用当前 commit
冒充，而是保留为 provenance gap。

- 生成时间（UTC）：`2026-08-13T09:48:11.046324+00:00`
- 当前仓库 commit：`b9dd38a983d5129717d65f881020735c1f202c43`
- 当前工作树状态：`not_evaluated`
- Catalog SHA256：`1d7b3210ee817d711740dce03246abbb64651353b3a572a8a5ed092a53b6e01e`
- JSON SHA256：`67781299a30cbef4d232a2d1d3ddd19386f542c5bcb543c085ce2d442832ada3`

## 2. 证据等级

| 等级 | 定义 |
|---|---|
| A | 原始输入、配置/运行清单、分析代码和机器可读结果均可访问，且生成版本可追溯。 |
| B | 原始输入和机器可读结果可访问，但历史 commit、配置快照或标准化摘要至少缺一项。 |
| C | 只有带时间戳的报告、日志摘要或部分结果，缺少当前可访问的原始数据包。 |
| D | 只有计划、接口或未经数据支撑的声明，不能作为实验结论。 |

## 3. 总表

| ID | 证据 | 数据层 | 等级 | 状态 | 样本范围 | 文件 | 原始输入 | 必需项 |
|---|---|---|---:|---|---|---:|---:|---:|
| BUILD-R00 | ThuThesis 论文构建基线 | document_build | A | complete | 180 页 A4 PDF，47 图，63 表，90 条 Biber 记录（R30 写作审计 + AUV-Master-Mag 电缆算法内容迁移后） | 15/15 | 0/0 | 完整 |
| MAG-CABLE-ALGORITHM-BOUNDARY | 专用磁探测仓库电缆探测算法级边界与迁移图 | algorithm_simulation | C | complete_with_boundaries | 专用电缆跟踪算法（AUV-Master-Mag，审计基线 commit 12e1884b59737dbe14e83c825b6cea9bb3c7a4bb）；确定性单次纯仿真复现（n=1）；覆盖先验轻/中/重档、稀疏/中断声呐、30--120 m 曲率、留一法消融、50/70 m 跨车道压力、20--36° 之字形埋深调优等多场景离线扫描 | 27/27 | 0/0 | 完整 |
| MAG-BG-45 | TMR/SK2301 45 Hz 短时背景记录 | sensor_hardware_raw | B | partial | 2000 Hz，7839 样本，3.9195 s，三轴 | 8/8 | 1/1 | 完整 |
| MAG-JOINT-45 | 45 Hz 电缆、TMR 与 ArUco 联合拟合 | sensor_hardware_analysis | B | complete_with_boundaries | 106821 ADC 样本，832 位姿记录，777 对齐点 | 43/43 | 2/2 | 完整 |
| MAG-ADC-ENOB-CH4 | SK2301 CH4 短接噪声、ENOB 与 45 Hz 等效磁噪声 | adc_hardware_raw | B | complete_with_boundaries | CH4 短接；2000/4000/8000/16000 Hz 各 10 s；最高 160000 样本 | 10/10 | 1/1 | 完整 |
| MAG-R08-HANDOFF | TMR/SK2301 M0/M1/M4 最小采集 handoff | sensor_hardware_infrastructure | D | infrastructure_complete_dry_run_only | M0×3、M1×3、M4 五档，共 11 个计划项；尚无本轮实测样本 | 9/9 | 0/0 | 完整 |
| ESKF-NIS-8X3 | ES-EKF 八场景三种子 NIS/R 聚合 | pvs_closed_loop | B | complete_with_negative_semantic_result | 8 场景 × 3 seed = 24 run，30 s/run | 91/91 | 24/24 | 完整 |
| UAMPC-ATTRIBUTION | UA-MPC 主消融、P-1/P-2 与 H4 归因 | pvs_and_deterministic_control | B | complete_with_known_observability_gap | 主消融 18 run；P-1 27 run；P-2 27 run；H4 8 组 | 124/124 | 72/72 | 完整 |
| PROXY-EXTREME-6 | 六类代理极端电缆场景冒烟 | pvs_proxy_closed_loop | B | partial_single_seed | 6 场景 × 2 模式 × 1 seed = 12 run | 29/29 | 12/12 | 完整 |
| COVERAGE-R12 | 之字形扫描覆盖率、航程与时间归一化扫描 | analytic_normalized_geometry | A | complete_with_hardware_boundary | 4 波束角 × 4 磁宽度比 × 5 间距比 × 4 速度比 × 4 横向误差比，共 1280 组 | 13/13 | 0/0 | 完整 |
| MPC-R15-DIAGNOSTICS | MPC 每周期可解性诊断基础设施 | control_observability_infrastructure | D | infrastructure_complete | 6 项确定性回归；成功、最大迭代失败、上一输出回退与 bundle 聚合路径 | 9/9 | 0/0 | 完整 |
| MPC-R16-FEASIBILITY | MPC 热启动、软约束与终端保持机制对照 | pvs_closed_loop_and_deterministic_mechanism_probe | B | complete | PVS baseline 3 seed x warm-start 2 x slack 2；H4 两路径 x 六机制变体 | 13/13 | 0/0 | 完整 |
| DECISION-R17-HYSTERESIS | BT/FSM 等价迟滞去抖与组合故障对照 | decision_core_monte_carlo | B | complete | 每架构 1000 次持续漏水、100 条 30 s 阈值噪声序列、500 次组合故障 | 10/10 | 0/0 | 完整 |
| ES-EKF-R18-LONG-HORIZON | ES-EKF 五分钟 seed 与观测相位敏感性 | offline_es_ekf_dynamics | B | complete | baseline/dvl_dropout_60/combined_stress x 5 seed x 0/100 ms DVL phase；每次 300 s | 10/10 | 0/0 | 完整 |
| MAG-R19-MEASURED-NOISE-REPLAY | 实测三轴背景噪声与同协方差高斯成对回放 | measured_noise_offline_replay | B | complete | 协方差匹配高斯/实测三轴回放 x 5 seed；每次 60 s；源记录 3.9195 s @ 2 kHz | 12/12 | 1/1 | 完整 |
| CONTROL-R13-PROXY-3SEED | 六代理电缆场景三种子正式矩阵 | pvs_proxy_closed_loop_with_repair_provenance | B | complete | 6 场景 x 2 模式 x 3 seed；每次 60 s；36 条权威记录 | 10/10 | 0/0 | 完整 |
| CONTROL-R13-V2-SOURCE-CONFIDENCE | R13-v2 分源置信保守 UA 正式矩阵 | pvs_proxy_closed_loop_source_specific_confidence | B | complete_with_negative_boundaries | 6 场景 x 2 模式 x 3 seed；每次 60 s；36/36 ok；18 个 UA MCAP 重新抽取 sonar p_track 样本 | 80/80 | 36/36 | 完整 |
| CONTROL-R13-V2-TELEMETRY-AUTHORITY-SUPPLEMENT | R13-v2 applied speed 与 authority snapshot 遥测补强 | pvs_proxy_closed_loop_source_specific_confidence_telemetry_supplement | B | complete_telemetry_observability_supplement_with_boundaries | 旧 R13-v2 36-run 正式矩阵事后缺口审计 + 当前 proxy 配置下 S-curve/buried_gap/combined/hairpin 四场景 x 3 seed x UA-only；共 12 个补强 run；每次约 60 s | 34/34 | 12/12 | 完整 |
| CONTROL-CBF-TERRAIN-HIGH-SMALL-MATRIX | terrain-high CBF 近底安全小矩阵 | pvs_proxy_terrain_cbf_kinematic_setpoint | B | complete_small_matrix_with_boundaries | terrain_high；PID/MPC 各 1 次；约 30 s/run；manual setpoint 3.0 m 离底目标；kinematic setpoint proxy | 42/42 | 6/6 | 完整 |
| CONTROL-CBF-TERRAIN-HIGH-60S-RECHECK | terrain-high CBF 60 s 复核 | pvs_proxy_terrain_cbf_kinematic_setpoint | B | complete_recheck_with_realtime_boundary | terrain_high；PID/MPC 各 1 次；约 60 s/run；manual setpoint 3.0 m 离底目标；kinematic setpoint proxy | 50/50 | 6/6 | 完整 |
| CONTROL-CBF-TERRAIN-LOW-MID-HIGH-60S-MATRIX | CBF terrain low/mid/high 60 s 单 seed 矩阵 | pvs_proxy_terrain_cbf_kinematic_setpoint | B | complete_single_seed_matrix_with_boundaries | terrain low/mid/high；PID/MPC 各 1 次；共 6 run；约 60 s/run；manual setpoint 3.0 m 离底目标；kinematic setpoint proxy；single seed | 130/130 | 18/18 | 完整 |
| CONTROL-CBF-TERRAIN-LOW-MID-HIGH-60S-3SEED-MATRIX | CBF terrain low/mid/high 60 s 三种子复核矩阵 | pvs_proxy_terrain_cbf_kinematic_setpoint | B | complete_multi_seed_proxy_matrix_with_boundaries | terrain low/mid/high x 3 seed x PID/MPC；共 18 run；约 60 s/run；manual setpoint 3.0 m 离底目标；kinematic setpoint proxy | 41/41 | 0/0 | 完整 |
| CONTROL-R14-R13-DIAGNOSIS | R13 深度硬饱和归因、平滑修复与固定置信权重分解 | pvs_proxy_closed_loop_and_state_snapshot_replay | B | complete | 216 组快照/网格求解；18 组关键场景闭环；综合极端 4 变体 x 3 seed | 13/13 | 0/0 | 完整 |
| ES-EKF-R20-FILTER-STRATEGIES | 固定 R、全局/分源自适应 R、Huber 与时间戳处理基线 | offline_filter_strategy_ablation | B | complete | 3 场景 x 6 策略 x 5 seed；90 次 120 s 离线运行 | 8/8 | 0/0 | 完整 |
| SCENARIO-R21-NATIVE-FACTORS | 原生电缆几何、地形、实测噪声与横流因子生成器 | factorized_native_scenario_generator | C | infrastructure_complete | 2^4 因子组合 x 2 seed；32 次 50 s 生成器契约验证 | 9/9 | 0/0 | 完整 |
| CONTROL-R22-NATIVE-CLOSED-LOOP-SMOKE | R22 原生声磁--地形--横流闭环 smoke 与时序审计 | native_factor_simulation_proxy_closed_loop | C | smoke_complete_with_timing_boundary | 2 个因子端点 x 2 seed x baseline/UA；共 8 次 10 s 离线闭环；dt=0.5 s，预测窗 4.0 s | 20/20 | 0/0 | 完整 |
| CONTROL-R22-NATIVE-CLOSED-LOOP-FACTORIAL | R22 原生声磁--地形--横流 2^4 多 seed 闭环矩阵 | native_factor_simulation_proxy_closed_loop | A | factorial_complete_with_solver_timing_boundary | 16 个因子组合 x 3 seed x baseline/UA；共 96 次 20 s 离线闭环；dt=0.5 s，预测窗 4.0 s | 109/109 | 0/0 | 完整 |
| CONTROL-R22-NATIVE-CLOSED-LOOP-60S-FACTORIAL | R22 原生声磁--地形--横流 60 s 全因子长时复核 | native_factor_simulation_proxy_closed_loop | A | long_horizon_factorial_complete_with_boundary | 16 个因子组合 x 3 seed x baseline/UA；共 96 次 60 s 离线闭环；dt=0.5 s，预测窗 4.0 s | 108/108 | 0/0 | 完整 |
| CONTROL-R22-NATIVE-TERRAIN-CURRENT-120S-STRESS | R22 地形加横流 120 s 长时边界压力测试 | native_factor_simulation_proxy_closed_loop | B | terminal_tail_boundary_identified | 地形与横流开启的 4 个因子组合 x 3 seed x baseline/UA；共 24 次 120 s 离线闭环；dt=0.5 s，预测窗 4.0 s | 36/36 | 0/0 | 完整 |
| CONTROL-R22-NATIVE-TERRAIN-CURRENT-120S-TERMINAL-EXIT | R22 地形加横流 120 s 任务层终端退出验证 | native_factor_simulation_proxy_closed_loop | A | terminal_exit_boundary_closed | 地形与横流开启的 4 个因子组合 x 3 seed x baseline/UA；共 24 次离线闭环；请求时长 120 s，terminal_policy=exit_at_end，实际有效时长 65.0--105.0 s | 36/36 | 0/0 | 完整 |
| CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE | native PVS depthHeadingAutopilot 执行链 smoke 审计 | native_pvs_protocol_udp_simulation_execution_chain | B | native_pvs_execution_chain_smoke_complete_with_boundaries | 约 50 s constant-depth/constant-heading native PVS/protocol_udp smoke；ROS2 controller/MPC/arbiter 经 protocol_udp/Mock AMD AUTO dispatch 进入 PVSSimWrapper.depthHeadingAutopilot；1 个 MCAP，setpoint 245 帧，mpc_cmd 720 帧，filtered state 998 帧 | 17/17 | 1/1 | 完整 |
| HARDWARE-PC104-UDP-TIMING-PROBE | PC104/VxWorks UDP 时序探针与 host-relay 实机记录 | physical_pc104_udp_packet_timing_probe | C | physical_hostrelay_packet_timing_complete_with_boundaries | 30 s PC104 host-relay 实机探针；remote 192.168.65.254:10022，local 0.0.0.0:21；发送 300 帧零推力下行，解析 450 帧 $AUV 上行，上行到达频率 15.000 Hz，p95 间隔 85.710 ms，parse error 0 | 28/28 | 0/0 | 完整 |
| JETSON-R09-HANDOFF | Jetson clean benchmark 与历史产物回收 handoff | jetson_hardware_infrastructure | D | infrastructure_complete_dry_run_only | baseline/combined 120 s；MPC steady 200 与 stress 50；combined 1800 s soak 计划 | 8/8 | 0/0 | 完整 |
| JETSON-25W | Jetson Orin NX 25W smoke 与 MPC microbench | jetson_hardware_documented | C | documented_only | 60 s smoke 记录；MPC steady 200 solve；constraint stress 50 solve | 4/9 | 0/3 | 完整 |
| CONTROL-MPC-EXTREME-E1-MULTISEED | MPC 极端平面路径多种子统计验证 | deterministic_guidance_offline_closed_loop_multiseed | B | complete_with_scope_boundaries | 长波/短波 S 弯、90° 直角折弯、180° 发卡 4 场景 x 仅航向 PID/PID-LOS/预瞄 MPC 3 控制器 x 5 seed；受控扰动（恒定横流≤0.15 m/s、初始横向偏移≤0.8 m、逐步艏向白噪声≤1.5°）；离线制导闭环，不依赖历史 bag | 5/5 | 0/0 | 完整 |
| ESTIMATOR-E2-TRI-ESTIMATOR-FAIR | 三估计器公平初始化对比重算（O-1 修复后） | offline_estimator_comparison_fair_init | B | complete_with_observability_boundary | P1 sensor sweep 同源 8 场景 x 3 seed = 24 个 bag；Raw DR / Std EKF / ES-EKF 三引擎；fair 与 legacy-auto 双口径对照；每 run 30 s | 12/12 | 0/0 | 完整 |
| ESTIMATOR-E3-COVARIANCE-AB | 分源自适应 R 协方差整定 A/B（O-3/O-4，独立对照，不改主线默认） | offline_covariance_consistency_ab | B | complete_with_structural_dvl_floor | P1 sensor sweep 同源 8 场景 x 3 seed = 24 个 bag；三臂 A_baseline_default / B_per_source_gating / C_per_source_tuned；与 §5.5.5 分源 NIS 审计逐量测同口径重算（深度 17630 事件、DVL 17613 事件/臂） | 9/9 | 0/0 | 完整 |

## 4. 分项边界

### BUILD-R00 ThuThesis 论文构建基线

- Artifact digest：`e44b00ac3f23ee80ad6caefa76a536bc135fd146b2e4a2aa084941926930d7bd`
- 可访问字节数：`13113116`
- 可支持结论：Tex/Bib 单一权威源可以从干净辅助文件生成最终 PDF；最终日志不存在 undefined command/citation/reference；R30 阶段性写作审计后主文由 185 页压缩到 175 页、图由 59 张压缩到 42 张（净删 17 张过程性/单次样张/UI 产物图），负结果与边界集中到第 5 章 §5.6，n=1 单元验证类归档指向附录 A.7、DL/T 验收与操作员产物类归档指向附录 A.8；AUV-Master-Mag 电缆算法内容迁移后新增 5 张图（第 2/3 章方法图各 1、第 5.5.11 节算法级因果图 3），主文回到 180 页、47 图；迁移仅补方法/因果图与算法级边界，未改判任何主仓端到端或实物结论
- 不可外推：构建通过不等于占位符、论证或排版质量已经最终验收；写作审计只压缩了主文叙事与图表数量，未新增、删除或改判任何实验证据；被移出主文的图对应的原始实验证据仍以本清单其余条目为准
- 主要文件：`thuthesis/auv-thesis.pdf`

### MAG-CABLE-ALGORITHM-BOUNDARY 专用磁探测仓库电缆探测算法级边界与迁移图

- Artifact digest：`ea21e9b5645fb21903cd3f9a4f62d8d31d3953442fab8735ea65d3ba5c9293f7`
- 可访问字节数：`1197292`
- 可支持结论：关闭在线先验修正会在重档错位先验下引发横偏累积（漂移至 30--40 m）并在约 2119 s 触发 +57.5 m 跨车道投影跳变；map-frame 投影连续与先验物理配准是两个不同机制：关闭在线修正时全局路由跳变 686.4/724.1 m 但地图系投影跳变仍约 0.2 m，基线累计约 7.53 m 平移与约 -3.18 度旋转把错位地图拉回真实电缆；当前场景中在线先验修正与自适应之字形是关闭即失败的载荷机制，进度窗口投影与磁路径观测在该场景下为冗余安全网；之字形主动激励在调优后显示进入 0.15 m 参考线的算法级潜力：1.0/1.5/2.0 m 埋深在 36/32/25 度摆幅下达 0.124/0.079/0.123 m 单周期平均误差；30--120 m 曲率扫描未击穿曲率边界，30 m 为环境硬下限、瓶颈接近电缆几何物理下限而非固定曲率半径
- 不可外推：全部是专用算法仓库的单次确定性纯仿真（n=1），不等于主仓 ROS/PVS 端到端、多种子或实物结论；30 m 是扫描下限而非实际失效阈值；埋深达标点是参数扫描最优点，不代表固定幅值全场景达标；幅值需按埋深/信号状态自适应；无声呐初始捕获仍失败，是可观测性负边界；综合健康分是任务级复合指标，机制判断需同时引用原始横偏、完成度、跳变和通过状态；results/ 在子仓库内不受 Git 跟踪、docs/figure 相对提交为 modified，故本 artifact 以各文件当前 SHA256 而非子仓库 commit 唯一确定
- Provenance gaps：随机种子未透传，当前 n=1，无法给出多种子统计分布；真值字段仅允许离线评价，不进入在线感知管线；算法级边界尚未在主仓 ROS/PVS 端到端或真机链路上复核
- 主要文件：`AUV-Master-Mag/results/20260628_dr_ins_boundary/critical_sweep_after_estimator_guard.csv`；`AUV-Master-Mag/results/20260630_ablation/ablation_sweep.csv`；`AUV-Master-Mag/results/20260630_radius_boundary/radius_sweep.csv`；`AUV-Master-Mag/results/20260705_lane_shortcut/lane_shortcut_prior_alignment_50.csv`；`AUV-Master-Mag/results/20260705_lane_shortcut/lane_shortcut_prior_alignment_70.csv`；`AUV-Master-Mag/results/20260705_radius_causality/radius_causality.csv`；`AUV-Master-Mag/results/20260705_zigzag_burial/zigzag_burial_sweep.csv`；`AUV-Master-Mag/results/20260705_zigzag_burial/zigzag_burial_tuning_depth2.csv`；另有 2 项见 JSON

### MAG-BG-45 TMR/SK2301 45 Hz 短时背景记录

- Artifact digest：`5bf8ca0102e031da01f82fadf4470a529ce98c75ce537524465016ac6f4b3c30`
- 可访问字节数：`126538`
- 可支持结论：真实 TMR/SK2301 链存在可离线分析的短时背景记录；当前数据可用于窗函数与泄漏机理初筛
- 不可外推：不能支撑长期稳定性、可靠假警率或 0.05 nT 系统验收；Hann 向量 p99 仍为 0.398 nT，负结果只能说明泄漏显著缓解
- Provenance gaps：采集时 Git commit 与完整硬件元数据未写入 NPZ 外部 manifest
- 主要文件：`hardware_wrappers/fangkong_adc/raw_data/1780675809_291477.npz`；`results/magnetic_analysis/20260809_r07_45hz_reanalysis/background_hann/analysis_summary.json`；`results/magnetic_analysis/20260809_r07_45hz_reanalysis/r07_summary.json`；`results/magnetic_analysis/20260809_r07_45hz_reanalysis/report.md`

### MAG-JOINT-45 45 Hz 电缆、TMR 与 ArUco 联合拟合

- Artifact digest：`4d0e6f11e31c01f8b538b921f20a4cbdb0d7ccdd8d50411c2c44ac9f40951fc2`
- 可访问字节数：`5121475`
- 可支持结论：移动单三轴 TMR 加外部位姿可形成合成空间阵列；直导线三轴复 I/Q 自由尺度拟合 complex R²=0.8792；固定峰值电流拟合 complex R²=0.8711；post-hoc 残差归因复算 component RMSE=0.4795 µT、向量残差 p95=1.223 µT，平行/正交残差能量约为 52.0%/48.0%；公共复增益、每轴复增益、每轴固定背景与时间平移只能解释有限残差，剩余误差主要对应直导线/公共复尺度和未标定轴向因素边界
- 不可外推：不是海缆绝对埋深验收；未完成独立九参数标定和三通道复增益标定；无限长直导线模型不覆盖多芯回流与铠装屏蔽；残差归因为归档数据的事后分析，不是新增硬件采集；归因结果不能替代可溯源电流、距离、转台或多芯海缆标定
- Provenance gaps：采集与分析时 Git/submodule commit 未进入结果摘要
- 主要文件：`hardware_wrappers/fangkong_adc/raw_data/1783235358_205719.npz`；`hardware_wrappers/fangkong_adc/raw_data/joint_analysis/1783235358_205719/fit_summary.json`；`hardware_wrappers/fangkong_adc/raw_data/joint_analysis/1783235358_205719/joint_analysis_report.md`；`hardware_wrappers/fangkong_adc/raw_data/relative_pose_log.txt`；`results/magnetic_analysis/20260809_r07_45hz_reanalysis/joint_reproduction_audit/joint_reanalysis_audit.json`；`results/magnetic_analysis/20260809_r07_45hz_reanalysis/report.md`；`results/magnetic_analysis/20260810_joint_residual_attribution/report.md`；`results/magnetic_analysis/20260810_joint_residual_attribution/residual_attribution_summary.json`

### MAG-ADC-ENOB-CH4 SK2301 CH4 短接噪声、ENOB 与 45 Hz 等效磁噪声

- Artifact digest：`63e49f46f693d00808643aa959cf4e0b96976df8666b6f8390e55c435aa720e0`
- 可访问字节数：`1663119`
- 可支持结论：2000 Hz 原始短接噪声 ENOB 为 16.877 bit；16 kHz 采样经 OSR=8 输出 2 kHz 后噪声 ENOB 为 18.342 bit；按 20 mV/µT 名义灵敏度换算，1 s、45 Hz 锁相矢量 RMS 为 0.0230 nT
- 不可外推：短接噪声 ENOB 不是满量程正弦 SINAD 动态 ENOB；I/Q 单分量 3σ 为 0.0514 nT，不能宣称整机达到 0.05 nT；未包含 TMR 本征噪声、模拟前端、温漂、环境、标定和绝对真值误差；灵敏度量级不等于绝对精度或标准符合性
- Provenance gaps：采集脚本和实验时 Git commit 未写入历史结果包；20 mV/µT 为名义换算灵敏度，尚无本次链路的可溯源绝对标定
- 主要文件：`hardware_wrappers/fangkong_adc/raw_data/enob/20260809T161036/ch4_enob_capture.npz`；`hardware_wrappers/fangkong_adc/raw_data/enob/20260809T161036/ch4_enob_report.md`；`hardware_wrappers/fangkong_adc/raw_data/enob/20260809T161036/ch4_enob_results.json`；`results/magnetic_analysis/20260809_r08_adc_enob_alignment/enob_alignment_summary.json`；`results/magnetic_analysis/20260809_r08_adc_enob_alignment/report.md`

### MAG-R08-HANDOFF TMR/SK2301 M0/M1/M4 最小采集 handoff

- Artifact digest：`279a2d799d24bb87febdba4b8f152ad800c323ae5e29ac3c2c7f82ecf517e025`
- 可访问字节数：`52354`
- 可支持结论：单命令可编排 M0/M1/M4 并生成统一返回 bundle；新 NPZ 契约强制保存 45 Hz 频率来源、硬件状态、有效样本和失败事件
- 不可外推：dry-run 的 valid_run_count=0、contract_complete=false；不能用于声称 TMR/SK2301 噪声、检测概率或 0.05 nT 指标已验证
- Provenance gaps：真实 R24 需在连接 TMR/SK2301 的现场执行并返回完整 bundle
- 主要文件：`results/magnetic_handoff/20260809_r08_tmr_minimal_handoff_dry_run/metrics.csv`；`results/magnetic_handoff/20260809_r08_tmr_minimal_handoff_dry_run/report.md`；`results/magnetic_handoff/20260809_r08_tmr_minimal_handoff_dry_run/run_manifest.json`；`results/magnetic_handoff/20260809_r08_tmr_minimal_handoff_dry_run/status.json`

### ESKF-NIS-8X3 ES-EKF 八场景三种子 NIS/R 聚合

- Artifact digest：`ca4748fc63be1117dd397cd2fbfb7132a388668897c5fb48c6497715a863e726`
- 可访问字节数：`58389456`
- 可支持结论：24 个源运行与对应 MCAP 当前全部可访问；自适应 R 在八类场景均发生触发；可按观测源和自由度生成标准 NIS、卡方覆盖率、协方差和创新时序
- 不可外推：历史 adaptive-R 滑窗混合 3 维 DVL 与 1 维深度原始 NIS，固定阈值 9.0 不具备统一卡方语义；innovation/gate proxy 仅作诊断，不得与标准 NIS 混合；30 s 与 3 seed 不构成长时漂移结论
- Provenance gaps：历史 sweep manifest 未记录 Git commit、子模块 commit 和配置快照
- 主要文件：`log/thesis_sweep/20260612_170618_p1_sensor_3seed/manifest.json`；`log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv`；`results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/aggregate_report.md`；`results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/summary_by_scenario_mode.csv`；`results/uncertainty_aggregates/20260809_r05_nis_semantic_audit/aggregate_report.md`；`results/uncertainty_aggregates/20260809_r05_nis_semantic_audit/nis_semantic_audit.json`；`results/uncertainty_aggregates/20260809_r05_nis_semantic_audit/summary_nis_by_scenario_source.csv`

### UAMPC-ATTRIBUTION UA-MPC 主消融、P-1/P-2 与 H4 归因

- Artifact digest：`425e832c0b96b81e290ecd19188e51588c96eed0a358e619643a17b1012842c4`
- 可访问字节数：`589809759`
- 可支持结论：sigmoid 控制代价降权是可解性与横向精度主贡献；单纯提高 max_iter 不能工程化修复高 fallback；confidence_alpha=1.0 仅提供边际精度收益；hairpin 全时段误差主要来自 terminal stop 缺失
- 不可外推：H4 是确定性运动学基准，不替代六自由度或真机；失败 wall time 尚未在所有 fallback 类型中完整记录
- Provenance gaps：历史 sweep manifest 未记录 Git/submodule commit 和完整配置快照
- 主要文件：`docs/experiment/uampc_p2_h4_attribution_20260807.md`；`log/thesis_sweep/20260612_172535_h1_uampc_main_ablation/failures.log`；`log/thesis_sweep/20260612_172535_h1_uampc_main_ablation/manifest.json`；`log/thesis_sweep/20260612_172535_h1_uampc_main_ablation/results.csv`；`log/thesis_sweep/20260806_223405_p1_a0_baseline/failures.log`；`log/thesis_sweep/20260806_223405_p1_a0_baseline/manifest.json`；`log/thesis_sweep/20260806_223405_p1_a0_baseline/results.csv`；`log/thesis_sweep/20260806_224623_p1_a2_nosigmoid/failures.log`；另有 13 项见 JSON

### PROXY-EXTREME-6 六类代理极端电缆场景冒烟

- Artifact digest：`cae92c1b9eb3855716fde82c47eaa5c89e2997a852361af834d69e91e64ef4d9`
- 可访问字节数：`586236486`
- 可支持结论：六类代理场景均可产生非空 MCAP 和控制聚合；横流与综合场景构成较高横向误差压力
- 不可外推：单 seed 不能比较 baseline 与 UA 的统计优劣；代理字段不等价于原生声磁、地形和电缆几何耦合
- Provenance gaps：历史 runner manifest 未记录 Git/submodule commit 和配置快照
- 主要文件：`log/proxy_cable_sweep/20260613_182825_cable_proxy_full6_smoke/manifest.json`；`log/proxy_cable_sweep/20260613_182825_cable_proxy_full6_smoke/results.csv`；`results/control_aggregates/20260613_182825_cable_proxy_full6_smoke/control_aggregate_report.md`

### COVERAGE-R12 之字形扫描覆盖率、航程与时间归一化扫描

- Artifact digest：`d35df167780ac6ac91ec06854a3a8ea08761d076d87a8b713096e02bf391acba`
- 可访问字节数：`707419`
- 可支持结论：横向误差界为有效宽度 10% 时，0.8 是当前网格中保持完全保证覆盖的最大间距比；间距比增至 0.9 后保证覆盖率降为 88.9%；间距比降至 0.7/0.6 时任务时间相对 0.8 档增加约 15.6%/31.1%
- 不可外推：全部长度和速度均为归一化量，不代表任何具体声呐或磁传感器的绝对量程；米制间距与绝对时长仍需实测波束图、作业高度、磁检测宽度、转弯半径和速度上限
- 主要文件：`results/coverage_normalized/20260809_r12/reference_spacing_table.csv`；`results/coverage_normalized/20260809_r12/report.md`；`results/coverage_normalized/20260809_r12/run_manifest.json`；`results/coverage_normalized/20260809_r12/summary.json`

### MPC-R15-DIAGNOSTICS MPC 每周期可解性诊断基础设施

- Artifact digest：`05a6f36557294611bb72c068d02a51d7a9666d3bf1c1996d6c1f9fdf069fa942`
- 可访问字节数：`227853`
- 可支持结论：当前成功和失败周期均可记录 wall time、迭代数、warm-start、约束残差与 fallback；上一成功控制输出与当前失败诊断已分离；thesis/proxy sweep 可在正式 bag 返回后自动回填 R04 诊断字段
- 不可外推：基础设施回归不能替代 R16 的闭环机制对照；尚未据此修改 UA-MPC 默认配置或宣称高 fallback 已修复
- Provenance gaps：需由 R16/R13 正式运行生成多周期 MCAP 和统计结果

### MPC-R16-FEASIBILITY MPC 热启动、软约束与终端保持机制对照

- Artifact digest：`289cdc9c93888f3d3aaf8638fb3eab965b227e49a30b96974b8dc2abb850096d`
- 可访问字节数：`349263`
- 可支持结论：统一配置后 warm-start 硬约束组合取得最低回退率 0.0086、阻塞率 0.0086 和平均求解时间 11.29 ms；soft slack 增加优化维度、迭代数和阻塞，默认保持关闭；terminal hold 降低发卡末端误差，reference ramp 恶化有效段 RMSE
- 不可外推：开发机 wall time 不替代 Jetson 25 W 真机结果；确定性 terminal hold plant 无反推力，不支持定点保持精度；PVS baseline 配置冻结结果不替代六代理场景多种子 R13
- Provenance gaps：Jetson 真机实时性由 R23 返回
- 主要文件：`log/thesis_sweep/20260809_203915_r16_profile_synced_3seed/run_manifest.json`；`results/control/r16_feasibility/20260809_r16/report.md`

### DECISION-R17-HYSTERESIS BT/FSM 等价迟滞去抖与组合故障对照

- Artifact digest：`724b87eb0befb060d1fb986004d32f83413ff219d7465477c98333a7cbbc0852`
- 可访问字节数：`130899`
- 可支持结论：同一规则下 BT 与 FSM 的紧急响应延迟和组合故障生存率相同；施密特触发与三帧去抖使平均模式切换由 149.09 降至 2.23 次/30 s；两种架构均保持 100 ms 紧急响应、零遗漏和 100% 组合故障生存率
- 不可外推：不支持 BT 响应速度优于 FSM；结果来自决策核心仿真，不包含 ROS2 调度、硬件时延或 PC104 链路；架构优势只表述为横切安全逻辑的集中组织与维护成本
- Provenance gaps：系统级延迟由 R23/R25 真机 handoff 补充
- 主要文件：`results/decision/r17_hysteresis/20260809_r17/report.md`；`results/decision/r17_hysteresis/20260809_r17/run_manifest.json`

### ES-EKF-R18-LONG-HORIZON ES-EKF 五分钟 seed 与观测相位敏感性

- Artifact digest：`eb3cc99b44854619c2e2c5cdeb19b8e7e6624f8671aa3547e6ccb26f9d5e5fd1`
- 可访问字节数：`264195`
- 可支持结论：五分钟水平误差显著高于 60/120 s 前缀，短时结果不能外推长期稳定性；相同 5 Hz DVL 与相同逐样本噪声下，100 ms 更新相位可产生与场景扰动同量级的误差差异；丢包比例不能单独决定长期误差排序
- 不可外推：离线动力学结果不替代 PVS 六自由度闭环或真机；当前轨迹缺少持续绝对水平位置与航向观测；大漂移用于定位可观性和时序问题，不外推为完整声磁融合后的系统精度
- Provenance gaps：R20 需增加时间戳插值/延迟状态更新与滤波基线对照
- 主要文件：`results/state_estimation/r18_long_horizon/20260809_r18/report.md`；`results/state_estimation/r18_long_horizon/20260809_r18/run_manifest.json`；`results/state_estimation/r18_long_horizon/20260809_r18/summary_by_scenario.csv`

### MAG-R19-MEASURED-NOISE-REPLAY 实测三轴背景噪声与同协方差高斯成对回放

- Artifact digest：`13826fbffd471bcbdbf2c2c23144bc45f9998a77808e2f47fc819db9a852cf54`
- 可访问字节数：`206588`
- 可支持结论：实测回放与同协方差高斯的平均距离 RMSE 和平均磁 NIS 接近；实测回放的距离 RMSE 跨 seed 标准差约为高斯对照 29 倍，磁 NIS 标准差约为 26 倍；源记录三轴相关系数为 0.996--1.000，主峰约 50.01 Hz
- 不可外推：3.92 s 源记录采用循环回放，不支持长时平稳性结论；结果只能称实测噪声回放，不能称完整 Sim-to-Real；源记录是用于 45 Hz 处理链的背景数据，主峰不是 45 Hz 信号
- Provenance gaps：需由 R24/R26 返回更长 M0/M1/M4 与多工况记录
- 主要文件：`results/state_estimation/r19_measured_noise_replay/20260809_r19/noise_characterization.json`；`results/state_estimation/r19_measured_noise_replay/20260809_r19/report.md`；`results/state_estimation/r19_measured_noise_replay/20260809_r19/run_manifest.json`；`results/state_estimation/r19_measured_noise_replay/20260809_r19/summary_by_noise_mode.csv`

### CONTROL-R13-PROXY-3SEED 六代理电缆场景三种子正式矩阵

- Artifact digest：`9ad574d59cc6b5f2ab5d48f7aee67587fa911b22bd3051fdb61aca91cc2ac88c`
- 可访问字节数：`152966`
- 可支持结论：首轮六场景横向 RMSE 均未改善；平均求解时间 89--113 ms，0.5 s 诊断快照回退比例为 0.90--0.99；首轮坡面与综合极端安全差异是待归因现象，不构成 UA 优势
- 不可外推：场景为完整 ROS2 控制栈上的代理配置，不是原生声磁闭环；R14 已证明高回退主要由深度硬饱和引起，安全差异混入 fallback 持有行为；UA 置信度几乎恒为 0.367，首轮不是动态不确定性适应对照；一次无有效观测包的原运行已保留，并以相同条件 repair 显式替换
- Provenance gaps：分源置信重跑已由 CONTROL-R13-V2-SOURCE-CONFIDENCE 另包补齐；本首轮包自身仍不支持动态置信结论；R22 需在原生因子闭环中验证交互效应
- 主要文件：`results/control_aggregates/20260809_r13_authoritative/aggregate/control_summary_by_scenario_mode.csv`；`results/control_aggregates/20260809_r13_authoritative/bundle/run_manifest.json`；`results/control_aggregates/20260809_r13_authoritative/effects/paired_summary.csv`

### CONTROL-R13-V2-SOURCE-CONFIDENCE R13-v2 分源置信保守 UA 正式矩阵

- Artifact digest：`a03617f25dda6d542d20ed053f8033d0682505029901069a16b78353b1f834be`
- 可访问字节数：`7413542481`
- 可支持结论：source-specific 质量链、tracking authority、conservative policy 和 MPC 在 36 个正式运行中端到端闭合；fallback 为 0，平均 p95 wall time 约 10 ms，旧 R13 的高回退问题未复现；全局控制变化率 RMS 从 0.247 降至 0.085；hairpin、combined 与 cross-current 的控制变化率分别下降约 89.8%、84.4% 与 52.0%；buried_gap 的 p_track 跨 SEARCH/TRACK 门限并出现 HOLD/SEARCH/TRACK，可作为分源置信机制主证据；combined extreme 未进入 TRACK，是 tracking authority 硬门拒绝低质量观测的边界证据；CONTROL-R13-V2-TELEMETRY-AUTHORITY-SUPPLEMENT 补充证明 policy 后 applied speed 与 controller 侧 authority snapshot 已进入 debug 遥测，但只作为正式矩阵的可观测性补强
- 不可外推：不能宣传 R13-v2 全面改善 RMSE；全局 RMSE 从 7.932 m 变为 8.006 m；不能宣传六个场景均完成 TRACK 闭环；combined extreme 的 TRACK 占比为 0；原 36-run 正式矩阵不能单独宣传速度缩放已被 MCAP 量化；速度缩放遥测由 CONTROL-R13-V2-TELEMETRY-AUTHORITY-SUPPLEMENT 单独支撑，不反向修订 paired RMSE 或控制变化率统计；不能把 simulation_proxy 概率标定写成实物部署置信度标定；hairpin 的低 TRACK 占比主要来自观测稀疏和 authority age gate，不能误写成 p_track 低
- Provenance gaps：原 36-run 正式矩阵 MCAP 不含 policy 后 applied_target_speed_mps 与 controller 侧 authority snapshot；该可观测性缺口已由当前 proxy 配置下的 telemetry supplement 补强，但正式矩阵本身未重跑；物理声呐/磁探测独立验证集和实物概率标定尚未完成；R22 原生因子闭环仍需验证几何、横流、地形和实测噪声交互效应
- 主要文件：`log/proxy_cable_sweep/20260810_000843_r13_v2_formal_20260810T000842/r13_v2_authority_policy_summary_by_scenario_mode.csv`；`log/proxy_cable_sweep/20260810_000843_r13_v2_formal_20260810T000842/r13_v2_quality_policy_audit.csv`；`log/proxy_cable_sweep/20260810_000843_r13_v2_formal_20260810T000842/results.csv`；`log/proxy_cable_sweep/20260810_000843_r13_v2_formal_20260810T000842/run_manifest.json`；`results/control_aggregates/20260810_r13_v2_full/control_summary_by_scenario_mode.csv`；`results/control_aggregates/20260810_r13_v2_full/r13_v2_thesis_audit/r13_v2_claim_boundary_table.csv`；`results/control_aggregates/20260810_r13_v2_full/r13_v2_thesis_audit/r13_v2_thesis_audit_manifest.json`

### CONTROL-R13-V2-TELEMETRY-AUTHORITY-SUPPLEMENT R13-v2 applied speed 与 authority snapshot 遥测补强

- Artifact digest：`dbd7314f0f7aca1994e020b6f0e8169adca95b7945086380b4b0d893c81eefed`
- 可访问字节数：`2487031707`
- 可支持结论：旧 R13-v2 正式矩阵事后审计确认 36/36 run 均缺少 policy 后 applied target speed 与 controller 侧 authority snapshot，说明原矩阵不能单独量化速度缩放；修订 controller debug 后，12/12 个 UA 补强 run 均有效，applied speed 与 debug authority snapshot 缺失均为 0；补强 run 的 quality-control policy 接受率均值为 0.995，speed scale 最小值、逐 run q05 下界和逐 run 均值分别为 0.000、0.805 和 0.896；最大 applied speed 动态范围为 0.285 m/s，证明 conservative quality-control policy 实际改变了 MPC 消费的目标速度；12 个补强 run 的 fallback max 为 0，solver wall-time p95/max 上界为 13.43/51.71 ms；controller debug 已记录 requested_target_speed_mps、applied_target_speed_mps、quality_control_policy.speed_scale、confidence 与 authority_snapshot，可用于后续 MCAP 级审计
- 不可外推：该补强只关闭遥测可观测性缺口，不替换 R13-v2 36-run 正式矩阵的 paired RMSE、控制变化率、fallback 或 safety 统计；补强运行使用当前 proxy 配置和 patched controller debug；不能据此反向修订原正式矩阵的 combined extreme no-TRACK 边界；该补强为 UA-only，没有形成新的 baseline/UA 成对性能矩阵；solver p95 上界为 13.43 ms，但单次最大 wall time 为 51.71 ms；不能写成所有控制周期均低于 50 ms；该数据层仍为 PVS/proxy closed-loop，不是实物部署、真实声呐/磁传感概率标定或 PC104 物理时延证据；速度缩放由 conservative quality-control policy 触发，不能据此宣称横向 RMSE 改善或 full-flow 巡缆成功率提升
- Provenance gaps：尚未在 patched telemetry 下重跑完整 6 场景 x 2 模式 x 3 seed 正式矩阵；当前补强配置与 20260810_000843 正式矩阵的 combined 配置 hash 不完全一致，需把正式矩阵结论和补强遥测结论分开引用；缺少物理声呐/磁探测独立验证集和实物概率标定；缺少真实 Jetson--PC104/AMD 通信链路下的 applied-speed 端到端执行确认
- 主要文件：`log/proxy_cable_sweep/20260810_180055_r13_v2_telemetry_authority_3scenario_3seed_ua_20260810/r13_telemetry_authority_audit/r13_telemetry_authority_by_run.csv`；`log/proxy_cable_sweep/20260810_180055_r13_v2_telemetry_authority_3scenario_3seed_ua_20260810/r13_telemetry_authority_audit/r13_telemetry_authority_by_scenario_mode.csv`；`log/proxy_cable_sweep/20260810_180055_r13_v2_telemetry_authority_3scenario_3seed_ua_20260810/results.csv`；`log/proxy_cable_sweep/20260810_181351_r13_v2_telemetry_authority_hairpin_3seed_ua_20260810/r13_telemetry_authority_audit/r13_telemetry_authority_by_run.csv`；`log/proxy_cable_sweep/20260810_181351_r13_v2_telemetry_authority_hairpin_3seed_ua_20260810/r13_telemetry_authority_audit/r13_telemetry_authority_by_scenario_mode.csv`；`log/proxy_cable_sweep/20260810_181351_r13_v2_telemetry_authority_hairpin_3seed_ua_20260810/results.csv`；`results/control_aggregates/20260810_r13_v2_full/r13_v2_telemetry_authority_supplement/r13_telemetry_authority_supplement_by_scenario_mode.csv`

### CONTROL-CBF-TERRAIN-HIGH-SMALL-MATRIX terrain-high CBF 近底安全小矩阵

- Artifact digest：`62bc7a845716796894da588ebd96d498cd7e69e66a607da5e4386ebbef4d5657`
- 可访问字节数：`242355857`
- 可支持结论：guidance-level CBF filter、预瞄海床约束、紧急上浮和速度门控在可信 kinematic setpoint proxy 下完成 PID/MPC 小矩阵验证；PID 与 MPC 两个运行的最小净空均为 2.70 m，1.5 m 低净空违规率和海床穿透率均为 0；CBF speed gate 在两类控制器下均被触发，PID speed scale 最低约 0.37，MPC 最低约 0.20；MPC 运行 fallback 为 0，solver p95 为 17.94 ms，可作为实时性边界证据
- 不可外推：该结果只是 terrain_high 小矩阵，不能外推为所有极端场景或完整近底安全闭合；运行使用 manual setpoint/kinematic setpoint proxy，本条实验不能证明 native PVS depthHeadingAutopilot 路径；该执行链另由 CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE 覆盖；不能据此宣称 CBF 改善跟踪精度、任务完成率或横向 RMSE；MPC solver p95 约 17.94 ms，不能写成满足 10 ms 实时性目标；该数据层仍为 simulation_proxy，不是实物部署或真实海况安全验收
- Provenance gaps：尚无标准 run_manifest/status/config snapshot，运行配置由审计文档、manual_setpoint.csv、bag_path.txt 和脚本记录共同约束；60 s terrain_high 复核已由 CONTROL-CBF-TERRAIN-HIGH-60S-RECHECK 覆盖；low/mid/high 60 s 单 seed 矩阵已由 CONTROL-CBF-TERRAIN-LOW-MID-HIGH-60S-MATRIX 覆盖；三种子复核已由 CONTROL-CBF-TERRAIN-LOW-MID-HIGH-60S-3SEED-MATRIX 覆盖；native PVS depthHeadingAutopilot 执行链已由 CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE 另立验证，不与本 kinematic setpoint proxy 结果混写
- 主要文件：`results/control/terrain_following_20260810_140727/pid_terrain/analysis/summary_statistics.csv`；`results/control/terrain_following_20260810_140845/mpc_terrain/analysis/summary_statistics.csv`

### CONTROL-CBF-TERRAIN-HIGH-60S-RECHECK terrain-high CBF 60 s 复核

- Artifact digest：`811bd0d74e0cd0b8720e28bbf2eb4083e58c75448fc5d9cf637a4b45e4ac2d7f`
- 可访问字节数：`491228680`
- 可支持结论：terrain_high CBF 结果从约 30 s 小矩阵延长到约 60 s 复核后仍保持安全指标闭合；PID 与 MPC 两个运行的最小净空均为 2.70 m，1.5 m 低净空违规率和海床穿透率均为 0；CBF speed gate 在 60 s 复核中仍被触发，PID/MPC 激活样本分别为 17/119 和 31/120，最低 speed scale 分别约 0.395 和 0.107；MPC 运行 fallback 为 0，但 solver p95 为 21.44 ms，是实时性负边界
- 不可外推：该结果只是 terrain_high 60 s 复核；low/mid/high 单 seed 矩阵另见 CONTROL-CBF-TERRAIN-LOW-MID-HIGH-60S-MATRIX，三种子复核另见 CONTROL-CBF-TERRAIN-LOW-MID-HIGH-60S-3SEED-MATRIX；仍不能外推为所有极端场景安全闭合；运行使用 manual setpoint/kinematic setpoint proxy，本条实验不能证明 native PVS depthHeadingAutopilot 路径；该执行链另由 CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE 覆盖；不能据此宣称 CBF 改善跟踪精度、任务完成率或横向 RMSE；MPC solver p95 约 21.44 ms，不能写成满足 10 ms 实时性目标；该数据层仍为 simulation_proxy，不是实物部署或真实海况安全验收
- Provenance gaps：尚无标准 experiment_contract run_manifest/status/config_snapshot；运行配置由审计文档、manual_setpoint.csv、bag_path.txt、脚本记录和原始 MCAP 共同约束；terrain low/mid/high 60 s 单 seed 矩阵已由 CONTROL-CBF-TERRAIN-LOW-MID-HIGH-60S-MATRIX 覆盖；三种子复核已由 CONTROL-CBF-TERRAIN-LOW-MID-HIGH-60S-3SEED-MATRIX 覆盖；native PVS depthHeadingAutopilot 执行链已由 CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE 另立验证，不与本 kinematic setpoint proxy 结果混写；R22 原生声磁--地形--横流闭环仍未由本实验覆盖
- 主要文件：`results/control/terrain_following_20260810_144704/cbf_terrain_recheck_summary.csv`；`results/control/terrain_following_20260810_144704/cbf_terrain_recheck_summary.json`；`results/control/terrain_following_20260810_144704/mpc_terrain/analysis/summary_statistics.csv`；`results/control/terrain_following_20260810_144704/pid_terrain/analysis/summary_statistics.csv`

### CONTROL-CBF-TERRAIN-LOW-MID-HIGH-60S-MATRIX CBF terrain low/mid/high 60 s 单 seed 矩阵

- Artifact digest：`320f106a6b4c6da99c0813971e73fcb6dcff4d3f239ae08ba2e3ca1ae9c6785c`
- 可访问字节数：`1477424898`
- 可支持结论：CBF terrain low/mid/high 60 s 单 seed 矩阵 6/6 run 完成，1.5 m 低净空违规率和海床穿透率均为 0；最小净空 low/mid/high 分别为 2.90 m、2.80 m 和 2.70 m，均高于 1.5 m 安全阈值；CBF speed gate 在六个 run 中均实际触发，最低 speed scale 范围为 0.107--0.648；MPC 三个 run fallback 均为 0，但 solver p95 为 21.44--25.12 ms，是实时性负边界
- 不可外推：该历史矩阵本身是 low/mid/high 单 seed 60 s 验证；三种子复核另见 CONTROL-CBF-TERRAIN-LOW-MID-HIGH-60S-3SEED-MATRIX；运行使用 manual setpoint/kinematic setpoint proxy，本条实验不能证明 native PVS depthHeadingAutopilot 路径；该执行链另由 CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE 覆盖；不能据此宣称 CBF 改善跟踪精度、任务完成率或横向 RMSE；MPC solver p95 为 21.44--25.12 ms，不能写成满足 10 ms 实时性目标；low/mid 配置为保持执行链一致已对齐 kinematic_setpoint 和 0 m/s 横流；该矩阵验证的是地形强度，不验证横流耦合；该数据层仍为 simulation_proxy，不是实物部署或真实海况安全验收
- Provenance gaps：尚无标准 experiment_contract run_manifest/status/config_snapshot；运行配置由审计文档、manual_setpoint.csv、bag_path.txt、脚本记录、配置快照和原始 MCAP 共同约束；三种子统计复核已由 CONTROL-CBF-TERRAIN-LOW-MID-HIGH-60S-3SEED-MATRIX 覆盖；本条 artifact 保留为 single-seed 前置证据；native PVS depthHeadingAutopilot 执行链已由 CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE 另立验证，不与本 kinematic setpoint proxy 结果混写；R22 原生声磁--地形--横流闭环仍未由本实验覆盖
- 主要文件：`results/control/cbf_terrain_matrix_20260810_145822/cbf_terrain_recheck_summary.csv`；`results/control/cbf_terrain_matrix_20260810_145822/cbf_terrain_recheck_summary.json`；`results/control/terrain_following_20260810_144704/mpc_terrain/analysis/summary_statistics.csv`；`results/control/terrain_following_20260810_144704/pid_terrain/analysis/summary_statistics.csv`；`results/control/terrain_following_20260810_145512/mpc_terrain/analysis/summary_statistics.csv`；`results/control/terrain_following_20260810_145512/pid_terrain/analysis/summary_statistics.csv`；`results/control/terrain_following_20260810_145822/mpc_terrain/analysis/summary_statistics.csv`；`results/control/terrain_following_20260810_145822/pid_terrain/analysis/summary_statistics.csv`

### CONTROL-CBF-TERRAIN-LOW-MID-HIGH-60S-3SEED-MATRIX CBF terrain low/mid/high 60 s 三种子复核矩阵

- Artifact digest：`a5acc6c3a5b83a3772179fbb2654534c158cd8e730bffaec6744c3b60db2a5a4`
- 可访问字节数：`410135`
- 可支持结论：18/18 run 有效，low/mid/high 三档地形在 PID 与 MPC 下均完成三种子复核；1.5 m 低净空违规率和海床穿透率在 18 个 run 中均为 0；全局最小净空为 2.70 m；各 controller--terrain 组最小净空下界为 2.70--2.90 m；CBF speed gate 在 18 个 run 中均实际触发，全局最低 speed scale 为 0.180；MPC 9 个 run fallback 均为 0，solver p95 上界为 23.84 ms；PID 组最小净空下界为 2.80 m，MPC 组最小净空下界为 2.70 m；该结果将 CBF 近底安全证据从 single seed 前置矩阵提升到三种子统计复核口径
- 不可外推：该矩阵验证的是 low/mid/high 地形强度下的近底安全过滤，不验证横流耦合、完整电缆极端场景或任务完成率；运行使用 manual setpoint 和 kinematic setpoint proxy，本条实验不能证明 native PVS depthHeadingAutopilot 路径；该执行链另由 CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE 覆盖；不能据此宣称 CBF 改善跟踪精度、横向 RMSE 或巡缆终端保持能力；MPC solver p95 上界为 23.84 ms，仍应按 20 Hz/10 Hz/0.3 s 预算单独说明，不能写成满足 10 ms 目标；该数据层仍为 simulation/PVS proxy，不是实物部署、真实海况或真实 PC104 时延证据；三种子复核降低了随机地形种子的偶然性，但不等同于完整显著性检验或所有参数边界搜索
- Provenance gaps：尚无标准 experiment_contract status.json；运行配置由 results.csv、summary_by_terrain.csv、aggregate_report.md、configs、logs、bag_path 和原始 MCAP 指针共同约束；native PVS depthHeadingAutopilot 执行链已由 CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE 另立验证，不与本 kinematic setpoint proxy 结果混写；尚未覆盖横流、速度、初始高度偏差和电缆跟踪任务层耦合下的 CBF 参数敏感性
- 主要文件：`results/control/terrain_controller_seed_sweep_20260810_171620_cbf_terrain_3seed_pid_mpc_60s/results.csv`；`results/control/terrain_controller_seed_sweep_20260810_171620_cbf_terrain_3seed_pid_mpc_60s/summary_by_terrain.csv`

### CONTROL-R14-R13-DIAGNOSIS R13 深度硬饱和归因、平滑修复与固定置信权重分解

- Artifact digest：`284d3e861cacc611e8cc36482a59630bdf14249cda64bca33e965ad2fc807e25`
- 可访问字节数：`268363`
- 可支持结论：R13 高回退主因是深度硬饱和在长预测域造成梯度退化；平滑饱和使 36 个实际快照 N=20 成功率由 0 提升至 1，p95 为 41.03 ms；18 组关键场景闭环 fallback 为 0，首轮安全改善未复现；控制降权主导控制变化率增大，固定跟踪放大未产生稳定正收益
- 不可外推：闭环修复矩阵为 3 场景 x 2 模式 x 3 seed x 30 s，不替代首轮六场景 60 s 矩阵；UA 置信度几乎恒为 0.367，机制对照只识别固定权重工作点；尚未形成 Jetson 目标平台实时性证据
- Provenance gaps：分源置信接口和六场景重跑已由 CONTROL-R13-V2-SOURCE-CONFIDENCE 另包补齐；R14 本包仍不替代 Jetson 目标平台实时性证据
- 主要文件：`results/control/r14_r13_diagnosis/20260809_r14/run_manifest.json`；`results/control/r14_r13_diagnosis/20260809_r14/summary_by_model_horizon.csv`；`results/control/r14_r13_diagnosis/20260809_r14_closed_loop_effects/run_manifest.json`；`results/control/r14_r13_diagnosis/20260809_r14_closed_loop_effects/summary_by_variant.csv`

### ES-EKF-R20-FILTER-STRATEGIES 固定 R、全局/分源自适应 R、Huber 与时间戳处理基线

- Artifact digest：`d8db58cd44f03d0e6daefd5a7171f41cd385e6ae455cf5b41a3a9c75032e948e`
- 可访问字节数：`103974`
- 可支持结论：历史全局 R 在异常场景中因跨源污染而劣于固定 R；Huber 即时降权将脉冲与延迟异常 RMSE 降低约 79%；仅按时间差膨胀 R 未解决陈旧观测对应旧状态的问题
- 不可外推：离线动力学不替代 PVS 或实物闭环；Huber 方案 NIS 覆盖率仍低，误差改善不代表协方差已校准；尚未实现时间戳插值或 delayed-state update
- Provenance gaps：R22 需加入真正的延迟状态更新与声磁绝对水平观测
- 主要文件：`results/state_estimation/r20_filter_strategies/20260809_r20/run_manifest.json`；`results/state_estimation/r20_filter_strategies/20260809_r20/summary_by_strategy.csv`

### SCENARIO-R21-NATIVE-FACTORS 原生电缆几何、地形、实测噪声与横流因子生成器

- Artifact digest：`48cd53e97d4d825cc90db517d04aabe4dc65d924a320d9ded431071301d006d7`
- 可访问字节数：`100158`
- 可支持结论：曲线几何、地形与埋设、实测噪声回放和横流可独立开关；物理 truth 与 sensor measurement 使用独立载荷；实测回放保留强时间相关，代理场景未被覆盖删除
- 不可外推：当前只验证生成器契约，不支持原生闭环控制性能结论；3.92 s 实测噪声仍采用循环回放；闭环交互效应由 CONTROL-R22-NATIVE-CLOSED-LOOP-FACTORIAL 覆盖，native PVS 与实物链路仍另行验证
- Provenance gaps：R21 本身只作为生成器契约证据；不能替代 R22 闭环矩阵、native PVS 或实物链路证据
- 主要文件：`results/scenarios/r21_native_generator/20260809_r21/factor_metrics.csv`；`results/scenarios/r21_native_generator/20260809_r21/run_manifest.json`

### CONTROL-R22-NATIVE-CLOSED-LOOP-SMOKE R22 原生声磁--地形--横流闭环 smoke 与时序审计

- Artifact digest：`1e461a39728abb027bc7901b28dd30a48efb3e9c0c342388468738f715d4fd0e`
- 可访问字节数：`215242`
- 可支持结论：R21 原生几何、地形、实测噪声和横流因子已接入制导级 MPC 与分源 conservative policy 的离线闭环；8/8 次运行有效，fallback 为 0，1.5 m 低净空违规率和海床穿透率均为 0；最坏横向 p95 为 1.298 m，最小净空为 2.556 m；solver p95 最大 17.42 ms，solver max 最大 27.51 ms；相对 ROS 20 Hz、bridge 10 Hz、VxWorks 主控 10 Hz 和 NetRecv 0.3 s 周期均未越界
- 不可外推：当前只是两个端点因子组合的 low-cost smoke，不是完整 2^4 因子矩阵，不能给出严格主效应或交互效应统计结论；数据层限定为 offline simulation_proxy，不是 native PVS depthHeadingAutopilot、真机或海试证据；时序审计只比较 MPC solver wall time 与已知周期预算，不测量 Jetson--AMD 物理 UDP 时延、丢包或 VxWorks 接收/解包时间戳；实测噪声仍来自 3.92 s 三轴背景记录循环回放
- Provenance gaps：完整 R22 仍需扩展到 2^4 因子、多 seed、失败样本和最坏边界搜索；延迟状态更新和声磁绝对水平观测仍未由本 smoke 闭合；Jetson 目标平台和 AMD/VxWorks 物理通信频率仍需 R23 或实物链路专项验证
- 主要文件：`results/control/r22_native_closed_loop_smoke_timing_h8_20260810/effect_summary.csv`；`results/control/r22_native_closed_loop_smoke_timing_h8_20260810/run_manifest.json`

### CONTROL-R22-NATIVE-CLOSED-LOOP-FACTORIAL R22 原生声磁--地形--横流 2^4 多 seed 闭环矩阵

- Artifact digest：`37ffd2ccc545b0a609165f0efeb6cc67fccc06324e9cf1d47aefe10c7c567206`
- 可访问字节数：`1704304`
- 可支持结论：R21 原生几何、地形与埋设、实测噪声回放和横流四因子已进入制导级 MPC、tracking authority 与 conservative quality-control policy 的完整 2^4 离线闭环矩阵；96/96 次运行有效，fallback 为 0，1.5 m 低净空违规率和海床穿透率均为 0，最小净空为 2.536 m；最坏横向 p95 为 1.716 m；横流是横向 p95 的主导主效应，baseline/UA/all 口径下效应分别约为 0.627/0.652/0.639 m；曲线几何与横流构成主要二阶交互项，baseline/UA 口径下横向 p95 交互效应约为 0.532/0.261 m；UA 将平均控制变化率 RMS 从 4.831 降至 0.814，但平均横向 p95 从 1.173 m 小幅升至 1.206 m；其主要价值仍是控制平滑而非路径精度全面提升；solver p95 最大 24.02 ms，solver max 最大 38.83 ms；相对 ROS 20 Hz、bridge 10 Hz、VxWorks 主控 10 Hz 和 NetRecv 0.3 s 周期均未越界
- 不可外推：数据层限定为 offline simulation_proxy，不是 native PVS depthHeadingAutopilot、真机或海试证据；本矩阵为 3 seed、20 s/run 的短时闭环验证，不替代长航时 soak、故障注入或最坏边界搜索；实测噪声回放和地形因子在本设置下对闭环指标主效应接近 0，只能说明当前短时代理闭环不敏感，不能外推为真实物理环境不重要；时序审计只比较 MPC solver wall time 与已知周期预算，不测量 Jetson--AMD 物理 UDP 时延、丢包或 VxWorks 接收/解包时间戳
- Provenance gaps：native PVS depthHeadingAutopilot 执行链 smoke 已由 CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE 覆盖；仍需 native PVS 性能矩阵验证；PC104 host-relay packet timing 已由 HARDWARE-PC104-UDP-TIMING-PROBE 覆盖到达间隔；仍需最终 Jetson 部署拓扑、固件 echo/共享时钟和目标平台算力复核；若论文需要最坏工况结论，还需扩展更长航时、更多 seed、失败样本和边界搜索
- 主要文件：`results/control/r22_native_closed_loop_full_3seed_timing_h8_20260810/run_manifest.json`

### CONTROL-R22-NATIVE-CLOSED-LOOP-60S-FACTORIAL R22 原生声磁--地形--横流 60 s 全因子长时复核

- Artifact digest：`fa840dc176959cb4fe04aa629d41dfba6d961b661d4fdae13b635c2393fce8b0`
- 可访问字节数：`4573425`
- 可支持结论：96/96 次运行有效，fallback 为 0，1.5 m 低净空违规率和海床穿透率均为 0；最坏横向 p95 为 2.176 m，最小净空为 2.384 m；相对 20 s 矩阵，长窗口仍保持安全净空与接口闭合；终端审计显示 96/96 次运行均未触发有限参考路径末端，因此 full-window lateral 指标可作为活动巡缆段指标使用；横流仍为横向 p95 主导主效应；跨 baseline/UA 汇总的横流主效应约为 1.144 m；UA 将平均控制变化率 RMS 从 4.634 降至 0.665，但平均横向 p95 从 baseline 的 0.956 m 升至 UA 的 1.212 m；不能写成全局精度改善；solver p95 最大 14.93 ms，solver max 最大 43.70 ms；相对 ROS 20 Hz、bridge 10 Hz、VxWorks 主控 10 Hz 和 NetRecv 0.3 s 周期均未越界
- 不可外推：数据层限定为 offline simulation_proxy，不是 native PVS depthHeadingAutopilot、真机或海试证据；60 s 全因子结果仍不是长航时 soak；120 s 地形+横流专项显示路径完成后的终端尾段必须单独计量；时序审计只比较 MPC solver wall time 与已知周期预算，不测量 Jetson--AMD 物理 UDP 时延、丢包或 VxWorks 接收/解包时间戳
- Provenance gaps：native PVS depthHeadingAutopilot 执行链 smoke 已由 CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE 覆盖；仍需 native PVS 性能矩阵验证；PC104 host-relay packet timing 已由 HARDWARE-PC104-UDP-TIMING-PROBE 覆盖到达间隔；仍需最终 Jetson 部署拓扑、固件 echo/共享时钟和目标平台算力复核；若要给出长航时稳定结论，需继续做 120--300 s 以上全矩阵或自适应边界搜索，并加入失败归因
- 主要文件：`results/control/r22_native_closed_loop_full_3seed_60s_h8_20260810/run_manifest.json`

### CONTROL-R22-NATIVE-TERRAIN-CURRENT-120S-STRESS R22 地形加横流 120 s 长时边界压力测试

- Artifact digest：`4f55754eb9bc3461af74deee637a0790341dd275f1f80b25c0a19d4dcd548ce7`
- 可访问字节数：`2365895`
- 可支持结论：24/24 次运行有效，1.5 m 低净空违规率和海床穿透率均为 0，最小净空为 2.384 m；全窗口横向 p95 最坏达到 6.839 m；终端审计显示 24/24 次运行均已到达有限参考路径末端；活动巡缆段横向 p95 最大为 2.152 m，终端尾段横向 p95 最大为 7.703 m；6 m 量级全窗口指标主要应解释为路径完成后的终端尾段边界；baseline 全窗口横向 p95 均值为 6.622 m、fallback 最大为 0；UA 全窗口横向 p95 均值为 5.041 m，但 fallback 最大达到 0.113；UA 在该专项中延后部分样本到达终点并降低若干全窗口均值，但引入非零 fallback，不能写成已解决终端保持或长航时稳定性；solver p95 最大 34.36 ms，solver max 最大 48.28 ms；相对 ROS 20 Hz 周期未越界但已接近预算上限的 68.7%
- 不可外推：该专项只覆盖地形与横流开启的 4 个组合，不是完整 2^4 120 s 全矩阵；数据层限定为 offline simulation_proxy，不是 native PVS depthHeadingAutopilot、真机或海试证据；结果是终端任务边界/负结果证据，不应与 R22 20 s 全矩阵的接口闭合结论混写为正向稳定性，也不能写成活动巡缆段跟踪崩溃
- Provenance gaps：路径完成后的任务层退出逻辑已由 CONTROL-R22-NATIVE-TERRAIN-CURRENT-120S-TERMINAL-EXIT 另包验证；若要评估长航时活动巡缆稳定性，需延长参考路径或采用路径长度归一化口径，而不是固定时长超过有限路径末端；仍需对速度、初始横偏、横流强度和 horizon 做敏感性搜索；仍需 native PVS 与真实 Jetson--PC104 链路复核
- 主要文件：`results/control/r22_native_closed_loop_terrain_current_3seed_120s_h8_20260810/run_manifest.json`

### CONTROL-R22-NATIVE-TERRAIN-CURRENT-120S-TERMINAL-EXIT R22 地形加横流 120 s 任务层终端退出验证

- Artifact digest：`73c045c8baa624a69e1d6617af510e230f970335b200de7c87c2df1d524cd17a`
- 可访问字节数：`1720467`
- 可支持结论：24/24 次运行有效，24/24 均到达有限参考路径末端并由任务层退出；1.5 m 低净空违规率和海床穿透率均为 0，最小净空为 2.384 m；退出终端尾段后 full-window 横向 p95 最大为 2.152 m，与上一包按 active tracking 分段审计得到的活动段上界一致，说明原 6.839 m 全窗口指标主要来自路径完成后的 terminal tail；baseline 横向 p95 均值/最大值为 1.445/1.616 m，fallback 最大为 0；UA 横向 p95 均值/最大值为 2.112/2.152 m，fallback 最大为 0.018；baseline 平均有效时长为 77.0 s，UA 平均有效时长为 93.6 s，说明 UA 延后部分样本到达终点，但不能写成精度全面改善；solver p95 最大 22.99 ms，solver max 最大 53.27 ms；相对 ROS 20 Hz 的 p95 预算未越界，但单点 max 使最大 20 Hz 周期越界率为 0.006；相对 bridge/VxWorks 10 Hz 和 NetRecv 0.3 s 周期均未越界
- 不可外推：该专项只覆盖地形与横流开启的 4 个组合，不是完整 2^4 120 s 全矩阵；terminal_policy=exit_at_end 验证的是任务完成后退出/截断指标，不是定点保持、横流悬停或终端 station-keeping 控制能力；数据层限定为 offline simulation_proxy，不是 native PVS depthHeadingAutopilot、真机或海试证据；UA 在该口径下仍有非零 fallback，且平均横向 p95 高于 baseline，不能写成 UA 全局精度改善
- Provenance gaps：native PVS depthHeadingAutopilot 执行链 smoke 已由 CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE 覆盖；仍需 native PVS 性能矩阵验证；PC104 host-relay packet timing 已由 HARDWARE-PC104-UDP-TIMING-PROBE 覆盖到达间隔；仍需最终 Jetson 部署拓扑、固件 echo/共享时钟和目标平台算力复核；若要评估长航时活动巡缆稳定性，需延长参考路径或采用路径长度归一化口径，而不是固定时长超过有限路径末端；若要声称终端保持能力，需另行设计具备横流补偿的 terminal hold/station-keeping 实验
- 主要文件：`results/control/r22_native_closed_loop_terrain_current_3seed_120s_terminal_exit_h8_20260810/run_manifest.json`

### CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE native PVS depthHeadingAutopilot 执行链 smoke 审计

- Artifact digest：`b938487490bbc383e5b9d23c8077e3b14b121ef61cc137ea7ae3fe167ad26518`
- 可访问字节数：`4212130`
- 可支持结论：专用配置使用 bridge.backend=protocol_udp、pvs.control_mode=depthHeadingAutopilot、pvs.autonomy_motion_model=native，且审计确认未使用 kinematic_setpoint proxy；审计状态为 passed；launcher 日志观测到 native PVS autopilot backend open 1 次、AUTO mode 149 次、kinematic log 0 次，protocol control mode 0xEE 计数为 268；ROS2 执行链观测到 /auv/control/setpoint、/auv/control/mpc_cmd、/auv/arbiter/status、/auv/state/filtered 进入 MCAP，arbiter effective control mode 238 计数为 8561；filtered state 在约 50 s 窗口内产生非零运动响应：x/y/z/yaw span 分别约为 24.035 m、7.892 m、1.127 m、30.7 deg；controller debug 的 72 个求解状态均为 Solve_Succeeded，solver wall time p95/max 分别为 19.318/20.404 ms；/auv/control/mpc_cmd 与 /auv/state/filtered 话题频率约为 20.04/20.02 Hz；该 smoke 关闭的是 ROS2 setpoint/controller 到 protocol_udp/Mock AMD 再到 native PVS 内层自动驾驶的执行链风险，而不是 R22 离线因子矩阵的性能统计
- 不可外推：该结果只支撑 native PVS/protocol_udp 仿真执行链闭合，不是 PC104/VxWorks 物理时延、海试或硬件 handoff 证据；本运行是 constant-depth/constant-heading smoke，不覆盖 R22 的声磁、地形、横流全因子性能矩阵、长航时鲁棒性或终端保持能力；速度参考通过 protocol_udp 主推 RPM 映射进入 PVS；该 smoke 不能写成精确速度跟踪或推进器实物响应验收；Mock AMD 只复现二进制协议与 AUTO dispatch 语义，不能替代真实 VxWorks 接收、解包、调度和本地安全逻辑；审计仍依赖 MCAP/launcher log 的外部可观测证据，未对 PVS 内部每个积分步做 intrusive trace
- Provenance gaps：需要扩展到多 seed、长窗口、横流/地形扰动和速度/初始偏差敏感性搜索，才能形成 native PVS 性能矩阵；真实 Jetson--AMD/PC104 链路仍需在最终部署拓扑下复核到达间隔、丢包和固件 echo/共享时钟能力；若论文需要端到端 applied-speed 结论，需要补充 native PVS 内层执行与下行 RPM/速度参考之间的逐步追踪
- 主要文件：`results/control/native_pvs_execution_chain_constant_feature_smoke_20260810/20260810_225652/native_pvs_execution_chain_audit/native_pvs_execution_chain_summary.json`

### HARDWARE-PC104-UDP-TIMING-PROBE PC104/VxWorks UDP 时序探针与 host-relay 实机记录

- Artifact digest：`72b0494bef2cab9faf78970fb379a76fff63a5bfe6539cd2a2e6b241b0a5459e`
- 可访问字节数：`423240`
- 可支持结论：已补齐可在 Jetson/PC104 网段上直接运行的 packet-level UDP 时序探针；探针默认发送安全零推力 $CKTH 下行帧，并记录 $AUV 上行帧到达间隔、frame gap、PC104 uptime 和解析错误；host-relay 路径已完成 30 s 实机闭环记录：300 帧零推力下行进入 relay，450 帧 PC104 $AUV 上行进入容器，parse error 0；观测到 PC104 主上行到达频率约 15.000 Hz，inter-arrival p50/p95/p99 分别为 57.983/85.710/85.944 ms；已保存逐包原始 timing CSV，并生成 PC104 上行/下行包间隔与 R22 MPC solver wall-time 直方图；R22 60 s 全矩阵 96 条 trace 共 11520 个 MPC 解算样本，全样本 p95 为 11.167 ms；该结果确认 Docker Desktop 场景下容器侧下行入口应使用 host.docker.internal IPv4 192.168.65.254:10022，并由 host relay 经 192.168.0.11:21 转发给 PC104；探针输出明确标记 one_way_latency_claim=false 与 round_trip_latency_claim=false；当前容器端口映射已完成拓扑判读：若 PC104 仍固定上行到宿主机 21/udp 与 52367/udp，则需宿主机转发到 10021/udp 与 62367/udp；已补充宿主机 full-duplex relay，使 timing probe 下行可经宿主机 192.168.0.11:21 转发到 PC104，而不是由容器 172.18.0.2 直接发往 PC104；fan-out 被定位为并发 ROS2/PySide6/旁路记录与下行安全门控方案，不是物理 timing 基线的必要条件
- 不可外推：当前结果是 host-relay/Docker Desktop 路径下的 packet arrival timing，不是裸网卡直连 timing；没有共享时钟或 firmware echo 时，该探针只能报告上行到达间隔、序列跳变和 PC104 uptime 单调性，不能报告单向物理时延；当前 30 s 结果不能声明 Jetson--AMD 一程物理 latency 或闭环控制端到端延迟；不能把 10021:21/udp 容器映射本身写成已接通 PC104 固定 21/udp 上行；单向 socat 上行转发只能用于 receive-only 检查，不能证明零推力下行已以宿主机 192.168.0.11:21 身份进入 PC104；若使用 fan-out，报告的到达间隔包含用户态转发路径，不应写成裸链路最小时延
- Provenance gaps：需要确认 VxWorks 上行 PC104 uptime marker 是否有效；若论文需要单向时延，需增加固件时间戳回显或共享时钟同步；建议后续在最终 Jetson 部署形态下重跑 300 s，并保存宿主机 tcpdump 作为旁路网卡时间证据；需要记录最终宿主机端口转发命令、容器端口映射快照和 PC104 固件上行目标端口
- 主要文件：`results/control/pc104_udp_timing_nohardware_20260810/run_manifest.json`

### JETSON-R09-HANDOFF Jetson clean benchmark 与历史产物回收 handoff

- Artifact digest：`3b066a4a32653364a68e0056001938b032c0e39582b989f4d54a10dff325c6fc`
- 可访问字节数：`39615`
- 可支持结论：单命令可执行 25 W/8 核环境门控、系统短测、MPC 两档和 30 min soak；每阶段可同步采集 tegrastats、进程、bag、日志和配置快照；可用 --recover 回收历史 Jetson 机器可读目录
- 不可外推：当前结果仅为非 Jetson 开发机 dry-run，contract_complete=false；不能用于真机实时性、热稳定或系统功耗结论
- Provenance gaps：须在 Jetson Orin NX 上关闭背景负载后执行 R23 并返回完整 bundle
- 主要文件：`results/jetson_clean_benchmark/20260809_r09_dry_run/run_manifest.json`

### JETSON-25W Jetson Orin NX 25W smoke 与 MPC microbench

- Artifact digest：`f385a4a2eb05c96994ae6a72404c988cc1f3d86163039732e5ec94d056b1932b`
- 可访问字节数：`75219`
- 可支持结论：带时间戳部署记录表明 PVS/protocol_udp/ROS2/cable tracking/bag 主链曾跑通；文档记录 warm-start p95 约 36 ms 与压力档 0.5--0.6 s
- 不可外推：当前工作区没有 Jetson 原始 bag、tegrastats 或 microbench CSV/JSON；不能升级为系统级实时性、热稳定或 PC104 真链路验收
- Provenance gaps：原始结果位于另一设备且未回收；缺少可校验的 Jetson 环境与结果 bundle
- **已知缺失包**：/auv_data/bags/20260713_002210；/auv_data/bags/20260713_002921；/auv_data/bags/20260713_011233；results/mpc_solve_microbench/jetson_20260713_depth_stress；results/mpc_solve_microbench/jetson_20260713_steady_200
- 主要文件：`docs/JETSON_DEPLOYMENT_CONTEXT.md`

### CONTROL-MPC-EXTREME-E1-MULTISEED MPC 极端平面路径多种子统计验证

- Artifact digest：`bb1d5524c9475af4977b905b0764b8797e92fed32c9c00c7ebe52e02e24357c6`
- 可访问字节数：`82454`
- 可支持结论：把原 n=1 极端路径结论升级为 n=5 统计：长波 S 弯 MPC 横向 RMSE 0.133±0.034 m vs PID-LOS 1.146±0.148 m，均值±1σ 区间互不重叠，MPC 全胜；180° 发卡掉头 MPC 2.363±0.234 m vs PID-LOS 4.246±0.459 m，区间互不重叠，MPC 全胜；短波 S 弯 MPC 1.824±0.190 m 与 PID-LOS 1.672±0.043 m 统计持平，二者均优于仅航向 PID 2.725±0.315 m；同一 seed 下三控制器共享同一扰动实现与噪声流以保证公平，MPC 变体冻结为确定性通道选出的 best 以防逐 seed 樱桃摘取；不传 --seeds 时 plant 逐字节复现旧 n=1（PID/LOS 位精确，MPC 仅 IPOPT ~1e-6 浮点噪声、三位小数不变），向后兼容归档
- 不可外推：90° 直角折弯 PID-LOS 1.003±0.513 m 最优、MPC 未领先，作为诚实边界保留，不外推为 MPC 全场景最优；该结论为离线制导闭环 + 简化艏向一阶动力学代理，非 PVS 六自由度或原生声磁闭环，也非真机；扰动为受控合成（恒定横流+初始偏移+艏向白噪声），不代表真实海流谱与传感噪声；n=5 种子为统计充分性下界，非大样本蒙特卡洛
- Provenance gaps：源 run 落在 AUV_DATA_ROOT 隔离目录（.auv_data_e1/results/control/mpc_xy_yaw_extreme/20260813_151303），不随仓库同步；仓库内仅保留 multiseed_summary.csv/multiseed_raw.csv 派生产物；该场景族缺少与真机或 PVS 原生闭环的横向 RMSE 交叉核对
- 主要文件：`docs/thesis/figures/experiments/control_mpc_xy_yaw_extreme/_SOURCE.md`；`docs/thesis/figures/experiments/control_mpc_xy_yaw_extreme/multiseed_summary.csv`

### ESTIMATOR-E2-TRI-ESTIMATOR-FAIR 三估计器公平初始化对比重算（O-1 修复后）

- Artifact digest：`c699b856536cd10d356debfcefacf795c616c9917be78930eab6ca934caf92dc`
- 可访问字节数：`141825`
- 可支持结论：统一三引擎初始化口径（同一 truth 起点位姿、同一 NED frame、去除手动翻 Z）后，24 次运行水平 RMSE 统计等价：Raw DR 3.197±0.695 m、Std EKF 3.196±0.692 m、ES-EKF 3.200±0.692 m，±1σ 完全重叠；深度维 12 m 恒偏伪影已消除，Z RMSE 落到 0.025/0.110/0.203 m 量级；Raw DR 因直接透传深度计读数、不做协方差融合而 Z RMSE 最小；legacy-auto 口径下 ES-EKF 水平 3.187 m 的微优被证实为首帧自对齐伪影，公平口径下消失，从根上消除 23 号 §8.1 的排序矛盾与开发文档 dvl_fixed_final 不自洽；水平三方等价属结构性可观性边界：观测仅 DVL(测速)+depth(测 z)，x/y 无绝对位置量测项，correct_gps 未接入，任何滤波器都退化为速度积分漂移；O-1 只改 benchmark 脚手架（新增 --es-ekf-init、收敛内联翻 Z 为具名 _ros_up_to_ned），不动 algorithm/es_ekf.py 主线算法
- 不可外推：水平等价不可通过调 R 突破，须引入绝对横向观测（USBL/GPS/声磁绝对定位）才能改变阶数，属论文展望（O-5）；深度维 Std/ES-EKF 略大于 Raw DR 属协方差整定口径问题（深度 R 偏小、DVL R 过保守），非算法精度结论，可整定项见 O-3/O-4（须批准）；离线滤波误差不等于控制侧 RMSE；n=3 种子、30 s 片段、数字孪生代理，非真机检测噪声
- Provenance gaps：逐 run 输出根落在 AUV_DATA_ROOT 隔离目录（results/state_estimation/e2_tri_estimator_fair），不随仓库同步；仓库内保留 summary/raw/pooled 派生产物与 legacy-auto 对照；尚未在 O-3/O-4 分源协方差整定后重算以验证深度维一致性改善
- 主要文件：`docs/thesis/figures/experiments/tri_estimator_fair/_SOURCE.md`；`docs/thesis/figures/experiments/tri_estimator_fair/tri_estimator_fair_summary.csv`；`log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv`

### ESTIMATOR-E3-COVARIANCE-AB 分源自适应 R 协方差整定 A/B（O-3/O-4，独立对照，不改主线默认）

- Artifact digest：`8c9887b8bee4239e8f02e31eb919694ad13ed1bfe0349db981051ff9f9f3cf8c`
- 可访问字节数：`154928`
- 可支持结论：baseline 臂不传任何覆盖开关即逐字节复现正文引用口径（深度 NIS/自由度 7.205、DVL 0.119），证明 A/B 与正文同口径、既有 24 矩阵与 ESKF-NIS-8X3 产物不失效、不回改；O-3 分源门控消除跨源污染：DVL 实际 R 缩放由 baseline 的 1.69x（上调占比 0.30）落回 1.000x（上调占比 0），全局机制把深度失配施加到 DVL 的伪影被切断；O-4 深度参数整定把负结果翻正：sigma_depth 0.05->0.12 后深度 NIS/自由度 7.205->3.280、95% 带覆盖率 0.561->0.735、上界超限率 0.416->0.215，逐 run 稳健（深度 3.21±1.27、覆盖率 0.739±0.072，n=24）；整定仅经 tools/uncertainty_metrics.py 新增 CLI 覆盖开关（--sigma-dvl/--sigma-depth/--adaptive-r-mode/--adaptive-r-normalized-threshold）在实验进程内改写口径，algorithm/es_ekf.py 与 brain_linux/config/params.yaml 默认协方差不变；新增 applied_r_scale 列如实记录 per_source 模式下逐源实际生效的 R 缩放，弥补 r_scale_after_update 在 per_source 恒为 1.0 而低估分源缩放的问题；既有列数值逐字节不变
- 不可外推：DVL 过保守（NIS/自由度约 0.05）是结构性下界而非可整定项：自适应 R 仅膨胀（下界 1.0x），分源门控下 DVL 从不触发上调；根治须下调 DVL 名义协方差 sigma_dvl 本身（属改主线默认），本独立实验刻意不做，如实记为下界；整定臂为独立对照口径，未回写 es_ekf.py/params.yaml 默认，正文主结论不依赖 B/C 臂；C 臂 sigma_depth=0.12 未在闭环控制侧验证一致性收益；离线逐量测重算 NIS 不等于在线控制侧协方差一致性；n=3 种子、30 s 片段、数字孪生代理，非真机检测噪声
- Provenance gaps：逐 bag 输出根落在 AUV_DATA_ROOT 隔离目录（results/state_estimation/e3_covariance_ab），不随仓库同步；仓库内保留 summary/raw/pooled/comparison 派生产物；整定后的默认协方差若要进入主线需单独批准并重跑既有 24 矩阵，本条目不含该主线变更
- 主要文件：`docs/thesis/figures/experiments/covariance_ab/_SOURCE.md`；`docs/thesis/figures/experiments/covariance_ab/covariance_ab_summary.csv`；`log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv`

## 5. 当前最重要缺口

1. 历史 sweep manifest 均未保存实验时 Git/submodule commit 和完整配置快照；
2. Jetson smoke 与 microbench 的原始 bag、CSV/JSON 结果未在当前工作区；
3. 45 Hz 短背景记录有原始 NPZ，但标准化阈值摘要要等 R06/R07；
4. NIS 原始与聚合数据完整，但自由度和 internal/proxy 语义要等 R05；
5. 代理极端场景只有单 seed，不能据此比较两种控制模式的统计优劣。

## 6. 重生成

```bash
python3 tools/build_thesis_artifact_manifest.py
python3 tools/build_thesis_artifact_manifest.py --check
```
