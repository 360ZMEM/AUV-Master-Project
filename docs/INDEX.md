# AUV 硕士毕设项目 — 文档总入口

本项目是一套面向自主水下机器人（AUV）的完整研发平台，集成了仿真环境、ROS 2 决策控制栈和 PySide6 上位机系统，支持从算法开发到真机部署的全流程工作。

---

## 推荐阅读路径

| 读者角色 | 起点 | 说明 |
|----------|------|------|
| **新用户 / 实验操作者** | 明线 `user-guide/` | 了解系统由哪些模块构成、每个模块怎么用、前置条件和操作步骤 |
| **开发者 / 维护者** | 暗线 `internals/` | 深入系统内部原理、数据流架构、各子系统协作机制 |

---

## 文档目录

### 明线 — 使用者指南

> 路径：[user-guide/INDEX.md](user-guide/INDEX.md)

- [quick_start.md](user-guide/quick_start.md) — 5 分钟启动第一次仿真实验
- [experiment_runner.md](user-guide/experiment_runner.md) — start_experiment.sh 完整实验录制与参数详解
- [console.md](user-guide/console.md) — 上位机（PySide6）：遥控、自主授权、ESTOP
- [rosbag_analysis.md](user-guide/rosbag_analysis.md) — MCAP 数据回放与离线分析工具链
- [benchmarks.md](user-guide/benchmarks.md) — 基准测试：PID/MPC 对比、BT/FSM 对比、EKF 性能
- [foxglove.md](user-guide/foxglove.md) — Foxglove 实时可视化：布局生成与导入
- [experiments_catalog.md](user-guide/experiments_catalog.md) — 实验目录：已完成/可复现/待开展的仿真实验清单
- [real_hardware_sop.md](user-guide/real_hardware_sop.md) — 真机迁移 SOP：从仿真到实物的完整操作流程
- [config_reference.md](user-guide/config_reference.md) — 配置文件速查：主线配置地图与参数含义

### 暗线 — 开发者内幕

> 路径：[internals/INDEX.md](internals/INDEX.md)

- 系统架构总览与节点拓扑
- ROS 2 数据流与话题/服务映射
- 决策层（行为树 / 有限状态机）内部实现
- 控制层（PID / MPC）算法细节
- 状态估计（EKF）与传感器融合
- 仿真后端接口与物理引擎对接
- 上位机通信协议与前后端交互

---

## 最小启动命令

```bash
cd scripts && bash start_experiment.sh --sim-backend pvs --duration 120
```

该命令将使用 PVS 仿真后端启动一次时长 120 秒的实验。
