# 基准测试

本文档是项目所有基准测试的**统一契约**，定义了命令行入口、输出路径规范和使用方法。

---

## 输出路径契约

### 路径机制说明

基准测试的输出路径存在**两种模式**：

| 模式 | 触发条件 | 实际输出路径 |
|------|----------|-------------|
| 显式指定 | 传 `--output-dir results/...` 参数 | 项目内相对路径（如 `results/localization/my_run/`） |
| 默认模式 | 不传 `--output-dir` 或脚本无此参数 | `$AUV_DATA_ROOT/results/<类别>/YYYYMMDD_HHMMSS/` |

- `$AUV_DATA_ROOT` 优先取环境变量，其次读 `brain_linux/config/params.yaml` 中的 `auv_data_root`，最终回退 `/tmp/auv_data`
- 同一次进程内多个输出共享同一时间戳子目录

### 最终归档结构（项目内）

已确认的最终可引用版结果存放在项目内 `results/`：

```
results/
├── control/                    # 控制器对比（PID vs MPC）
│   └── benchmark_final/
├── decision/                   # 决策架构对比（BT vs FSM）
│   └── benchmark_final/
├── localization/               # 定位算法评估（ES-EKF）
│   ├── dvl_fixed_final/        # DVL修复后验证（最终版）
│   ├── enhanced_diagnosis/
│   └── turning_convergence/
├── tuning/                     # EKF 参数调优
└── archive/                    # 历史中间结果（不引用）
```

**最佳实践**：运行基准时显式传 `--output-dir results/<类别>/<描述性名称>` 可确保结果留在项目内。不传则输出到 `$AUV_DATA_ROOT` 下的临时位置。

---

## 一、控制器对比（PID vs MPC）

### 命令行入口

```bash
# 控制器模块入口（当前是库模块；2026-06-18 验证：直接执行会 exit 0 但不产出报告）
python tools/control_benchmark_module.py --output-dir results/control/<run_name>

# 替代入口（测试套件风格）
python tests/benchmark_pid_vs_mpc.py

# MPC 独立验证（无 --output-dir 参数，输出由 get_output_dir 决定）
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

### 依赖与注意事项

- 2026-06-18 验证：`tools/control_benchmark_module.py` 当前缺少 CLI main，不能作为可引用的一键产出入口；请使用 `tests/benchmark_pid_vs_mpc.py` 或补齐模块 CLI 后再归档结果。
- `mpc_test.py` 依赖 `/root/PythonVehicleSimulator/src`（硬编码路径）
- 依赖 CasADi + IPOPT（`pip install casadi`）
- MPC/PID 测试无需 rosbag 输入，完全独立运行

---

## 二、决策架构对比（行为树 vs FSM）

### 命令行入口

```bash
# 注意：此脚本无 --output-dir 参数，输出路径由 get_output_dir 决定
python tests/benchmark_bt_vs_fsm.py
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
| 振荡频率 | 0 Hz | 4.77 Hz | BT 无振荡 |
| 圈复杂度 | **15** | 40 | ↓62% |
| 扩展成本 | **~8行/状态** | ~28行/状态 | ↓71% |
| 蒙特卡洛存活率 | 100% | 100% | 等价 |

**结论**：运行时性能完全等价，BT 在代码可维护性全面胜出。

### 依赖与注意事项

- 依赖 `brain_linux/src/auv_decision/` 下的引擎模块（需 colcon build 后 PYTHONPATH 正确）
- 依赖 `mccabe` 包（`pip install mccabe`）
- 默认输出会写入 `$AUV_DATA_ROOT`；若当前用户无 `/auv_data` 写权限，先设置 `AUV_DATA_ROOT=$PWD/.auv_data`
- 2026-06-18 验证：本机 matplotlib 版本不接受 `Axes.boxplot(tick_labels=...)`，需改为兼容旧版本的 `labels=...` 后才能产出图表
- 此测试无需 rosbag 输入，纯内存计算

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

### 依赖与注意事项

- 需要安装 `mcap` 和 `mcap-ros2-support` pip 包
- `--output-dir` 传相对路径时输出到项目内；不传则输出到 `$AUV_DATA_ROOT/results/localization/...`
- 输入 MCAP 文件必须完整（有 footer），否则解析失败

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
# 标准实验（PVS + Zenoh, 120s, 自动rosbag录制）
bash scripts/start_experiment.sh --sim-backend pvs --bridge-backend zenoh_json --duration 120

