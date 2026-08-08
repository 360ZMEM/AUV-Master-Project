# 15 - 实现级架构图索引

> 本文档归档论文正文不再使用的实现级架构图。它们保留具体模块、节点和通信链路，服务于开发、联调和维护；学位论文正文仅使用 `docs/thesis/figures/architecture/` 中的学术抽象图。

## 图的边界

| 图 | 用途 | 对应内部文档 |
|---|---|---|
| 代码层级架构 | 按实际目录和模块定位运行责任 | [01_architecture.md](01_architecture.md) |
| ROS2 节点拓扑 | 跟踪 ROS2 节点、Topic 与启动依赖 | [06_ros2_stack.md](06_ros2_stack.md) |
| 安全仲裁器部署 | 核对仲裁器、协议桥接和上位机的实现链路 | [07_arbiter.md](07_arbiter.md) |

## 代码层级架构

![代码层级架构](figures/architecture/auv_code_layer_architecture.png)

可编辑源文件：`figures/architecture/auv_code_layer_architecture.drawio`。

## ROS2 节点拓扑

![ROS2 节点拓扑](figures/architecture/auv_ros2_node_topology.png)

可编辑源文件：`figures/architecture/auv_ros2_node_topology.drawio`。

## 安全仲裁器部署

![安全仲裁器部署](figures/architecture/auv_safety_arbiter_deployment.png)

可编辑源文件：`figures/architecture/auv_safety_arbiter_deployment.drawio`。

## 维护约束

- 修改实现拓扑时，同时更新本页所列图的 `.drawio` 源文件和 `.png/.svg/.drawio.png` 导出件。
- 不将代码文件名、ROS2 节点名或协议实现细节直接回填至论文正文图；正文采用相应的 v2 学术抽象图。
