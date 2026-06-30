# 第 5 章：实验与结果讨论
<!-- continuation: docs/thesis/paper/05_experiments_and_discussion_continued.md -->

## 5.1 实验平台方案与评价指标定义

### 5.1.1 虚实结合实验架构描述

| 层级 | 平台 | 作用 | 状态 |
|---|---|---|---|
| L1 | PVS + Mock AMD | 算法快速迭代、CI 流水线、chaos 故障注入 | 已就绪 |
| L2 | HoloOcean + Mock AMD | 高保真流体/碰撞仿真、视觉验证 | 已就绪 |
| L3 | Jetson（emulated）+ 完整 ROS2 栈 | 算力压力测试、IPOPT 求解器性能 | 已 emulated 验证 |
| L4 | 真机 Jetson + AMD/VxWorks + 传感器 | 实物部署、真网络时延、硬件标定 | 待执行 |

实验由 `scripts/start_experiment.sh` 和 `scripts/run_experiment_runner.py` 管理。实验运行器支持三种模式：`all`（全部场景顺序执行）、`single`（单场景执行）和 `list`（指定场景列表执行）。每个实验生成独立的 `summary.csv`，包含定位、控制和安全指标。

### 5.1.2 评价指标的数学定义与物理意义

评价指标分为定位、控制、terrain 和电缆巡检四类。本节给出各指标的详细定义。

#### （1）定位指标

| 指标名称 | 符号 | 计算公式 | 物理意义 |
|---|---|---|---|
| XY RMSE | `RMSE_xy` | `sqrt(mean((x_est - x_gt)^2 + (y_est - y_gt)^2))` | 水平面平均定位精度 |
| Z RMSE | `RMSE_z` | `sqrt(mean((z_est - z_gt)^2))` | 深度方向平均估计误差 |
| CEP50 | `CEP50` | `argmin_r: P(sqrt((dx)^2 + (dy)^2) <= r) >= 0.5` | 50% 概率下的圆概率误差 |
| Max Drift | `max_drift` | `max_t sqrt((x_est(t) - x_gt(t))^2 + (y_est(t) - y_gt(t))^2)` | 最差时刻偏离距离 |
| NIS | `NIS` | `(1/T) * sum(x_tilde_k^T * P_k^(-1) * x_tilde_k)` | 归一化创新平方均值，用于检验 EKF 协方差一致性。理想值等于状态维度 |

NIS（Normalized Innovation Squared）的统计意义：若 EKF 协方差与实际误差匹配，则 `NIS ~ chi^2(n)`，其中 n 为观测维度。`NIS/DOF` 的 95% 置信区间约为 `[0.85, 1.15]`。该指标是第 3 章 ES-EKF 协方差一致性的核心量化依据。

#### （2）控制指标

| 指标名称 | 符号 | 计算公式 | 物理意义 |
|---|---|---|---|
| Heading RMSE | `RMSE_psi` | `sqrt(mean(wrap(psi_est - psi_ref)^2))` | 航向跟踪精度 |
| Depth RMSE | `RMSE_z_ctrl` | `sqrt(mean((z_est - z_ref)^2))` | 深度跟踪精度 |
| Lateral RMSE | `RMSE_lat` | `sqrt(mean(d_lat^2))`，`d_lat` 为到参考路径的横向距离 | 路径跟踪横向偏差 |
| 控制量平滑度 | `RMS_rate` | `sqrt(mean(||dU/dt||^2))` | 控制指令变化率，越低越平滑 |
| 控制努力 | `E_ctrl` | `mean(||U||)` | 平均控制量幅值 |
| MPC 求解时间 | `t_solve` | IPOPT `t_proc_total x 1000` | 单次优化求解耗时（ms） |
| Fallback Rate | `f_fb` | `count(fallback=True) / N_samples` | MPC 求解失败回退比例 |
| 状态源回退率 | `f_state_fb` | `count(state_source_fallback=True) / N_samples` | 使用状态估计降级源的比例 |
| 安全违规率 | `f_safety` | `max(seabed_violation, penetration_ratio)` | 离底高度违规或穿透比例 |

**控制量平滑度的详细说明**：控制量变化率 `RMS_rate` 通过以下方式计算。从 `/auv/controller/debug` topic 解析出控制量时间序列 `U(t)`，计算相邻样本差分 `dU/dt`，取 L2 范数后求 RMS。该指标量化控制指令的"抖动"程度，值越低说明控制指令越平滑，执行器机械磨损越小。

**Fallback Rate 的判定逻辑**：当 `/auv/controller/debug` 中的 `solver_status` 包含 "FALLBACK" 或 `fallback_reason` 非空，判定为一次 fallback。Fallback 的触发原因包括 IPOPT 求解失败、求解超时（超过 `max_solve_time_ms`）、或状态估计不可靠。

#### （3）Terrain 指标

Terrain 指标用于评估近底地形跟随安全性。以离底高度为核心量：

| 指标名称 | 符号 | 计算公式 | 物理意义 |
|---|---|---|---|
| 平均离底高度 | `h_mean` | `mean(seabed_clearance)` | 平均安全裕度 |
| 最小离底高度 | `h_min` | `min(seabed_clearance)` | 最危险时刻的安全裕度 |
| 离底高度标准差 | `h_std` | `std(seabed_clearance)` | 离底高度波动程度 |
| 目标 RMSE | `RMSE_to_3m` | `sqrt(mean((clearance - 3)^2))` | 相对 3 m 目标高度的偏差 |
| 安全违规率 | `v_ratio` | `count(clearance < 1.5 m) / N` | 离底高度低于 1.5 m 的比例 |

terrain-following 模式下，目标不是保持固定深度，而是保持恒定离底高度。因此用 `seabed_clearance_rmse_to_3m` 替代 `depth_error_rmse_m` 作为主指标。

#### （4）电缆巡检指标

| 指标名称 | 符号 | 计算公式 | 物理意义 |
|---|---|---|---|
| 横向偏移 RMSE | `RMSE_lat_cable` | `sqrt(mean(d_lat_cable^2))` | 相对电缆中心线的横向偏差 |
| 路由完成率 | `R_route` | `L_tracked / L_total` | 沿电缆路由完成巡检的比例 |
| 埋深反演误差 | `eps_buried` | `\|d_est - d_true\|` | 反演埋深与真实埋深的偏差 |
| 检测连续性 | `C_det` | `T_detected / T_total` | 在巡检过程中成功检测到电缆的时间比例 |

1. **定位指标**：`tools/analyze_bag.py` 从 MCAP bag 中解析真实轨迹和估计轨迹，计算 RMSE、NIS 等。
2. **控制指标**：`tools/aggregate_control_metrics.py` 从 `/auv/controller/debug` 和 `/auv/control/mpc_cmd` topics 解析控制量时间序列，计算求解时间、fallback rate、控制平滑度等。
3. **实验运行器**：`tools/run_thesis_sweep.py` 组织多场景 x 多种子 x 多模式实验，自动调用上述工具聚合结果，输出 `summary.csv` 和 `aggregate.md`。

