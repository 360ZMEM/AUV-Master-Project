# 实验目录

本文档为毕设论文列出所有已完成和可以继续开展的仿真实验。

---

## 已完成实验

| 实验 | 脚本/命令 | 产出 | 论文章节参考 |
|------|----------|------|-------------|
| PVS 120s标准航迹跟踪 | `start_experiment.sh --sim-backend pvs --duration 120` | 轨迹RMSE、控制量曲线 | 控制器验证 |
| 透明度三级基准(L1/L2/L3) | `run_transparency_level_benchmark.sh` | 三级对比报告 | 决策系统分级验证 |
| PID vs MPC控制器对比 | `benchmark_pid_vs_mpc.py` | 超调量/稳态误差/方差对比 | 控制器选型 |
| BT vs FSM决策架构对比 | `benchmark_bt_vs_fsm.py` | 蒙特卡洛生存率/延迟对比 | 决策架构设计 |
| ES-EKF定位精度评估 | `offline_ekf_benchmark.py` | RMSE(1.523m)、CEP | 定位系统验证 |
| 洋流鲁棒性测试(三场景) | `test_current_robustness.py` | 无/弱/强洋流RMSE | 抗扰性分析 |
| 转向收敛对比 | `analyze_turning_convergence.py` | 转向段ES-EKF vs StdEKF | EKF性能评估 |
| DVL坐标系修复验证 | 修复前后对比数据 | RMSE 598m→12m | 系统集成调试 |
| EKF初始化增强验证 | 自动首帧对齐 | 消除6.2m系统偏移 | 算法优化 |
| Mock AMD故障注入测试 | `test_mock_amd_chaos.py` | 传感器故障场景下系统表现 | 鲁棒性 |
| 仲裁器无扰切换验证 | `test_headless_integration.py` | 5场景通过 | 安全机制 |
| 电缆巡检 clean-prior 端到端闭环验收 | `start_experiment.sh`（cable_acceptance profile） | DL/T 1278 scorecard、pass/ready | §5.5.10 |
| 电缆巡检 distorted-prior PVS 闭环恢复(3f) | `run_cable_closedloop_distorted.sh` + `score_cable_closedloop_recovery_runs.sh` | mid/heavy 各 3/3 ready/pass、聚合 summary | §5.5.11 (3f) |

---

## 可继续开展的实验

| 实验方向 | 说明 | 对应命令/配置 |
|----------|------|-------------|
| HoloOcean 3D完整环境长时测试 | 使用HoloOcean引擎（有视觉反馈） | `start_experiment.sh --duration 300` |
| 多轨迹类型对比 | 修改trajectory type(cable_like_3d/circle_3d) | 编辑sim_params.yaml中trajectory段 |
| PID参数敏感性分析 | 批量扫描Kp/Ki/Kd组合 | `tools/pid_tuner.py` |
| MPC预测步数影响 | 修改N=10/20/30 | 编辑algorithm/auv_mpc_controller.py |
| 真机协议全链路验证 | Protocol UDP + Mock AMD延迟 | `--bridge-backend protocol_udp --arbiter-profile` |
| 地形跟踪模式验证 | depth_mode=TERRAIN_FOLLOWING | `ros2 param set /auv_controller_node depth_mode TERRAIN_FOLLOWING` |
| 磁场跟踪模式验证 | heading_mode=MAGNETIC_TRACKING | 修改feature_flags或ros2 param set |
| 更长时实验(10min+) | 测试积分器饱和/EKF漂移 | `--duration 600` |
| 传感器降级场景 | DVL失效/IMU漂移下的系统表现 | 启用mock_amd chaos配置 |
| 上位机集成实验 | Console→Bridge→MockAMD→Decision全链路 | 运行console main.py + start_experiment.sh |

---

## 电缆巡检 distorted-prior 闭环恢复 (3f)：命令契约

这是当前电缆巡检最新的**正向结果**：在满足磁观测前提的 PVS 六自由度闭环中，在线先验修正被真实接受、闭环恢复被首次复现，mid/heavy 两档各 3/3 达 ready/pass（§5.5.11 (3f)）。

### 前置：启用在线先验修正

distorted-prior 变体配置在 `quality` 段打开开关（canonical `cable_tracking.yaml` 保持 `false`，即 §5.5.10 clean-prior 行为不变）：

```yaml
quality:
  enable_online_prior_alignment: true    # 默认 false；须先确认磁观测前提（缆在车下、By 主导）成立
```

同时桥接配置 `config/bridge_params.protocol_udp.pvs.yaml` 的 `pvs:` 段启用运动学位形响应：

```yaml
pvs:
  autonomy_motion_model: kinematic_setpoint
  kinematic_max_yaw_rate_deg_s: 12.0
  kinematic_depth_time_constant_s: 4.0
```

### 复现命令

```bash
# 1) fresh 闭环 run（mid/heavy 各 3 次），配方与 §5.5.10 clean fresh run 完全一致
bash scripts/run_cable_closedloop_distorted.sh

# 2) recovery-gate 两阶段评分 + 聚合
bash scripts/score_cable_closedloop_recovery_runs.sh
```

### 产物与验收

聚合结果落盘于：

```text
results/cable_ops_report/closedloop_e2e/_agg_mid_recovery/acceptance_runs_summary.json
results/cable_ops_report/closedloop_e2e/_agg_heavy_recovery/acceptance_runs_summary.json
```

验收判据：两档聚合 `preliminary_acceptance_ready=true`；mid max route offset 3.395 m（阈 3.4）、mean 2.412 m（阈 2.5）；heavy max 3.394 m、mean 2.318 m；两档 `valid_burial_ratio=1.0`、`confidence_p05≥0.902`。同源对照（在线修正 OFF 的 `*_prioroff`）全程 max route offset 约 15.3/20.1 m、窗口内点数为 0、0/3 invalid。

### 原理与边界

- 原理详解（磁导出横偏观测、在线先验修正、PVS 闭环恢复、recovery-gate 评分）见暗线 [12_cable_tracking_mag_integration.md](../internals/12_cable_tracking_mag_integration.md)。
- 部署 I/O 契约见 [real_deployment/08](../real_deployment/08_cable_inspection_io_contract.md) §6；孪生输出字段见 [real_deployment/09](../real_deployment/09_dlt1278_digital_twin_outputs.md)。
- 探索历史（从负结果 (3d) 到正结果 (3f)）见 [experiment/cable_distorted_prior_closedloop_20260707.md](../experiment/cable_distorted_prior_closedloop_20260707.md)。
- **诚实边界**：数字孪生确定性先验、静态位姿扭曲、缆在车下满足直线埋缆前提、窗口内判定、n=3/档；**不得**写成"通过真实海缆检测精度验收"。真实检测噪声、多种子统计、硬件实物三环仍待补。
