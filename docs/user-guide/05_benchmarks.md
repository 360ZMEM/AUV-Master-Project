# 基准测试

本文档是项目所有基准测试的**统一契约**，定义了命令行入口、输出路径规范和使用方法。

---

## 输出路径契约

所有基准测试结果统一存放在 `results/` 目录下：

```
results/
├── control/                    # 控制器对比（PID vs MPC）
│   └── benchmark_final/        # 最终可引用版
│       ├── pid/figures/         # PID 响应曲线
│       ├── mpc/figures/         # MPC 响应曲线
│       ├── control_benchmark_summary.md
│       ├── pid/pid_control_report.md
│       └── mpc/mpc_control_report.md
├── decision/                   # 决策架构对比（BT vs FSM）
│   └── benchmark_final/        # 最终可引用版
│       ├── figures/             # 对比图表
│       ├── decision_architecture_benchmark.md
│       └── thesis_reference.md
├── localization/               # 定位算法评估（ES-EKF）
│   ├── dvl_fixed_final/        # DVL修复后验证（最终版）
│   ├── enhanced_diagnosis/     # 增强版诊断分析
│   └── turning_convergence/    # 转向段收敛对比
├── tuning/                     # EKF 参数调优
│   ├── ekf_comprehensive/      # 综合调优结果
│   ├── es_ekf_tuning_report.md
│   └── tuning_report.md
└── archive/                    # 历史中间结果（不引用）
```

**新产生的结果应遵循此路径**——各脚本通过 `--output-dir` 参数指定输出到对应子目录。

---

## 一、控制器对比（PID vs MPC）

### 命令行入口

```bash
# 主基准脚本：PID + MPC 三场景同时测试
python tools/control_benchmark_module.py --output-dir results/control/<run_name>

# 替代入口（测试套件风格）
python tests/benchmark_pid_vs_mpc.py

# MPC 独立验证
python tools/mpc_test.py
```

### 测试场景

| 编号 | 场景 | 时长 | 评估重点 |
|------|------|------|----------|
| 1 | 深度阶跃 (0→5m) | 40s | 响应速度、超调量 |
| 2 | 航向阶跃 (0→30°) | 40s | 转向精度、稳态误差 |
| 3 | 电缆跟踪（正弦深度+余弦航向） | 60s | 综合路径跟踪能力 |

### 评估指标

- **RMSE**：跟踪误差均方根
- **上升时间 (90%)**：达到目标 90% 的时间
- **稳态误差**：系统稳定后残余偏差
- **最大误差**：跟踪过程中的峰值偏差
- **控制量**：舵角/推力的使用范围

### 当前最终结果

路径：`results/control/benchmark_final/`

| 场景 | 指标 | PID | MPC | 胜者 |
|------|------|-----|-----|------|
| 深度阶跃 | RMSE | 4.011 m | **2.028 m** | MPC (-49%) |
| 深度阶跃 | 上升时间 | 未达到 | **13.65 s** | MPC |
| 航向阶跃 | RMSE | **9.5°** | 12.4° | PID (-23%) |
| 航向阶跃 | 稳态误差 | **0.00°** | 0.17° | PID |
| 电缆跟踪 | 深度RMSE | **2.364 m** | 2.721 m | PID (-13%) |
| 电缆跟踪 | 航向RMSE | **9.1°** | 16.7° | PID (-45%) |

**结论**：MPC 深度阶跃响应显著更快（RMSE -49%），PID 航向和综合跟踪全面胜出。

---

## 二、决策架构对比（行为树 vs FSM）

### 命令行入口

```bash
python tests/benchmark_bt_vs_fsm.py --output-dir results/decision/<run_name>
```

### 评估维度

| 维度 | 方法 | 说明 |
|------|------|------|
| 响应延迟 | 10Hz Tick 统计 | 事件→行为切换的耗时 |
| 状态振荡 | 30s 切换计数 | Chattering Index |
| 圈复杂度 | 静态分析 V(G) | 代码认知负担 |
| 扩展成本 | 新增状态代码行 | 可维护性 |
| 蒙特卡洛生存率 | 500次随机扰动 | 鲁棒性 |

### 当前最终结果

路径：`results/decision/benchmark_final/`

| 维度 | BT | FSM | BT优势 |
|------|-----|-----|--------|
| 响应延迟 | 100 ms | 100 ms | 等价 |
| Chattering | 4.77 Hz | 4.77 Hz | 等价 |
| 存活率 | 100% | 100% | 等价 |
| 圈复杂度 | **15** | 40 | ↓62% |
| 紧急检查重复 | **1x** | 5x | ↓80% |
| 扩展成本 | **~8行/状态** | ~28行/状态 | ↓71% |

**结论**：运行时性能完全等价，BT 在代码可维护性全面胜出。

---

## 三、定位算法评估（ES-EKF）

### 命令行入口

