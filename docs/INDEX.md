# 📚 AUV_Master_Project 文档索引

欢迎来到 AUV Master Project 的文档中心。这个索引将帮助你快速找到需要的信息。

---

## 🚀 快速开始

**首次接触本项目？**→ 从这里开始：
1. [原理说明.md](原理说明.md) — 了解项目的五层分层架构和核心设计原则
2. [字段真值表.md](字段真值表.md) — 查看所有 topic 和数据字段的完整映射

**先做一次最小烟测？**→ 直接看这里：
- [attacker_station 烟测与开关说明](guides/attacker_station_smoke_test.md) — 攻击站命令行开关、最小回路烟测与进度确认
- 建议命令：`/usr/bin/python3 scripts/attacker_station.py --profile heartbeat --duration 1 --rate-hz 2 --response-timeout-s 0.2 --no-csv --no-live-report`

**想要快速启动系统？**→ 查看具体指南：
- [仿真侧启动](guides/simulation_startup.md) — 如何启动 HoloOcean 仿真与 Zenoh 桥接
- [决策侧启动](guides/brain_startup.md) — 如何启动 ROS2 决策栈
- [完整联动](guides/end_to_end_setup.md) — 从仿真到决策的完整闭环

---

## 📖 核心设计文档

这些文档解释了系统的核心架构和设计哲学。

### 架构与设计
- **[原理说明.md](原理说明.md)** — 系统的五层分层架构、数据流、坐标系约定
- **[字段真值表.md](字段真值表.md)** — Zenoh topic 和 JSON 键名的完整映射表

### 协议与接口
- **[实物通信协议对接建议_2026-03-31.md](实物通信协议对接建议_2026-03-31.md)** — 与水下实物的二进制协议设计与映射建议

---

## 🛠️ 启动与配置指南

### 快速启动脚本
根据你的需求，选择对应的启动方式：

| 场景 | 命令 | 文档 |
|------|------|------|
| **仿真独立运行** | `bash scripts/start_lin_sim.sh sim` | [仿真启动指南](guides/simulation_startup.md) |
| **仿真 + Zenoh 桥接** | `bash scripts/start_lin_sim.sh both` | [桥接配置](guides/bridge_setup.md) |
| **ROS2 决策栈** | `bash scripts/start_lin_brain.sh stack` | [决策启动指南](guides/brain_startup.md) |
| **完整端到端** | `bash scripts/start_foxglove_holoocean_ros.sh` | [端到端设置](guides/end_to_end_setup.md) |
| **长实验 benchmark** | `bash scripts/start_experiment.sh --duration 120` | [实验配置](guides/experiment_guide.md) |

### 配置参数
- **[配置参数详解](guides/configuration.md)** — `config/` 目录下所有 YAML 文件的参数说明
- **[Foxglove 配置指南](guides/foxglove_setup.md)** — 可视化界面的布局配置与调试

---

## 🔧 调试与排障

遇到问题？这些资源可以帮助你快速定位和解决。

### 联调与验收
- **[联调调试记录_2026-03-21.md](联调调试记录_2026-03-21.md)** — 系统全栈联调的完整记录与已验证的工作范围
- **[联调验收摘要_2026-03-21.md](联调验收摘要_2026-03-21.md)** — 联调验收的检查项与最终结论
- **[综合验证报告_Shadow_RawDR_决策回放.md](综合验证报告_Shadow_RawDR_决策回放.md)** — 仿真与决策回放的验证报告

### 仿真调试
- **[PVS 调试速查](guides/pvs_debugging.md)** — PVS 仿真后端的快速调试指南
  - [PVS 全流程 runbook](guides/pvs_full_runbook.md) — 完整的 PVS 使用流程
  - [PVS 调试排坑记录](PVS调试排坑记录.md) — 已知问题与解决方案
- **[HoloOcean 调试指南](guides/holoocean_debugging.md)** — HoloOcean 环境的联调与排障
  - [HoloOcean 日志解读](holoocean_brain_linux日志解读指南_2026-03-21.md)
  - [HoloOcean 视频采集](guides/holoocean_video_capture.md)

### 协议与通信
- **[protocol_udp 联调复现与模式切换_2026-04-01.md](protocol_udp联调复现与模式切换_2026-04-01.md)** — 新旧桥接模式的切换与完整复现步骤
- **[控制回路问题定位与修复建议_2026-04-01.md](控制回路问题定位与修复建议_2026-04-01.md)** — 当前控制问题、关联参数与修复方向