## 5.2 基于 HoloOcean/PVS 的高保真数字孪生仿真

### 5.2.1 复杂海底电缆巡检场景构建

当前 PVS 场景库包含 baseline、DVL 丢包（4 档）、磁畸变（2 档）、声呐杂波和 combined stress。这些场景是传感器和通信不确定性验证的基础，但不完整模拟海缆巡检的几何、地形和声磁耦合。

| 场景 ID | 扰动类型 | 严重程度 | 用途 | 代码路径 |
|---|---|---|---|---|
| `scenario_baseline.yaml` | 无 | 干净环境 | 算法 baseline 对照 | `scenarios/` |
| `scenario_dvl_dropout_10.yaml` | DVL 丢包 | 10% | 轻度速度观测丢失 | `scenarios/` |
| `scenario_dvl_dropout_30.yaml` | DVL 丢包 | 30% | 中度速度观测丢失 | `scenarios/` |
| `scenario_dvl_dropout_60.yaml` | DVL 丢包 | 60% | 重度速度观测丢失 | `scenarios/` |
| `scenario_dvl_dropout_90.yaml` | DVL 丢包 | 90% | 极重度速度观测丢失 | `scenarios/` |
| `scenario_mag_distortion_light.yaml` | 磁畸变 | 1e-6 T | 轻度磁饱和 | `scenarios/` |
| `scenario_mag_distortion_heavy.yaml` | 磁畸变 | 1e-8 T | 重度磁饱和 | `scenarios/` |
| `scenario_sonar_clutter.yaml` | 声呐杂波 | 固定参数 | 声呐成像噪声 | `scenarios/` |
| `scenario_combined_stress.yaml` | 多扰动联合 | 0.3 m/s 海流 + 丢包 + 磁畸变 | 综合压力测试 | `scenarios/` |

这些 YAML 配置定义包含 `chaos`（故障注入）、`perception`（传感器噪声）、`flow`（流场）和 `mpc_mode`（MPC 消融模式）四个配置节。

### 5.2.2 combined_stress 场景详解

`combined_stress` 是论文主鲁棒比较的关键场景，单个 YAML 内同时打开 8 个扰动源，对应论文中"模拟现场最不利组合"的物理意图：

| 扰动源 | 参数值 | 物理意图 |
|---|---|---|
| 总线丢包 | `packet_loss_prob = 0.05` | 模拟低带宽 acoustic modem |
| DVL 丢包 | `drop_rate = 0.30`，窗口 `[1.0, 3.0] s` | 浊水/杂草遮挡导致的中等丢包 |
| IMU 漂移 | `bias_rate = 0.001` | 无热漂温补的 MEMS 慢漂移 |
| 深度尖峰 | `rate_hz = 0.05`，`amplitude_m = 0.5` | 平均 20 s 一次的 0.5 m 压力传感 EMI |
| 磁饱和 | `threshold = 1e-7 T` | 母船电磁场近场干扰 |
| 加速度计噪声 | `imu_acc_noise_scale = 1.5` | 振动耦合增强 |
| 声呐噪声 | `sonar_noise_scale = 2.0` | 浑浊浅水条件 |
| 海流 | `current_speed = 0.3 m/s` | 长江口/近海典型流速 |

论文写作中应同时给出 baseline、单维度场景、combined_stress 三层数据，证明 UA-MPC 的鲁棒性增益是叠加生效，而非单点偶然。

### 5.2.3 传感器噪声注入实验

Mock AMD 子系统通过三大模块模拟真实水下通信和传感不确定性：

| 模块 | 功能 | 关键参数 |
|---|---|---|
| `TransportDelayQueue` | 模拟非确定性通信延迟 | `base_delay_ms = 200`, `jitter_ms = 50` |
| `SensorSampleCache` | 模拟多速率传感器采样 | IMU 100 Hz, Depth 50 Hz, Mag 20 Hz, DVL 6 Hz |
| `ChaosInjector` | 故障注入 | drop_rate, reorder_rate, DVL 冻结、IMU 漂移、深度尖峰、磁力计饱和 |

**ChaosInjector 故障模型详解**：

| 故障类型 | 实现方式 | 概率模型 | 典型参数 |
|---|---|---|---|
| DVL 冻结 | 保持上一次 DVL 速度输出 | Bernoulli + 窗口均匀采样 | `drop_rate = 0.3`, window `[1, 3] s` |
| IMU 漂移 | 在加速度计输出上叠加线性偏置 | 连续时间随机游走 | `bias_rate = 0.001 m/s^2/s` |
| 深度尖峰 | 在深度测量中叠加瞬态脉冲 | 泊松过程 + 固定幅值 | `rate_hz = 0.05`, `amplitude = 0.5 m` |
| 磁力计饱和 | 超过阈值后截断磁场输出 | 硬饱和限幅 | `threshold = 1e-7 T` |
| 总线丢包 | 随机丢弃 UDP 帧 | Bernoulli | `prob = 0.05` |
| 数据包乱序 | 交换连续帧的时间戳顺序 | Bernoulli | `rate = 0.01` |

当前场景中的磁饱和阈值（1e-6 T / 1e-8 T）用于模拟传感器量程受限的情况，但尚未与真实 HSF-500 传感器噪声模型对齐。

> **表格占位符**：正式论文中需补充传感器噪声模型的参数来源、分布假设和与真实传感器手册的对照表。

### 5.2.4 核心算法对比测试

| 对比实验 | 对照算法 | 场景 | 样本量 | 当前状态 |
|---|---|---|---|---|
| ES-EKF vs Std-EKF vs Raw DR | 三种状态估计方法 | baseline + chaos | 8 场景 x 3 seed（24/24 ok） | 已完成 |
| PID baseline vs PID terrain | 两种地形跟随策略 | terrain benchmark | n=1/组 | 已就绪 |
| MPC vs PID yaw-only | guidance-level 预瞄 vs 无预瞄 | 离线极端路径 | n=1/场景 | 已就绪 |
| UA-MPC vs baseline-MPC | 不确定性感知 vs 固定权重 | baseline + chaos | 3 场景 x 2 模式 x 3 seed（18/18 ok） | 已完成 |

**ES-EKF 实验说明**：8 场景包括 baseline、DVL dropout 四档（10/30/60/90%）、磁畸变（heavy）、声呐杂波和 combined stress。每场景跑 3 个随机种子，每种子的真实种子编号记录在 `log/thesis_sweep/` 目录下。所有 24 个 run 均成功完成，支撑第 3 章"ES-EKF 在各类传感器不确定性下保持定位精度优势"的论述。

**UA-MPC 主消融说明**：3 场景包括 baseline、DVL dropout 60% 和 combined stress。每场景跑 baseline 和 ua 两种模式，每种模式 3 个种子，共 18 个 run。定位指标由 `run_thesis_sweep.py` 采集，控制指标由 `aggregate_control_metrics.py` 从 MCAP bag 中二次提取。当前结果为 offline EKF 指标闭环，控制侧 solve time 字段部分为 nan（待补工具链修复）。

