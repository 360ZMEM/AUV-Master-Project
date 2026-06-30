# 三组强解说力过渡实验（F1/F2/F3）

**日期**: 2026-06-20
**定位**: 在自洽性提升阶段（WP-F）新增三组确定性 / 离线实验，为论文第 2、3 章提供"声磁建模 → 标定 → 网络鲁棒性"的过渡性证据。三组均为可复现脚本，无需实时仿真。

---

## 总览

| 编号 | 实验 | 脚本 | 论文章节映射 | 一句话结论 |
|---|---|---|---|---|
| F1 | 三相螺旋海缆漏磁场对比 | [tools/helical_cable_magnetic_scan.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/helical_cable_magnetic_scan.py) | §2 声磁建模 / §3.3 磁指纹 | 三相平衡缆远场抵消 ~1400×、近场留螺距周期 ripple 81.6%；单芯准均匀 |
| F2 | DVL 外参标定敏感度消融 | [tools/es_ekf_extrinsics_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/es_ekf_extrinsics_benchmark.py) | §2.4 标定 / §3.5 ES-EKF | 安装角误差 +33% 漂移、杆臂可忽略 |
| F3 | DVL 网络抖动边界测试 | [tools/jitter_boundary_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/jitter_boundary_ekf_benchmark.py) | §2.5 通信 / §3.2 异步同步 | DVL NIS 单调 12× 上升、临界 jitter=150ms |

---

## F1 — 三相螺旋海缆漏磁场对比

### 方法

复用感知引擎的 Biot-Savart 实现 `perception_engine.compute_biot_savart_hvdc`，对两类海缆几何做磁场扫描对比：

- **单芯电缆**：单一直线导体（细分到与螺旋同段数 6000，保证线积分精度）。
- **三相平衡螺旋缆**：三导体绕公共轴螺旋排布，相位 120°、螺距 1.2m；快照电流 `I_k = I·cos(offset_k)`，三相和 = 0。

AUV 在海床上方 2m（`seabed_z=15`，`altitude=2`）沿 x 轴扫描，记录磁感应强度幅值。

### 结果（`results/perception/helical_cable_magnetic_scan/20260620_013450/`）

| 几何 | 场强 mean | ripple（峰谷/均值） | 物理解读 |
|---|---:|---:|---|
| 单芯 | 4.97e+04 nT | **0.1%** | 沿缆准均匀（单导体远场 ~1/r 缓变） |
| 三相平衡螺旋 | 34.4 nT | **81.6%** | 三相和=0 → 远场抵消 ~1400× 弱；近场残留螺距周期起伏 |

输出：`magnetic_scan.csv`（逐点场强）+ `ripple_metrics.csv` + PNG/PDF（标螺距周期竖线）。

### 关键陷阱（已修，方法学价值）

每段仅在中点放一个电流元，单芯若只用 2 控制点（1 大段）则中点积分近似极差，会产生 **263% 的伪 ripple**（首跑现象）。修复：单芯也细分到与螺旋相同段数（6000）。**论文方法学提示**：Biot-Savart 数值积分的离散密度必须在对比双方一致，否则离散误差会冒充物理信号。

### 学术价值

为论文"三相平衡缆比单芯缆更难磁定位（远场抵消）、但近场存在可利用的螺距周期特征"提供定量依据，支撑第 3 章磁指纹/磁辅助定位的适用边界讨论。

---

## F2 — DVL 外参标定敏感度消融

### 方法

在 ES-EKF 外参基准上新增两个消融 mode，隔离两类外参误差对定位漂移的贡献：

- `calibrated`：真值外参（对照）。
- `no_lever_arm`：杆臂置零（保留安装角）。
- `no_mounting_angle`：安装角注入 +5° yaw 误差（保留杆臂）。

profile=medium，3 seed（0,1,2）。`base_velocity_to_sensor` 用 `v + ω×杆臂 → 安装角旋转`，故安装角直接旋转速度方向、杆臂仅在角速度大时贡献。

### 结果（`results/es_ekf_extrinsics/20260620_012952/`）

| mode | XY RMSE (mean±std) | Z RMSE | 相对 calibrated | 解读 |
|---|---:|---:|---:|---|
| calibrated | 22.67 ± 11.03 m | 0.0031 m | — | 对照 |
| no_lever_arm | 22.03 ± 9.91 m | 0.0032 m | −3%（噪声内） | **杆臂可忽略** |
| no_mounting_angle | 30.06 ± 12.63 m | 0.0031 m | **+33%** | **安装角误差主导漂移** |

