# AUV_Master_Project

统一后的 AUV 项目根目录，目标是将仿真侧与 Linux ROS2 决策侧组织为一个可演进仓库。

---

## 📖 目录索引

- **[docs/INDEX.md](docs/INDEX.md)** — **从这里开始！** 完整的文档导航与快速检索

---

## 📁 项目结构

| 目录 | 说明 | 用途 |
|------|------|------|
| **common/** | 双端共享协议、枚举、物理常量 | 协议契约与常数定义 |
| **algorithm/** | 与环境无关的控制/导引算法 | PID、Guidance、ES-EKF、轨迹生成 |
| **sim_holoocean/** | HoloOcean 仿真与 Zenoh 桥接 | 仿真环境与跨进程通信 |
| **brain_linux/** | ROS2 Humble 工作区 | 决策栈：定位、控制、行为树 |
| **config/** | 仿真与桥接配置 | YAML 配置文件（仿真、桥接、实物） |
| **scripts/** | 一键启动脚本 | 快速启动各部分功能 |
| **docs/** | 原理说明与开发进度 | **详见下方文档快速指南** |
| **foxglove_layout_project/** | Foxglove 布局生成器 | 可视化系统配置与生成 |
| **msgs/** | 中间件无关消息映射 | Topic 与字段映射说明 |
| **tools/** | 辅助工具脚本 | 视频采集、数据处理等 |

---

## 🚀 快速启动

### 首次使用？
1. 阅读 [docs/INDEX.md](docs/INDEX.md) — 了解项目结构
2. 查看 [docs/原理说明.md](docs/原理说明.md) — 理解五层架构
3. 选择对应的启动指南（下面有链接）

### 选择你要做的事情

| 需求 | 推荐指南 | 相关命令 |
|------|--------|--------|
| **仅仿真验证** | [仿真启动指南](docs/guides/simulation_startup.md) | `bash scripts/start_lin_sim.sh sim` |
| **仿真 + 桥接** | [仿真启动指南](docs/guides/simulation_startup.md) | `bash scripts/start_lin_sim.sh both` |
| **ROS2 决策栈** | [决策启动指南](docs/guides/brain_startup.md) | `bash scripts/start_lin_brain.sh stack` |
| **完整端到端** | [端到端设置](docs/guides/end_to_end_setup.md) | `bash scripts/start_foxglove_holoocean_ros.sh` |
| **长实验 (120s)** | [实验配置指南](docs/guides/experiment_guide.md) | `bash scripts/start_experiment.sh --duration 120` |
| **参数调优** | [配置参数详解](docs/guides/configuration.md) | 编辑 `config/sim_params.yaml` |
| **遇到问题** | [文档索引](docs/INDEX.md#-调试与排障) | 查找对应排障指南 |

---

## 📚 文档指南

### 核心设计文档
- **[docs/原理说明.md](docs/原理说明.md)** — 五层架构、数据流、坐标系约定
- **[docs/字段真值表.md](docs/字段真值表.md)** — 所有 topic 和 JSON 字段的映射表

### 启动与配置
- **[docs/guides/simulation_startup.md](docs/guides/simulation_startup.md)** — 仿真侧启动（HoloOcean + Zenoh）
- **[docs/guides/brain_startup.md](docs/guides/brain_startup.md)** — 决策侧启动（ROS2 栈）
- **[docs/guides/end_to_end_setup.md](docs/guides/end_to_end_setup.md)** — 完整端到端闭环设置
- **[docs/guides/configuration.md](docs/guides/configuration.md)** — 所有 YAML 参数详解

### 调试与排障
- **[docs/联调调试记录_2026-03-21.md](docs/联调调试记录_2026-03-21.md)** — 全栈联调记录与已验证范围
- **[docs/控制回路问题定位与修复建议_2026-04-01.md](docs/控制回路问题定位与修复建议_2026-04-01.md)** — 当前问题与修复方向
- **[docs/protocol_udp联调复现与模式切换_2026-04-01.md](docs/protocol_udp联调复现与模式切换_2026-04-01.md)** — 二进制协议调试

### 进度与规划
- **[docs/开发进度.md](docs/开发进度.md)** — 当前阶段与后续计划
- **[docs/仲裁器长期路线图_2026-04-08.md](docs/仲裁器长期路线图_2026-04-08.md)** — 自主控制权仲裁设计

### 完整索引
**→ [docs/INDEX.md](docs/INDEX.md)** — 所有文档的分类索引与快速导航

---

## 💾 备份与版本控制

- **docs_backup/** — 原始文档备份（自动保存）
- **logs/** — 运行日志与实验数据
- **.github/copilot-instructions.md** — AI 助手的项目指导

## Foxglove 布局生成
```bash
cd foxglove_layout_project
/usr/bin/python3 -m foxglove_layout_project.generator.build_layout --pretty
```

如果要同时生成 mock topic 快照，使用：

```bash
/usr/bin/python3 -m foxglove_layout_project.generator.build_layout --with-mock-topics --pretty
```

一键联动启动：
```bash
cd scripts
bash start_foxglove_holoocean_ros.sh
bash start_foxglove_holoocean_ros.sh --bridge-backend protocol_udp --protocol-control-mode-byte 238
---

## 🔗 其他资源

### 工作流脚本
```bash
# 仿真等价性检查
bash scripts/run_sim_equivalence_check.sh --dry-run
bash scripts/run_sim_equivalence_check.sh

# HoloOcean 视频采集
python tools/capture_holoocean_video.py --format gif
python tools/capture_holoocean_video.py --capture-mode viewport --show-viewport --format mp4

# Foxglove 布局生成
cd foxglove_layout_project
python -m foxglove_layout_project.generator.build_layout --pretty
python -m foxglove_layout_project.generator.build_layout --with-mock-topics --pretty
```

### 向后兼容
```bash
# 直接调用 Python 脚本（仍支持）
cd sim_holoocean/apps
python main.py --config ../../config/sim_params.yaml
python run_zenoh_bridge.py --config ../../config/bridge_params.yaml
```

---

## ✅ 当前状态

| 功能 | 状态 | 备注 |
|------|------|------|
| HoloOcean 仿真 | ✅ 完成 | 可独立运行 |
| Zenoh 桥接 | ✅ 完成 | 跨进程通信正常 |
| ROS2 决策栈 | ✅ 完成 | 4 核心节点可运行 |
| Foxglove 可视化 | ✅ 完成 | 布局生成与导入 |
| 系统闭环 | ✅ 完成 | 仿真↔决策可交互 |
| auv_bridge | ⚠️ 进行中 | Zenoh JSON ↔ ROS2 DDS |
| 端到端回归 | ❌ 未完成 | 自动化测试脚本待完善 |