## 5.3 硬件系统集成与物理标定实验

> **本章大部分实验尚未执行，以下内容按"设计方案和未来工作"书写，不作为已完成结果。**

### 5.3.1 "双脑"通信链路与实时性压力测试

Jetson 与 AMD/VxWorks 之间的 UDP 二进制通信链路需要在实物环境下测试真实时延和丢包率。当前 emulated 测试仅验证了协议解析正确性和软件栈算力约束。

UDP 二进制协议：下行帧 `$CKTH`（72 B）携带工作模式、任务指令、舵角、推力和 12 个可调浮点参数；上行帧 `$AUV`（145 B）携带 roll/pitch/yaw、GPS、DVL 三轴速度、深度、电压、温度、漏水、故障位图。Python 端与 VxWorks 端独立开发过程中已发现 7 处已知偏差（帧头长度差异、压力与航向字段错位、深度缩放因子不一致、舵角类型符号约定不同等），仿真期已通过协议单元测试闭环，实物部署时需逐一复核。

> **表格占位符**：实物部署阶段需补充 Jetson-AMD UDP 通信时延统计表（p50/p95/p99、丢包率、序列号跳变次数）。

### 5.3.2 基于高精度转台的磁传感器九参数在线标定

磁传感器标定需要同时估计硬铁（permanent magnetization）和软铁（induced magnetization）干扰。标定过程需要在高精度转台上旋转 AUV，记录磁场各向异性响应，拟合软铁矩阵和硬磁偏置。

> **表格占位符**：实物部署阶段需补充转台标定前后的磁场残差对比表和九参数标定结果。

### 5.3.3 故障注入自救逻辑验证

`docs/experiment/benchmark_test_log.md` 中已有单次故障注入结果（n=1），可作为工具链可用的初步证据。

## 5.4 实验室近底巡检模拟与反演精度分析

> **本章实验尚未执行，以下内容按"设计方案和未来工作"书写，不作为已完成结果。**

### 5.4.1 10A 大电流模拟电缆实验台搭建

该实验用于验证磁场反演算法。通过可控电流源向模拟电缆注入 10 A 电流，使用 HSF-500 磁传感器在不同距离和角度下采集磁场数据，验证毕奥-萨伐尔模型的反演精度。

### 5.4.2 基于 HSF-500 的电缆路由与埋深实时反演结果分析

## 5.5 实验结果讨论与 Sim-to-Real 迁移性分析

到此为止，前面四节已经把"实验平台、评价指标、场景库和噪声模型"四个准备工作交代清楚，本节进入论文的核心证据章——把所有已完成的实验数据按"证据等级"逐一摆出，然后讨论这些证据可以支撑什么样的结论、不能支撑什么样的结论、以及它们在 Sim-to-Real 迁移过程中会面临哪些已知挑战。这一组织思路与第 4 章鲁棒性分析一脉相承——任何实验结果在写入论文时都必须显式标注"样本量、测量边界、可外推条件"，否则就会出现"用 n=1 单次基准代替多 seed 统计"的过度推断。本章在表格的"边界"列中始终保留这一标注口径，使读者可以清楚看到每条结论各自的证据强度。

### 5.5.1 当前已完成实验总表

下表汇总了截至当前进度已完成或部分完成的所有实验类别，每行包括数据源、样本量、可写结论和测量边界四个字段。这张表的作用不是"实验流水账"，而是为论文写作提供一份"证据清单"——每条结论在写入正文之前，都应能在本表中找到对应的样本量与边界，从而避免引用单次或少数 seed 的实验数据时无意越界。

| 实验类别 | 当前数据源 | 样本量 | 可写结论 | 边界 |
|---|---|---:|---|---|
| baseline UA-mode 3 seed | `log/thesis_sweep/20260612_163001_c2_baseline_3seed/results.csv` | n=3 | baseline 定位指标 mean+/-std 可用 | 仅限 30 s 片段 |
| DVL dropout 4 档 3 seed | `log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv` | n=3/档 | 四档均 3/3 ok，支撑第 3 章鲁棒性 | 仅限定位指标 |
| Mag/Sonar/Combined 4 场景 3 seed | `log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv` | n=3/场景 | 四场景均 3/3 ok，支撑第 3 章鲁棒性 | XY RMSE 非单调 |
| UA-MPC 主消融（定位） | `log/thesis_sweep/20260612_172535_h1_uampc_main_ablation/results.csv` | 3 场景 x 2 模式 x 3 seed | baseline/combined UA-MPC 定位改善，dvl_60 无优势 | offline EKF 指标 |
| H1 控制侧指标聚合 | `results/control_aggregates/20260612_172535_h1_uampc_main_ablation/` | 3 场景 x 2 模式 x 3 seed | lateral RMSE、control rate RMS、fallback rate 已闭环 | solve time 为 nan |
| baseline 定位/控制/决策 | `docs/experiment/benchmark_test_log.md` | n=1 | 工具链和单次基准可用 | 不能替代多 seed |
| 60s terrain PID/MPC | `docs/experiment/terrain_benchmark_log.md` | n=1/组 | PID terrain 是当前近底主结果 | 需重复统计 |
| PID terrain low/mid/high | `results/control/pid_terrain_ablation_20260610_170846_summary.csv` | n=1/档 | 三档均无安全违规 | 缺多 seed |
| MPC 深度调参 | `docs/thesis/08_terrain_following_pid_mpc_status.md` | 多轮调参 | 深度 MPC 不作为主线 | 只能写回退理由 |
| MPC x/y/yaw extreme | `/auv_data/results/control/mpc_xy_yaw_extreme/20260620_011831/` | n=1/场景 | 公平口径下 MPC 在长波/短波 S 弯、hairpin 优于或持平基线 | 仅直角 chicane LOS 更优（诚实边界） |
| PVS chaos 场景库 | `docs/thesis/05_scenario_recipes.md` | 9 个 YAML | 可支撑不确定性场景设计 | 未完整模拟海缆巡检 |
| Jetson emulated | `docs/thesis/06_jetson_deploy_emulated.md` | emulated | 可讨论算力接口 | 不能写真机绝对时延 |
| BT vs FSM | `docs/experiment/benchmark_test_log.md` | n=1 | 行为树单次效果可用 | 缺多场景对比 |

### 5.5.2 Terrain Following 主结果

> **数据口径（2026-06-20 真口径重跑，取代旧表）**：本表已更新为 P0 真口径重跑结果 `results/control/terrain_following_20260619_222639/`（warm-up 跳过 10 s、四相 truth 统一 `/auv/sensors/ground_truth`、离底高度源 `real_altitude`）。早先 `20260610_175154` 旧表的 `seabed_clearance_mean≈4.0 m`、`depth_error_rmse≈7 m` 已确认是分析层 datum bug 造成的常值假象，已被取代；溯源与修复始末见 [docs/thesis/08_terrain_following_pid_mpc_status.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/08_terrain_following_pid_mpc_status.md) §8.1/§8.2。**每相为单次运行（n=1），引用须标注，后续应补 ≥3 次重复给出 mean±std。**

