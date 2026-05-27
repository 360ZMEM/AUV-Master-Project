# 暗线索引

> **暗线文档**面向开发者和维护者，关注系统内部工作原理——即"系统如何工作"，而非"如何操作"。
>
> 如果你需要操作指南、部署步骤或用户手册，请参阅 `docs/` 下的其他文档。暗线文档假设读者已具备项目基本背景知识，直接深入实现细节与设计决策。

---

## 文档目录

| 编号 | 文档 | 一句话说明 |
|------|------|-----------|
| 01 | [architecture.md](01_architecture.md) | 系统整体架构、五层结构与完整数据流 |
| 02 | [pvs_backend.md](02_pvs_backend.md) | PVS轻量仿真后端：REMUS 100 6-DOF动力学 |
| 03 | [mock_amd.md](03_mock_amd.md) | Mock AMD子系统：延迟/混沌/多速率传感器仿真 |
| 04 | [zenoh_bridge.md](04_zenoh_bridge.md) | Zenoh实时通信桥接：JSON发布/订阅 |
| 05 | binary_protocol.md | $CKTH/$AUV二进制协议：字节级编解码 |
| 06 | ros2_stack.md | ROS2决策栈：节点拓扑与Topic通信 |
| 07 | arbiter.md | 仲裁器：控制权分配与安全守卫 |
| 08 | controllers.md | 级联PID与MPC控制器原理 |
| 09 | es_ekf.md | ES-EKF误差状态卡尔曼滤波 |
| 10 | behavior_tree.md | 行为树决策引擎架构 |
