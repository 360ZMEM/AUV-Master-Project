# 第 5 章：实验与结果讨论
<!-- continuation: docs/thesis/paper/05_experiments_and_discussion_continued.md -->

## 5.1 实验平台方案与评价指标定义

### 5.1.1 虚实结合实验架构描述

| 层级 | 平台 | 作用 | 状态 |
|---|---|---|---|
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

### 5.5.1 当前已完成实验总表

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
| MPC x/y/yaw extreme | `/auv_data/results/control/mpc_xy_yaw_extreme/20260610_204314/` | n=1/场景 | MPC 对 yaw-only PID 有横向误差优势 | 未全面超过 LOS |
| PVS chaos 场景库 | `docs/thesis/05_scenario_recipes.md` | 9 个 YAML | 可支撑不确定性场景设计 | 未完整模拟海缆巡检 |
| Jetson emulated | `docs/thesis/06_jetson_deploy_emulated.md` | emulated | 可讨论算力接口 | 不能写真机绝对时延 |
| BT vs FSM | `docs/experiment/benchmark_test_log.md` | n=1 | 行为树单次效果可用 | 缺多场景对比 |

### 5.5.2 Terrain Following 主结果

| 指标 | PID baseline | PID terrain | MPC baseline | MPC terrain |
|---|---:|---:|---:|---:|
| duration_s | 59.5169 | 59.4934 | 58.8287 | 55.2146 |
| seabed_clearance_min_m | 2.7984 | 3.1725 | 2.8094 | 2.7978 |
| seabed_clearance_mean_m | 4.0207 | 3.1752 | 4.0768 | 3.6660 |
| seabed_clearance_std_m | 0.7941 | 0.0011 | 0.8013 | 0.6232 |
| seabed_clearance_rmse_to_3m | 1.2932 | 0.1752 | 1.3423 | 0.9121 |
| clearance < 1.5 m ratio | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

 benchmark 中，PID terrain 是最可靠的近底离底高度控制方案。MPC terrain 能改善 MPC baseline，但没有超过 PID terrain。PID terrain 的 `seabed_clearance_std_m = 0.0011 m` 说明离底高度几乎恒定，这得益于 PVS 内置 `depthHeadingAutopilot` 对地形的直接响应。

### 5.5.3 PID Terrain 地形强度消融

| terrain | RMSE to 3 m | mean (m) | std (m) | min (m) | violation < 1.5 m |
|---|---:|---:|---:|---:|---:|
| low | 0.0709 | 3.0218 | 0.0675 | 2.8612 | 0.0 |
| mid | 0.1735 | 3.1735 | 0.0028 | 3.1634 | 0.0 |
| high | 0.0586 | 2.9932 | 0.0582 | 2.8765 | 0.0 |

三档地形的 safety violation ratio 均为 0.0。其中 mid 地形的离底高度最稳定（std = 0.0028 m），low 和 high 地形的 std 略大但仍处于安全范围。这说明 PID terrain 在当前 PVS 地形模型下对地形强度的变化具有鲁棒性。

**当前边界**：本结果为 n=1/档，需扩展到 3 seed mean+/-std 才能作为论文主结论。

> 5.5.3 之后的新增实验补充，包括完整 P1 控制侧/NIS 聚合、terrain 3 seed retry 合并口径、代理电缆 smoke 与 6 场景扩展计划，已整理到 `docs/thesis/paper/05_experiments_and_discussion_continued.md`。下文保留原章节脉络，并清理明显的缓存/脚本输出污染。

### 5.5.4 MPC x/y/yaw 支线结果

 MPC x/y/yaw 极端路径实验中，将离线规划的 S 弯、急转和 hairpin 路径分别用 PID yaw-only、LOS 和 MPC 跟踪，比较横向跟踪误差（lateral RMSE）。数据源：`/auv_data/results/control/mpc_xy_yaw_extreme/`。

| 场景 | PID yaw-only lateral RMSE | LOS lateral RMSE | MPC best lateral RMSE | MPC 相对 yaw-only 改善 |
|---|---:|---:|---:|---:|
| s_turn_short_wave | 2.5965 m | 1.6574 m | 1.6345 m | 37.05% |
| chicane_90deg | 3.5961 m | 0.6586 m | 2.8230 m | 21.50% |
| hairpin_180deg | 4.6945 m | 4.6925 m | 2.8844 m | 38.56% |

**结论与边界**：
- MPC 在所有三个极端路径场景下对 PID yaw-only 均有显著的横向误差改善，改善幅度为 21.50%–38.56%。
- 但在 s_turn 和 hairpin 场景下，LOS 的 lateral RMSE 与 MPC best 接近甚至更优（s_turn: LOS 1.6574 m vs MPC 1.6345 m，差距很小）。这说明 MPC 对 yaw-only PID 的优势并不全面超过 LOS。
- 该支线结果为 n=1/场景，尚未扩展到多 seed 统计。作为支线结果，说明 MPC guidance-level 预瞄对极端路径有潜在优势，但尚不足以作为论文主结论。

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

 UA-MPC 消融的控制侧证据，使用 `tools/aggregate_control_metrics.py` 从 H1 主消融的 18 个 bag 中解析 lateral RMSE、MPC solve time、fallback rate、控制量变化率（control rate RMS）和安全违规率。数据源：`results/control_aggregates/20260612_172535_h1_uampc_main_ablation/control_aggregate_report.md`。