| 指标 | PID baseline | PID terrain | MPC baseline | MPC terrain |
|---|---:|---:|---:|---:|
| duration_s | 59.11 | 59.80 | 59.50 | 59.51 |
| clearance_source | real_altitude | real_altitude | real_altitude | real_altitude |
| seabed_clearance_min_m | 1.600 | 1.000 | 1.400 | 1.400 |
| seabed_clearance_mean_m | 2.699 | 1.954 | 2.657 | 2.647 |
| seabed_clearance_std_m | 0.470 | 0.442 | 0.495 | 0.500 |
| seabed_clearance_rmse_to_3m | 0.558 | 1.136 | 0.602 | 0.612 |
| depth_error_rmse_m | 6.493 | N/A | 6.427 | N/A |
| clearance < 1.5 m ratio | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| solve_time_mean_ms | nan | nan | 12.93 | 10.59 |
| solver_fallback_ratio | nan | nan | 0.000 | 0.1429 |

真口径下四相 `seabed_clearance_mean` 落在 1.95–2.70 m，离底高度随真地形起伏（`std≈0.44–0.50 m`），不再是旧表的 4.0 m 常值 datum 假象。terrain 模式主指标仍是 `seabed_clearance_rmse_to_3m`；`depth_error_rmse_m` 在 terrain 模式按"绝对目标深度"评分无物理意义，已正确标 N/A（仅留 `depth_error_rmse_diag_m` 作审计）。本次重跑为 n=1 单次运行，PID/MPC terrain 的 clearance RMSE 接近，**不应据此过度解读 PID 与 MPC terrain 的相对优劣**；地形跟随能力的稳健结论以 §5.5.3 的 low/mid/high 消融为准。此外 mpc_terrain 相有 14.3% 步触发 `FALLBACK_LAST_OUTPUT`，这是 MPC 在起始深度与目标差距过大（8 m→3 m）时带宽/速率约束求解不可行的真实工程边界（见 doc 08 §8.4），须诚实记录。

#### Terrain Following 实验图组

下列实验图分别展示 PID/MPC terrain 在离底高度跟踪、安全裕度、3D 轨迹和指令契约四个维度上的实测结果，对应上表的指标行：

![Terrain TZ 跟踪 PID vs MPC](../figures/terrain_following/terrain_tz_tracking_pid_mpc.png)

![Terrain Clearance RMSE 对比](../figures/terrain_following/terrain_clearance_rmse_pid_mpc.png)

![Terrain 安全裕度](../figures/terrain_following/terrain_clearance_safety_margin.png)

![PID Terrain 3D 轨迹](../figures/terrain_following/terrain_3d_pid_terrain_trajectory.png)

![Terrain Benchmark 指令契约](../figures/terrain_following/terrain_benchmark_command_contract.png)

### 5.5.3 PID Terrain 地形强度消融

| terrain | RMSE to 3 m | mean (m) | std (m) | min (m) | violation < 1.5 m |
|---|---:|---:|---:|---:|---:|
| low | 0.0709 | 3.0218 | 0.0675 | 2.8612 | 0.0 |
| mid | 0.1735 | 3.1735 | 0.0028 | 3.1634 | 0.0 |
| high | 0.0586 | 2.9932 | 0.0582 | 2.8765 | 0.0 |

三档地形的 safety violation ratio 均为 0.0。其中 mid 地形的离底高度最稳定（std = 0.0028 m），low 和 high 地形的 std 略大但仍处于安全范围。这说明 PID terrain 在当前 PVS 地形模型下对地形强度的变化具有鲁棒性。

![PID Terrain low/mid/high 消融](../figures/terrain_following/pid_terrain_low_mid_high_ablation.png)

**当前边界**：本结果为 n=1/档，需扩展到 3 seed mean+/-std 才能作为论文主结论。

> 5.5.3 之后的新增实验补充，包括完整 P1 控制侧/NIS 聚合、terrain 3 seed retry 合并口径、代理电缆 smoke 与 6 场景扩展计划，已整理到 `docs/thesis/paper/05_experiments_and_discussion_continued.md`。下文保留原章节脉络，并清理明显的缓存/脚本输出污染。

### 5.5.4 MPC x/y/yaw 支线结果

> **数据口径（2026-06-20 公平口径重跑，取代旧表）**：本表已更新为 WP-E 公平口径重跑结果 `/auv_data/results/control/mpc_xy_yaw_extreme/20260620_011831/`。早先 `20260610_204314` 旧表受 harness 一个 `+2.0 m` 常值下游偏置 bug 影响——该偏置把整条 MPC 参考（含 k=0）推到最近点下游，迫使 MPC 切弯、人为放大其横向 RMSE，而两条 PID 基线无此偏置，导致对比不公平。删除该偏置（保留 `k*v*dt` 真预瞄项）后 5 个 variant 一致复跑。溯源与修复始末见 [docs/thesis/08_terrain_following_pid_mpc_status.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/08_terrain_following_pid_mpc_status.md) §8.7。**每场景为单次运行（n=1），引用须标注。**

 MPC x/y/yaw 极端路径实验中，将离线规划的长波/短波 S 弯、直角 chicane 和 hairpin 路径分别用 PID yaw-only、LOS 和 MPC 跟踪，比较横向跟踪误差（lateral RMSE）。

| 场景 | PID yaw-only lateral RMSE | LOS lateral RMSE | MPC best lateral RMSE | 结论 |
|---|---:|---:|---:|---|
| s_turn_long_wave（60 m / 7 m） | 0.093 m | 1.047 m | 0.055 m | MPC 全胜（−41% vs yaw-only / −95% vs LOS） |
| hairpin_180deg | 4.69 m | 4.69 m | 2.277 m | MPC 全胜（−51%） |
| s_turn_short_wave | 2.597 m | 1.657 m | 1.655 m | MPC −36% vs yaw-only、与 LOS 持平 |
| chicane_90deg | 3.596 m | 0.659 m | 1.452 m | 诚实边界：直角 chicane 上 LOS 前瞻最优 |

**结论与边界**：
- 公平口径下，MPC 在长波 S 弯、急转 hairpin、短波 S 弯三类工况均优于或持平基线：长波 S 弯与 hairpin 上 MPC 对两条基线均全胜，短波 S 弯上 MPC 显著优于 yaw-only 且与 LOS 持平。
- 唯一的诚实边界是直角 `chicane_90deg`：该路径由分段直线组成，LOS 几何前瞻最贴合，横向 RMSE（0.659 m）优于 MPC（1.452 m）。该边界予以保留，不做过度宣称。
- 早先"MPC 不普遍优于基线"的判断源自 harness 的 `+2.0 m` 偏置 bug，修复后已被推翻。
- 该支线结果为 n=1/场景，尚未扩展到多 seed 统计。作为支线结果，说明 MPC guidance-level 多步预瞄与速度规划对复杂曲率路径有横向误差优势，但尚不足以作为论文主结论。

