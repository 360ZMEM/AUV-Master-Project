# 电缆巡检 distorted-prior 端到端闭环探索历史：从负结果到正结果

**日期区间**: 2026-07-05 ~ 2026-07-07
**目的**: 记录"先验带偏差时，主仓端到端电缆巡检链路能否承受并恢复"这一实物部署最关心问题的完整探索历史——从开环回放的确定性失效、到闭环但恢复能力架构性缺席、到接线后因几何前提不成立的诚实负结果、再到解耦轻量闭环与 PVS 六自由度闭环两次正结果。本文面向"之后自己独立回看这条负→正因果链"，每一步都保留目标、命令、结果、根因判断与诚实边界。

**阅读边界**: 本文件是 2026-07 电缆巡检专项的**原始探索日志**，记录的是"我们怎么一步步从失败走到正结果、每一步的根因是什么"，不是最终工程结论本身。最终结论以论文正文 [docs/thesis/paper/05_experiments_and_discussion.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/05_experiments_and_discussion.md) §5.5.11 为准；可执行路线与改动登记以 [docs/thesis/paper/e2e_distorted_prior_next_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/e2e_distorted_prior_next_plan.md) 为准；部署 I/O 契约见 [docs/real_deployment/08_cable_inspection_io_contract.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/real_deployment/08_cable_inspection_io_contract.md)。**本文全程遵守一条铁律：(3f) 是新增/抬升，不覆盖也不改写 (3d)/(3e) 的负结果与轻量闭环历史。**

---

## 0. 探索总览：一条负→正的因果链

在读任何一步细节前，先建立整条链的骨架。每一步都不是"推翻上一步"，而是"把上一步暴露的根因再削掉一层"：

| 阶段 | 形态 | 结果 | 削掉的那层根因 |
|---|---|---|---|
| (3b) | 端到端**开环回放** | 负（0/3 invalid） | 证明链路能感知先验偏差压力，但轨迹被 clean 录制固定、在线修正得不到闭环激励 |
| (3c) | 端到端 **PVS 闭环** fresh run | 负（0/3 invalid） | 证明闭环确实"闭上了"（制导层被修正 17–20°），但根因是**部署门面未接入在线先验修正估计器** |
| (3d) | 接线后 **PVS 闭环**复验 | **诚实的负结果**（0/3 invalid） | 在线修正已接进部署门面、单测已过，但当时 PVS 产磁几何近共面、磁横偏观测前提不成立，被 EKF 残差门 100% 拒绝 |
| (3e) | **解耦轻量**闭环（Direction A） | 正（算法部署接口可用） | 用满足磁观测前提的轻量运动学外壳，证明"前提成立时在线修正能在部署 ROS 闭环被真实接受" |
| (3f) | **PVS 六自由度闭环**复验 | **正结果**（mid/heavy 各 3/3 ready/pass） | 把满足前提的产磁几何迁回 PVS、修复车体位形响应，闭环恢复被首次复现 |

一句话概括这条链：**"能感知压力(3b) → 闭环闭上了但没接在线修正(3c) → 接上了但几何前提不成立(3d) → 轻量外壳证明前提成立时能工作(3e) → 迁回 PVS 六自由度让前提成立、恢复被复现(3f)"。** 关键是理解每一步的负结果都不是"能力缺失"，而是"某个前提尚未满足"，(3f) 逐个补齐了这些前提。

---

## 1. 起点：clean-prior 已闭环达标，但 distorted-prior 未验证

专项开始前，主仓端到端电缆巡检**只在 clean prior 下闭环验收**（§5.5.10，`max_route_offset≈7.1e-15 m`、pass/ready）。而实物部署最关心的问题是：**真实海缆图纸必带系统性平移/旋转/缩放误差与航位漂移，先验带偏差时端到端能否承受并恢复？**

