# AUV 联合开发平台文档

欢迎使用 AUV 联合开发平台！这是一个将 HoloOcean 仿真与 Linux ROS2 决策系统统一为一体的可演进仓库。

## 📚 文档导航

### 🔰 新手入门
如果你是第一次接触本项目，建议按以下顺序阅读：

1. [项目简介](01_getting_started/01_project_intro.md) - 了解项目是什么，解决什么问题
2. [快速安装](01_getting_started/02_quick_install.md) - 5 分钟完成环境配置
3. [第一次运行](01_getting_started/03_first_run.md) - 启动你的第一个仿真
4. [常见问题](01_getting_started/04_faq.md) - 新手常见问题解答

### 🏗️ 架构设计
理解项目的整体设计思路：

1. [系统架构概览](02_architecture/01_system_architecture.md) - 高层架构图
2. [分层设计](02_architecture/02_layered_design.md) - 各层职责与边界
3. [数据流设计](02_architecture/03_data_flow.md) - 数据如何流动
4. [仲裁器架构](02_architecture/04_arbiter_architecture.md) - 控制仲裁设计

### 🔑 核心概念
深入理解关键概念：

1. [坐标系统一](03_core_concepts/01_coordinate_systems.md) - UE4 ↔ NED 转换
2. [通信协议](03_core_concepts/02_communication_protocol.md) - Zenoh 与 UDP 协议
3. [消息契约](03_core_concepts/03_message_contract.md) - 统一数据契约
4. [状态机设计](03_core_concepts/04_state_machines.md) - 行为与仲裁状态机

### 💻 开发指南
参与开发需要了解的内容：

1. [开发环境配置](04_development/01_dev_environment.md) - 配置开发环境
2. [代码规范](04_development/02_coding_standards.md) - 编码规范
3. [修改指南](04_development/03_modification_guide.md) - 如何正确修改代码
4. [测试指南](04_development/04_testing_guide.md) - 单元测试与集成测试

### 🔧 运维与调试
日常使用与问题排查：

1. [运行模式切换](05_operations/01_mode_switching.md) - zenoh_json 与 protocol_udp 切换
2. [控制调试](05_operations/02_control_debugging.md) - 控制回路问题排查
3. [日志解读](05_operations/03_log_analysis.md) - 日志分析与解读
4. [性能监控](05_operations/04_performance_monitoring.md) - 系统性能指标

### 📖 参考文档
详细的参考资料：

1. [字段真值表](06_reference/01_field_truth_table.md) - 数据字段权威参考
2. [配置文件说明](06_reference/02_configuration_reference.md) - 配置参数详解
3. [命令参考](06_reference/03_command_reference.md) - 所有命令说明
4. [历史文档](06_reference/04_legacy_docs.md) - 原有文档索引

## 🚀 快速命令参考

### 启动仿真
```bash
cd scripts
bash start_lin_sim.sh sim          # 仅启动 HoloOcean 仿真
bash start_lin_sim.sh both         # 仿真 + Zenoh 桥接
```

### 启动决策端
```bash
cd scripts
bash start_lin_brain.sh bootstrap  # 首次构建
bash start_lin_brain.sh stack      # 启动完整决策栈
```

### 一键启动完整系统
```bash
cd scripts
bash start_foxglove_holoocean_ros.sh
```

## 📊 项目状态

- ✅ Phase 1: Common 契约层完成
- ✅ Phase 2: 仿真侧重构完成
- ✅ Phase 3: Linux 决策侧迁移完成
- ✅ Phase 4: 跨端桥接闭环完成
- ✅ Phase 5-8: 仲裁器与守门员实现完成
- 🔄 Phase 9: 长期稳定性测试中

## 🆘 获取帮助

- 遇到问题？先查看 [常见问题](01_getting_started/04_faq.md)
- 需要调试？参考 [控制调试指南](05_operations/02_control_debugging.md)
- 想深入了解？阅读 [架构设计文档](02_architecture/)

## 📝 文档更新日志

- **2026-04-14**: 创建新文档体系，重组原有文档
- **2026-04-10**: 仲裁器 Phase 7-8 完成
- **2026-04-08**: 仲裁器 Phase 1-6 完成
- **2026-04-01**: protocol_udp 联调完成