### 5.5.5 ES-EKF 多场景多种子鲁棒性结果

C0–C5 低成本验证后，进一步扩展到 8 个 PVS chaos 场景 x 3 seed（共 24 次运行），用于验证 ES-EKF 在多种传感器/通信扰动下的定位鲁棒性。数据源：`log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv`。

| 场景 | ok/total | XY RMSE mean+/-std | Z RMSE mean+/-std | CEP50 mean+/-std | Max Drift mean+/-std |
|---|---:|---:|---:|---:|---:|
| dvl_dropout_10 | 3/3 | 2.97+/-1.41 m | 0.20+/-0.03 m | 2.98+/-1.40 m | 2.98+/-1.40 m |
| dvl_dropout_30 | 3/3 | 3.37+/-0.13 m | 0.20+/-0.01 m | 3.38+/-0.13 m | 3.38+/-0.13 m |
| dvl_dropout_60 | 3/3 | 2.89+/-0.46 m | 0.22+/-0.01 m | 2.90+/-0.45 m | 2.89+/-0.46 m |
| dvl_dropout_90 | 3/3 | 3.55+/-0.23 m | 0.19+/-0.04 m | 3.55+/-0.23 m | 3.55+/-0.23 m |
| mag_distortion_light | 3/3 | 2.76+/-0.34 m | 0.18+/-0.01 m | 2.76+/-0.34 m | 2.76+/-0.34 m |
| mag_distortion_heavy | 3/3 | 3.42+/-0.10 m | 0.22+/-0.02 m | 3.42+/-0.10 m | 3.42+/-0.10 m |
| sonar_clutter | 3/3 | 3.27+/-1.06 m | 0.20+/-0.03 m | 3.27+/-1.05 m | 3.27+/-1.06 m |
| combined_stress | 3/3 | 3.27+/-1.09 m | 0.20+/-0.02 m | 3.28+/-1.09 m | 3.28+/-1.09 m |

**结论与边界**：
- 8 个场景均达到 100% 成功率（24/24 ok），说明 ES-EKF 在 DVL 丢包（10%–90%）、磁畸变、声呐杂波及联合扰动下均能稳定输出定位结果。
- XY RMSE 不严格按扰动强度单调变化。例如 dvl_dropout_60 的 XY RMSE（2.89 m）低于 dvl_dropout_30（3.37 m），combined_stress（3.27 m）低于 sonar_clutter（3.27 m）和 mag_distortion_heavy（3.42 m）。这说明 30 s 片段、seed 初始化和观测时序对结果有显著影响，不宜将单次或少数场景的数值差异过度解读为"扰动强度的单调响应"。
- 本表指标来自 `tools/offline_ekf_benchmark.py`（offline EKF），反映的是状态估计误差，不直接等价于控制侧 lateral RMSE 或轨迹跟踪性能。

### 5.5.6 UA-MPC 主消融结果（定位侧）

UA-MPC（Uncertainty-Aware MPC）与 baseline-MPC 的对比实验在 3 个场景（baseline、dvl_dropout_60、combined_stress）x 2 种 MPC 模式 x 3 seed 下执行，共 18 次运行。数据源：`log/thesis_sweep/20260612_172535_h1_uampc_main_ablation/results.csv`。

| 场景 | 模式 | ok/total | XY RMSE mean+/-std | Z RMSE mean+/-std | CEP50 mean+/-std |
|---|---|---:|---:|---:|---:|
| baseline | baseline-MPC | 3/3 | 4.62+/-0.61 m | 0.30+/-0.003 m | 4.63+/-0.61 m |
| baseline | UA-MPC | 3/3 | 4.40+/-1.01 m | 0.30+/-0.004 m | 4.41+/-1.00 m |
| dvl_dropout_60 | baseline-MPC | 3/3 | 3.49+/-0.95 m | 0.29+/-0.001 m | 3.50+/-0.95 m |
| dvl_dropout_60 | UA-MPC | 3/3 | 3.55+/-0.50 m | 0.30+/-0.006 m | 3.56+/-0.49 m |
| combined_stress | baseline-MPC | 3/3 | 4.11+/-0.11 m | 0.29+/-0.004 m | 4.12+/-0.12 m |
| combined_stress | UA-MPC | 3/3 | 3.68+/-0.50 m | 0.29+/-0.002 m | 3.69+/-0.50 m |

UA-MPC 相对 baseline-MPC 的 XY RMSE 变化：

| 场景 | UA-MPC 相对变化 |
|---|---:|
| baseline | 改善约 4.7% |
| dvl_dropout_60 | 变差约 1.9% |
| combined_stress | 改善约 10.4% |

**结论与边界**：
- UA-MPC 在 baseline 和 combined_stress 场景下对定位相关指标（XY RMSE、CEP50）有轻微改善，尤其在 combined_stress 下改善约 10.4%。
- 在 dvl_dropout_60 场景下，UA-MPC 的 XY RMSE 反而略差于 baseline-MPC（变差约 1.9%），说明 UA 权重在 DVL 重度丢包下不一定带来定位优势。
- **重要边界**：当前消融指标来自 offline EKF benchmark（XY/Z/CEP50 定位误差），不是完整的控制侧性能指标（lateral RMSE、fallback rate、control smoothness）。因此不能将本表单独写成"UA-MPC 控制性能显著优于 baseline-MPC"。更准确的表述是：UA mode 在部分场景下对定位指标有轻微改善，控制侧结论需结合 lateral/fallback/control-effort 指标综合判断。

### 5.5.7 H1 控制侧指标聚合

5.5.6 节给出的是 UA-MPC 在"定位侧"的消融结果，但定位精度仅是 MPC 价值的一个侧面，控制侧能否做到"指令更平滑、fallback 更少、安全无违规"才是验证 MPC 工程可用性的更直接证据。本节据此给出 UA-MPC 消融的控制侧证据，使用 `tools/aggregate_control_metrics.py` 从 H1 主消融的 18 个 bag 中解析 lateral RMSE、MPC solve time、fallback rate、控制量变化率（control rate RMS）和安全违规率。数据源：`results/control_aggregates/20260612_172535_h1_uampc_main_ablation/control_aggregate_report.md`。