```bash
# 离线三方案对比（Raw DR / Std EKF / ES-EKF）
python tools/offline_ekf_benchmark.py \
    --input <bag>.mcap \
    --output-dir results/localization/<run_name>

# 增强版诊断（含坐标系/时间戳/初始偏移检测）
python tools/enhanced_benchmark_analysis.py \
    --input <bag>.mcap \
    --output-dir results/localization/<run_name>

# 转向段收敛对比
python tools/analyze_turning_convergence.py \
    --input <bag>.mcap \
    --output-dir results/localization/<run_name>
```

### 评估指标

| 指标 | 含义 |
|------|------|
| XY RMSE (m) | 水平面位置误差均方根 |
| Z RMSE (m) | 深度误差均方根 |
| 3D RMSE (m) | 三维位置误差均方根 |
| CEP50 (m) | 50% 圆概率误差 |
| Max Drift (m) | 最大漂移量 |

### 当前最终结果

路径：`results/localization/dvl_fixed_final/`

| 算法 | XY RMSE | Z RMSE | CEP50 | Max Drift |
|------|---------|--------|-------|-----------|
| Raw DR | 17.697 m | 11.995 m | 15.122 m | 30.878 m |
| Std EKF | **0.915 m** | 11.994 m | 0.790 m | 1.604 m |
| ES-EKF | 0.949 m | 11.990 m | 0.833 m | 1.649 m |

**结论**：DVL 坐标系修复后，EKF XY 精度达亚米级 (0.9m)，相比 Raw DR 改善 95%。

---

## 四、EKF 参数调优

### 命令行入口

```bash
# 全面调优（308次评估，含热力图/灵敏度图）
python tools/es_ekf_comprehensive_tuner.py \
    --input <bag>.mcap \
    --output-dir results/tuning/<run_name>

# 快速调优（缩小范围，迭代验证用）
python tools/es_ekf_quick_tune.py

# 深度调优
python tools/es_ekf_deep_tune.py

# 单参数扫描
python tools/es_ekf_param_tuner.py
```

### 当前最终结果

路径：`results/tuning/`

| 参数 | 灵敏度 | 最优值 | 基线值 |
|------|--------|--------|--------|
| sigma_dvl | **强 (r=0.78)** | 0.005 | 0.03 |
| sigma_acc | 弱 | 0.01~0.2 | 0.08 |
| sigma_gyro | 极弱 | 0.001~0.01 | 0.01 |
| sigma_depth | 极弱 | 0.05 | 0.1 |

**结论**：sigma_dvl 是唯一显著敏感参数。系统性误差（时间戳、初始偏移）影响远大于参数调优。

---

## 五、透明度级别基准

### 命令行入口

```bash
bash scripts/run_transparency_level_benchmark.sh
```

### 三级含义

| 级别 | debug_level | 行为模式 | 评估重点 |
|------|-------------|----------|----------|
| L1 (Hold) | 1 | 定深定航稳定 | 底层控制精度 |
| L2 (AnalyticalPath) | 2 | 解析式轨迹跟踪 | 路径跟踪能力 |
| L3 (FullMission) | 0/3 | 完整任务执行 | 端到端性能 |

每级自动启动完整栈 + rosbag 录制 + 定时停止。

---

## 六、回归与集成测试

### 命令行入口

```bash
# 120s PVS 快速回归
bash scripts/run_benchmark.sh

# 7步集成测试
bash scripts/run_integration_test.sh

# 洋流鲁棒性（无/弱/强三场景）
python scripts/test_current_robustness.py

# 仿真等价性验证
bash scripts/run_sim_equivalence_check.sh
```

---

## 七、全栈实验录制与分析

### 命令行入口

```bash
# 标准实验（PVS, 120s, 自动rosbag录制）
bash scripts/start_experiment.sh --sim-backend pvs --duration 120

# 分析产出的MCAP数据
python tools/analyze_bag.py <bag_path>/*.mcap --output-dir ./figures

# 离线轨迹动画（无需HoloOcean）
python tools/replay_mcap_video.py <bag>.mcap --output replay.gif --fps 24
```

### 输出路径

实验录制输出到：`log/experiments/YYYYMMDD_HHMMSS/`

```
log/experiments/20260503_143351/
├── metadata.txt          # 运行参数快照
├── rosbag/               # 原始 ROS2 bag
├── rosbag_mcap/          # MCAP 格式
└── analysis/             # 分析产物（图表/统计）
```

---

## 八、如何新增一次基准测试

1. 选择对应类别的命令（见上各节）
2. 通过 `--output-dir results/<category>/<描述性名称>` 指定输出路径
3. 运行完成后检查生成的 Markdown 报告
4. 如为最终可引用版本，将路径更新到本文档对应章节

**命名规范**：
- 最终版使用 `benchmark_final` 作为目录名
- 中间迭代使用 `YYYYMMDD_HHMMSS` 时间戳
- 废弃结果移入 `results/archive/`
