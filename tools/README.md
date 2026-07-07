# tools/ 脚本索引

本目录收录论文实验、数据分析、可视化、实机部署配套等一次性/半自动脚本。**文件一律保持在 `tools/` 顶层**（不按子目录物理拆分）——因为它们被 25 处 shell 脚本按 `tools/<name>.py` 路径调用、被 700+ 处文档链接引用，且每个脚本内以 `PROJECT_ROOT = Path(__file__).resolve().parents[1]` 定位仓库根，物理移动会一次性破坏所有引用。本文件即"逻辑分组索引"，用途分组仅在此文档维护，磁盘上不生成子目录。

已废弃/被取代的一次性调试脚本见 [archive/](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/archive/README.md)。

> **约定**：标 🟢 的是被 shell 脚本或活跃文档直接调用的入口脚本（改动需谨慎）；标 📦 的是被其他脚本 `import` 的库模块（非直接运行）；其余为手动运行的分析/绘图脚本。

---

## 1. 电缆巡检与 DL/T 1278 验收（cable inspection）

| 脚本 | 用途 |
|---|---|
| 🟢 [dlt1278_cable_report.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/dlt1278_cable_report.py) | 从 tracking JSONL 生成 DL/T 1278 式电缆巡检评分与验收产物（recovery gate / 巡检窗口 / burial-ready 分级）。被 `score_cable_closedloop_*.sh`、`run_cable_replay_one.sh` 调用 |
| 🟢 [extract_cable_tracking_jsonl.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/extract_cable_tracking_jsonl.py) | 从 MCAP rosbag 抽取 `/auv/cable/tracking` JSON 逐帧负载为 JSONL。评分链路第一步 |
| 🟢 [aggregate_cable_acceptance_runs.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/aggregate_cable_acceptance_runs.py) | 把多个 inspection_summary.json 聚合为验收报告（pass_ratio / preliminary_acceptance_ready / worst_run） |
| [make_pose_error_config.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/make_pose_error_config.py) | 生成带指定 `prior.pose_error` 档位（mid/heavy 平移/旋转/缩放）的 cable_tracking 配置变体 |
| [plot_cable_dlt1278_scorecard.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/plot_cable_dlt1278_scorecard.py) | 从 inspection_summary.json 画 DL/T 式验收记分卡 |
| [plot_cable_operator_products.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/plot_cable_operator_products.py) | 从报告目录生成面向操作员的电缆巡检图像产品 |
| [plot_cable_tracking_fullflow.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/plot_cable_tracking_fullflow.py) | 从 tracking JSONL 画全流程电缆跟踪补充图 |
| [plot_direction_a_online_prior.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/plot_direction_a_online_prior.py) | 画 Direction A 解耦轻量闭环的在线先验修正诊断（§5.5.11(3e)） |
| [plot_pvs_closedloop_recovery.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/plot_pvs_closedloop_recovery.py) | 画 PVS 六自由度闭环 distorted-prior 恢复对比图（§5.5.11(3f)：横偏恢复 + 验收收敛） |
| [make_cable_tracking_gif.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/make_cable_tracking_gif.py) | 从 tracking JSONL 生成论文用动画 GIF |
| [migrate_cable_visual_artifacts.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/migrate_cable_visual_artifacts.py) | 把电缆巡检报告产物迁移到论文 figure 资产目录 |
| 🟢 [run_proxy_cable_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_proxy_cable_sweep.py) | 用逐场景 bridge 配置跑低成本代理电缆场景（§5.7.7 六场景 smoke） |

## 2. 磁传感器杆臂/安装角标定（magnetometer extrinsics）

| 脚本 | 用途 |
|---|---|
| [calibrate_sensor_extrinsics_sim.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/calibrate_sensor_extrinsics_sim.py) | 纯脚本 ES-EKF 基准用的仿真外参标定 |
| [mag_extrinsics_apply_estimate.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mag_extrinsics_apply_estimate.py) | 把估计出的磁强计外参写入新配置文件 |
| [mag_extrinsics_calibration_run.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mag_extrinsics_calibration_run.py) | 生成第一阶段仿真磁强计外参标定记录 |
| [plot_mag_extrinsics_validation.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/plot_mag_extrinsics_validation.py) | 画磁杆臂标定验证产物 |
| [verify_mag_extrinsics_bag_proof.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/verify_mag_extrinsics_bag_proof.py) | 校验 MCAP rosbag 内磁杆臂/外参证据 topic |
| [aggregate_extrinsics_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/aggregate_extrinsics_benchmark.py) | 聚合 ES-EKF 外参基准结果 |
| [es_ekf_extrinsics_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/es_ekf_extrinsics_benchmark.py) | 纯脚本 ES-EKF 传感器外参基准 |
| [helical_cable_magnetic_scan.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/helical_cable_magnetic_scan.py) | F1 — 三相螺旋电缆漏磁空间扫描（论文 §2.3.2） |