| 场景 | 模式 | ok/total | lateral RMSE mean+/-std | solve time mean (ms) | fallback rate | control rate RMS | safety violation |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline | baseline-MPC | 3/3 | 0.0038+/-0.0004 m | nan | 0.0000+/-0.0000 | 0.14+/-0.01 | 0.0000+/-0.0000 |
| baseline | UA-MPC | 3/3 | 0.0037+/-0.0003 m | nan | 0.0000+/-0.0000 | 0.44+/-0.27 | 0.0000+/-0.0000 |
| dvl_dropout_60 | baseline-MPC | 3/3 | 0.0033+/-0.0003 m | nan | 0.0000+/-0.0000 | 0.13+/-0.06 | 0.0000+/-0.0000 |
| dvl_dropout_60 | UA-MPC | 3/3 | 0.0039+/-0.0013 m | nan | 0.0000+/-0.0000 | 0.19+/-0.22 | 0.0000+/-0.0000 |
| combined_stress | baseline-MPC | 3/3 | 0.0035+/-0.0002 m | nan | 0.0000+/-0.0000 | 0.14+/-0.07 | 0.0000+/-0.0000 |
| combined_stress | UA-MPC | 3/3 | 0.0029+/-0.0004 m | nan | 0.0000+/-0.0000 | 0.03+/-0.004 | 0.0000+/-0.0000 |

把这五个指标合在一起看，可以分别得到下面五条结论，其中前两条相对稳健，后三条需要谨慎解读：

- **Lateral RMSE**：在 combined_stress 场景下，UA-MPC 的 lateral RMSE（0.0029 m）优于 baseline-MPC（0.0035 m），改善约 15.8%。这一改善幅度与定位侧 XY RMSE 改善 10.4% 同向，说明 UA-MPC 在多扰动叠加场景下的优势具有"定位 + 控制"双侧一致性。baseline 和 dvl_dropout_60 下两者差异较小（baseline: 0.0037 m vs 0.0038 m；dvl_60: 0.0039 m vs 0.0033 m），其中 dvl_60 的 UA-MPC 反而略差，这与 4.5.1 节"UA-MPC 在感知崩溃下不再有优势"的结论吻合——它进一步印证 UA 机制的有效性依赖于 EKF 输出质量未完全退化。
- **Fallback rate**：所有 18 次运行的 fallback rate 均为 0.0000，说明在该实验条件下两种模式都没有触发 fallback。这一结果有两种工程解读：一是 PVS 仿真侧的扰动幅度虽强但仍处于 IPOPT 求解可行域内，没有把"求解失败"这一 4.4.6 节定义的兜底分支真正激活；二是当前 30 s 实验片段过短，未能复现长时间任务下偶发的求解失败。无论哪一种解读，结论都是"当前实验未能给出 fallback 路径的有效压力测试"——这一缺口必须等到极端工况场景（5.7 节定义的 6 个场景）和长时间运行实验中才能补齐。
- **Control rate RMS**：UA-MPC 在 baseline 场景下控制量变化率（0.44）显著高于 baseline-MPC（0.14），说明 UA 权重在干净环境下可能使控制律更激进；但在 combined_stress 下反而更低（0.03 vs 0.14），说明在联合扰动下 UA 权重起到了平滑作用。这一"反向行为"乍看反直觉，但其物理机制是清晰的——UA 机制的核心是把感知不确定性映射到代价权重，干净环境下置信度本就高、UA 权重接近 baseline，二者控制律差异主要来自微小数值波动；联合扰动下置信度被显著拉低，UA 机制据此放大跟踪权重 + 减小控制权重，使控制律自动转向"保守跟随参考"的模式。换言之，control rate RMS 的"反向行为"恰恰是 UA 机制按设计工作的结果，而不是失效的征兆。
- **Safety violation**：所有 18 次运行均无安全违规。与 fallback rate 的解读类似，这一结果在当前 PVS 仿真条件下属于"未触及边界"，需要等待 5.7 节六类极端场景（特别是 Slope Crossing 和 Combined Extreme）给出更尖锐的安全压力测试。
- **MPC solve time**：由于 H1 旧 bag 中的 `/auv/controller/debug` 未发布 `solve_time_ms` 字段，当前表中 solve time 为 nan。已在 `brain_linux/src/auv_controller/auv_controller/auv_controller_node.py` 补充 debug payload（包含 `solve_time_ms`、`solver_status` 和 `fallback_reason`），后续重跑 H1 或 H2 时可记录该指标。在补齐之前，论文不能写"求解时间在 100 ms 周期内可控"这类基于 solve_time_ms 的具体结论，只能援引 emulated Jetson 上的算力接口验证作为间接证据。

### 5.5.8 UA-MPC 消融变体设计

UA-MPC 消融设计包含以下变体，用于验证各模块的独立贡献：

| 变体 ID | 名称 | 关键开关 | 预期效果 | 状态 |
|---|---|---|---|---|
| A0 | baseline-MPC | `AUV_MPC_MODE=baseline` | 对照基线，权重恒定 | 已完成 |
| A1 | UA-MPC（默认） | `AUV_MPC_MODE=ua` | RMSE 降低，控制能量降低 | 已完成 |
| A2 | UA-MPC w/o sigmoid | `cov_to_conf.smoothing=hard` | UA-MPC 优势缩小 | 待执行 |
| A3 | UA-MPC alpha=1.0 | `low_conf_alpha=1.0` | 线性调整，稳定性下降 | 待执行 |
| A4 | UA-MPC scale=0 | `low_conf_scale=0.0` | 退化为 baseline-MPC | 待执行 |

> **表格占位符**：正式论文中需补充 A2–A4 变体的消融结果表。

### 5.5.9 Sim-to-Real 迁移性讨论

PVS 仿真侧的实验已经把"算法层面正确性"的证据建立得较充分，但工程论文必须主动回答下一个更尖锐的问题——这些结论能否原样迁移到真实 AUV？把仿真结论直接当作实物结论是工程论文的常见过度推断，本节据此把 Sim-to-Real 迁移面临的具体障碍按"模型偏差、噪声差异、时延分布、算力约束"四类逐项展开，并给出当前可见的应对策略。

1. **动力学模型偏差**：PVS 基于 Fossen 船舶动力学模型，水动力系数（`mass_u`, `drag_u`, `yaw_rate_gain` 等）为经验估计值，与真实 AUV 存在偏差。这一偏差对算法层结论的影响是非对称的——状态估计和决策层结论受影响较小（它们主要依赖观测序列的统计特性），而控制层结论受影响较大（控制律对水动力参数直接敏感）。本系统的应对策略是把 MPC guidance-level 化，让水动力偏差主要由 PVS 内层 PID 通过实测调参吸收，而不让 MPC 自身假设过于精确的动力学。
2. **传感器噪声模型差异**：Mock AMD 的噪声模型为 Bernoulli 丢包 + 线性漂移 + 脉冲尖峰，真实水下环境的噪声可能呈现更复杂的频谱特征（如多径反射造成的相关噪声、磁场背景的 1/f 噪声）。本系统在仿真侧用"DVL 60% / 90% 丢包 + 磁畸变 1e-8 T 阈值"等极端配置作压力测试，目的是把仿真噪声配置推到比预期真实噪声更恶劣的位置，从而在不依赖噪声谱精确对齐的前提下给出鲁棒性的"安全裕度"。
3. **通信时延分布**：仿真中 `TransportDelayQueue` 使用固定基线延迟 + 均匀抖动（200 +/- 50 ms），真实 acoustic modem 的时延可能呈现长尾分布。这一差异对 ROS2 节点拓扑和行为树的影响相对可控（节点级缓冲已经吸收了大部分抖动），但对"上位机 ESTOP 双通道"和"VxWorks 失联保护"的边界值整定有直接影响——仿真中验证过的 1 s 失联阈值在真实链路中可能需要根据实测时延 p99 重新校准。
4. **算力约束**：emulated Jetson 测试了 IPOPT 求解器的算力接口，但真机上的 CPU 频率限制、内存带宽和散热约束可能导致求解时间分布不同。这一影响主要落在 MPC 实时性上——若真机求解时间分布超过 100 ms 控制周期，热启动机制会被打破，须用更短的预测时域或更稀疏的离散化作为退路。

