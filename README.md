# AUV Master Project

自主水下机器人（AUV）硕士研究项目。集成了仿真环境、ROS2 决策控制栈、上位机系统和可视化工具链，支持从纯仿真到实物测试的完整开发流程。

---

## 30 秒上手

```bash
cd scripts
bash start_experiment.sh --sim-backend pvs --duration 120
```

这会启动一个 120 秒的 PVS 仿真实验，自动录制 rosbag，输出到 `$AUV_DATA_ROOT/bags/YYYYMMDD_HHMMSS/`。

分析数据：
```bash
python tools/analyze_bag.py <bag路径>/*.mcap --output-dir ./figures
```

实时可视化：浏览器打开 Foxglove → 连接 `ws://localhost:8765`

---

## 文档入口

> **从这里开始 → [docs/INDEX.md](docs/INDEX.md)**

文档分为两条线：

| 维度 | 面向 | 内容 | 入口 |
|------|------|------|------|
| **明线** (user-guide) | 使用者 | 每个模块怎么用、按什么按钮、输出怎么读 | [docs/user-guide/INDEX.md](docs/user-guide/INDEX.md) |
| **暗线** (internals) | 开发者 | 系统内部原理、数据流、子系统协作 | [docs/internals/INDEX.md](docs/internals/INDEX.md) |

### 快速导航

| 我想... | 去看 |
|---------|------|
| 5 分钟跑通第一次仿真 | [快速开始](docs/user-guide/01_quick_start.md) |
| 了解 start_experiment.sh 所有参数 | [实验脚本详解](docs/user-guide/02_experiment_runner.md) |
| 使用上位机遥控/授权自主 | [上位机指南](docs/user-guide/03_console.md) |
| 分析 rosbag 数据 | [数据分析工具链](docs/user-guide/04_rosbag_analysis.md) |
| 运行基准测试(PID/MPC/EKF) | [基准测试](docs/user-guide/05_benchmarks.md) |
| 配置 Foxglove 可视化 | [Foxglove](docs/user-guide/06_foxglove.md) |
| 查看已做/可做的实验清单 | [实验目录](docs/user-guide/07_experiments_catalog.md) |
| 把系统部署到真机 | [真机迁移 SOP](docs/user-guide/08_real_hardware_sop.md)（速记） + [实物部署多 Level 路径](docs/real_deployment/INDEX.md)（完整 SOP） |
| 查配置文件参数含义 | [配置速查](docs/user-guide/09_config_reference.md) |
| 理解系统整体架构 | [架构总览](docs/internals/01_architecture.md) |
| 了解仲裁器安全机制 | [仲裁器](docs/internals/07_arbiter.md) |
| 了解二进制通信协议 | [协议说明](docs/internals/05_binary_protocol.md) |

---

## 项目结构

```
AUV-Master-Project/
├── algorithm/           控制/导引/定位算法（PID, MPC, ES-EKF, LOS, 轨迹生成）
├── brain_linux/         ROS2 Humble 工作区（决策栈 5 节点）
├── common/              双端共享协议、枚举、物理常量
├── config/              仿真与桥接 YAML 配置（4 种组合）
├── console_soft/        上位机（PySide6 主线 + C# 旧版参照）
├── docs/                文档体系（明线 + 暗线）
├── foxglove_layout_project/  Foxglove 布局生成器
├── scripts/             一键启动脚本（实验/仿真/决策/可视化）
├── sim_holoocean/       仿真环境（HoloOcean/PVS + Zenoh/UDP 桥接）
├── tests/               基准测试与集成测试
└── tools/               数据分析、调参、视频捕获工具
```

---

## 核心启动脚本链

```
start_experiment.sh            ← 顶层：实验录制入口
  └── start_foxglove_holoocean_ros.sh  ← 中层：统一启动器
        ├── start_lin_sim.sh           ← 仿真侧（HoloOcean/PVS + Zenoh Bridge）
        └── start_lin_brain.sh         ← 决策侧（ROS2 栈 colcon build + launch）
```

### 配置自动推导