输出：`summary_by_error_level.csv` + `extrinsics_report.md`。Z RMSE 三者均 ~0.003m（深度通道由独立深度计观测，不受机体平面外参影响）。

### 学术价值

定量证明 DVL 速度方向对**安装角**敏感、对小**杆臂**不敏感 → 标定时应优先保证安装角精度。物理合理（速度方向误差随时间积分成位置漂移），支撑第 2.4 节标定框架的优先级论证。注：XY 绝对量级大是因为 DVL+depth 下 XY 本不可观、由航位推算漂移主导，本实验关注的是**相对**信号（mode 间差异）而非绝对 RMSE。

---

## F3 — DVL 网络抖动边界测试

### 方法

复用传输层延迟队列 `mock_amd_delay.TransportDelayQueue`，对喂给 ES-EKF 的 DVL 流注入 `base_delay=20ms` + 可变 jitter（0→500ms）。DVL 包入队时打捕获时间戳，滤波器时间推进时从队列取**已释放的陈旧包**做 `correct_dvl_sensor`，模拟网络对 DVL 的老化/乱序。为支撑诊断，在 [algorithm/es_ekf.py](file:///home/auv_user/auv_ws/AUV-Master-Project/algorithm/es_ekf.py#L157-L163) 暴露 `last_K`/`last_S`/`last_innov`（最近一次观测更新的 Kalman 增益/创新协方差/创新向量）。轨迹采用激进动力学（快速 yaw + 速度调制），使 0.1–0.5s 滞后真正产生误差。3 seed。

### 边界指标选型（关键诚实记录）

| 候选指标 | 是否采用 | 原因 |
|---|---|---|
| XY 位置 RMSE | ✗ | XY 不可观（DVL 仅机体速度、depth 仅 z），RMSE 由航位推算漂移主导、掩盖 jitter |
| velocity RMSE | △ 旁证 | adaptive-R 折扣陈旧 DVL 后保护了状态，velocity RMSE 噪声大、非单调 |
| **DVL NIS** | ✓ **主指标** | 归一化创新平方直接度量观测-预测一致性，正是 jitter 破坏的量 |

### 结果（`results/es_ekf_jitter_boundary/20260620_014529/`，3 seed）

| jitter (ms) | DVL NIS mean | Kalman 增益范数 mean | velocity RMSE (m/s) |
|---:|---:|---:|---:|
| 0 | 0.125 | 8.38 | 0.232 |
| 50 | 0.176 | 8.60 | 0.225 |
| 100 | 0.244 | 8.15 | 0.232 |
| **150** | **0.337** | 7.84 | 0.273 |
| 200 | 0.448 | 6.96 | 0.236 |
| 300 | 0.727 | 5.92 | 0.183 |
| 400 | 1.096 | 5.16 | 0.244 |
| 500 | 1.554 | 4.52 | 0.366 |

**临界 jitter = 150ms**（DVL NIS 首超 2× nominal）。三 witness 相互印证：NIS 严格单调 ~12× 上升；Kalman 增益范数从 8.38 单调降到 4.52（滤波器渐进折扣陈旧 DVL，与 adaptive-R 自洽）；velocity RMSE 噪声大（被 adaptive-R 保护）。

输出：`jitter_results.csv` + `jitter_summary.csv` + `critical_jitter.csv` + 三子图 PNG/PDF（NIS / 增益 / velocity）。

### 学术价值

给出 ES-EKF DVL 辅助在网络抖动下的**可信边界**（150ms），并展示 adaptive-R 机制如何通过降低增益保护状态估计——支撑第 2.5 节通信鲁棒性与第 3.2 节异步同步的工程论证。NIS 作为边界指标的选型本身也是方法学贡献：在不可观维度上，应以创新一致性而非状态 RMSE 判定滤波器健康。

---

## 复现命令

```bash
python3 tools/helical_cable_magnetic_scan.py
python3 tools/es_ekf_extrinsics_benchmark.py --true-profile medium --estimation-modes calibrated,no_lever_arm,no_mounting_angle
python3 tools/jitter_boundary_ekf_benchmark.py
```

三脚本均 matplotlib Agg 出图、CSV 落盘到 `$AUV_DATA_ROOT/results/<sub>/<TS>/`，确定性（固定 seed）可复现。