| 场景 | 模式 | ok/total | lateral RMSE mean+/-std | solve time mean (ms) | fallback rate | control rate RMS | safety violation |
|---|---|---:|---:|---:|---:|---:|---:|
| baseline | baseline-MPC | 3/3 | 0.0038+/-0.0004 m | nan | 0.0000+/-0.0000 | 0.14+/-0.01 | 0.0000+/-0.0000 |
| baseline | UA-MPC | 3/3 | 0.0037+/-0.0003 m | nan | 0.0000+/-0.0000 | 0.44+/-0.27 | 0.0000+/-0.0000 |
| dvl_dropout_60 | baseline-MPC | 3/3 | 0.0033+/-0.0003 m | nan | 0.0000+/-0.0000 | 0.13+/-0.06 | 0.0000+/-0.0000 |
| dvl_dropout_60 | UA-MPC | 3/3 | 0.0039+/-0.0013 m | nan | 0.0000+/-0.0000 | 0.19+/-0.22 | 0.0000+/-0.0000 |
| combined_stress | baseline-MPC | 3/3 | 0.0035+/-0.0002 m | nan | 0.0000+/-0.0000 | 0.14+/-0.07 | 0.0000+/-0.0000 |
| combined_stress | UA-MPC | 3/3 | 0.0029+/-0.0004 m | nan | 0.0000+/-0.0000 | 0.03+/-0.004 | 0.0000+/-0.0000 |

**结论与边界**：
- **Lateral RMSE**：在 combined_stress 场景下，UA-MPC 的 lateral RMSE（0.0029 m）优于 baseline-MPC（0.0035 m），改善约 15.8%。baseline 和 dvl_dropout_60 下两者差异较小（baseline: 0.0037 m vs 0.0038 m；dvl_60: 0.0039 m vs 0.0033 m）。
- **Fallback rate**：所有 18 次运行的 fallback rate 均为 0.0000，说明在该实验条件下两种模式都没有触发 fallback。这表明在当前 PVS 仿真环境中，控制器对传感器扰动的鲁棒性足够，未出现需要降级到安全模式的情况。
- **Control rate RMS**：UA-MPC 在 baseline 场景下控制量变化率（0.44）显著高于 baseline-MPC（0.14），说明 UA 权重在干净环境下可能使控制律更激进；但在 combined_stress 下反而更低（0.03 vs 0.14），说明在联合扰动下 UA 权重可能起到了平滑作用。
- **Safety violation**：所有 18 次运行均无安全违规。
- **MPC solve time**：由于 H1 旧 bag 中的 `/auv/controller/debug` 未发布 `solve_time_ms` 字段，当前表中 solve time 为 nan。已在 `brain_linux/src/auv_controller/auv_controller/auv_controller_node.py` 补充 debug payload（包含 `solve_time_ms`、`solver_status` 和 `fallback_reason`），后续重跑 H1 或 H2 时可记录该指标。

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

Sim-to-Real 迁移面临以下挑战：

1. **动力学模型偏差**：PVS 基于 Fossen 船舶动力学模型，水动力系数（`mass_u`, `drag_u`, `yaw_rate_gain` 等）为经验估计值，与真实 AUV 存在偏差。
2. **传感器噪声模型差异**：Mock AMD 的噪声模型为 Bernoulli 丢包 + 线性漂移 + 脉冲尖峰，真实水下环境的噪声可能呈现更复杂的频谱特征。
3. **通信时延分布**：仿真中 `TransportDelayQueue` 使用固定基线延迟 + 均匀抖动（200 +/- 50 ms），真实 acoustic modem 的时延可能呈现长尾分布。
4. **算力约束**：emulated Jetson 测试了 IPOPT 求解器的算力接口，但真机上的 CPU 频率限制、内存带宽和散热约束可能导致求解时间分布不同。

后续场景迁移分三步推进：第一步，将 S 弯和 hairpin 路径迁移为 PVS 场景配置；第二步，把 terrain height map 与电缆中心线绑定，形成 slope crossing；第三步，加入声呐短时不可见、磁信号衰减、DVL dropout 和横流，形成 combined cable extreme 等场景。

## 5.6 缺失实验与讨论

**第一类：统计与过程证据补充。** baseline UA-mode 已完成 3 seed、ES-EKF 8 场景 x 3 seed 已完成（24/24 ok）、UA-MPC 主消融 3 场景 x 2 模式 x 3 seed 已完成（18/18 ok）。后续已进一步补充 terrain PID 3 seed、P1 控制侧聚合、P1 NIS/R 聚合和 H1 solve-time 重跑；具体回填见续写文件。

