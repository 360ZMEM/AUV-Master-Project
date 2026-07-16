# 答辩 PPT 图素材清单（自包含 · 复用现有正文图表）

**日期**: 2026-08-20  
**定位**: 27 号文 P2「答辩 PPT 图素材」。**纯复用**已入正文的图与表，不重跑仿真、不改任何实验配置。  
**用法**: 每个"叙事节点"给出——① PPT 直接引用的图（**PNG 优先**，可直接拖入幻灯片）② 配套数据表（正文 label）③ 可粘贴的一句话 caption ④ 诚实"so what"（讲清楚它证明了什么、边界在哪）。  
**图目录根**: `docs/thesis/figures/`（PPT 拖图时在此目录下按下方相对路径取 `.png`）。  
**权威事实源**: `thuthesis/data/auv-chap0*.tex`（正文为唯一权威，本清单数值均取自正文/摘要）。

> **总原则（对齐用户写作偏好）**：视觉重心（Hero/Focus）每页一张主图；诚实边界随图注同屏；"先定义后引用"——先给任务与指标定义页，再给结果页。所有数值只写实跑结果，单次（n=1）与多种子（n≥3）严格区分。

---

## 0. 建议的答辩叙事线（12–14 页主线，图随页走）

| 页 | 主题 | Hero 图 | 支撑表 |
|---|---|---|---|
| P1 | 任务与技术路线 | `fig:ch01-technical-route`（技术路线图） | §1.4 三主线文字 |
| P2 | 仿真验证体系与指标定义 | 场景库示意 | `tab:ch05-scenarios`、`tab:ch05-evidence-inventory` |
| P3 | 主线一：声磁协同状态估计（鲁棒性） | `eskf_param_sensitivity.png` | `tab:ch05-eskf-robustness` |
| P4 | 主线一：不确定性量化与一致性校准 | （NIS A/B 数值页） | `tab:ch05-nis-covariance-ab` |
| P5 | 主线一：磁探测联合实验 | `complex_iq_fit.png` + `trajectory_colored_by_b.png` | `tab:ch05-mag-calibration` |
| P6 | 磁外参仿真标定 | `01_mag_extrinsics_residual.png` | `tab:ch05-mag-calibration` |
| P7 | 主线三：近底地形跟随（空间直觉 Hero） | `terrain_3d_pid_terrain_trajectory.png` | `tab:ch05-terrain-main` |
| P8 | 地形跟随多种子稳健性 | `terrain_tz_tracking_pid_mpc.png` | `tab:ch05-terrain-ablation` |
| P9 | 主线二：不确定性感知控制（UA-MPC） | `r13_v2_authority_modes_ua.png` | `tab:ch05-uampc-control` |
| P10 | UA-MPC 控制平滑（配对对比） | `r13_v2_control_rate_paired.png` | `tab:ch05-r13-v2-main-results` |
| P11 | 电缆巡检闭环验收 | `pvs_closedloop_acceptance_convergence.png` | `tab:ch05-closed-loop-acceptance` |
| P12 | 先验畸变下的重定位恢复 | `pvs_closedloop_recovery_prior_alignment.png` | `tab:ch05-distorted-prior` |
| P13 | 行业指标对齐验收单 | `cable_dlt1278_scorecard_fresh1.png` | 标准对齐表 |
| P14 | 边界与剩余验证（诚实收口） | 硬件 ENOB 两图 + `mag_chain_noise_ros_comparison.png` | `tab:ch05-negative-results`、`tab:ch05-mag-chain-noise-ros` |

---

## 1. 主线一：声磁协同状态估计与不确定性量化