## 3. ES-EKF 状态估计调优与基准（state estimation）

| 脚本 | 用途 |
|---|---|
| 🟢 [offline_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/offline_ekf_benchmark.py) | 基于 MCAP 回放的定位算法离线基准。被 `run_noise_scan.sh`、`run_4mode.sh` 调用 |
| [enhanced_benchmark_analysis.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/enhanced_benchmark_analysis.py) | 基于 MCAP 回放的定位算法增强版分析与诊断 |
| [es_ekf_comprehensive_tuner.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/es_ekf_comprehensive_tuner.py) | ES-EKF 综合参数调优（针对指定 MCAP 数据集） |
| [es_ekf_deep_tune.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/es_ekf_deep_tune.py) | ES-EKF 深度调优 + 算法改进验证 |
| [es_ekf_param_tuner.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/es_ekf_param_tuner.py) | ES-EKF 离线参数搜索调优 |
| [es_ekf_quick_tune.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/es_ekf_quick_tune.py) | ES-EKF 关键参数快速搜索 |
| [jitter_boundary_ekf_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/jitter_boundary_ekf_benchmark.py) | F3 — ES-EKF DVL 辅助的网络抖动边界测试（论文 §2.5.1 / §3.2.1） |
| [analyze_turning_convergence.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_turning_convergence.py) | 分析 ES-EKF vs StdEKF 在剧烈转向段的收敛速度差异 |
| 📦 [uncertainty_metrics.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/uncertainty_metrics.py) | 不确定性/新息后处理库（论文 §3.4），被聚合脚本 import |
| [aggregate_uncertainty_metrics.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/aggregate_uncertainty_metrics.py) | 从 thesis sweep results.csv 聚合 ES-EKF 不确定性/NIS 指标 |

## 4. MPC / PID 控制器基准与调参（control）

| 脚本 | 用途 |
|---|---|
| [mpc_test.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_test.py) | MPC 控制器离线测试（PVS 动力学验证 params.yaml，三场景基准） |
| [mpc_solve_microbench.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_solve_microbench.py) | MPC 求解器微基准（台架确定性 solve_time 测量，H1） |
| [mpc_xy_yaw_extreme_benchmark.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mpc_xy_yaw_extreme_benchmark.py) | 制导层 MPC 的 x/y/yaw 极端路径离线基准 |
| 📦 [control_benchmark_module.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/control_benchmark_module.py) | 控制算法基准测试库模块 |
| [pid_tuner.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/pid_tuner.py) | PID 控制器自动调优 v4 |
| [pid_tuner_pvs.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/pid_tuner_pvs.py) | PID 控制器自动调优 v5（PVS 后端，最终版） |
| [pid_pvs_tracking_plots.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/pid_pvs_tracking_plots.py) | 生成 PID/PVS 内环参考跟踪图 |
| [wp_c_depth_ab.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/wp_c_depth_ab.py) | WP-C 深度补偿离线 A/B 回查（buoyancy_term / ki_z 去留判定） |

## 5. 实验批量运行与聚合（sweep & aggregation）

| 脚本 | 用途 |
|---|---|
| 🟢 [run_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_thesis_sweep.py) | 论文实验 sweep 驱动器。被 `run_mag_sweep.sh`、`run_dvl_sweep.sh`、`run_combined_sweep.sh` 调用 |
| [aggregate_thesis_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/aggregate_thesis_sweep.py) | 把 run_thesis_sweep.py 的 results.csv 聚合为论文用表 |
| [aggregate_control_metrics.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/aggregate_control_metrics.py) | 从 MCAP bag 或 sweep 结果聚合控制侧指标 |
| [run_terrain_pid_seed_sweep.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/run_terrain_pid_seed_sweep.py) | 多地形 seed 跑 PID 地形跟踪并聚合（§5.5.3 三 seed） |
| [plot_terrain_following_figures.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/plot_terrain_following_figures.py) | 生成论文用地形跟踪图 |