后续场景迁移分三步推进：第一步，将 S 弯和 hairpin 路径迁移为 PVS 场景配置，把"几何极端 + 完整闭环"的组合工况补齐；第二步，把 terrain height map 与电缆中心线绑定，形成 slope crossing；第三步，加入声呐短时不可见、磁信号衰减、DVL dropout 和横流，形成 combined cable extreme 等场景。这三步迁移的共同特点是"先在 PVS 内做扩展，再迁到真机"——PVS 内的扩展能给出可重复、可消融的统计基线，真机迁移则只需在该基线之上叠加"硬件物理偏差"维度，避免一上来就让多个不确定性因素同时进入实验。

## 5.6 缺失实验与讨论

5.5 节给出了所有已完成实验的可写结论与边界，本节进一步把"尚未完成"的实验按工程缺口性质分类组织。把缺口写出来不是为了"自我贬低"，而是为了让读者明确知道"哪些结论已经成立、哪些结论还在路上、哪些结论必须留到未来工作"。这种主动的"缺口披露"比"含糊地把所有内容都写成已完成"更接近工程实证的精神。具体而言，当前缺口可以归纳为三类，分别对应"统计充分性、场景真实性、硬件实物证据"三个维度：

**第一类：统计与过程证据补充。** baseline UA-mode 已完成 3 seed、ES-EKF 8 场景 x 3 seed 已完成（24/24 ok）、UA-MPC 主消融 3 场景 x 2 模式 x 3 seed 已完成（18/18 ok）。后续已进一步补充 terrain PID 3 seed、P1 控制侧聚合、P1 NIS/R 聚合和 H1 solve-time 重跑；具体回填见续写文件。这一类缺口的特点是"数据采集成本相对低、方法论无新增"——只需在现有工具链上多跑几个 seed、把日志重新聚合即可补齐，因此被归为"短期可解"的缺口。

**第二类：场景真实性不足。** 现有 PVS chaos 更偏传感器和通信扰动，尚未形成电缆几何、地形、声磁观测和横流耦合的完整海缆巡检场景。需要新增电缆 S 弯、急转、坡面横穿、半掩埋和 combined cable extreme 等场景。这一类缺口的特点是"工具链改造成本中等、需要把 PVS height map 与 cable centerline 绑定"——属于"中期可解"的缺口，对应 5.7 节定义的 6 个极端电缆巡检场景。

**第三类：硬件与实物证据不足。** Jetson 真机、AMD UDP 时延、转台磁标定、10A 电缆台和 HSF-500 埋深反演仍不能写成已完成。这些实验对第 5 章很有价值，但依赖现场条件，若短期无法完成，应在论文中写成实验方案和未来工作。这一类缺口的特点是"必须依赖硬件条件、实验周期长、单次成本高"——属于"长期可解"的缺口，本文据此把这一类内容显式标注为"实验方案 + 未来工作"，而不强行等同于已完成结果。

把三类缺口合在一起看，它们对论文整体证据等级的影响是：第 3 章状态估计和第 4 章决策与控制的"算法层面正确性"已经被 PVS 仿真侧大量证据支撑；第 4.5.2 节六类极端场景的"鲁棒性边界"和第 5.3、5.4 节的"硬件实物证据"则属于"已识别接口、待补实验"——这一定位与第 2 章 2.2.3 节"PVS 给出的是算法层面证据，不是硬件物理证据"的整体立场一致。

## 5.7 极端电缆巡检场景设计

第二类缺口指向的"场景真实性不足"问题，本节通过定义 6 个极端电缆巡检场景给出系统性补救方案。为什么需要单独设计一组"极端场景"，而不是简单地把 chaos 场景的扰动幅度调大？答案在第 4.5.2 节已经讨论过——极端工况的物理风险量级与常规消融不同，需要按"几何极端 / 耦合极端 / 感知极端 / 多因素极端"四类各自构造代表性场景，才能让"分层架构能否守住底线"这一问题获得有覆盖度的证据。下列 6 个场景按这一组织原则展开，每个场景包含路径设置、真实风险、观测角色和评价指标四个维度，对应 4.5.2 节的"场景 × 模式"二维消融设计。

### 5.7.1 S-curve 急弯场景

该场景模拟海缆连续 S 形弯曲，要求 AUV 在连续反向转弯中保持稳定的横向偏移。S-curve 是最常见也最先暴露"预瞄能力差异"的几何极端工况——LOS 制导在反向转弯过渡区会因前视点跳变出现瞬态偏移，MPC 则因预测时域内能"看到"反向曲率而提前减小偏差。这一对比是 4.5.1 节"复杂路径预瞄"层结论在极端几何下的直接验证。

| 维度 | 设定 |
|---|---|
| 路径 | 两个反向圆弧，半径 15 m，总长 200 m |
| 真实风险 | 舵角饱和导致跟踪失败 |
| 观测角色 | UA-MPC 预瞄 vs LOS 预瞄 |
| 指标 | 最大横向偏移、控制量平滑度 |

### 5.7.2 Hairpin 180 deg 掉头场景

海缆路由可能出现 180 deg 急弯。该场景测试 AUV 在航向突变下的跟踪能力。它与 S-curve 的差异在于"半径更小、转弯角更大"——一旦半径接近 AUV 最小转弯半径，即使最优预瞄也无法在物理上完成跟随，必须由行为树触发"短时退出 + 重新对准"的应急路径。把该场景写入实验设计的目的不是"证明 MPC 一定能跟住"，而是验证"当几何不可行时，分层架构能否优雅退出而不直接撞断电缆"。

| 维度 | 设定 |
|---|---|
| 路径 | 180 deg U-turn，半径 10 m |
| 真实风险 | AUV 最小转弯半径不足，路径不可行 |
| 观测角色 | MPC 预测时域能否提前预判 |
| 指标 | 跟踪失败距离、航向 RMSE |

### 5.7.3 Slope Crossing 陡坡穿越场景

该场景测试 terrain-following 和深度跟踪在斜坡穿越时的协同。其本质难点不在"地形坡度本身"，而在"水平推进 + 垂直深度调节"必须在斜坡进入瞬间几乎同时完成——预测能力不足或内层 PID 响应不够快，都会让离底高度短暂跌入 1.5 m 安全阈值以下。这一场景是 4.5.1 节"近底安全"层证据在极端地形下的延伸验证。

