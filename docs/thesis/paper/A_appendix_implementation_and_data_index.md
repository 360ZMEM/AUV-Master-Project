# 附录 A：实现配置与数据源索引

本附录集中收纳第 4、5 章正文为保持叙述连贯而下沉的实现细节：包括仿真场景的标识与扰动配置、故障注入模型参数、模型预测控制的权重与约束默认值、求解器配置、评价指标的计算工具与数据通道、各项实验的数据源路径，以及端到端电缆探测证据链所涉及的代码、配置与复现脚本指针。正文各节在需要时以"见附录 A.x"的形式引用本附录，从而把"机理与结论"留在正文、把"可复现的具体取值与路径"归并到此处，既避免正文被实现符号淹没，也为后续实验复现和代码走查提供一份单一检索入口。

本附录中所列的配置键、文件路径、数据通道名称与参数默认值，均与当前代码库和实验产物目录一一对应；若正文数值与本附录出现不一致，以本附录为准并同步回改正文。

---

## A.1 仿真场景标识与扰动配置映射

第 5.2 节所述的 PVS 场景库由若干 YAML 配置文件定义，每个文件对应一类传感器或通信不确定性。下表给出场景标识、中文名称、扰动类型与严重程度的对应关系，正文引用场景时使用中文名称，此处保留其配置文件标识以便定位。

| 场景标识（配置文件） | 中文名称 | 扰动类型 | 严重程度 | 用途 |
|---|---|---|---|---|
| `scenario_baseline.yaml` | 干净环境基线 | 无 | — | 算法对照基线 |
| `scenario_dvl_dropout_10.yaml` | DVL 轻度丢包 | DVL 丢包 | 10% | 轻度速度观测丢失 |
| `scenario_dvl_dropout_30.yaml` | DVL 中度丢包 | DVL 丢包 | 30% | 中度速度观测丢失 |
| `scenario_dvl_dropout_60.yaml` | DVL 重度丢包 | DVL 丢包 | 60% | 重度速度观测丢失 |
| `scenario_dvl_dropout_90.yaml` | DVL 极重度丢包 | DVL 丢包 | 90% | 极重度速度观测丢失 |
| `scenario_mag_distortion_light.yaml` | 磁畸变（轻） | 磁饱和 | 阈值 1e-6 T | 轻度磁饱和 |
| `scenario_mag_distortion_heavy.yaml` | 磁畸变（重） | 磁饱和 | 阈值 1e-8 T | 重度磁饱和 |
| `scenario_sonar_clutter.yaml` | 声呐杂波 | 声呐成像噪声 | 固定参数 | 声呐噪声压力 |
| `scenario_combined_stress.yaml` | 综合压力场景 | 多扰动联合 | 见 A.1 下表 | 综合鲁棒性压力测试 |

每份场景 YAML 包含 `chaos`（故障注入）、`perception`（传感器噪声）、`flow`（流场）与 `mpc_mode`（消融模式）四个配置节。

综合压力场景（`scenario_combined_stress.yaml`）在单份配置内同时打开八个扰动源，对应第 5.2.2 节"模拟现场最不利组合"的物理意图，各扰动源的参数取值与物理意图如下：

| 扰动源 | 参数取值 | 物理意图 |
|---|---|---|
| 总线丢包 | `packet_loss_prob = 0.05` | 低带宽声学调制解调器 |
| DVL 丢包 | `drop_rate = 0.30`，窗口 `[1.0, 3.0] s` | 浊水/杂草遮挡导致的中等丢包 |
| IMU 漂移 | `bias_rate = 0.001` | 无温补 MEMS 慢漂移 |
| 深度尖峰 | `rate_hz = 0.05`，`amplitude_m = 0.5` | 约 20 s 一次的压力传感 EMI |
| 磁饱和 | `threshold = 1e-7 T` | 母船电磁场近场干扰 |
| 加速度计噪声 | `imu_acc_noise_scale = 1.5` | 振动耦合增强 |
| 声呐噪声 | `sonar_noise_scale = 2.0` | 浑浊浅水条件 |
| 海流 | `current_speed = 0.3 m/s` | 近海典型流速 |

## A.2 上位机仿真（Mock AMD）模块与故障注入模型参数

第 5.2.3 节所述的上位机仿真子系统由三个模块构成，分别模拟通信时延、多速率采样与故障注入。其模块职责与关键参数如下：

