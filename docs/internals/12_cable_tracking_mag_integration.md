# 电缆跟踪磁探测集成

## 边界划分

主仓库负责车辆安全、仲裁、通信传输、控制器执行、仿真管线和可视化。`AUV-Master-Mag` 负责电缆感知、电缆跟踪状态、route progress、埋深估计和 guidance intent。

## 运行时流程

1. `cable_tracking_node.py` 加载 `brain_linux/config/cable_tracking.yaml`。
2. `cable_prior_adapter.py` 通过 `AUV-Master-Mag.api.CableMap` 加载 CSV、GeoJSON 或 YAML 先验。
3. ROS2 导航和磁场消息转换为 `NavigationInput` 与 `MagneticInput`。
4. `AuvMagTrackingPipeline.step_with_guidance()` 返回 tracking 和 guidance。
5. `cable_guidance_limits.py` 将命令限制在配置的车辆运动包线内。
6. 节点发布 `/auv/control/setpoint`；下层链路保持不变。

## 真值边界

仿真真值字段仍可用于评估和 Foxglove 叠加显示，但在线电缆跟踪不得消费 `ground_truth.cable_closest_ned` 或 `ground_truth.cable_distance_m`。

---

## 在线先验修正（distorted-prior 恢复的核心机制）

上文第 4 步的默认行为是把车辆位置投影到**先验航线**巡检。真实海缆图纸必带系统性平移/旋转/缩放误差，先验一旦被扭曲，车辆会被忠实操舵去贴合**被扭曲的**航线，相对真值电缆的横偏不会被吸收——这是 §5.5.11 (3c)/(3d) 记录的失效通道。在线先验修正就是为闭合这个缺口引入的可选路径，默认**关闭**。

### 为什么需要一个独立于先验的观测

在线修正的估计器 `PriorAlignmentEstimator.update()` 需要一个**独立于先验投影**的横偏观测 `observed_point_xy`。若观测本身也来自"投影到先验"，则误差自洽、无法纠正先验偏差。闭环 ROS 节点不订阅 sonar（`SonarInput` 虽 import 但从不喂入），`source` 恒为 `map_projection`，因此需要另找一个独立观测源。

### 磁导出横偏观测（Path A）

仿真两端的磁场 `B_ned` 均由 `compute_biot_savart_hvdc` 从**真值电缆几何**算出（电缆专有场、无地磁背景）。以电缆走向为参考，把磁异常向量分解为电缆垂直水平分量 `B_perp` 与竖直分量 `B_down`，同一线电流驱动两者、比值消去电流，满足无限长直线模型反演带符号横偏：

```text
y = (B_down / B_perp) · d
```

其中 `d` = 车体到电缆的垂直分离 = 航高 + 标称埋深。反演出的 `y_mag` 由 `nav_xy + y_mag·normal` 构造出独立于先验投影的 `observed_point_xy`，喂 `PriorAlignmentEstimator` 累积平移/旋转修正，再用 `apply_route_prior_pose_error` 重建投影 cache，使后续横偏/操舵基于**修正后**的先验。相关组件：

- `MagneticCrossTrackEstimator`（TLS 主轴 + 质量门控），`AUV-Master-Mag/src/auv_mag_tracking/perception/cross_track.py`。
- `PriorAlignmentEstimator`（累积平移/旋转 EKF），残差门 `max_residual_m=18.0 m`。
- 启用开关 `DeploymentPerceptionConfig.enable_online_prior_alignment`（默认 `False`），主仓 `cable_tracking.yaml` 的 `quality` 段透传。

### 观测前提（成败的分水岭）

直线埋缆反演模型要求缆位于**车体下方一定埋深**，使 `B_perp=By` 主导。这是 (3d)→(3f) 一负一正的根因：

- **前提不成立（(3d)）**：当 PVS 产磁电缆与车辆近乎同深（`Bz` 主导，`Bz/By≈−5`），反演横偏被系统性放大约 4–5 倍（约 −40 m vs 真值 −10 m），EKF 残差门正确拒绝全部越界观测（`reason_code=2`，`translation_norm≡0`）。这是**观测源前提不成立**，不是接线或 EKF bug。
- **前提成立（(3f)）**：把产磁几何迁回车体下方 `d≈7.5 m`（By 主导）后，同一套已接线的在线修正立即被接受（约 98% 帧、`reason_code=1`、`vsep` 中位 7.53 m、`translation_norm` 峰值 5.8–9.1 m），闭环恢复被首次复现。