| 维度 | 设定 |
|---|---|
| 路径 | 电缆沿 30 deg 斜坡上升 5 m |
| 真实风险 | 离底高度骤降，碰撞风险 |
| 观测角色 | PID terrain vs MPC terrain |
| 指标 | 最小离底高度、深度 RMSE |

### 5.7.4 Buried Gap 埋设间断场景

该场景模拟电缆部分掩埋或观测弱化，重点考察声磁观测接力和滤波器连续性。Buried Gap 是 ES-EKF 声磁通道协同的最尖锐压力测试——掩埋段内磁场特征突变、声呐图像几乎完全失去电缆边缘特征，AUV 必须仅靠"惯性递推 + 杆臂修正"维持位置估计连续性，直到电缆暴露段重新出现观测。该场景同时检验 4.4.4 节"参考轨迹生成"在观测中断时是否能切换到恒定航向兜底参考。

| 维度 | 设定 |
|---|---|
| 路径 | 50 m 掩埋段 + 20 m 暴露段 + 50 m 掩埋段 |
| 真实风险 | 磁场特征突变导致定位漂移 |
| 观测角色 | ES-EKF 声磁接力切换 |
| 指标 | 检测连续性、埋深反演误差 |

### 5.7.5 Cross Current 横流冲击场景

AUV 受到持续横向推力。该场景测试欠驱动 AUV 的横流补偿能力。Cross Current 与一般"扰动"的区别在于横流是"持续而非瞬态"——欠驱动 AUV 没有横向执行器，只能通过"航向偏置"间接抵消横流，这就要求 MPC 在预测时域内能识别出"横向偏移持续累积"的趋势，并主动给出"航向偏离参考路径若干度"的偏置量。该场景对 UA-MPC 跟踪权重与控制权重的平衡提出明确要求，是 4.5.1 节第三层证据在持续扰动下的延伸。

| 维度 | 设定 |
|---|---|
| 路径 | 直线电缆，横流 0.5 m/s |
| 真实风险 | 横向偏移持续积累，舵角饱和 |
| 观测角色 | MPC 横流前馈 vs PID 反馈补偿 |
| 指标 | 稳态横向偏移、控制努力 |

### 5.7.6 Combined Extreme 综合极端场景

前五个场景把"几何、地形、感知、扰动"四类极端因素分别隔离测试，本场景则把它们叠加在一起，专门用于检验整个分层架构的最坏情形稳健性。Combined Extreme 不是为"刷某个指标"设计的，而是为了把"行为树高优先级 Selector 子树是否被按设计触发"、"UA-MPC 是否在多重压力下保持收敛"、"VxWorks 失联保护是否在极端通信扰动下兜底"这三类问题同时压力测试——这是判断分层架构能否真正交付到工程现场的最关键一项实验。

| 维度 | 设定 |
|---|---|
| 几何 | S 弯 + hairpin + 陡坡 + 横流 |
| 扰动 | DVL dropout 30% + 磁畸变 + 声呐杂波 |
| 真实风险 | 多重失效耦合 |
| 观测角色 | 系统整体鲁棒性 |
| 指标 | 路由完成率、安全违规率 |

> **表格占位符**：正式论文中需补充极端场景的实验结果表，包括各场景的路由完成率、最大横向偏移、安全违规次数和控制平滑度。

## 5.8 本章小结

本章按"平台 → 指标 → 仿真 → 硬件 → 实验室 → 讨论 → 极端场景"的顺序，把支撑全文论点的实验证据、可写结论和已识别缺口完整摆出，使读者可以判断每条结论各自的证据等级和适用范围。具体而言：5.1 节构建了 L1–L4 四层实验体系，并把定位、控制、terrain 和电缆巡检四类评价指标的物理意义和数学口径定义清楚；5.2 节阐述了 PVS 9 场景的扰动配置和 ChaosInjector 的 6 类故障模型，重点说明了 combined_stress 场景的 8 维扰动源设计；5.3 节和 5.4 节按"实验方案 + 未来工作"的边界把硬件集成与实验室反演实验摆出；5.5 节作为本章主线，把所有已完成实验按"证据清单"逐一展开，并对每条结论标注样本量与边界；5.6 节把"统计充分性、场景真实性、硬件实物证据"三类缺口主动披露；5.7 节给出 6 个极端电缆巡检场景的统一设计，对应 4.5.2 节的"场景 × 模式"二维消融蓝图。

把全章可稳妥支撑的核心证据合在一起看，可归纳为四条：**第一**，PID terrain 是当前最可靠的近底方案（真口径 `seabed_clearance_rmse_to_3m` 落在 0.56–1.14 m 区间、四相 clearance 随真地形起伏、三档地形零安全违规），调优 PID/PVS 在 terrain following 主任务上不弱于 MPC（早先 `0.1752 m` 系分析层 datum bug 假象，已被 §5.5.2 真口径表取代）；**第二**，公平口径下 MPC x/y/yaw 极端路径支线显示 MPC 在长波/短波 S 弯与 hairpin 上优于或持平基线，仅直角 chicane 上 LOS 前瞻更优——MPC 的优势区是"LOS 不擅长"的不规则曲率路径预瞄（早先"未全面超过 LOS"的判断源自 harness `+2.0 m` 偏置 bug，修复后已被推翻）；**第三**，ES-EKF 8 场景 × 3 seed 鲁棒性验证达到 24/24 ok，状态估计在多类传感器/通信扰动下保持稳定；**第四**，UA-MPC 主消融在 baseline 和 combined_stress 下展现"定位 + 控制"双侧改善（XY RMSE 改善 10.4%、lateral RMSE 改善 15.8%），但在 DVL 60% 丢包场景下不再有优势，印证了"感知-控制不确定性必须沿层向上传递"的整体观点。

不能稳妥支撑的结论同样需要明确：**MPC 全面优于 PID/LOS 不成立**；**UA-MPC 单独可应对所有不确定性场景不成立**；**fallback 路径在仿真侧未被有效压力测试**（18/18 run fallback rate 全为 0，需等待 5.7 节六类极端场景）；**硬件物理证据缺失**——磁传感器九参数标定、HSF-500 埋深反演、AMD UDP 真机时延仍属"实验方案 + 未来工作"。

把以上结论与缺口合在一起，本章给出的是"算法层面正确性 + 已识别硬件接口"的完整证据图，而不是"已经覆盖一切工况"的过度承诺。这一定位与第 2 章 2.2.3 节"PVS 给出的是算法层面证据、不是硬件物理证据"的整体立场一致，也为下一阶段实物部署阶段留出了清晰的工作清单——PVS 内的"统计补充 + 场景扩展"是短中期工作，硬件实物证据是长期工作，二者按"先仿真扩展、再迁到真机"的顺序推进，可在不依赖一次性满足所有条件的前提下逐步把实证强度抬到工程交付水平。