# 分析产出的MCAP数据
python tools/analyze_bag.py <bag_path>/*.mcap --output-dir ./figures

# 离线轨迹动画（无需HoloOcean）
python tools/replay_mcap_video.py <bag>.mcap --output replay.gif --fps 24
```

### HoloOcean 后端 smoke 契约

HoloOcean 适合做短时高保真可视化、答辩视频和 MCAP 展示素材，不建议直接替代 PVS 做大规模多 seed sweep。当前建议先跑 15-30s smoke，确认 ROS topic 与分析工具契约，再决定是否扩展到正式实验。

```bash
# 仅验证 HoloOcean 仿真本体能进入主循环
bash scripts/start_lin_sim.sh sim --sim-backend holoocean

# 录制一个可供 ES-EKF/可视化工具消费的短 MCAP
AUV_DATA_ROOT=$PWD/.auv_data \
SIM_DELAY_S=3 \
bash scripts/start_experiment.sh \
  --sim-backend holoocean \
  --bridge-backend zenoh_json \
  --duration 15 \
  --record-bag \
  --bag-storage mcap \
  --wait-before-record 1 \
  --brain-ready-topic /auv/sensors/imu \
  --brain-ready-timeout 45 \
  --skip-layout

# 对 HoloOcean MCAP 运行定位 benchmark
python tools/offline_ekf_benchmark.py \
  --input .auv_data/bags/<run_id>/rosbag/rosbag_0.mcap \
  --output-dir results/localization/holoocean_smoke_<date>
```

注意事项：
- `start_foxglove_holoocean_ros.sh` 默认 `SIM_DELAY_S=10`。短实验若不覆盖该变量，brain 可能在实验结束前才启动，导致 bag 缺 `/auv/sensors/*`。
- HoloOcean + Zenoh 当前会发布 `/auv/sensors/ground_truth`、`imu`、`dvl`、`depth`，可被 `offline_ekf_benchmark.py` 消费。
- `rt/auv/sensors/altitude` 和 `rt/auv/sensors/forward_sonar` 已在 `common.protocol.REQUIRED_BY_TOPIC` 登记；若仍出现 unsupported topic，优先检查运行环境是否加载了最新源码/安装包。
- HoloOcean MCAP 的坐标转换参数仍需按结果复核。2026-06-18 smoke 中默认转换得到较小 Z RMSE，但 `--no-coordinate-transform` 会出现约 24m Z 误差，说明 truth/滤波输出的 Z 语义仍需统一确认。

### HoloOcean 可视化生成

```bash
# 使用已有 MCAP 生成曲线动画
python tools/capture_holoocean_video.py \
  --mcap-input <bag>.mcap \
  --mcap-render-mode curves \
  --output log/holoocean_curves.mp4 \
  --format mp4

# 同时生成曲线、agent 视角和 viewport 视角
python tools/capture_holoocean_video.py \
  --mcap-input <bag>.mcap \
  --mcap-render-all \
  --mcap-render-all-dir log/replays \
  --format mp4
```

已有产物表明该链路可以生成毕设展示素材，例如 `log/mcap_bundle_curves.mp4`、`log/mcap_bundle_holoocean_agent.mp4`、`log/mcap_bundle_holoocean_viewport.mp4`。正式答辩素材建议固定一条 60-120s MCAP 后再批量导出三类视频。

### 输出路径

实验录制输出到：`$AUV_DATA_ROOT/bags/YYYYMMDD_HHMMSS/`

```
$AUV_DATA_ROOT/bags/20260608_172454/
├── rosbag/
│   └── rosbag_0.mcap       # MCAP 格式录制
└── (metadata.yaml)
```

> **✅ 已修复：`--duration` 停止导致 MCAP 损坏**
>
> 此问题已修复（`scripts/start_experiment.sh` 第 176 行 `kill` → `kill -INT` + `sleep 2`）。
> 修复前的旧录制文件可能仍然损坏，可使用 `log/experiments/benchmark_120s/rosbag_mcap/rosbag_mcap_0.mcap` 作为已知完好的替代。

---

## 八、如何新增一次基准测试

1. 选择对应类别的命令（见上各节）
2. 通过 `--output-dir results/<category>/<描述性名称>` 指定输出路径（仅支持 `--output-dir` 参数的脚本）
3. 运行完成后检查生成的 Markdown 报告
4. 如为最终可引用版本，将路径更新到本文档对应章节

**命名规范**：
- 最终版使用 `benchmark_final` 作为目录名
- 中间迭代使用 `YYYYMMDD_HHMMSS` 时间戳
- 废弃结果移入 `results/archive/`