| 模块（工程实现） | 职责 | 关键参数 |
|---|---|---|
| 传输时延队列（`TransportDelayQueue`） | 模拟非确定性通信时延 | `base_delay_ms = 200`，`jitter_ms = 50` |
| 传感采样缓存（`SensorSampleCache`） | 模拟多速率传感器采样 | IMU 100 Hz、深度 50 Hz、磁 20 Hz、DVL 6 Hz |
| 故障注入器（`ChaosInjector`） | 故障注入 | 见下表 |

故障注入器实现的六类故障、其实现方式、概率模型与典型参数如下：

| 故障类型 | 实现方式 | 概率模型 | 典型参数 |
|---|---|---|---|
| DVL 冻结 | 保持上一次 DVL 速度输出 | 伯努利 + 窗口均匀采样 | `drop_rate = 0.3`，窗口 `[1, 3] s` |
| IMU 漂移 | 在加速度计输出上叠加线性偏置 | 连续时间随机游走 | `bias_rate = 0.001 m/s²/s` |
| 深度尖峰 | 在深度测量中叠加瞬态脉冲 | 泊松过程 + 固定幅值 | `rate_hz = 0.05`，`amplitude = 0.5 m` |
| 磁力计饱和 | 超过阈值后截断磁场输出 | 硬饱和限幅 | `threshold = 1e-7 T` |
| 总线丢包 | 随机丢弃 UDP 帧 | 伯努利 | `prob = 0.05` |
| 数据包乱序 | 交换连续帧的时间戳顺序 | 伯努利 | `rate = 0.01` |

需要说明的是，上述磁饱和阈值（1e-6 T / 1e-8 T / 1e-7 T）用于模拟传感器量程受限的情况，尚未与真实磁传感器噪声模型逐点对齐；正式论文中此处需补充噪声模型的参数来源、分布假设与真实传感器手册的对照。

## A.3 不确定性感知模型预测控制参数与消融变体开关

第 4.4.3 节所述的不确定性感知权重调整机制由一组参数控制，其默认值、含义与对应的消融变体如下表。表中 `(1 - conf)^α` 幂函数中的 α、低置信度缩放因子、sigmoid 陡峭度等，均在正文中以机理形式阐述，此处给出可复现的具体取值。

| 参数（配置键） | 默认值 | 含义 | 消融变体 |
|---|---|---|---|
| `mpc_mode` | `ua` | 基线 / 不确定性感知模式切换 | A0 对 A1 |
| `low_confidence_scale` | 3.0 | 低置信度下跟踪权重放大倍数 | A4（设为 0 退化为基线） |
| `low_confidence_control_scale` | 0.3 | 低置信度下控制代价缩放因子 | — |
| `confidence_alpha` | 1.5 | 跟踪权重幂指数 α | A3（设为 1.0 退化为线性） |
| `confidence_smoothness_k` | 8.0 | sigmoid 陡峭度 k | A2（设为 hard 关闭 sigmoid） |
| `confidence_threshold` | 0.6 | 置信度阈值 | — |
| `prediction_horizon` | 20 | 预测步数 N | — |
| `dt` | 0.1 | 时间步长（s） | — |

模式切换在实验中通过环境变量 `AUV_MPC_MODE` 实现（取 `baseline` 或 `ua`），以支持多场景 × 多模式 sweep 实验的自动化。第 5.5.8 节所述的消融变体设计一并列此，各变体通过对应的关键开关从默认配置派生：

| 变体标识 | 名称 | 关键开关 | 预期效果 | 状态 |
|---|---|---|---|---|
| A0 | 基线 MPC | `AUV_MPC_MODE=baseline` | 权重恒定的对照基线 | 已完成 |
| A1 | UA-MPC（默认） | `AUV_MPC_MODE=ua` | 定位误差与控制能量降低 | 已完成 |
| A2 | UA-MPC 去 sigmoid | `cov_to_conf.smoothing=hard` | UA 优势缩小 | 待执行 |
| A3 | UA-MPC α=1.0 | `low_conf_alpha=1.0` | 线性调整、稳定性下降 | 待执行 |
| A4 | UA-MPC scale=0 | `low_conf_scale=0.0` | 退化为基线 MPC | 待执行 |

## A.4 代价权重与约束默认值

第 4.4.2 节代价函数中各状态分量的跟踪权重与控制量惩罚权重默认值如下。深度跟踪在近底巡检中权重最大（深度误差直接关系离底安全裕度），航向次之，水平面位置与速度较为宽松。