### 1.1 ES-EKF 多扰动鲁棒性（主结果，n=24）
- **图（PPT）**: `experiments/state_estimation/eskf_param_sensitivity.png`（正文 `fig:ch05-eskf-param-sensitivity`，§5.5.5）
- **表**: `tab:ch05-eskf-robustness`（八类扰动 × 三种子 = 24 次运行）
- **一句话 caption**: 「ES-EKF 在 8 类传感器/通信扰动、每类 3 个随机种子共 24 次运行中全部成功，自适应协方差机制全场景触发（触发率 0.24–0.36）。」
- **so what / 边界**: 证明**估计连续性**在多源不确定性下成立；参数敏感性探针（左 Pearson、右单参数扫描）显示仅 σ_DVL 强相关（0.779），佐证"水平不可观"是**结构性**而非整定问题。**边界**：敏感性探针为单包 n=1，仅作机制佐证。

### 1.2 分源 NIS 一致性校准 A/B（不确定性量化）
- **图（PPT）**: 建议做**数值对比页**（无独立图，直接引表数）。
- **表**: `tab:ch05-nis-covariance-ab`（独立对照，**不改主线默认协方差**）
- **一句话 caption**: 「深度 σ 由 0.05→0.12 且取消 DVL R 缩放后，深度 NIS/dof 由 7.205 降至 3.285，落回卡方一致带内。」
- **so what / 边界**: 改善的是**一致性**（NIS）而非**水平点位精度**——与 §1.1 呼应。**边界**：DVL 自适应门控仅单向膨胀→过保守，作为"结构性下界/类型 2 边界"如实承认。

### 1.3 磁探测联合实验（合成空间阵列）
- **图（PPT）**: `experiments/magnetic_joint/complex_iq_fit.png`（45 Hz 复 I/Q 拟合） + `experiments/magnetic_joint/trajectory_colored_by_b.png`（按磁场着色轨迹）
- **一句话 caption**: 「移动单三轴磁传感器形成合成空间阵列，复 I/Q 联合实验恢复相对几何。」
- **so what / 边界**: 证明低成本磁采集链路可行性。**边界**：磁探测灵敏度为**子链量级、非整机达标**（Hann p95 0.19–0.31 nT，未达 0.05 nT 整机指标）。

### 1.4 磁外参仿真标定
- **图（PPT）**: `experiments/mag_lever_arm_fullflow_20260705_2145/01_mag_extrinsics_residual.png`
- **表**: `tab:ch05-mag-calibration`
- **一句话 caption**: 「磁外参仿真标定（单次）使平移误差和安装角误差分别降低 96.27% 和 95.31%。」
- **so what / 边界**: 杆臂/安装角可仿真辨识。**边界**：单次标定（n=1），实物待验证。

---

## 2. 主线三：近底巡检地形跟随（控制主结果）

### 2.1 三维地形跟随（空间直觉 Hero，P2-1a 新提升）
- **图（PPT）**: `terrain_following/terrain_3d_pid_terrain_trajectory.png`（正文 `fig:ch05-terrain-3d`，§5.5.2，Figure 5.6）
- **表**: `tab:ch05-terrain-main`
- **一句话 caption**: 「确定性重建海底曲面 + AUV 轨迹：车辆在起伏海床上方以近似恒定净空推进；重建曲面与沿程 DVL 实测海底 r≈0.91、RMS≈0.34 m。」
- **so what / 边界**: 空间化印证米级以内离底 RMSE。**边界**：n=1 单次，稳健结论以 §2.2 三档多种子为准；bag 点云因是原点静态快照不用于本图（已核验去相关）。

### 2.2 地形强度三档多种子消融（稳健主结论）
- **图（PPT）**: `terrain_following/terrain_tz_tracking_pid_mpc.png`（`fig:ch05-terrain-tracking`）
- **表**: `tab:ch05-terrain-ablation`（低/中/高各 3/3 成功）
- **一句话 caption**: 「低/中/高三档地形各三次全部成功、零安全违规，离底 RMSE 0.59–0.71 m。」
- **so what / 边界**: 这是**近底安全的主结论**（均值±标准差）。**边界**：MPC 未优于 PID，如实记录。

---

## 3. 主线二：感知不确定性驱动控制（UA-MPC）

