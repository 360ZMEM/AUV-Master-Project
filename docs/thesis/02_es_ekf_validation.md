# T3 — ES-EKF 验证（论文 §3.4 / §5.4）

> **对应论文章节**：§3.4 ES-EKF 设计；§5.4 EKF 算法可行性验证
> **直接消费方**：论文 §3.4 公式与 §5.4 表 5-1 / 图 5-X
> **生成时机**：Phase 4 — A 档骨架 + Phase 1 既有 n=1 实证 + 多 seed 待补

---

## 1. 算法对象与状态变量

实现：[algorithm/es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py)（顶层类 ESEKF，[L109 `__init__`](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L109)）。

### 1.1 状态向量（15 维误差状态）

| 索引 | 子向量 | 含义 |
| --- | --- | --- |
| 0–2 | `δp` | 位置误差 (NED, m) |
| 3–5 | `δv` | 速度误差 (NED, m/s) |
| 6–8 | `δθ` | 姿态误差（旋转向量，rad） |
| 9–11 | `b_a` | 加速度计零偏 (m/s²) |
| 12–14 | `b_g` | 陀螺仪零偏 (rad/s) |

**名义状态**：`(p, v, q, b_a, b_g)`，q 为单位四元数（[L31 `quat_to_rotmat`](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L31)，[L19 `quat_multiply`](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L19)）。论文 §3.4 公式 3-1 ~ 3-5 与代码一一对应。

### 1.2 协方差 P (15×15)

每周期 `predict` 内由 [L329 `predict`](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L329) 推进：`P = F P F^T + G Q G^T`。NED 系下取 `R(q)` 把 body 加速度旋至导航坐标。

---

## 2. 量测通道

| 通道 | 入口符号 | 频率（典型） | 噪声特性 |
| --- | --- | --- | --- |
| DVL（body 系） | [L430 `correct_dvl`](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L430) | 50 Hz | 高斯，受丢包扰动 |
| DVL（world 系） | [L441 `correct_dvl_world`](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L441) | — | 离线复算用 |
| DVL + timestamp | [L450 `correct_dvl_with_timestamp`](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L450) | — | 时间一致性版本 |
| Depth (压力) | [L479 `correct_depth`](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L479) | 20 Hz | 单维高斯 |
| GPS XY (水面) | [L488 `correct_gps`](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L488) | 1–5 Hz | 仅水面 |
| Mag (3 轴) | [L497 `correct_mag`](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L497) | 10 Hz | 易饱和（拖缆电流） |

`correct_mag` 实现于 Phase 2 E1（[thesis_experiment_phase2_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/.trae/documents/thesis_experiment_phase2_plan.md)）。论文 §3.4.2 描述磁观测最小钩。

---

## 3. 自适应 R + NIS 监测

实现位于 [es_ekf.py L138-L145, L376-L415](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py)（Phase 2 E2）。

- **NIS（归一化新息平方）滑动窗口**：`get_nis_stats` ([L417](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L417)) 返回 mean / 95-CI / chi2 阈值。
- **自适应规则**：当窗口 NIS mean 超过 χ² 阈值时，按比例放大 R 矩阵；低于阈值时缓慢回归到先验。
- **窗口长度**：默认 N=50；详见 [07_drift_log_and_known_issues.md D1.4](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md)。

> 论文 §3.5 要求图：NIS 时序 + χ² 阈值带 + 自适应 R 触发标记，由 [tools/offline_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py) `innovation_residual.png` 提供素材。

---

## 4. 验证矩阵（论文 §5.4 表 5-1 + 鲁棒性）

| 实验 | 输入 | 期望产物 | 状态 |
| --- | --- | --- | --- |
| baseline n=1 | `scenario_baseline.yaml` + seed 0 rosbag | XY/Z RMSE / CEP50 / Max Drift；4 张 PNG | ✅ Phase 1（[benchmark_test_log.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/experiment/benchmark_test_log.md)） |
| baseline n=5 | seeds 0..4 | 同上 mean±std | ⏳ pending（D4.1） |
| dvl_dropout 系列 | dvl_dropout_{10,30,60,90} × seeds 0..4 | RMSE-vs-drop_rate 曲线 | ⏳ pending |
| mag_distortion 系列 | mag_distortion_{light,heavy} × seeds 0..4 | NIS 时序 + 自适应 R 触发率 | ⏳ pending |
| sonar_clutter | × seeds 0..4 | 声呐通道 NIS 影响 | ⏳ pending |
| 传感器外参/杆臂 | `light/medium/heavy` × `none/calibrated/calibrated_from_yaml/online_lite` | 外参误差敏感性、标定收益、online-lite 边界 | ✅ 纯脚本 smoke，PVS 场景已接入 |
| 单元测试 | 静态四元数运算 | 全部通过 | ✅（与 Phase 1 一致） |

---

## 5. 复现命令

### 5.1 离线复算（用现有 mcap）

```bash
python3 tools/offline_ekf_benchmark.py \
  --input log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap \
  --output-dir results/localization/ekf_validation_baseline \
  --verbose
```

### 5.2 多场景多种子（pending）

```bash
python3 tools/run_thesis_sweep.py \
  --scenarios baseline,dvl_dropout_30,dvl_dropout_60,mag_distortion_heavy \
  --seeds 0,1,2,3,4 \
  --mpc-modes ua \
  --output-root /auv_data/sweeps/ekf_validation
```