### 诊断字段

在线修正的关键诊断暴露在 `/auv/cable/tracking` JSON 与 `/auv/cable/diagnostics`：

| 字段 | 含义 |
|---|---|
| `prior_alignment_observed` | 磁观测是否被激励 |
| `prior_alignment_accepted` | 观测是否被 EKF 接受 |
| `reason_code` | 1=ACCEPTED，2=RESIDUAL_TOO_LARGE |
| `prior_alignment_vertical_separation_m` | 垂直分离 `d` |
| `cross_track_quality` | 横偏拟合质量（门限 0.35） |
| `translation_norm` | 累积平移修正量 |

---

## PVS 六自由度闭环恢复（(3f) 的位形响应链）

要在 PVS 六自由度闭环里真正复现"横偏被吸收"，除了在线修正被接受，还需要**车体对横向/艏向设定值产生真实位形响应**。(3d) 附注曾发现 PVS mock 车体的 Y/yaw 全程恒为 0.0——仅沿 +x 前进，制导层虽发布非平凡 `target_heading_rad`，车体位形却不响应。该缺口由运动学 setpoint 模型修复（详见 [02_pvs_backend.md](02_pvs_backend.md) 的第三种控制路径 `kinematic_setpoint`，实现于 `pvs_sim_wrapper.py` 的 `_step_kinematic_autonomy()`）：

```yaml
pvs:
  autonomy_motion_model: kinematic_setpoint
  kinematic_max_yaw_rate_deg_s: 12.0
  kinematic_depth_time_constant_s: 4.0
```

启用后，heavy 起始横偏约 −10.25 m 在约 12 s 内收敛进 ±3.4 m 廊道并保持，全程 `|heading_correction_deg|>1°` 占 1112/1219 帧——即车体被真实横向操舵去贴合修正后的先验，而非 (3b)/(3c) 中冻结在开环几何差上。

---

## DL/T 1278 recovery-gate 两阶段评分

distorted-prior 起始横偏被人工注入（heavy 约 −10.25 m），车辆需一段恢复过程才进廊道。若用普通 start-health 口径，起始段会直接把整 run 判为 `invalid`。因此 distorted-prior 评分改用 recovery-gate 两阶段口径：

- **第一阶段（恢复段）**：从起点到恢复门（连续 20 帧落入 3.4 m 廊道且 burial-ready）之间的样本不计入巡检证据。
- **第二阶段（巡检段）**：从恢复门起、50 m 巡检窗口内、burial-ready，再套正常巡检廊道与验收阈值。

该口径**不放宽物理阈值**（corridor 取较小值 3.4 m，不放到 5 m），只是把"恢复过程"与"稳定巡检"分成两段计分，避免起始注入偏差污染巡检段证据。字段/参数详见 [09_dlt1278_digital_twin_outputs.md](../real_deployment/09_dlt1278_digital_twin_outputs.md) §3。

---

## 命令契约（(3f) 正向结果复现）

fresh 闭环 run（mid/heavy 各 3 次）+ recovery-gate 评分聚合：

```bash
bash scripts/run_cable_closedloop_distorted.sh
bash scripts/score_cable_closedloop_recovery_runs.sh
```

产物：`results/cable_ops_report/closedloop_e2e/_agg_{mid,heavy}_recovery/acceptance_runs_summary.json`（两档聚合 `preliminary_acceptance_ready=true`，mid/heavy 各 3/3 ready/pass）。

完整命令契约与部署边界见 [08_cable_inspection_io_contract.md](../real_deployment/08_cable_inspection_io_contract.md) §6；从负结果到正结果的探索历史见 [cable_distorted_prior_closedloop_20260707.md](../experiment/cable_distorted_prior_closedloop_20260707.md)。

---

## 诚实边界

- 磁导出横偏基于**无限长直线模型 + 已知电缆走向**假设，弯段/远离段模型失真，靠 TLS 质量门控 gate 出；标称 ~1m 级精度。
- `d`（垂直分离）用航高 + 标称埋深近似，埋深误差直接进入横偏标度。
- 仿真磁场为电缆专有场、无地磁背景与检测噪声；真机须先去背景/去噪，边界如实标注。
- (3f) 达标限定在数字孪生确定性先验、静态位姿扭曲、缆在车下满足前提、窗口内判定、n=3/档，**不得**写成"通过真实海缆检测精度验收"。