| sim-backend | bridge-backend | 仿真配置 | 桥接配置 |
|-------------|---------------|----------|----------|
| holoocean | zenoh_json | sim_params.yaml | bridge_params.yaml |
| holoocean | protocol_udp | sim_params.yaml | bridge_params.protocol_udp.yaml |
| pvs | zenoh_json | sim_params.pvs.yaml | bridge_params.pvs.yaml |
| pvs | protocol_udp | sim_params.pvs.yaml | bridge_params.protocol_udp.pvs.yaml |

---

## 典型使用场景

```bash
# PVS 快速实验（最轻量，推荐日常使用）
bash scripts/start_experiment.sh --sim-backend pvs --duration 120

# HoloOcean 完整 3D 仿真
bash scripts/start_experiment.sh --duration 120

# 模拟真机通信协议
bash scripts/start_experiment.sh --sim-backend pvs --bridge-backend protocol_udp --arbiter-profile --duration 120

# 透明度三级基准测试
bash scripts/run_transparency_level_benchmark.sh

# 仅启动上位机
cd console_soft/auv_console_pyside6 && python main.py

# PID vs MPC 控制器对比
python tests/benchmark_pid_vs_mpc.py

# 离线 EKF 定位分析
python tools/offline_ekf_benchmark.py --input <bag>.mcap --output-dir ./results
```

---

## 主线配置文件（必须关心的 4 个）

| 文件 | 用途 |
|------|------|
| `config/sim_params.pvs.yaml` | 仿真实验核心参数（PID增益、轨迹、阈值） |
| `brain_linux/config/params.protocol_udp_arbiter.yaml` | 真机部署核心参数 |
| `brain_linux/config/feature_flags.yaml` | 功能开关（决策/控制/桥接各层使能） |
| `console_soft/auv_console_pyside6/console_config.yaml` | 上位机通信参数 |

---

## 当前状态

| 功能 | 状态 |
|------|------|
| PVS 轻量仿真 | 完成 |
| HoloOcean 3D 仿真 | 完成 |
| Zenoh JSON 桥接 | 完成 |
| Protocol UDP 桥接 | 完成 |
| ROS2 决策栈 (5节点) | 完成 |
| 级联 PID 控制器 | 完成 |
| MPC 控制器 | 完成 |
| ES-EKF 定位 | 完成 (RMSE 1.5m) |
| 行为树决策 | 完成 |
| 仲裁器安全机制 | 完成 |
| Mock AMD 故障注入 | 完成 |
| 上位机 (PySide6) | 完成 |
| Foxglove 可视化 | 完成 |
| 真机部署 | 配置就绪，待实物对接 |

---

## 实物部署 Real Deployment

仓库提供从仿真到真机的**多 Level 实施路径**，每阶段独立 shell 入口、独立通过判据、独立失败回退：

```
S0 静态自检  →  S1 链路审计  →  S2 静态执行器极性  →  S3 影子导航  →  S4 单点闭环  →  S5 全自主
                                                                                       └ KS 急停（任何阶段可触发）
```

三种 target 共用同一套脚本骨架：
- `mock` — 默认；用 mock_amd_server.py 在 PC 本机回环验证
- `vxsim` — 把 mock 换为 csd_vx6.8_vxsim VxWorks 仿真
- `real` — 真机；需 `--i-have-physical-auv` 显式确认

文档与脚本入口：

| 类别 | 入口 |
|---|---|
| SOP 体系（预先规约） | [docs/real_deployment/INDEX.md](docs/real_deployment/INDEX.md) |
| 过程日志（事后记录） | [docs/experiment/real_deployment/INDEX.md](docs/experiment/real_deployment/INDEX.md) |
| 现场速记表 | [docs/user-guide/08_real_hardware_sop.md](docs/user-guide/08_real_hardware_sop.md) |
| 阶段 shell 脚本 | [scripts/real_deployment/](scripts/real_deployment/) |
| 急停 | [scripts/real_deployment/kill_switch.sh](scripts/real_deployment/kill_switch.sh) |

最小命令（mock target，dry-run 不发实弹）：

```bash
RD_DRY_RUN=true bash scripts/real_deployment/00_static_preflight.sh --target mock
RD_DRY_RUN=true bash scripts/real_deployment/01_link_audit.sh --target mock
# ... 02..05 同前缀
```