> 产物聚合见 [run_thesis_sweep.py write_sensitivity_summary L534](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py#L534)。

---

## 6. 已确认数据（n=1，源自 Phase 1）

| 算法 | XY RMSE (m) | Z RMSE (m) | CEP50 (m) | Max Drift (m) |
| --- | --- | --- | --- | --- |
| Raw DR | 4.305 | 0.030 | 4.062 | 6.557 |
| Std EKF | 4.378 | 0.005 | 4.106 | 6.703 |
| ES-EKF | 4.375 | 0.005 | 4.102 | 6.697 |

> 数据语境见 [01_baseline_repro_log.md §3.1](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/01_baseline_repro_log.md)。当前 baseline 中 EKF 不显著优于 DR 的根因（D1.1 已修后仍存在的 ground-truth 偏移）见 [07_drift_log_and_known_issues.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/07_drift_log_and_known_issues.md)。

---

## 7. 论文 §3.4 公式 ↔ 代码符号对照

| 公式 | 论文符号 | 代码符号（[es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py)） | 行号 |
| --- | --- | --- | --- |
| 名义运动学 (3-1) | `p̂ ← p̂ + v̂ Δt` | `self.p = self.p + self.v * dt` | L329 起 |
| 速度更新 (3-2) | `v̂ ← v̂ + (R(q̂)(a_m - b_a) + g) Δt` | predict 内 a_world 行 | L329 起 |
| 姿态更新 (3-3) | `q̂ ← q̂ ⊗ exp(½(ω_m - b_g) Δt)` | `quat_multiply` | L19 + L329 |
| 误差状态预测 (3-6) | `δx̂ = F δx + G η` | `F`, `G` 装配段 | L329 起 |
| DVL 更新 (3-9) | `H = [0, R(q̂)^T, ...]` | `correct_dvl` 内 H 装配 | L430 |
| 自适应 R | `R_t = max(R_0, k · S̄)` | `_adapt_R` / `get_nis_stats` | L138, L376, L417 |
| 注入更新 | `q̂ ← q̂ ⊗ exp(½ δθ)` + `quat_normalize` | post-update 段 | L376–L415 |

## 7.1 杆臂与传感器外参补充验证

第一阶段已加入统一外参模块 `common/sensor_extrinsics.py`，并在 ES-EKF 中新增 sensor-frame DVL 与 depth sensor 观测接口。外参使用两套语义：

- `sensor_extrinsics_truth`：仿真侧生成错位观测。
- `ekf.sensor_extrinsics`：滤波器侧估计外参，用于观测改正。

纯脚本 smoke 当前结果显示，`light` 外参 profile 下，oracle `calibrated` 和标定 YAML `calibrated_from_yaml` 均优于 `none`。关键结果：

| 数据源 | mode | XY RMSE | Z RMSE | 3D RMSE / 改善 |
| --- | --- | ---: | ---: | ---: |
| pure-script smoke | none | 2.2571m | 0.0495m | 2.2576m |
| pure-script smoke | calibrated | 2.1947m | 0.0030m | 2.1947m |
| pure-script calibration | calibrated_from_yaml | 8.2549m | 0.0037m | 相对 none 改善 1.2390% |

PVS 侧已完成 `extrinsics_light/medium/heavy` smoke 和低样本 sweep。`log/thesis_sweep/20260613_163259_extrinsics_main_3seed/results.csv` 当前为 `6/9 ok`，每个 profile 的 seed0/1 可用，seed2 的 MCAP 损坏导致 offline benchmark 失败。聚合报告见 `results/thesis_sweep_aggregates/20260613_163259_extrinsics_main_3seed/aggregate_report.md`：

| scenario | ok/total | XY RMSE mean±std | Z RMSE mean±std | CEP50 mean±std |
| --- | ---: | ---: | ---: | ---: |
| extrinsics_light | 2/3 | 1.6145±0.7304m | 0.3360±0.4384m | 1.6625±0.7969m |
| extrinsics_medium | 2/3 | 1.5480±0.7920m | 0.5145±0.0714m | 1.6485±0.7220m |
| extrinsics_heavy | 2/3 | 1.9330±0.3055m | 0.6345±0.1549m | 2.0415±0.2411m |

这支撑一个有限结论：外参改正进入观测模型后能恢复一部分 ES-EKF 性能，PVS 后端也能注入传感器错位并产出可评估 bag；但 PVS 当前只是 `2/3` 可用的补充证据，不应写成完整 3-seed 统计。`online_lite` 当前仍带有 oracle 上限评估含义，不能写成完整在线标定。

---

## 8. 与论文图 5-X 的对应

| 论文图 | 来源 PNG | 备注 |
| --- | --- | --- |
| 轨迹 XY 对比 | `trajectory_xy.png` | DR / Std-EKF / ES-EKF 三线 |
| XY 误差时序 | `error_time.png` | 含 1-σ 包络 |
| XYZ 分量误差 | `error_components.png` | 论文 supplementary |
| 新息/残差 + NIS | `innovation_residual.png` | 含 χ² 阈值带 |

> 当前 4 张图源自 baseline n=1。多场景对比图需 §4 sweep 完成后由聚合脚本绘制。

---

## Pre-Snapshot @ Phase 4 A6

- ES-EKF 类完整（15 维误差状态 + 6 通道观测）
- 自适应 R + NIS（Phase 2 E2）
- mag 通道（Phase 2 E1）
- 离线复算工具就位（[offline_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py)）
- baseline n=1 数据完整

## Post-Snapshot @ Phase 4

待 P2（TaskList #32）补全多场景多种子聚合数据。
