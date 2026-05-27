# 基准测试

本文档说明项目中所有基准测试的使用方法。

## 三大类基准测试概览

| 类别 | 目的 | 主要脚本 |
|------|------|----------|
| 控制器对比 | PID vs MPC 性能评估 | `tools/control_benchmark_module.py` |
| 决策架构对比 | 行为树 vs FSM 对比 | `tests/benchmark_bt_vs_fsm.py` |
| 定位算法评估 | ES-EKF 性能分析 | `tools/offline_ekf_benchmark.py` |
| 透明度级别基准 | L1/L2/L3 三级 debug_level | `scripts/run_transparency_level_benchmark.sh` |

## 控制器基准测试（PID vs MPC）

### 运行方式

```bash
# 主脚本
python tools/control_benchmark_module.py

# 替代脚本
python tests/benchmark_pid_vs_mpc.py
```

### 对比指标

- **RMSE**：跟踪误差的均方根
- **超调量**：阶跃响应中超过目标值的最大百分比
- **稳态误差**：系统稳定后的残余偏差
- **控制量方差**：控制输出的波动程度（反映能耗与执行器磨损）
- **MPC 求解时间**：每步优化求解耗时（评估实时性）

### 测试场景

- **深度阶跃**：给定深度跳变，比较两种控制器的响应速度与精度
- **航向阶跃**：给定偏航角跳变，评估转向性能
- **电缆跟踪**：跟踪海底电缆路径，评估曲线跟踪能力

### MPC 独立测试

```bash
python tools/mpc_test.py
```

单独验证 MPC 控制器的求解收敛性与实时性能。

## 决策架构基准测试（行为树 vs FSM）

### 运行方式

```bash
python tests/benchmark_bt_vs_fsm.py
```

### 对比指标

- **响应延迟**：从事件触发到行为切换的耗时
- **状态振荡**：单位时间内状态切换次数（过高表示决策不稳定）
- **代码复杂度**：节点数/状态数、圈复杂度等
- **蒙特卡洛生存率**：随机扰动下任务成功完成比例

## 透明度级别基准测试

### 运行方式

```bash
bash scripts/run_transparency_level_benchmark.sh
```

### 工作流程

脚本自动遍历三个透明度级别：

| 级别 | 含义 | 行为 |
|------|------|------|
| L1 (Hold) | 最低透明度 | 仅保持位置/深度 |
| L2 (AnalyticalPath) | 中等透明度 | 执行解析式路径规划 |
| L3 (FullMission) | 最高透明度 | 完整任务执行 |

每级自动执行：
1. 启动完整 ROS2 栈
2. 设定对应的 `debug_level`
3. 启动 rosbag 录制
4. 运行预设时长
5. 停止并保存数据

### 输出目录结构

```
$AUV_DATA_ROOT/benchmarks/transparency/
├── L1_Hold/
│   ├── bags/
│   └── results/
├── L2_AnalyticalPath/
│   ├── bags/
│   └── results/
└── L3_FullMission/
    ├── bags/
    └── results/
```

## EKF 调参基准测试

### 离线基准对比

```bash
python tools/offline_ekf_benchmark.py --input bag.mcap --output-dir ./results
```

对比 Raw DR、Standard EKF、ES-EKF 三种方案的定位精度。

### 参数调优

```bash
# 全面调优（耗时较长，搜索范围广）
python tools/es_ekf_comprehensive_tuner.py --input bag.mcap

# 快速调优（缩小搜索范围，适合迭代验证）
python tools/es_ekf_quick_tune.py
```

调优工具会自动搜索 Q/R 矩阵参数，输出最优参数组合及对应的 RMSE。

## 简易 120s PVS Benchmark

```bash
bash scripts/run_benchmark.sh
```

执行一次 120 秒的标准 PVS 流程，自动启动仿真、控制器、导航、录制，结束后生成分析报告。适合快速回归验证。

## 集成测试

```bash
bash scripts/run_integration_test.sh
```

执行 7 步验证流程：

1. 环境依赖检查
2. ROS2 节点启动验证
3. 话题发布频率校验
4. 传感器数据有效性检查
5. 控制器响应测试
6. EKF 收敛性验证
7. 端到端任务完成确认

所有步骤通过后输出 `PASS`，任一步骤失败则输出详细错误信息。