| 权重项 | 符号 | 默认值 | 说明 |
|---|---|---:|---|
| x 位置跟踪 | `W_x` | 1.0 | 水平面位置 |
| y 位置跟踪 | `W_y` | 1.0 | 水平面位置 |
| 深度跟踪 | `W_z` | 5.0 | 近底安全裕度，权重最大 |
| 航向跟踪 | `W_ψ` | 3.0 | 路径几何跟随 |
| 前向速度跟踪 | `W_u` | 0.5 | 较宽松 |
| 垂向速度跟踪 | `W_w` | 1.0 | — |
| 航向指令惩罚 | `W_ψ_cmd` | 0.1 | 指令幅值 L2 惩罚 |
| 深度指令惩罚 | `W_z_cmd` | 0.1 | 指令幅值 L2 惩罚 |
| 推力指令惩罚 | `W_T` | 0.05 | 指令幅值 L2 惩罚 |

第 4.4.1 节连续动力学方程中的模型系数（航向增益、阻力、质量、深度到垂速的耦合增益、浮力项、俯仰限幅等），在仿真中取自 Fossen 型船舶动力学的经验估计值；其中俯仰限幅范围为 ±0.524 rad（±30°），推力经非负限幅确保不产生反向推力。

第 4.4.5 节的约束体系分硬约束与速率/带宽扩展约束两层，默认取值如下。

硬约束：

| 约束类型 | 表达式 | 默认范围 | 物理含义 |
|---|---|---|---|
| 航速下限 | `u_k ≥ min_speed` | 0.1 m/s | 确保舵效 |
| 航向指令限幅 | `ψ_cmd ∈ [min, max]` | [−π, π] rad | 航向指令合理性 |
| 深度指令限幅 | `z_cmd ∈ [min, max]` | [0, 50] m | 深度指令合理性（对齐最大下潜深度） |
| 推力下限 | `T_cmd ≥ min_thrust` | 0% | 防止推力清零失稳、禁止反推 |
| 推力上限 | `T_cmd ≤ max_thrust` | 100% | 执行器饱和 |

速率与带宽扩展约束（可分别通过 `enable_rate_constraints` 与 `enable_band_constraints` 启用/禁用，用于消融）：

| 约束类型 | 表达式 | 默认值 | 物理含义 |
|---|---|---|---|
| 深度指令速率 | `\|z_cmd_{k+1} − z_cmd_k\| ≤ Δz_max` | 0.5 m/step | 深度指令变化率 |
| 航向指令速率 | `\|ψ_cmd_{k+1} − ψ_cmd_k\| ≤ Δψ_max` | 8°/step | 航向指令变化率 |
| 深度指令带宽 | `\|z_cmd_k − z_current\| ≤ z_band` | 3.0 m | 深度指令偏离当前态上限 |
| 航向指令带宽 | `\|ψ_cmd_k − ψ_current\| ≤ psi_band` | 45° | 航向指令偏离当前态上限 |

## A.5 求解器配置

第 4.4.6 节所述的模型预测控制求解器采用 CasADi Opti 作为符号建模框架、IPOPT 作为内点法后端。工程实现上"构建一次、复用多次"（初始化时编译一次求解器结构，运行期仅更新参考、当前状态、置信度等参数值）、热启动（以上一周期最优控制序列右移一步作为初始猜测，通常在 5–10 次迭代内收敛，冷启动约需 30–50 次）、以及求解失败兜底（求解器返回失败时抛出异常，由上层根据配置回退到上一次输出或退化为开环设定点，这正是行为树"控制器异常 → 回退到 PID 基线"应急规则的接入点）三项机理详见正文。求解器的具体配置取值如下：

| 配置项 | 取值 | 说明 |
|---|---|---|
| `ipopt.tol` | 1e-4 | 收敛容差；MPC 快速迭代场景下足够，过低只会延长求解 |
| `ipopt.max_iter` | 100 | 迭代次数软上限；配合热启动实际平均迭代远小于此 |
| `print_level` | 0 | 关闭求解器日志输出，避免污染 ROS2 日志 |
| 控制周期 | 100 ms | 每周期重新求解一次 |
| 优化变量规模 | 约 360 | 20 步 × 6 维状态 × 3 维控制 |

