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
