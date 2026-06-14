# 明线 — 使用者指南索引

本文档面向**实验操作者和系统使用者**。如果你需要快速启动仿真、执行实验、操作上位机或分析数据，这里是你的起点。

阅读本指南后你将能够：

- 在 5 分钟内完成首次仿真实验
- 掌握完整的实验录制与参数配置流程
- 使用上位机进行遥控操作和自主任务授权
- 利用工具链回放和分析实验数据
- 了解从仿真到真机迁移的完整步骤

---

## 文档目录

| 编号 | 文档 | 一句话说明 |
|------|------|-----------|
| 01 | [quick_start.md](quick_start.md) | 5 分钟启动第一次仿真实验 |
| 02 | [experiment_runner.md](experiment_runner.md) | start_experiment.sh 完整实验录制与参数详解 |
| 03 | [console.md](console.md) | 上位机（PySide6）：遥控、自主授权、ESTOP |
| 04 | [rosbag_analysis.md](rosbag_analysis.md) | MCAP 数据回放与离线分析工具链 |
| 05 | [benchmarks.md](benchmarks.md) | 基准测试：PID/MPC 对比、BT/FSM 对比、EKF 性能 |
| 06 | [foxglove.md](foxglove.md) | Foxglove 实时可视化：布局生成与导入 |
| 07 | [experiments_catalog.md](experiments_catalog.md) | 实验目录：已完成/可复现/待开展的仿真实验清单 |
| 08 | [real_hardware_sop.md](real_hardware_sop.md) | 真机迁移 SOP：从仿真到实物的完整操作流程 |
| 09 | [config_reference.md](config_reference.md) | 配置文件速查：主线配置地图与参数含义 |
| 10 | [terrain.md](10_terrain.md) | 地形跟随基准：恒深 vs 自适应离底高度对比 |
| 11 | [control_aggregate.md](11_control_aggregate.md) | 控制侧指标聚合：lateral RMSE、solve time、fallback、安全违规率 |
| 12 | [real_deployment/INDEX.md](../real_deployment/INDEX.md) | **多 Level 实物部署路径**：08 是速记表，本入口给出 S1–S5 完整 SOP 体系 |

---

## 建议阅读顺序

1. 从 **quick_start** 开始，确认环境可用
2. 阅读 **experiment_runner** 了解实验脚本的完整能力
3. 根据需要查阅 **console**（交互操作）或 **rosbag_analysis**（离线分析）
4. 进阶用户可参考 **benchmarks** 和 **experiments_catalog** 设计自己的对比实验
5. 准备真机部署时查阅 **real_hardware_sop**

如需了解系统内部实现原理，请转至 [暗线 — 开发者内幕](../internals/INDEX.md)。