限幅方面采用三层冗余：优化器内部限幅、MPC 输出后限幅、以及内层自动驾驶再限幅。仿真侧舵角限幅为 ±5°–±6°（在内层深度-航向自动驾驶处实现），角速度限制由 MPC 变体的航向带宽参数（`psi_band_deg`）控制，推力下限由 `min_thrust` 约束。任一层失效都不会让超界指令穿透到执行器。

## A.6 评价指标计算工具与数据通道索引

第 5.1.4 节定义的各类评价指标由如下工具从记录的数据中离线计算，其数据通道（ROS2 topic）与工具对应关系如下。

| 指标类别 | 计算工具 | 主要数据来源 |
|---|---|---|
| 定位指标（RMSE / NIS / CEP50 等） | `tools/analyze_bag.py` | MCAP bag 中的真值轨迹与估计轨迹 |
| 控制指标（求解时间 / 回退率 / 平滑度） | `tools/aggregate_control_metrics.py` | `/auv/controller/debug`、`/auv/control/mpc_cmd` |
| 多场景实验组织与聚合 | `tools/run_thesis_sweep.py` | 调用上述工具，输出 `summary.csv` 与 `aggregate.md` |

控制指标解析涉及的关键字段：控制量时间序列由 `/auv/controller/debug` 通道解析得到，据此计算控制量变化率（相邻样本差分取 L2 范数后求 RMS）；回退判定依据同一通道中的 `solver_status`（含 "FALLBACK"）与 `fallback_reason` 字段；求解时间字段 `solve_time_ms` 亦由该通道发布。需要说明的是，正文第 5.5.7 节记录了该字段在重跑口径下恒为 0 ms、计时语义待确认的情况，因此不能据此写具体求解性能结论。

单次实验由 `scripts/start_experiment.sh` 管理，多场景、多种子与控制模式的笛卡尔积由 `tools/run_thesis_sweep.py` 编排。每次运行生成独立的元数据、时序记录和离线评价目录，跑批层汇总为 `results.csv`，并将启动失败、空记录、记录损坏与离线评价失败分别写入失败清单。

## A.7 数据源索引表

第 5.5.1 节的证据清单表在正文中以中文结论与边界呈现，其对应的数据源路径统一编号收纳于此。正文引用某项实验数据时以"见附录 A.7（D0x）"的形式指向本表。

| 编号 | 实验类别 | 数据源路径 | 样本量 |
|---|---|---|---:|
| D01 | baseline UA 模式 3 seed | `log/thesis_sweep/20260612_163001_c2_baseline_3seed/results.csv` | n=3 |
| D02 | DVL dropout 四档 3 seed | `log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv` | n=3/档 |
| D03 | 磁/声呐/综合 4 场景 3 seed | `log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv` | n=3/场景 |
| D04 | UA-MPC 主消融（定位） | `log/thesis_sweep/20260612_172535_h1_uampc_main_ablation/results.csv` | 3 场景 × 2 模式 × 3 seed |
| D05 | H1 控制侧指标聚合（旧 bag） | `results/control_aggregates/20260612_172535_h1_uampc_main_ablation/` | 3 场景 × 2 模式 × 3 seed |
| D06 | H1 solve-time 重跑 | `log/thesis_sweep/20260613_173559_h1_uampc_main_ablation_solvetime/`、`results/control_aggregates/20260613_173559_h1_uampc_main_ablation_solvetime/` | 3 × 2 × 3 |
| D07 | P1 全场景控制侧聚合 | `results/control_aggregates/20260612_170618_p1_sensor_3seed/` | 8 场景 × 3 seed |
| D08 | P1 NIS/自适应 R 聚合 | `results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/` | 8 场景 × 3 seed |
| D09 | baseline 单次基准（定位/控制/决策） | `docs/experiment/benchmark_test_log.md` | n=1 |
| D10 | 60 s terrain PID/MPC | `docs/experiment/terrain_benchmark_log.md` | n=1/组 |
| D11 | terrain-following 真口径重跑 | `results/control/terrain_following_20260619_222639/` | n=1/组 |
| D12 | PID terrain low/mid/high 3 seed 复验 | `results/control/terrain_pid_seed_sweep_20260613_162512_terrain_pid_3seed/` + low/mid retry | n=3/档 |
| D13 | MPC x/y/yaw 极端路径（公平口径） | `/auv_data/results/control/mpc_xy_yaw_extreme/20260620_011831/` | n=1/场景 |
| D14 | 磁传感器杆臂/安装角标定（仿真） | `results/mag_extrinsics/fullflow_20260705_2145/` | n=1 全流程 |
| D15 | 代理电缆 6 场景 smoke | `log/proxy_cable_sweep/20260613_182825_cable_proxy_full6_smoke/`、`results/control_aggregates/20260613_182825_cable_proxy_full6_smoke/` | 6 场景 × 2 模式 × seed0 |
| D16 | 代理电缆 3 核心场景 smoke | `log/proxy_cable_sweep/20260613_171423_cable_proxy_smoke/`、`results/control_aggregates/20260613_171423_cable_proxy_smoke/` | 3 场景 × 2 模式 × seed0 |
| D17 | 海缆 DL/T 1278 数字孪生验收聚合 | `results/cable_ops_report/acceptance_multirun_fresh_20260706/` | 3 次 fresh run |
| D18 | DL/T 三次 fresh run 逐次目录 | `results/cable_ops_report/.../acceptance_fresh1_20260706_135331/`、`acceptance_fresh2_20260706_135757/`、`acceptance_fresh3_20260706_140156/` | 各 n=1 |
| D19 | DL/T 单次 fullflow 初步样张 | `/auv_data/bags/20260705_213816/` | n=1（limited） |
| D20 | Direction A 解耦轻量闭环 | `results/cable_ops_report/direction_a_decoupled/20260706_221801/` | n=1 smoke |
| D21 | PVS 闭环 distorted-prior 恢复 | `results/cable_ops_report/closedloop_e2e/_agg_{mid,heavy}_recovery/` | mid/heavy 各 3 次 fresh run |
| D22 | TMR8637 随附三轴测试报告 | `docs/thesis/figures/hardware/tmr8637_test_report/` | 1 份报告/编号 6# 模组三轴 |

