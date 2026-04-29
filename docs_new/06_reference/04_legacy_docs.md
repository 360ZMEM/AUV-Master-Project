# 历史文档索引

本文档提供了原有文档到新文档的映射关系，帮助用户快速找到需要的信息。

## 文档重组说明

原有的 `docs/` 文件夹包含大量技术文档，但组织结构不够清晰。新的 `docs_new/` 文件夹按照用户需求重新组织，更加易于查找和使用。

### 重组原则

1. **面向新手**: 先看快速入门，再深入了解
2. **按场景分类**: 开发、运维、参考分别组织
3. **保留技术细节**: 原有技术内容全部保留
4. **添加导航**: 清晰的目录结构和交叉引用

## 文档映射表

### 原理与架构类

| 原文档 | 新文档 | 说明 |
|--------|--------|------|
| `原理说明.md` | [系统架构概览](../02_architecture/01_system_architecture.md) | 高层架构 |
| `原理说明.md` | [分层设计](../02_architecture/02_layered_design.md) | 详细分层 |
| `原理说明.md` | [数据流设计](../02_architecture/03_data_flow.md) | 数据流向 |
| `仲裁器长期路线图_2026-04-08.md` | [仲裁器架构](../02_architecture/04_arbiter_architecture.md) | 仲裁器设计 |

### 字段与协议类

| 原文档 | 新文档 | 说明 |
|--------|--------|------|
| `字段真值表.md` | [消息契约](../03_core_concepts/03_message_contract.md) | 数据契约 |
| `字段真值表.md` | [字段真值表详细版](01_field_truth_table.md) | 完整字段参考 |
| `实物通信协议对接建议_2026-03-31.md` | [通信协议](../03_core_concepts/02_communication_protocol.md) | 协议设计 |

### 开发与调试类

| 原文档 | 新文档 | 说明 |
|--------|--------|------|
| `开发进度.md` | [项目简介](../01_getting_started/01_project_intro.md) | 当前状态 |
| `控制回路问题定位与修复建议_2026-04-01.md` | [控制调试指南](../05_operations/02_control_debugging.md) | 调试方法 |
| `holoocean_brain_linux联调指南_2026-03-21.md` | [第一次运行](../01_getting_started/03_first_run.md) | 启动指南 |
| `holoocean_brain_linux配置状态与设置_2026-03-21.md` | [配置文件说明](02_configuration_reference.md) | 配置参考 |
| `holoocean_brain_linux日志解读指南_2026-03-21.md` | [日志解读](../05_operations/03_log_analysis.md) | 日志分析 |

### 模式切换类

| 原文档 | 新文档 | 说明 |
|--------|--------|------|
| `protocol_udp联调复现与模式切换_2026-04-01.md` | [运行模式切换](../05_operations/01_mode_switching.md) | 模式切换 |

### Foxglove 类

| 原文档 | 新文档 | 说明 |
|--------|--------|------|
| `Foxglove整合落地计划_2026-03-24.md` | [系统架构](../02_architecture/01_system_architecture.md) | 可视化部分 |
| `Foxglove_HoloOcean_ROS脚本说明.md` | [第一次运行](../01_getting_started/03_first_run.md) | Foxglove 启动 |
| `foxglove/布局生成器调试上下文_2026-03-25.md` | [命令参考](03_command_reference.md) | 布局生成 |

### 联调记录类

| 原文档 | 新文档 | 说明 |
|--------|--------|------|
| `联调调试记录_2026-03-21.md` | [控制调试指南](../05_operations/02_control_debugging.md) | 调试案例 |
| `联调验收摘要_2026-03-21.md` | [项目简介](../01_getting_started/01_project_intro.md) | 验收标准 |

## 新增文档

以下文档是新增的，在原有 `docs/` 中没有对应内容：

### 新手入门
- [项目简介](../01_getting_started/01_project_intro.md) - 介绍项目是什么
- [快速安装](../01_getting_started/02_quick_install.md) - 安装指南
- [第一次运行](../01_getting_started/03_first_run.md) - 运行指南
- [常见问题](../01_getting_started/04_faq.md) - FAQ

### 架构设计
- [系统架构概览](../02_architecture/01_system_architecture.md) - 总体架构
- [分层设计](../02_architecture/02_layered_design.md) - 各层职责
- [数据流设计](../02_architecture/03_data_flow.md) - 数据流动

