# AUV Master Project

自主水下机器人（AUV）硕士研究项目。集成了 PVS/HoloOcean 仿真、ROS2 决策控制栈、上位机系统和可视化工具链，支持从数字孪生、电缆巡检仿真到实物部署的完整开发流程。

当前主线已在 **Jetson Orin NX 25W / 8 核** 上复核：PVS + `protocol_udp` + ROS2 brain stack + cable tracking + rosbag 链路可以运行，60 s smoke 生成约 59.4 s 有效 bag。

---

## 子仓库

下面的命令可以把磁场探测专属模块加入到仓库：

```bash
git submodule update --init --recursive
```

## Jetson 60 秒 Smoke

```bash
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --preflight-clean \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration 60 \
  --record-bag \
  --bag-profile cable_acceptance \
  --wait-before-record 8 \
  --bag-finalize 15 \
  --auto-activate \
  --skip-layout \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_tracking_config:=/home/auv_dev/AUV-Master-Project/brain_linux/config/cable_tracking.yaml
```

这会启动 PVS/protocol_udp 电缆巡检 smoke，自动录制 rosbag，输出到 `$AUV_DATA_ROOT/bags/YYYYMMDD_HHMMSS/`。

检查 bag：

```bash
source /opt/ros/humble/setup.bash
ros2 bag info /auv_data/bags/<TS>/rosbag
```

通过条件：`/auv/sensors/magnetic`、`/auv/cable/tracking`、`/auv/control/setpoint` 三类 topic 均有非零消息。

---

## 文档入口

> **从这里开始 → [docs/INDEX.md](docs/INDEX.md)**

仓库级接手入口：

- [AGENTS.md](AGENTS.md) - AI/开发者协作协议、主线命令速记、禁止过度结论清单
- [prompt.md](prompt.md) - 下一轮 AI 接手提示词
- [docs/JETSON_DEPLOYMENT_CONTEXT.md](docs/JETSON_DEPLOYMENT_CONTEXT.md) - Jetson Orin NX 上的仿真电缆巡检、全链路仿真测试、依赖状态、性能结论和边界

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
# Jetson 本机可运行性 smoke（推荐先跑）
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --preflight-clean --sim-backend pvs --bridge-backend protocol_udp \
  --arbiter-profile --duration 60 --record-bag --bag-profile cable_acceptance \
  --wait-before-record 8 --bag-finalize 15 --auto-activate --skip-layout \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_tracking_config:=/home/auv_dev/AUV-Master-Project/brain_linux/config/cable_tracking.yaml

# PVS 快速实验
bash scripts/start_experiment.sh --sim-backend pvs --duration 120

# 模拟真机通信协议
bash scripts/start_experiment.sh --sim-backend pvs --bridge-backend protocol_udp --arbiter-profile --duration 120

# distorted-prior 闭环恢复（耗时，需先确认 smoke）
bash scripts/run_cable_closedloop_distorted.sh
bash scripts/score_cable_closedloop_recovery_runs.sh

# 透明度三级基准测试
bash scripts/run_transparency_level_benchmark.sh

# 仅启动上位机
cd console_soft/auv_console_pyside6 && python main.py

# PID vs MPC 控制器对比
python tests/benchmark_pid_vs_mpc.py

# 离线 EKF 定位分析
python tools/offline_ekf_benchmark.py --input <bag>.mcap --output-dir ./results
```

注意：当前 Jetson 环境未安装 `holoocean` 和 `casadi`。HoloOcean 3D 仿真、CasADi/MPC 相关路径需要单独补依赖后再宣称可运行。

---

## 主线配置文件（必须关心的 4 个）

| 文件 | 用途 |
|------|------|
| `config/sim_params.pvs.yaml` | 仿真实验核心参数（PID增益、轨迹、阈值） |
| `brain_linux/config/params.protocol_udp_arbiter.yaml` | 真机部署核心参数 |
| `brain_linux/config/feature_flags.yaml` | 功能开关（决策/控制/桥接各层使能） |
| `console_soft/auv_console_pyside6/console_config.yaml` | 上位机通信参数 |

---

## Jetson 当前状态

| 功能 | 状态 |
|------|------|
| Jetson Orin NX 25W / 8 核 | 已确认 |
| PVS 轻量仿真 | 可运行 |
| PVS + protocol_udp 电缆巡检 smoke | 可运行；60 s bag 约 59.4 s 有效数据 |
| `/auv/sensors/magnetic` side-channel | 可运行；最新 smoke 2704 条 |
| `/auv/cable/tracking` | 可运行；最新 smoke 452 条 |
| `/auv/control/setpoint` | 可运行；最新 smoke 891 条 |
| HoloOcean 3D 仿真 | 当前 Jetson 缺 `holoocean`，未确认 |
| Zenoh JSON 桥接 | 完成 |
| Protocol UDP 桥接 | 完成 |
| ROS2 决策栈 (5节点) | 完成 |
| 级联 PID 控制器 | 完成 |
| MPC 控制器 | 代码存在；当前 Jetson 缺 `casadi`，相关路径需补依赖 |
| ES-EKF 定位 | 完成 (RMSE 1.5m) |
| 行为树决策 | 完成 |
| 仲裁器安全机制 | 完成 |
| Mock AMD 故障注入 | 完成 |
| 上位机 (PySide6) | 完成 |
| Foxglove 可视化 | 完成 |
| 真机部署 | 配置就绪，待实物对接 |

### Jetson 性能结论

最新 25W/8 核 smoke：

| 指标 | 结果 |
|---|---:|
| 命令总墙钟 | 1m19.947s |
| bag 时长 | 59.406705384s |
| bag 消息数 | 21048 |
| bag 大小 | 5.7 MiB |

结论：业务段接近 1:1；第一次 20 s smoke 失败主要因为前序 `colcon build` 占用窗口，不是 PVS/cable tracking 依赖缺失。正式实验建议先完成构建，然后使用 `AUV_SKIP_BRAIN_BUILD=1`。

CPU 余量仍偏紧。正式 benchmark 前建议关闭 Firefox/桌面可视化负载，并考虑禁用非必要 viz bridge。当前还存在一个收尾脚本问题：`start_foxglove_holoocean_ros.sh` cleanup 阶段可能报 `BRIDGE_PID: unbound variable`，不影响本次 bag 产物，但需要后续修复。

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