## A.8 DL/T 1278 验收处理参数与评分脚本链

第 5.5.10 节所述的海缆巡检 DL/T 1278 风格数字孪生验收，其运行时到评分产物的处理链路与关键参数如下。

评分脚本链：运行时由 `/auv/cable/tracking` 通道落盘 MCAP bag，经 `extract_cable_tracking_jsonl.py` 提取逐帧记录，再由 `dlt1278_cable_report.py` 得到 DL/T 1278 风格评分与工业验收判定，最后由 `aggregate_cable_acceptance_runs.py` 对多次 run 聚合。评分链路与阈值定义详见 [16_cable_dlt1278_scoring_and_operator_products.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/16_cable_dlt1278_scoring_and_operator_products.md)，单次全流程记录见 [12_cable_mag_dlt1278_fullflow.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/12_cable_mag_dlt1278_fullflow.md)。

验收处理参数（canonical）：

```
--inspection-require-burial-ready
--inspection-max-route-progress-m 50
--inspection-max-abs-cross-track-m 2.0
--max-burial-sigma-over-limit-ratio 0.05
--start-health-sample-count 30
--start-max-route-progress-m 20
--start-max-abs-cross-track-m 5
```

多 run 聚合口径：`min_runs = 3`、`min_pass_ratio = 0.67`；据此三次 fresh run 全部 ready/pass 时聚合判定 `preliminary_acceptance_ready = True`。三次 run 有效窗口点数约 770–790，逐次目录见 A.7（D18）。

面向答辩/附录的上位机操作员工作流演示视频由 [tools/record_console_operator_video.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/record_console_operator_video.py) 在离屏模式（`QT_QPA_PLATFORM=offscreen`）下驱动真实上位机界面回放真实遥测生成，产物见 `../figures/console_operator_video/`；其为真实遥测的离线回放演示，非现场实时操作会话。

## A.9 端到端电缆探测证据链的代码、配置与复现指针

第 5.5.11 节所述的端到端电缆探测分层证据，涉及的运行时节点、配置、复现脚本与来源文档指针统一收纳于此，正文只保留结论、机理与边界。

运行时节点与算法接口：主仓电缆巡检运行时节点 [cable_tracking_node.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros/cable_tracking_node.py) 通过 `ensure_auv_master_mag_on_path()` 挂载专用磁探测仓库 `AUV-Master-Mag`，实例化其部署 API 中的核心跟踪流水线（`AuvMagTrackingPipeline`）、部署感知配置（`DeploymentPerceptionConfig`）与磁/导航/声呐输入结构，每帧（约 0.1 s）调用 `pipeline.step_with_guidance(...)` 推进跟踪，并通过 `/auv/cable/tracking` 通道发布结果（字段含 `cross_track_m`、`route_progress_m`、`burial_depth_m`、`burial_sigma_m`、`confidence`、`magnetic_snr_db`、`quality_flags`、`acceptance_flags`、`industrial_ready`）。