这个缺口的证据当时只停留在专用仓库 `AUV-Master-Mag` 的**算法级、n=1、离线非 ROS** 扫描（三档承受边界、纯磁失效时序、跨 lane 压力扫描），**从未在主仓端到端 ROS 链路复现**。判定因此明确写作：**实物部署可接受性——否。** 专项目标就是把这个缺口向"主仓端到端"逐步推进。

改动登记（功能层，须先记录经批准）：在主仓侧先验适配器 [cable_prior_adapter.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros/cable_prior_adapter.py) 加一个**默认关闭**的先验位姿误差注入 hook（`prior.pose_error`，施加 `S·R(θ0)·P + t0` 静态位姿扭曲），保持 §5.5.10 clean-prior 行为逐位不变。tier 数值取自算法级扫描：

```yaml
prior:
  pose_error:
    enabled: false        # 默认 false，clean-prior 为默认行为
    tier: mid             # mid: t0=(0,7.5)m / θ0=3.0° / S=(0.99,1.0)
    #      heavy: t0=(0,10.0)m / θ0=5.0° / S=(0.98,1.0)
```

回归确认：`enabled:false` 时端到端 `max_route_offset≈7.1e-15 m` 逐位复现原始 fresh run。

---

## 2. (3b) 端到端开环回放：能感知压力，但恢复得不到激励（负）

### 目标

在没有活体仿真后端时，先用最低成本的路线检验"端到端链路能否感知 distorted prior 的压力"。

### 命令

本环境当时误判 `import pvs` 失败（模块名错误，真实包名是 `python_vehicle_simulator`），无法起真闭环，故走 replay-driven 路线：只回放三次 clean-prior fresh run 已录制的输入 topic（nav/mag/mission），喂给运行同源 `AuvMagTrackingPipeline` 的真实 `cable_tracking_node`，录制新 `/auv/cable/tracking`。

```bash
bash scripts/run_cable_replay_e2e.sh        # 逐 run: run_cable_replay_one.sh
# 临时 tier 配置由 tools/make_pose_error_config.py 生成，不改磁盘 canonical
```

### 结果（n=3/档，跨 3 个源 bag realization）

| tier | 全程 route offset max（m） | 起始横偏（m，阈 5.0） | 窗口内点数 | 聚合 ready |
|---|---:|---:|---:|---|
| mid | 15.36 / 15.39 / 15.50 | ≈7.9 ✗ | 0 | **False（0/3 invalid）** |
| heavy | 20.24 / 20.27 / 20.40 | ≈10.7 ✗ | 0 | **False（0/3 invalid）** |

产物：`results/cable_ops_report/replay_e2e/{mid,heavy}_run*_bag*` 与聚合 `_agg_mid`/`_agg_heavy`。

### 结论与根因

方向上与算法级扫描一致（先验偏差越大、offset 越大、越难验收），跨 realization 离散极小（说明是先验几何偏差的确定性后果，非随机噪声）。**但这是开环**：轨迹被 clean 录制**固定**，distorted prior 只改参考航线、不重新操舵车辆，`PriorAlignmentState` 在线修正**得不到闭环激励**，`prior_alignment_residual_m == cross_track_m` 每帧相等、横偏单调累积不被吸收。

**准确表述**：只证明"端到端能感知并如实评判先验偏差压力"，**未复现"闭环恢复"**。遗留唯一未闭合项——带活体仿真的闭环 fresh run。

---

## 3. (3c) PVS 闭环 fresh run：闭环闭上了，但部署门面没接在线修正（负）

### 目标

在 PVS（PythonVehicleSimulator，REMUS 100 六自由度刚体动力学）后端就位后，用真闭环 fresh run 检验在线先验修正能否吸收横偏——即闭合 (3b) 的遗留项。

### 命令

`import pvs` 之前失败系模块名误判，真实包名为 `python_vehicle_simulator`，本就可用。用与 §5.5.10 clean fresh run **完全一致**的 PVS 配方：

