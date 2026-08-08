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
| 11 | [experiment_state_machine.md](11_experiment_state_machine.md) | start_experiment.sh 编排状态机：进程拓扑、时序图、trap 路径 |
| 12 | [cable_tracking_mag_integration.md](12_cable_tracking_mag_integration.md) | 电缆跟踪磁探测集成：在线先验修正、磁导出横偏观测、PVS 闭环恢复原理 |
| 13 | [mag_lever_arm_calibration.md](13_mag_lever_arm_calibration.md) | 磁强计杆臂标定：外参配置模型与 bag 级证明 |
| 14 | [fangkong_adc_wrapper_architecture.md](14_fangkong_adc_wrapper_architecture.md) | FK2301/TMR8637 真实磁 wrapper：submodule API 边界、默认标定、主仓 IP override 与脚本分层 |
| 15 | [implementation_architecture_figures.md](15_implementation_architecture_figures.md) | 实现级架构图：代码层级、ROS2 拓扑与安全仲裁部署 |