先验配置与适配器：主仓电缆巡检配置 [cable_tracking.yaml](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/cable_tracking.yaml) 使用 `scenario_name: case1`，先验航线由 `prior.yaml_points_ned`（`[[0,0,-1.5],[50,0,-1.5],[100,10,-1.6]]`）直接给出；先验适配器 [cable_prior_adapter.py](file:///home/auv_user/auv_ws/AUV-Master-Project/brain_linux/src/auv_control/auv_decision_ros/cable_prior_adapter.py) 构造电缆地图时不施加平移/旋转/缩放，本次专项在其中新增了默认关闭的先验位姿误差注入 hook（用于开环回放激励 distorted prior）。

关键复现脚本与配置：

| 用途 | 脚本 / 配置 |
|---|---|
| distorted-prior PVS 闭环复现 | `run_cable_closedloop_distorted.sh` |
| Direction A 解耦轻量闭环节点 | `decoupled_cable_sim_node.py` |
| Direction A 场景配置 | `cable_tracking_direction_a.yaml` |
| Direction A 运行入口 | `run_direction_a_decoupled_cable_sim.sh` |
| 埋深反演 | `burial_inversion.py` |
| PVS 部署侧桥接参数 | `bridge_params.protocol_udp.pvs.yaml` |
| 部署质量判定 | `deployment_quality.py` |

算法级 sub-repo 扫描（引用，n=1，纯仿真）：先验偏差三档承受边界、纯磁失效时序、最小可承受曲率半径、留一法机制分解、跨 lane 压力扫描等结论，来自专用磁探测仓库的离线场景扫描脚本（`tools/radius_boundary_sweep.py`、`ablation_sweep.py`、`lane_shortcut_stress_sweep.py` 等），原始叙述与插图保留在专用仓库文档 [28_声磁协同方法论合龙.md](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/docs/28_声磁协同方法论合龙.md) 与 [29_声磁协同实验设计与结果.md](file:///home/auv_user/auv_ws/AUV-Master-Project/AUV-Master-Mag/docs/29_声磁协同实验设计与结果.md) 中，本仓只引用不迁移。下一步计划登记见 [e2e_distorted_prior_next_plan.md](file:///home/auv_user/auv_ws/AUV-Master-Project/docs/thesis/paper/e2e_distorted_prior_next_plan.md)。

PVS 六自由度闭环恢复的关键达标条件（对应第 5.5.11 恢复能力小节）：缆布置于车体下方约 7.5 m、`autonomy_motion_model: kinematic_setpoint`、埋深门控参数 `burial_max_depth_m`、关闭自适应上限、之字形摆幅 0.6、走廊半宽 3.4 m——达标来自物理/控制层修正而非放宽阈值。

## A.10 代理电缆场景 sweep 执行命令与字段

第 5.7.7 节所述的 6 场景全量代理电缆 smoke，其执行命令与场景字段收纳于此。

执行命令：

```
tools/run_proxy_cable_sweep.py \
  --scenarios cable_s_curve_proxy,cable_hairpin_proxy,cable_slope_crossing_proxy,cable_buried_gap_proxy,cable_cross_current_proxy,combined_cable_extreme_proxy \
  --seeds 0 \
  --mpc-modes baseline,ua \
  --duration 30 \
  --label cable_proxy_full6_smoke
```

代理场景通过四组场景 YAML 字段的组合把第 5.7.1–5.7.6 节的六个极端场景表达为可运行替身：`cable_path.points_ned`（电缆中心线几何）、`digital_twin.terrain_noise_*` 与 `terrain_slope_deg`（近底地形复杂度）、`perception.noise` 与 `perception.sonar`（声磁观测质量）、`pvs.current_speed_mps` 与 `current_direction_deg`（横流压力）。运行状态 12/12 成功、控制聚合状态 `generated,12`，数据源见 A.7（D15）。此为低成本可运行替身，仅 seed0（n=1 smoke），不能写成基线 MPC 与 UA-MPC 的统计优劣。