## 6. MCAP bag 离线分析（bag analysis）

| 脚本 | 用途 |
|---|---|
| 🟢📦 [analyze_bag.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_bag.py) | MCAP 离线分析主工具（可视化 + 指标提取）。被 `run_terrain_benchmark.sh`、`run_transparency_level_benchmark.sh` 调用，并被 replay_mcap_video.py import |
| [analyze_mcap_experiments.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/analyze_mcap_experiments.py) | 批量扫描 MCAP 实验数据的异常检测（直接用 mcap SDK） |
| [mcap_period_stats.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/mcap_period_stats.py) | 周期与延迟 p95 后处理（论文 §5.5 / T7 §4） |

## 7. 回放与视频（replay & video）

| 脚本 | 用途 |
|---|---|
| [capture_holoocean_video.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/capture_holoocean_video.py) | HoloOcean 视频生成（优先从 MCAP 回放生成 GIF/MP4） |
| [replay_mcap_holoocean.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/replay_mcap_holoocean.py) | MCAP → HoloOcean 位姿驱动回放器 |
| [replay_mcap_video.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/replay_mcap_video.py) | MCAP 回放视频生成器（轻量级动画，import analyze_bag） |

## 8. Foxglove 与上位机控制台（Foxglove & operator console）

| 脚本 | 用途 |
|---|---|
| [foxglove_indexeddb_inject_layout.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/foxglove_indexeddb_inject_layout.py) | 把 Foxglove layout JSON 注入浏览器 IndexedDB 缓存 |
| [foxglove_layout_deeplink.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/foxglove_layout_deeplink.py) | 生成 Foxglove layout 链接与本地导入提示 |
| [foxglove_playwright_import_layout.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/foxglove_playwright_import_layout.py) | 用 Playwright 无文件选择器导入 Foxglove layout |
| [foxglove_public_loop.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/foxglove_public_loop.py) | Foxglove 公开页反馈回路脚手架 |
| [gui_console_dlt_probe.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/gui_console_dlt_probe.py) | 电缆 DL/T runtime 面板的离屏 PySide6 探针 |
| [gui_console_loop.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/gui_console_loop.py) | PySide6 控制台反馈回路脚手架 |
| [record_console_operator_video.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/record_console_operator_video.py) | 录制 PySide6 上位机操作员工作流演示视频 |

## 9. 实机部署硬件配套（real-deployment bring-up）

| 脚本 | 用途 |
|---|---|
| 🟢 [actuator_polarity_recorder.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/actuator_polarity_recorder.py) | S2 配套：从上行 $AUV 帧记录每路执行器极性/死区。被 `02_static_actuator.sh` 调用 |
| 🟢 [manual_protocol_injector.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/manual_protocol_injector.py) | 手动协议注入工具（UDP 二进制协议）。被 `02_static_actuator.sh` 调用 |
| 🟢 [shadow_diff_recorder.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/shadow_diff_recorder.py) | S3 影子导航配套：记录 \|Jetson_cmd − Human_cmd\| 跟踪误差。被 `03_shadow_navigation.sh` 调用 |
| 🟢 [single_setpoint_driver.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/single_setpoint_driver.py) | S4 配套：以恒定 setpoint 驱动决策栈、绕过行为树。被 `04_closed_loop_single.sh` 调用 |

## 10. 论文素材规划（thesis assets）

| 脚本 | 用途 |
|---|---|
| [plan_thesis_visual_assets.py](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/plan_thesis_visual_assets.py) | 生成论文静态图/动态 GIF 素材闭合计划 |

---

## 维护约定

- **新增脚本**：放在 `tools/` 顶层，命名沿用现有前缀约定（`analyze_*` / `aggregate_*` / `plot_*` / `run_*` / `es_ekf_*` / `pid_*` / `mpc_*` / `foxglove_*` / `mag_extrinsics_*`），并在本索引对应分组补一行。
- **废弃脚本**：`git mv` 到 [archive/](file:///home/auv_user/auv_ws/AUV-Master-Project/tools/archive/)，并在 archive 的 README 记录被取代原因。归档前先 `grep` 确认无 shell 脚本/活跃文档引用。
- **不要物理拆子目录**：脚本以 `Path(__file__).resolve().parents[1]` 定位仓库根、被大量 `tools/<name>.py` 硬路径引用，移动会破坏 shell 调用、文档链接与 sibling import。分组只在本文档维护。