### 测试与验证
- **[测试与验证指南](guides/testing_guide.md)** — 单元测试、集成测试、端到端测试、回归测试
  - 协议验证测试
  - 坐标系统一验证
  - 性能基准测试
  - CI/CD 集成
- **[attacker_station 烟测与开关说明](guides/attacker_station_smoke_test.md)** — 攻击站命令行开关、烟测流程与进度确认

### 高级主题
- **[Mock AMD 真实性测试蓝图](guides/mock_amd_testing.md)** — 硬件合约与模拟设备的验证
- **[Foxglove 布局生成器调试](guides/foxglove_generator_debug.md)** — 布局 schema 与生成器的深度调试

---

## 📊 开发进度与规划

### 当前进度
- **[开发进度.md](开发进度.md)** — 项目当前阶段、已完成功能、进行中的工作、后续计划

### 长期规划
- **[仲裁器长期路线图_2026-04-08.md](仲裁器长期路线图_2026-04-08.md)** — 自主控制权仲裁的设计与长期演进规划

### 高级功能
- **[HoloOcean 脚本说明](guides/holoocean_ros_scripts.md)** — Foxglove、HoloOcean、ROS 的脚本集成说明
- **[Foxglove 整合落地计划_2026-03-24.md](Foxglove整合落地计划_2026-03-24.md)** — 可视化系统的完整规划与实施方案

---

## 📋 文档分类速查表

### 按用途
| 用途 | 推荐文档 |
|------|--------|
| **我是新手** | 原理说明.md → 字段真值表.md → 仿真启动指南 |
| **我要启动仿真** | 仿真启动指南 → 配置参数详解 |
| **我要启动 ROS2** | 决策启动指南 → 配置参数详解 |
| **我要完整闭环** | 端到端设置 → 联调调试记录 |
| **我要调试问题** | 控制回路问题定位 → 对应的排障指南 |
| **我要看可视化** | Foxglove 配置指南 → 布局生成器调试 |

### 按系统模块
| 模块 | 关键文档 |
|------|--------|
| **仿真(HoloOcean)** | 原理说明 → PVS 调试 → HoloOcean 调试 |
| **桥接(Zenoh)** | 字段真值表 → protocol_udp 联调 → bridge 设置 |
| **决策(ROS2)** | 决策启动指南 → 配置参数 → 仲裁器设计 |
| **可视化(Foxglove)** | Foxglove 配置 → 布局生成器 → Foxglove 整合规划 |
| **实物对接** | 实物通信协议建议 → protocol_udp 联调 |

---

## 🔗 其他资源

### 代码与脚本
- **scripts/** — 一键启动脚本（sim、brain、experiment 等）
- **common/** — 双端共享的协议、枚举、物理常量
- **config/** — YAML 配置文件（sim_params、bridge_params 等）

### 相关目录
- **foxglove_layout_project/** — Foxglove 布局生成器源代码
- **docs_backup/** — 原始文档备份（归档用）

---

## 📝 文档贡献指南

若你想改进现有文档或添加新内容：

1. **内容修改** — 直接编辑对应的 `.md` 文件
2. **新增文档** — 在 `guides/` 目录下创建新文件，并在本 INDEX.md 中添加对应链接
3. **备份** — 原始版本自动保存在 `docs_backup/` 中

### 文档命名约定
- **核心设计**：`原理说明.md`、`字段真值表.md` （无日期后缀）
- **启动指南**：`guides/` 目录下，简洁命名，如 `simulation_startup.md`
- **调试记录**：包含日期后缀，如 `联调调试记录_2026-03-21.md`
- **长期规划**：包含日期后缀，如 `仲裁器长期路线图_2026-04-08.md`

---

## ❓ 快速常见问题

**Q: 我应该从哪个文档开始？**  
A: 从[原理说明.md](原理说明.md) 开始，了解架构后再选择具体的启动指南。

**Q: 怎么知道某个参数的含义？**  
A: 查看[字段真值表.md](字段真值表.md) 获取 topic/JSON 字段，查看[配置参数详解](guides/configuration.md) 获取 YAML 参数。

**Q: 系统无法启动？**  
A: 首先查看对应的[启动指南](guides/simulation_startup.md)，然后根据具体错误查看[调试指南](#🔧-调试与排障)。

**Q: 我想看完整的联调历史？**  
A: 查看[联调调试记录_2026-03-21.md](联调调试记录_2026-03-21.md)。

---

**最后更新**：2026-04-25  
**维护者**：AUV Master Project 团队  
**反馈**：若发现文档错误或改进建议，欢迎提出！