**第二类：场景真实性不足。** 现有 PVS chaos 更偏传感器和通信扰动，尚未形成电缆几何、地形、声磁观测和横流耦合的完整海缆巡检场景。需要新增电缆 S 弯、急转、坡面横穿、半掩埋和 combined cable extreme 等场景。

**第三类：硬件与实物证据不足。** Jetson 真机、AMD UDP 时延、转台磁标定、10A 电缆台和 HSF-500 埋深反演仍不能写成已完成。这些实验对第 5 章很有价值，但依赖现场条件，若短期无法完成，应在论文中写成实验方案和未来工作。

## 5.7 极端电缆巡检场景设计

本节定义 6 个极端电缆巡检场景。这些场景覆盖了实际海缆路由中最具挑战性的几何、环境和传感器工况。

### 5.7.1 S-curve 急弯场景

该场景模拟海缆连续 S 形弯曲，要求 AUV 在连续反向转弯中保持稳定的横向偏移。

| 维度 | 设定 |
|---|---|
| 路径 | 两个反向圆弧，半径 15 m，总长 200 m |
| 真实风险 | 舵角饱和导致跟踪失败 |
| 观测角色 | UA-MPC 预瞄 vs LOS 预瞄 |
| 指标 | 最大横向偏移、控制量平滑度 |

### 5.7.2 Hairpin 180 deg 掉头场景

海缆路由可能出现 180 deg 急弯。该场景测试 AUV 在航向突变下的跟踪能力。

| 维度 | 设定 |
|---|---|
| 路径 | 180 deg U-turn，半径 10 m |
| 真实风险 | AUV 最小转弯半径不足，路径不可行 |
| 观测角色 | MPC 预测时域能否提前预判 |
| 指标 | 跟踪失败距离、航向 RMSE |

### 5.7.3 Slope Crossing 陡坡穿越场景

该场景测试 terrain-following 和深度跟踪在斜坡穿越时的协同。

| 维度 | 设定 |
|---|---|
| 路径 | 电缆沿 30 deg 斜坡上升 5 m |
| 真实风险 | 离底高度骤降，碰撞风险 |
| 观测角色 | PID terrain vs MPC terrain |
| 指标 | 最小离底高度、深度 RMSE |

### 5.7.4 Buried Gap 埋设间断场景

该场景模拟电缆部分掩埋或观测弱化，重点考察声磁观测接力和滤波器连续性。

| 维度 | 设定 |
|---|---|
| 路径 | 50 m 掩埋段 + 20 m 暴露段 + 50 m 掩埋段 |
| 真实风险 | 磁场特征突变导致定位漂移 |
| 观测角色 | ES-EKF 声磁接力切换 |
| 指标 | 检测连续性、埋深反演误差 |

### 5.7.5 Cross Current 横流冲击场景

AUV 受到持续横向推力。该场景测试欠驱动 AUV 的横流补偿能力。

| 维度 | 设定 |
|---|---|
| 路径 | 直线电缆，横流 0.5 m/s |
| 真实风险 | 横向偏移持续积累，舵角饱和 |
| 观测角色 | MPC 横流前馈 vs PID 反馈补偿 |
| 指标 | 稳态横向偏移、控制努力 |

### 5.7.6 Combined Extreme 综合极端场景

| 几何 | S 弯 + hairpin + 陡坡 + 横流 |
| 扰动 | DVL dropout 30% + 磁畸变 + 声呐杂波 |
| 真实风险 | 多重失效耦合 |
| 观测角色 | 系统整体鲁棒性 |
| 指标 | 路由完成率、安全违规率 |

> **表格占位符**：正式论文中需补充极端场景的实验结果表，包括各场景的路由完成率、最大横向偏移、安全违规次数和控制平滑度。

## 5.8 本章小结

本章构建了 L1–L4 四层实验体系，详细定义了定位、控制、terrain 和电缆巡检四类评价指标的数学公式和物理意义。介绍了 PVS 9 场景的完整配置，重点阐述了 combined_stress 场景的 8 维扰动源设计和 ChaosInjector 的 6 种故障模型。

Terrain Following 主结果表明，PID terrain 是当前最可靠的近底方案（`seabed_clearance_rmse_to_3m = 0.1752 m`）；PID terrain 地形强度消融中三档均无安全违规；MPC x/y/yaw 极端路径支线显示 MPC 对 yaw-only PID 有 21%–39% 横向误差改善，但未全面超过 LOS；ES-EKF 8 场景 x 3 seed 鲁棒性验证达到 24/24 ok；UA-MPC 主消融在定位侧 combined_stress 改善 10.4%，控制侧 lateral RMSE 改善 15.8%；H1 控制侧指标聚合中 18/18 run 无安全违规，fallback rate 全为 0。

UA-MPC 消融变体设计（A0–A4）中 A0/A1 已完成，A2–A4 待执行。Sim-to-Real 迁移面临动力学模型偏差、传感器噪声差异、通信时延分布和算力约束四类挑战。最后讨论了 6 个极端电缆巡检场景设计和当前三类实验缺口（统计充分性、场景真实性、硬件实物证据）。