```bash
bash scripts/run_cable_closedloop_distorted.sh
# 每 run 等价于：
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --sim-backend pvs --bridge-backend protocol_udp --arbiter-profile \
  --protocol-control-mode-byte 238 --bag-profile cable_acceptance \
  --brain-arg cable_tracking_config:=results/cable_ops_report/replay_e2e/_configs/heavy.yaml
```

clean 闭环基线先复现 pass/ready（723 帧、`max_route_offset≈7.1e-15 m`）确立有效性。

### 结果（n=3/档）

| tier | 全程 route offset max（m） | 窗口内点数 | conf_p05 | 聚合 ready |
|---|---:|---:|---:|---|
| mid | 15.27–15.31 | 0 | 0.732 | **False（0/3 invalid）** |
| heavy | 20.09–20.11 | 0 | 0.701 | **False（0/3 invalid）** |

### 结论与根因（这一步很关键）

- **闭环确实"闭上了"，非开环冻结**：逐帧 `guidance.desired_heading_deg` vs `raw_desired_heading_deg` 平均差 17–20°（峰值约 47–50°），mid ≈970/1223 帧、heavy ≈1046/1223 帧发生实质操舵。
- **但结果与开环几乎重合**（闭环 mid 15.3 vs 开环 15.4；闭环 heavy 20.1 vs 开环 20.3），仍确定性 0/3。
- **根因定位**：主仓出厂 ROS 部署门面 [AuvMagTrackingPipeline](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/src/auv_mag_tracking/api/pipeline.py) 的 `step()` 把车辆投影到**被扭曲后的** `CableMap`（`nearest_point_on_polyline`），**不实例化**离线 `orchestrator.py` 里的在线 `PriorAlignmentEstimator`；`prior_alignment_residual_m` 在 [deployment_quality.py](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/src/auv_mag_tracking/api/deployment_quality.py#L134) 按构造 `= abs(route_distance_m)`。

即：车辆被**忠实操舵去贴合被扭曲的先验航线**，恢复能力在出厂 ROS 节点中**架构性缺席**（不是"尝试恢复失败"）。这比 (3b) 更可操作——要闭合恢复缺口，必须把离线 `PriorAlignmentEstimator` 接进部署门面，而非仅靠调参。由此产生新剩余项 (a)。

---

## 4. (3d) 接线后 PVS 闭环复验：接线已通，但几何前提不成立（诚实的负结果）

### 目标

按 (3c) 指出的方向，把离线 `PriorAlignmentEstimator` 接进部署门面，在 PVS 闭环复验恢复。这一步的价值不在结果正负，而在**把失效性质从"能力缺失"细化为"前提不成立"**。

### 障碍与 Path A 依据

`PriorAlignmentEstimator.update()` 需要一个**独立于先验**的 `observed_point_xy`——而闭环 ROS 节点不订阅 sonar（`SonarInput` 虽 import 但从不喂入），`source` 恒为 `map_projection`，门面此前**没有**该观测。

已批准的 **Path A（磁导出横偏观测）**：仿真两端磁场均由 `compute_biot_savart_hvdc` 从真值电缆几何算出（电缆专有场、无地磁背景），闭环 SNR 68–118 dB。以电缆走向为参考，把磁异常向量分解为电缆垂直水平分量 `B_perp` 与竖直分量 `B_down`，同一线电流驱动两者、比值消去电流，按无限长直线模型反演带符号横偏：

```text
y = (B_down / B_perp) · d          # d = 车体到电缆垂直分离 = 航高 + 标称埋深
```

由此构造独立于先验投影的 `observed_point_xy` 喂在线 `PriorAlignmentEstimator` 累积平移/旋转修正、重建投影 cache。

### 改动清单（均默认关闭）

- `DeploymentPerceptionConfig` 新增 `enable_online_prior_alignment: bool = False`，既有行为逐位不变。
- `AuvMagTrackingPipeline.__init__`：启用时构造 `MagneticCrossTrackEstimator` + `PriorAlignmentEstimator`（初值零修正）。
- `AuvMagTrackingPipeline.step()`：启用时反演 `y_mag`、构造 `observed_point_xy`、调 `predict/update`、用 `apply_route_prior_pose_error` 重建 cache。
- 单测 [test_api_online_prior_alignment.py](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/tests/test_api_online_prior_alignment.py)：禁用逐位回归、启用吸收合成横偏、reset 恢复 base，3/3 通过。

### 命令

与 (3c) **完全一致**的 PVS 配方，仅在 mid/heavy 变体的 `quality` 段打开 `enable_online_prior_alignment: true`。

### 结果（n=3/档，负结果）

- 在线修正确实被**实例化并激励**：`prior_alignment_connected/online=True` 全程、`prior_alignment_observed`≈1204/1223 帧、`cross_track_quality` 中位数 1.0（远超门限 0.35）。
- 但**累积平移恒为 0**：EKF 残差门 `max_residual_m=18.0 m` 把 **1204/1204 帧观测全部拒绝**（`reason_code=2` RESIDUAL_TOO_LARGE，residual_norm 中位数≈29.7 m），`translation_norm≡0`；全程 route offset 与 (3c) 关闭修正时几乎逐位重合，仍 0/3 invalid。

### 根因（从 bag 复算证实）

反演横偏恒为约 −34…−45 m（真值几何横偏仅约 −10 m），系统性放大约 4–5 倍。PVS 端 `mock_amd` 产磁用的电缆几何（[bridge_params.protocol_udp.pvs.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/config/bridge_params.protocol_udp.pvs.yaml#L114-L119)：NED 深度约 12–13.5 m）与**车辆几乎同深**（车体 NED z≈12 m），并非"埋于车体正下方 `d≈7.5 m`"；实测磁场因此 **Bz 主导**（`Bz/By≈−5`），与"车在缆正上方、By 主导"的直线埋缆模型正好相反 → 比值反演 `y/d` 严重偏置。

**这是磁观测源前提不成立问题、非 EKF 或接线 bug——残差门"正确地"挡住了越界观测。**

### 附带独立发现（供 (3c) 加注）

复核 6 个闭环 bag 的 `/auv/state/filtered` 里程计，PVS mock 车体的 Y 与 yaw 在全程 2604 帧里**恒为 0.0**、仅沿 +x 前进，尽管节点发布了非平凡 `target_heading_rad`（峰值≈0.13 rad）与 `target_y_m`（峰值≈14.8 m）。即当前 PVS mock 后端**未对横向/艏向设定值产生位形响应**——(3c) 的"重新操舵 17–20°"应限定为**制导指令层**修正而非车体位形横向操舵。此项列为剩余项 (a2)。

### 结论（诚实表述，铁律）

**准确表述：接线已通、单测已过；当前 PVS 场景几何不满足磁横偏观测前提，故闭环恢复在该场景下未获激励。不得写成"在线修正在主仓闭环中已复现恢复"，也不得写成"在线修正失败"。**

由此细化新剩余项：(a1) 需要一个磁观测前提成立（缆在车下 `d` 米、By 主导）的 PVS 闭环场景；(a2) 修复 PVS mock 车体位形响应；(b) 真实检测噪声；(c) 多种子统计；(d) 硬件实物。

---

## 5. (3e) 解耦轻量闭环（Direction A）：前提成立时在线修正能工作（正，算法部署接口）

### 目标

为区分"当前 PVS 产磁几何不满足前提"与"部署算法本身是否可在线闭环"，先用一个**不依赖 PVS 动力学**的轻量闭环，快速证明"前提成立时在线修正能在部署 ROS 闭环被真实接受"。

### 命令

新增轻量 ROS2 闭环节点 [decoupled_cable_sim_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros/decoupled_cable_sim_node.py) + Direction A 配置 [cable_tracking_direction_a.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/cable_tracking_direction_a.yaml)：

```bash
bash scripts/run_direction_a_decoupled_cable_sim.sh
```

该节点只承担仿真外壳：消费出厂 `cable_tracking_node` 发布的 `/auv/control/setpoint`，用简单运动学积分车辆位姿，发布 `/auv/state/filtered`、`/auv/sensors/magnetic`、marker；磁场仍调用同一个 `compute_biot_savart_hvdc`，但把真值直缆布置在磁传感器正下方约 `d=7.5 m`，使 `B_perp=By` 主导、满足直线埋缆观测前提。

### 结果（短闭环 smoke）

| Direction A 关键量 | 值 | 与 (3d) PVS 闭环对照 |
|---|---:|---|
| 磁观测被激励 `observed` | 1.000 | (3d) 1204/1223 也被激励 |
| 在线修正被接受 `accepted` | 1.000 | (3d) 0/1204（残差门全拒） |
| 拒绝原因 `reason_code` | 1（accepted） | (3d) 恒为 2（残差超限） |
| 横偏拟合质量 `cross_track_quality` | ≈1.0（门限 0.35） | (3d) 中位 1.0 但仍被拒 |
| 垂直分离 `vsep` | 7.50 m（缆在车下） | (3d) ≈0 m（缆车近共面） |
| 累积平移 `translation_norm` | 非零（cache 被修正） | (3d) ≡0（cache 未被修正） |

8 s MCAP 验证包生成于 `results/cable_ops_report/direction_a_decoupled/20260706_221801/rosbag/rosbag_0.mcap`，可直接用于 Foxglove 巡检视频录制。

![Direction A 在线先验修正接受时序](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/figures/cable_acceptance/direction_a_online_prior_alignment.png)

### 结论（分层）

对"算法实机部署接口"而言，答案从"待证"修订为**是（限定算法部署接口与闭环运行形态）**：出厂 ROS 节点已按真实部署契约消费原始磁场/里程计输入、在线修正被满足前提的磁观测接受、控制输出经 `/auv/control/setpoint` 回到外部运动学闭环、全链路可录 Foxglove 视频。对"实物部署验收"而言仍为否：Direction A 是无地磁背景、无真实检测噪声、无硬件时延、无六自由度水动力的轻量闭环。

**准确表述："算法实机部署接口与闭环数据契约已成立；硬件实物验收证据仍待补。"**

---

## 6. (3f) PVS 六自由度闭环复验：在线修正被接受、闭环恢复被首次复现（正）

### 目标

把 (3d) 的接线证据与 (3e) 的"前提成立可工作"证据**合拢到同一个 PVS 六自由度闭环**里——不再另起轻量外壳，而是直接把满足磁观测前提的产磁几何迁回 PVS，闭合剩余项 (a1)/(a2)。

### (a1)/(a2) 的两处修复

**(a1) 产磁几何迁回车体下方**：[bridge_params.protocol_udp.pvs.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/config/bridge_params.protocol_udp.pvs.yaml) 把真值直缆布置于磁传感器下方、垂直分离 `d≈7.5 m`，使 `B_perp=By` 主导、恢复 `y=(B_down/B_perp)·d` 直线埋缆前提。

**(a2) PVS 车体位形响应**（修复 (3d) 附注的 Y/yaw≡0.0）：`pvs:` 段加运动学 setpoint 模型，实现见 [pvs_sim_wrapper.py](file:///home/auv_user/auv_ws/AUV-Master-Project/sim_holoocean/interfaces/pvs_sim_wrapper.py) 的 `_step_kinematic_autonomy()`：

```yaml
pvs:
  autonomy_motion_model: kinematic_setpoint
  kinematic_max_yaw_rate_deg_s: 12.0
  kinematic_depth_time_constant_s: 4.0
```

### 命令

与 §5.5.10 clean fresh run **完全一致**的 PVS 配方，mid/heavy 各 3 次真闭环 fresh run：

```bash
bash scripts/run_cable_closedloop_distorted.sh
# recovery-gate 两阶段评分 + 聚合：
bash scripts/score_cable_closedloop_recovery_runs.sh
```

recovery-gate 口径（起始注入偏差需一段恢复过程才进廊道）：第一阶段恢复段（连续 20 帧落入 3.4 m 廊道且 burial-ready 之前）不计入巡检证据；第二阶段从恢复门起、50 m 巡检窗口内、burial-ready，再套正常巡检廊道与验收阈值。

### (3f-i) 在线修正在 PVS 闭环中被真实接受（与 (3d) 直接对照）

迁回满足前提的产磁几何后，磁导出横偏观测**不再被残差门拒绝**：

| 诊断量 | (3f) 迁回后 | (3d) 近共面时 |
|---|---|---|
| `prior_alignment_observed/accepted` | ≈1200/1220 帧（接受率约 98%） | 观测 1204、接受 0 |
| `reason_code` | 1（ACCEPTED） | 2（RESIDUAL_TOO_LARGE） |
| `vertical_separation_m` 中位 | 7.53 m | ≈0 |
| `translation_norm` 峰值 | 5.8–9.1 m | ≡0 |
| heavy run1 观测横偏 vs 真值 | −2.22 m vs −2.15 m（逐帧吻合） | 被放大 4–5 倍到约 −40 m |

这直接证明 (3d) 负结果**根因确为产磁几何违反观测前提、而非接线/EKF bug**：一旦缆回到车下，同一套已接线的在线修正立即被接受。

### (3f-ii) 闭环恢复被首次复现（与 (3b)/(3c) 开环冻结直接对照）

heavy 起始横偏约 −10.25 m（distorted prior 注入），在线修正被接受后横偏在约 12 s 内收敛进 ±3.4 m 验收廊道并全程保持，全程 `|heading_correction_deg|>1°` 占 1112/1219 帧——即车辆被真实重新操舵去贴合**修正后**的先验，而非 (3b)/(3c) 中横偏被冻结在开环几何差上单调累积。

同源对照：在线修正**关闭**的 6 个 baseline run（`*_prioroff`）mid/heavy 全程 `max_route_offset` 约 15.3/20.1 m、窗口内点数为 0、0/3 invalid，与 (3c) 逐位重合。

![PVS 六自由度闭环 distorted-prior 恢复与在线先验修正接受时序](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/figures/cable_acceptance/pvs_closedloop_recovery_prior_alignment.png)

### (3f-iii) mid/heavy 各 3/3 达到 ready/pass

在验收窗口内两档全部 6 个 run 均通过工业验收，聚合 `preliminary_acceptance_ready=True`（数据源 [_agg_mid_recovery](file:///home/auv_user/auv_ws/AUV-Master-Project/results/cable_ops_report/closedloop_e2e/_agg_mid_recovery/acceptance_runs_summary.json)/[_agg_heavy_recovery](file:///home/auv_user/auv_ws/AUV-Master-Project/results/cable_ops_report/closedloop_e2e/_agg_heavy_recovery/acceptance_runs_summary.json)）：

| tier（PVS 闭环 + 在线修正 ON） | run ready/pass | 窗口内点数（min–max） | max route offset（worst, m） | mean route offset（worst, m） | valid_burial_ratio | conf_p05（min） | 聚合 ready |
|---|---|---:|---:|---:|---:|---:|---|
| mid `t0=(0,7.5)m/θ0=3.0°/S=(0.99,1.0)` | 3/3 | 328–1029 | 3.395（阈 3.4） | 2.412（阈 2.5） | 1.000 | 0.902 | **True** |
| heavy `t0=(0,10.0)m/θ0=5.0°/S=(0.98,1.0)` | 3/3 | 320–725 | 3.394（阈 3.4） | 2.318（阈 2.5） | 1.000 | 0.902 | **True** |

### (3f-iv) 达标是"物理/控制修正"而非"放宽阈值"

动力学迁回 PVS 后，首轮 full run 并未整体通过（mid 2/3、heavy 1/3），两类失败根因均在物理/控制层修正而非放宽阈值：

- **heavy `burial_sigma_over_limit`**：低磁强（250–350 nT）在标定幅度模型 `slant_range=K·I_rms/B` 下反推出 90–140 m 伪深埋，污染 IQR sigma。修复是在 [burial_inversion.py](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/src/auv_mag_tracking/perception/burial_inversion.py) 新增 `burial_max_depth_m` 物理门控（distorted 配置设 10 m），修复后 6 run `valid_burial_ratio=1.0`、`sigma_over=0`（回归测试 15 passed）。
- **mid 样本不足与 `mean_route_offset` 越限**：源自 `zigzag_limits.auto_limit` 与 PVS 目标航向语义不匹配的振荡与摆幅过大。修复是关闭 `auto_limit`、`zigzag_probe.lateral_amplitude_m` 从 1.0 降到 0.6、`track_cross_track_gain_deg_per_m` 取 3.5。
- **corridor 敏感性**：取满足样本充足与三项指标同时达标的**较小**值 3.4 m（不放到 5 m），并缩短 heavy burial fusion 窗口（`burial_min_samples 20→10`、`window 30→15`）。

![PVS 闭环 distorted-prior 验收收敛：首轮 2/3,1/3 → 末轮 3/3,3/3](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/figures/cable_acceptance/pvs_closedloop_acceptance_convergence.png)

---

## 7. 诚实边界（必须与 (3f) 结论同时保留）

- **(3f) 是新增/抬升，不覆盖也不改写 (3d)/(3e)**：(3d) 记录的"当时 PVS 产磁几何不满足前提→100% 拒绝"仍是真实历史，(3e) 的 Direction A 解耦闭环仍是独立证据。
- **(3f) 的达标限定在**：数字孪生确定性电缆先验（非真实检测噪声）、人工注入的静态位姿扭曲（未含旋转慢漂/导航漂移动态通道）、缆布置于车体下方满足直线埋缆观测前提（真机磁场须先去地磁背景/去噪才能满足）、有效巡检窗口内判定（全程含末段离窗漂移仍为 `limited`，如 heavy run3 全程 `max_route_offset=10.26 m`）、n=3/档。
- **不得**写成"通过真实海缆检测精度验收"或"距离实物验收已无缺口"。
- **仍未闭合的现场证据**（(3d) 遗留的 PVS 场景观测前提 (a1) 与车体位形响应 (a2) 已由 (3f) 闭合）：(b) 真实检测噪声；(c) 多种子统计（当前 n=3/档）；(d) 硬件实物（Jetson+AMD+磁传感器+水池/外场）。

---

## 8. 关键引用

- 论文正文结论：[docs/thesis/paper/05_experiments_and_discussion.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/05_experiments_and_discussion.md) §5.5.11（(3b)–(3f)）
- 专项计划与改动登记：[docs/thesis/paper/e2e_distorted_prior_next_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/e2e_distorted_prior_next_plan.md) §4.1/§4.2/§4.3/§5
- 部署 I/O 契约（(3f) 复现命令）：[docs/real_deployment/08_cable_inspection_io_contract.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/real_deployment/08_cable_inspection_io_contract.md) §6
- 孪生输出字段与 recovery-gate 评分：[docs/real_deployment/09_dlt1278_digital_twin_outputs.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/real_deployment/09_dlt1278_digital_twin_outputs.md) §3/§5
- 集成原理（暗线）：[docs/internals/12_cable_tracking_mag_integration.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/internals/12_cable_tracking_mag_integration.md)
