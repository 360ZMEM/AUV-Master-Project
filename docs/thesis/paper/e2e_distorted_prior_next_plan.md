# 端到端 distorted-prior 电缆探测验证 —— 下一步计划（独立专项）

- 生成时间：`2026-07-06`
- 定位：本文件是 [05_experiments_and_discussion.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/05_experiments_and_discussion.md) §5.5.11 第 (5) 条引用的独立计划文档。
- 结论前置：主仓端到端电缆探测目前**只在 clean prior 下闭环验收**（§5.5.10），"先验带偏差时端到端能否承受并恢复"这一实物部署最关心的问题，**尚未在主仓端到端 ROS 链路中验证**。本文规划把该缺口闭合的可执行路线。

## 1. 为什么需要这个专项（缺口定义）

§5.5.11 已核实并写入的三条事实：

1. 主仓运行时节点 [cable_tracking_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros/cable_tracking_node.py) 真实 `import` 并运行专用仓库 `AUV-Master-Mag` 的部署 API `AuvMagTrackingPipeline`（同源算法，非占位代理）。
2. 主仓配置 [cable_tracking.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/cable_tracking.yaml) 使用 `scenario_name: case1`，先验适配器 [cable_prior_adapter.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros/cable_prior_adapter.py) 构造 `CableMap` 时从不施加平移/旋转/缩放；节点/配置**不暴露先验偏差档位或位姿误差注入 knob**。运行时 `max_route_offset≈7.1e-15 m` 佐证端到端跑的是 clean prior。
3. docs 28-30 报告的 distorted-prior 失效/恢复边界（三档承受边界、纯磁失效时序、30 m 曲率、留一法机制分解、跨 lane 压力扫描）为**算法级、n=1、纯仿真、离线非 ROS** 证据，未在主仓端到端链路复现。

**实物部署可接受性判定：否。** clean-prior 端到端只证明"链路闭环 + 评分逻辑正确 + 干净先验下能贴线巡检"，不证明"先验带偏差时端到端可承受"。真实海缆图纸必然带系统性平移/旋转/缩放误差与航位漂移，因此工业验收必须补齐 distorted-prior 端到端证据。

## 2. 目标

在**主仓端到端 ROS 链路 + DL/T 1278 验收口径**下，复现并量化 distorted-prior 条件下的电缆探测承受边界，使论文能写出"主仓端到端在 mid/heavy 先验偏差下的鲁棒性"结论，而不再只依赖算法级引用。

验收判据（专项完成的定义）：
- 至少在 `mid` 与 `heavy` 两档先验偏差下，各完成 ≥3 次 fresh 端到端 run，产出 DL/T scorecard 与聚合报告。
- 端到端观测到与 sub-repo 算法级扫描**方向一致**的行为（如 heavy 先验触发可测的 route offset / 跨 lane 风险，或在线修正把 offset 收敛回验收窗口）。
- 诚实标注：端到端 run 仍为数字孪生、确定性先验偏差（非真实检测噪声），n 值如实记录。

## 3. 需要的改动（功能层，须先记录并经批准）

> 依据长期约束：`AUV-Master-Mag` 的 API/功能层改动不能破坏 `main.py` 独立运作；参数重构类改动需先记录并经用户批准（纯调参/override 不需要）。本专项引入的是**新的先验位姿误差注入路径**，属功能层改动，因此归入"需批准"，在本文件登记。

### 3.1 首选方案：主仓侧注入（改动最小、不动 sub-repo 算法）

在 [cable_prior_adapter.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros/cable_prior_adapter.py) 的 `load_cable_map_from_config` 之后、构造 `CableMap` 之前，增加一个**可选的先验位姿误差变换**：

- 在 [cable_tracking.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/cable_tracking.yaml) 的 `prior` 段新增可选 key（默认关闭，保持 clean-prior 为默认行为）：
  ```yaml
  prior:
    # ...existing...
    pose_error:
      enabled: false        # 默认 false，保持 §5.5.10 clean-prior 行为不变
      tier: mid             # light | mid | heavy（读 docs 28 表1 数值）
      translation_xy_m: [0.0, 7.5]
      rotation_deg: 3.0
      scale_xy: [0.99, 1.0]
  ```