### 核心概念
- [坐标系统一](../03_core_concepts/01_coordinate_systems.md) - 坐标系转换
- [通信协议](../03_core_concepts/02_communication_protocol.md) - 协议详解
- [消息契约](../03_core_concepts/03_message_contract.md) - 数据契约
- [状态机设计](../03_core_concepts/04_state_machines.md) - 状态机

### 开发指南
- [开发环境配置](../04_development/01_dev_environment.md) - 环境配置
- [代码规范](../04_development/02_coding_standards.md) - 编码规范
- [修改指南](../04_development/03_modification_guide.md) - 如何正确修改
- [测试指南](../04_development/04_testing_guide.md) - 测试方法

### 运维调试
- [运行模式切换](../05_operations/01_mode_switching.md) - 模式切换详解
- [控制调试](../05_operations/02_control_debugging.md) - 控制问题排查
- [日志解读](../05_operations/03_log_analysis.md) - 日志分析
- [性能监控](../05_operations/04_performance_monitoring.md) - 性能指标

### 参考文档
- [字段真值表](01_field_truth_table.md) - 完整字段参考
- [配置文件说明](02_configuration_reference.md) - 配置参数详解
- [命令参考](03_command_reference.md) - 所有命令
- [本文档](04_legacy_docs.md) - 历史文档索引

## 如何使用旧文档

### 仍然有效的旧文档

以下旧文档仍然包含有价值的技术细节，建议在深入了解时阅读：

1. **控制回路问题定位与修复建议_2026-04-01.md**
   - 详细的问题分析
   - 参数调优建议
   - 已整合到 [控制调试指南](../05_operations/02_control_debugging.md)

2. **仲裁器长期路线图_2026-04-08.md**
   - 详细的实施计划
   - 分阶段验收标准
   - 已整合到 [仲裁器架构](../02_architecture/04_arbiter_architecture.md)

3. **protocol_udp联调复现与模式切换_2026-04-01.md**
   - 具体的复现步骤
   - 排障检查清单
   - 已整合到 [运行模式切换](../05_operations/01_mode_switching.md)

4. **字段真值表.md**
   - 权威的字段定义
   - 单位和类型说明
   - 已整合到 [消息契约](../03_core_concepts/03_message_contract.md)

### 临时性文档

以下文档主要记录历史过程，可以归档：

- `联调调试记录_2026-03-21.md` - 历史调试记录
- `联调验收摘要_2026-03-21.md` - 特定时间点的验收状态
- `holoocean_brain_linux配置状态与设置_2026-03-21.md` - 配置快照

## 文档更新建议

### 对于新手

1. 先阅读 `docs_new/01_getting_started/` 下的所有文档
2. 根据需要查阅 `docs_new/02_architecture/` 了解架构
3. 遇到问题时查看 `docs_new/05_operations/` 和 `docs_new/01_getting_started/04_faq.md`

### 对于开发者

1. 熟悉 `docs_new/03_core_concepts/` 中的核心概念
2. 遵循 `docs_new/04_development/` 中的开发规范
3. 参考旧文档获取详细技术细节

### 对于调试者

1. 查看 `docs_new/05_operations/` 中的调试指南
2. 参考旧文档中的具体问题案例
3. 使用 `docs_new/06_reference/03_command_reference.md` 查询命令

## 文档维护

### 更新原则

1. **新内容优先添加到 docs_new/**
2. **技术细节保留在 docs/**
3. **定期合并重复内容**
4. **保持本文档的映射关系更新**

### 反馈与改进

如果发现：
- 文档缺失
- 映射错误
- 内容过时

请：
1. 在 `docs_new/` 中添加新文档
2. 更新本文档的映射表
3. 提交 PR 或 Issue

## 迁移计划

### Phase 1: 新文档体系建立 ✅
- 创建 `docs_new/` 目录结构
- 编写核心新手文档
- 建立映射关系

### Phase 2: 内容整合 (进行中)
- 将旧文档内容整合到新文档
- 提炼技术细节
- 更新交叉引用

### Phase 3: 旧文档归档
- 将临时性文档移到 `docs/archive/`
- 保留有价值的技术文档
- 更新所有引用

## 相关链接

- [返回文档首页](../README.md)
- [项目根目录](../../README.md)
- [CLAUDE.md](../../CLAUDE.md) - 项目开发指南