### 3.1 分源置信下的控制权限管理
- **图（PPT）**: `experiments/control/r13_v2_authority_modes_ua.png` + `experiments/control/r13_v2_p_track_boxplot_ua.png`
- **表**: `tab:ch05-uampc-control`、`tab:ch05-r13-v2-main-results`（六类代理场景 3 种子，36/36 有效）
- **一句话 caption**: 「六类代理电缆场景 R13-v2 正式矩阵 36/36 完成，fallback 全 0，p95 求解耗时约 9.8–9.9 ms。」
- **so what / 边界**: UA-MPC 的正结果是**控制平滑 + 实时可解 + 跟踪许可管理**。

### 3.2 控制变化率显著下降（配对对比）
- **图（PPT）**: `experiments/control/r13_v2_control_rate_paired.png`
- **一句话 caption**: 「保守分源置信控制将全局控制变化率 RMS 由 0.247 降至 0.085。」
- **so what / 边界**: **不宣称**横向 RMSE 全面提升——UA-MPC 的价值在风格与可解性，如实划界。

---

## 4. 电缆巡检闭环与行业验收

### 4.1 端到端闭环验收收敛
- **图（PPT）**: `cable_acceptance/pvs_closedloop_acceptance_convergence.png`（`tab:ch05-closed-loop-acceptance`）
- **一句话 caption**: 「干净先验下三次数字孪生闭环运行全部就绪并通过。」

### 4.2 先验畸变下的重定位恢复
- **图（PPT）**: `cable_acceptance/pvs_closedloop_recovery_prior_alignment.png`（`tab:ch05-distorted-prior`）
- **一句话 caption**: 「中/重两档先验畸变下六自由度闭环恢复各三次窗口内验收（几何重配恢复磁可观测性后）。」
- **so what / 边界**: 恢复能力依赖将真值直缆重置于传感器正下方约 7.5 m 的几何重配，须说明前提。

### 4.3 行业指标对齐验收单
- **图（PPT）**: `cable_acceptance/cable_dlt1278_scorecard_fresh1.png`
- **一句话 caption**: 「DL/T 1278 口径评分卡：埋深/沿线偏差/置信度等阈值逐项对齐。」
- **so what / 边界**: 每行显式标注"仿真满足 / 实物待验证"。

---

## 5. 边界与剩余验证（诚实收口页）

- **图（PPT）**: `hardware/adc_enob/ch4_enob_vs_osr.png` + `hardware/adc_enob/ch4_noise_spectral_density.png`
- **表**: `tab:ch05-negative-results`、`tab:ch05-evidence-inventory`
- **一句话 caption**: 「系统级计量与真机验收有意置于实物层；本文明确统计充分性、场景真实性、硬件实物三类边界。」
- **so what**: 主动划界即是贡献——为实物实验预留清晰推进路径（对齐用户"为后续实物实验留出叙述空间"）。

### 5.1 ADC--TMR 实测背景 ROS2 闭环回放
- **图（PPT）**: `experiments/mag_chain_noise_ros/mag_chain_noise_ros_comparison.png`
- **表**: `tab:ch05-mag-chain-noise-ros`
- **一句话 caption**: 「ADC--TMR 宿舍背景记录以 metadata 可追溯方式进入 `/auv/sensors/magnetic`，清洁/同协方差高斯/实测回放三臂闭环横偏 p95 均约 7.77 m，未改变同配置安全边界结论。」
- **so what / 边界**: 证明真实采集链噪声已进入 ROS 父层观测闭环。**边界**：Direction A 解耦轻量闭环门禁，非完整 AUV 水下实测，ready/pass 不作为本页结论指标。

---

## 6. 复用与追溯

- 所有图均来自正文已引用图，生成脚本与数据源见各图目录 `_SOURCE.md` 与 `docs/thesis/chapter5_figures_index` 系列文档（09 地形、12 电缆等）。
- **PPT 取图**：优先 `.png`（14 张主图均有 png）；矢量需求用同名 `.pdf`（地形 2 张与敏感性图有 pdf）。
- 本清单不产生新产物、不触碰任何实验配置，纯写作/答辩辅助。
- 数值口径若与正文更新出现分歧，**以 `thuthesis/data/auv-chap0*.tex` 为准**，回改本清单。