- 适配器读取该段后，对 `yaml_points_ned` 施加 `S·R(θ0)·P + t0`（与 docs 28 §2.3.1 步骤 2 静态位姿扭曲同构），再交给下游 `CableMap`。
- **优点**：完全在主仓内完成，不改 `AUV-Master-Mag` 算法与 `main.py`；先验适配器本就是"把主仓配置翻译成 CableMap"的边界层，注入误差是其职责的自然延伸。
- **边界**：只注入静态位姿扭曲（步骤 2）；docs 28 步骤 3 的"旋转慢漂 `θ_drift(t)`"与"导航漂移"是 sub-repo 场景内部的动态通道，主仓端到端若要复现需另议（见 3.2）。

### 3.2 备选方案：透传 sub-repo tier profile

若要在端到端复现完整三步构造链（含旋转慢漂与导航漂移），需让节点把 `prior_tier` 透传给 `DeploymentPerceptionConfig`，由 `AUV-Master-Mag` 内部的 `_PRIOR_TIER_PROFILES` 施加。此方案改动面更大（触及 sub-repo 部署 API 的配置表面），且需确认不破坏 `main.py`，故列为备选，仅在 3.1 不足以支撑论文结论时启用。

### 3.3 剩余项 (a) 的实施方案：磁导出横偏观测 + 部署门面在线先验修正（2026-07-06 登记，经用户批准）

> 依据长期约束：`AUV-Master-Mag` 的 API/功能层改动须先记录并经用户批准。剩余项 (a) 属功能重构类改动，本节即为改动登记。**已经用户批准采用 Path A**（`AskUserQuestion` 选项 A：磁导出横偏观测）。

**背景与障碍（§4.1 已定位）**：主仓出厂 ROS 闭环消费的部署门面 `AuvMagTrackingPipeline`（[pipeline.py](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/src/auv_mag_tracking/api/pipeline.py)）只把车辆投影到**被扭曲后的** `CableMap`，不实例化离线 `orchestrator.py` 的在线 `PriorAlignmentEstimator`；因此距扭曲先验的横偏被忠实操舵去贴合、恢复能力架构性缺席。要接入在线修正，`PriorAlignmentEstimator.update()` 需要一个**独立于先验**的 `observed_point_xy`——而门面此前**没有**该观测：闭环 ROS 节点 [cable_tracking_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros/cable_tracking_node.py) 不订阅 sonar（`SonarInput` 虽 import 但从不喂入），`source` 恒为 `map_projection`。

**Path A 依据**：仿真两端的磁场 `B_ned` 均由 [`compute_biot_savart_hvdc`](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/holoocean_physics_bridge.py#L270-L274) 从**真值电缆几何**算出（电缆专有场，无地磁背景），闭环 run SNR 68–118 dB、`magnetic_used=true`。离线 orchestrator 早有一条磁导出的独立横偏观测 [`_magnetic_cross_track_offset`](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/src/auv_mag_tracking/perception/orchestrator.py#L476-L515)：以电缆走向为参考，把异常向量分解为电缆垂直水平分量 `B_perp` 与竖直分量 `B_down`，同一线电流驱动两者、比值消去电流，满足无限长直线模型 `y = (B_down/B_perp)·d`（`d` = 车体到电缆垂直分离 = 航高 + 埋深），由 [`MagneticCrossTrackEstimator`](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/src/auv_mag_tracking/perception/cross_track.py)（TLS 主轴 + 质量门控）实现。这正是门面此前**丢弃**的独立信息。

**改动清单（均默认关闭）**：

- `DeploymentPerceptionConfig` 新增 `enable_online_prior_alignment: bool = False`（及若干门控参数默认值），保持既有行为逐位不变。
- `AuvMagTrackingPipeline.__init__`：当 `enable_online_prior_alignment` 时构造 `MagneticCrossTrackEstimator` 与 `PriorAlignmentEstimator`（初值零修正）。
- `AuvMagTrackingPipeline.step()`：启用时，用当前电缆走向（`cable_heading`）把磁异常分解为 `B_perp/B_down`，喂 cross-track 估计器得带符号横偏 `y_mag`；由 `nav_xy` + `y_mag·normal` 构造**独立于先验投影**的 `observed_point_xy`，对其投影到当前（修正后）route prior 得 `prior_point_xy/prior_tangent`，调 `PriorAlignmentEstimator.predict/update` 累积平移/旋转修正；用 [`apply_route_prior_pose_error`](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/src/auv_mag_tracking/math_utils.py#L508-L530) 重建投影 cache，使后续横偏/操舵基于**修正后**先验。诊断字段 `prior_alignment_*` 暴露累积修正与残差。
- 主仓侧 [cable_tracking.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/cable_tracking.yaml) `quality` 段暴露 `enable_online_prior_alignment`（默认 false），节点 `_build_deployment_config` 已按 dataclass 字段名自动透传。

**诚实边界（须随结果保留）**：

- 磁导出横偏基于无限长直线模型与**已知电缆走向**假设，弯段/远离段模型失真，靠 TLS 质量门控 gate 出；标称 ~1m 级精度。
- `d`（垂直分离）用航高 + 标称埋深近似，埋深误差直接进入横偏标度。
- 仿真磁场为**电缆专有场、无地磁背景与检测噪声**；真机须先去背景/去噪，边界如实标注，不可写成真机实测。
- 该路径复现"闭环恢复能力"的**机理**，n 值如实标注；未做多种子前不得写成统计显著。

## 4. 执行步骤

1. **登记与批准**：本文件即为改动记录；开工前向用户确认采用 3.1 还是 3.2。
2. **实现注入 hook**（默认关闭）：改 [cable_prior_adapter.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros/cable_prior_adapter.py) + [cable_tracking.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/cable_tracking.yaml)；加单元/最小验证：`enabled:false` 时 `CableMap` 与当前逐点一致（回归保护 §5.5.10）。
3. **回归 clean-prior**：`enabled:false` 重跑 1 次端到端，确认 `max_route_offset≈0` 未变。
4. **distorted-prior 端到端 run**：`mid` / `heavy` 各 ≥3 次 fresh run，走既有验收流水 `start_experiment.sh → extract_cable_tracking_jsonl.py → dlt1278_cable_report.py → aggregate_cable_acceptance_runs.py`。
5. **对照与写入**：把端到端 distorted-prior 结果与 docs 29 算法级同档结论对照，写入 §5.5.11（升级第 3/4 条），并把 §5.5.11 (4) 的"否"判定按新证据修订。

### 4.1 执行结果（2026-07-06 更新）

- **步骤 1-3 ✓ 完成**：采用 3.1 主仓侧静态位姿扭曲注入；hook 默认关闭、`main.py` 与 §5.5.10 clean-prior 行为不受影响；clean 回归 `max_route_offset≈7.1e-15 m`（逐位复现原始 fresh run）。
- **步骤 4：以"开环回放"完成（偏离原计划的闭环 fresh run）**。本环境**未部署活体仿真后端**（HoloOcean/PVS 未安装、`import pvs` 失败），无法用 `start_experiment.sh` 起真正闭环 run。经用户批准的 **Option 1（replay-driven end-to-end）** 路线：用 `ros2 bag play --topics` 只回放三次 clean-prior fresh run 已录制的输入 topic（nav/mag/mission），喂给运行同源 `AuvMagTrackingPipeline` 的真实 `cable_tracking_node`，录制新 `/auv/cable/tracking` 走既有验收流水。harness = `scripts/run_cable_replay_e2e.sh` / `run_cable_replay_one.sh`；临时 tier 配置由 `tools/make_pose_error_config.py` 生成（不改磁盘 canonical）。
  - 结果（n=3/档，跨 3 个源 bag realization）：mid 全程 `max_route_offset≈15.4 m`（15.36/15.39/15.50）、heavy≈20.3 m（20.24/20.27/20.40）；两档 windowed `point_count=0`（起始横偏 mid≈7.9 m、heavy≈10.7 m 超 start-health 5.0 m 门限 `start_cross_track_too_large`），`preliminary_acceptance_ready=false`、`pass_ratio=0.0`、`readiness=invalid`。产物在 `results/cable_ops_report/replay_e2e/{mid,heavy}_run*_bag*` 与聚合 `_agg_mid`/`_agg_heavy`。
  - **开环局限**：轨迹被 clean 录制固定，distorted prior 不重新操舵，`PriorAlignmentState` 在线修正得不到闭环激励，`prior_alignment_residual_m == cross_track_m` 每帧相等、横偏单调累积不被吸收——**故只证明"端到端能感知并如实评判先验偏差压力"，未复现"闭环恢复"**。
- **步骤 5 ✓ 完成**：§5.5.11 已升级为 (3)=(3a 算法级引用)+(3b 端到端开环实测)+(3c 端到端闭环实测)三层，(4) 判定由"完全未触及"逐步修订，(5) 记录进度与剩余缺口。
- **剩余唯一未闭合项 ✓ 已闭合（PVS 后端就位后补做）**：`import pvs` 此前失败系模块名误判——真实包名为 `python_vehicle_simulator`（PVS = PythonVehicleSimulator，REMUS 100 六自由度刚体动力学），本就可用。用 `scripts/run_cable_closedloop_distorted.sh` 包裹 `start_experiment.sh`（与 §5.5.10 clean fresh run 完全一致的 PVS 配方 + `AUV_SKIP_BRAIN_BUILD=1`），把 `cable_tracking_config` 指向 `results/cable_ops_report/replay_e2e/_configs/{mid,heavy}.yaml`，mid/heavy 各跑 3 次真闭环 fresh run。
  - 结果（n=3/档，产物在 `results/cable_ops_report/closedloop_e2e/`）：mid 全程 `max_route_offset≈15.3 m`（15.27–15.31）、heavy≈20.1 m（20.09–20.11）；两档 windowed `point_count=0`、起始横偏 mid≈7.9 m/heavy≈10.7 m 超门限，`preliminary_acceptance_ready=false`、`readiness=invalid×3`。clean 闭环基线先复现 pass/ready（723 帧、`max_route_offset≈7.1e-15 m`）确立有效性。
  - **闭环确实"闭上了"**：逐帧 `guidance.desired_heading_deg` vs `raw_desired_heading_deg` 平均差 17–20°（mid ≈970/1223 帧、heavy ≈1046/1223 帧实质操舵），车辆被真实重新操舵，非开环冻结。
  - **但结果与开环几乎重合**（闭环 mid 15.3 vs 开环 15.4；闭环 heavy 20.1 vs 开环 20.3），仍 0/3 fail/invalid。**根因定位**：主仓出厂 ROS 部署门面 `AuvMagTrackingPipeline`（[pipeline.py](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/src/auv_mag_tracking/api/pipeline.py) `step()`）把车辆投影到**被扭曲后的** `CableMap`，**不实例化**离线 `orchestrator.py` 里的在线 `PriorAlignmentEstimator`；`prior_alignment_residual_m` 在 [deployment_quality.py](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/src/auv_mag_tracking/api/deployment_quality.py#L134) 按构造 `= abs(route_distance_m)`。即车辆被忠实操舵去贴合被扭曲先验，恢复能力在出厂 ROS 节点中**架构性缺席**（非"尝试恢复失败"）。
- **由此产生的新剩余项**：（a）把离线 `PriorAlignmentEstimator` 接进部署门面并在线更新 `CableMap`、再在 PVS 闭环复验恢复（功能/参数重构类改动，须先记录经批准）；（b）真实检测噪声；（c）多种子统计；（d）硬件实物。

### 4.2 剩余项 (a) 执行结果（2026-07-06 更新，Path A：磁导出横偏观测；结论为诚实的负结果）

按 §3.3 登记且经用户批准的 Path A 实施，对应 §5.5.11 新增子节 (3d)：

- **接线实现 ✓ 完成**：`DeploymentPerceptionConfig` 新增 `enable_online_prior_alignment: bool = False`；`AuvMagTrackingPipeline` 在启用时构造 `MagneticCrossTrackEstimator` + `PriorAlignmentEstimator`，`step()` 用电缆走向把磁异常分解为 `B_perp/B_down`、按 `y=(B_down/B_perp)·d` 反演带符号横偏、构造独立于先验投影的 `observed_point_xy` 喂在线 EKF 累积平移/旋转修正、用 [`apply_route_prior_pose_error`](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/src/auv_mag_tracking/math_utils.py#L508-L530) 重建投影 cache。默认关闭、`main.py` 与 §5.5.10 clean-prior 行为逐位不变；单测 [test_api_online_prior_alignment.py](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/tests/test_api_online_prior_alignment.py) 覆盖禁用逐位回归、启用吸收合成横偏、reset 恢复 base，3/3 通过。
- **配置接线**：主仓 canonical [cable_tracking.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/cable_tracking.yaml) `quality` 段加 `enable_online_prior_alignment: false`（保持 §5.5.10 不变）；mid/heavy 变体 [_configs/mid.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/results/cable_ops_report/replay_e2e/_configs/mid.yaml)/heavy.yaml `quality` 段设 `true`。节点 `_build_deployment_config` 按 dataclass 字段名自动透传。闭环启动用 [run_cable_closedloop_distorted.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/run_cable_closedloop_distorted.sh)（与 (3c) 完全一致的 PVS 配方），打分聚合用 [score_cable_closedloop_runs.sh](file:///home/auv_user/auv_ws/AUV-Master-Project/scripts/score_cable_closedloop_runs.sh)。correction-off baseline 6 个 run 目录已重命名为 `*_prioroff` 保留对照。
- **PVS 闭环复验结果（n=3/档，负结果）**：（i）在线修正确实被**实例化并激励**——`prior_alignment_connected/online=True` 全程、`prior_alignment_observed`≈1204/1223 帧、`cross_track_quality` 中位数=1.0（远超 `min_confidence=0.35`）。（ii）但**累积平移恒为 0**——EKF 残差门 `max_residual_m=18.0 m` 把 **1204/1204 帧观测全部拒绝**（`reason_code=2` RESIDUAL_TOO_LARGE，residual_norm 中位数≈29.7 m），`translation_norm≡0`、投影 cache 从未被修正；全程 route offset 与 (3c) 关闭修正时几乎逐位重合（mid max 15.27–15.31 m、heavy max 20.09–20.18 m），仍确定性 0/3 invalid。
- **拒绝根因（从 bag 复算证实）**：反演横偏恒为约 −34…−45 m（真值几何横偏仅约 −10 m），系统性放大约 4–5 倍。PVS 端 `mock_amd` 产磁用的电缆几何（[bridge_params.protocol_udp.pvs.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/config/bridge_params.protocol_udp.pvs.yaml#L114-L119)：NED 深度约 12–13.5 m）与**车辆几乎同深**（车体 NED z≈12 m），并非"埋于车体正下方 `d≈7.5 m`"；实测磁场因此 **Bz 主导**（`Bz/By≈−5`），与"车在缆正上方、By 主导"的直线埋缆模型正好相反 → 比值反演 `y/d` 严重偏置。**这是磁观测源前提不成立问题、非 EKF 或接线 bug——残差门"正确地"挡住了越界观测。**
- **附带独立发现**：复核 6 个闭环 bag 的 `/auv/state/filtered` 里程计，PVS mock 车体的 Y 与 yaw 在全程 2604 帧里**恒为 0.0**、仅沿 +x 以 0.5–0.96 m/s 前进，尽管节点发布了非平凡 `target_heading_rad`（峰值≈0.13 rad）与 `target_y_m`（峰值≈14.8 m）。即当前 PVS mock 后端**未对横向/艏向设定值产生实际位形响应**——(3c) 的"重新操舵 17–20°"应限定为**制导指令层**修正而非车体位形横向操舵。此项与"部署门面是否接入在线修正"正交，属 PVS mock 车辆动力学响应缺口。
- **分层结论**：剩余项 (a) 的**部署门面接线已打通并经单测覆盖**，但在**当前 PVS 闭环 fresh run 中未复现恢复**（该后端产磁电缆与车辆近乎共面，直线埋缆假设不成立）。**准确表述：接线已通、单测已过；当前 PVS 场景几何不满足磁横偏观测前提，故闭环恢复在该场景下未获激励。不得写成"在线修正在主仓闭环中已复现恢复"，也不得写成"在线修正失败"。**
- **由此细化的新剩余项**：（a1）需要一个磁观测前提成立（缆埋于车体下方 `d` 米、By 主导）的 PVS 闭环场景，或改用不依赖直线假设的观测反演，来真正激励已接入的在线修正并复验恢复；（a2）修复 PVS mock 车体对横向/艏向设定值的位形响应（当前 Y/yaw 恒为 0.0）；（b）真实检测噪声；（c）多种子统计；（d）硬件实物。

## 5. 诚实边界（本专项完成后仍须保留的标注）

- 端到端 distorted-prior run 仍为数字孪生、确定性先验偏差，**非真实检测噪声**；不可写成真机实测。
- 先验位姿误差为人工注入档位，用于压力测试端到端承受边界，不等价于真实图纸误差分布。
- 若采用 3.1（仅静态扭曲），须注明"未复现旋转慢漂/导航漂移动态通道"，与 sub-repo 完整三步链的差异如实记录。
- n 值如实标注；未做多种子前不得写成统计显著。
- 剩余项 (a) 磁导出横偏观测基于**无限长直线埋缆模型 + 已知电缆走向**假设，要求缆埋于车体下方一定深度（By 主导）；当前 PVS 场景产磁缆与车近乎共面（Bz 主导），该前提不成立，故 (3d) 为负结果——接线已通但恢复未在该场景复现，不得表述为"闭环恢复已复现"。

## 6. 与主仓约束的一致性检查

- [x] 不迁移 docs 28-30 原文/图片到主仓（仅引用）。
- [x] 注入 hook 默认关闭，`main.py` 与 §5.5.10 clean-prior 验收行为不受影响。
- [x] 功能层改动先登记（本文件）、开工前经批准。
- [x] 诚实边界：clean-prior 与 distorted-prior、算法级与端到端、仿真与真机三组边界显式区分。
