# 📖 启动与配置指南集合

本目录包含 AUV_Master_Project 的所有启动、配置和调试指南。

---

## 快速导航

### 我需要...

- **启动系统** → 查看 [仿真启动](simulation_startup.md) 或 [决策启动](brain_startup.md)
- **完整闭环** → 查看 [端到端设置](end_to_end_setup.md)
- **配置参数** → 查看 [配置参数详解](configuration.md)
- **运行实验** → 查看 [实验配置](experiment_guide.md)
- **调试问题** → 查看对应的排障指南

---

## 按类别

### 🚀 启动指南
1. **[仿真启动指南](simulation_startup.md)** — HoloOcean 仿真 + Zenoh 桥接
2. **[决策启动指南](brain_startup.md)** — ROS2 决策栈
3. **[端到端设置](end_to_end_setup.md)** — 完整闭环系统

### ⚙️ 配置与参数
4. **[配置参数详解](configuration.md)** — 所有 YAML 参数说明
5. **[实验配置指南](experiment_guide.md)** — 长实验与数据记录

### 🔧 调试与排障
6. **[HoloOcean 调试](holoocean_debugging.md)** — 仿真环境排障
7. **[PVS 调试](pvs_debugging.md)** — 高保真物理引擎调试
8. **[Foxglove 配置](foxglove_setup.md)** — 可视化界面设置

### 📊 高级功能
9. **[HoloOcean 视频采集](holoocean_video_capture.md)** — 仿真视频录制
10. **[PVS 全流程 Runbook](pvs_full_runbook.md)** — 高保真仿真实战手册
11. **[HoloOcean 与 ROS 脚本集成](holoocean_ros_scripts.md)** — 一键启动与自动化
12. **[测试与验证指南](testing_guide.md)** — 单元测试、集成测试、回归测试

---

## 推荐阅读顺序

### 新手入门（第一天）
1. 原理说明（位于上级目录）[原理说明.md](../原理说明.md)
2. [仿真启动指南](simulation_startup.md) — 启动第一个仿真
3. [配置参数详解](configuration.md) — 理解关键参数
4. [决策启动指南](brain_startup.md) — 启动 ROS2 决策

### 完整搭建（第二天）
5. [端到端设置](end_to_end_setup.md) — 建立闭环
6. [Foxglove 配置](foxglove_setup.md) — 可视化监控
7. [实验配置指南](experiment_guide.md) — 运行长实验

### 深度调优（后续）
8. [HoloOcean 调试](holoocean_debugging.md) / [PVS 调试](pvs_debugging.md)
9. [PVS 全流程 Runbook](pvs_full_runbook.md)
10. [HoloOcean 视频采集](holoocean_video_capture.md)
11. [HoloOcean 与 ROS 脚本集成](holoocean_ros_scripts.md) — 自动化工作流
12. [测试与验证指南](testing_guide.md) — 回归与质量保证

---

## 文档命名约定

| 类型 | 命名规则 | 示例 |
|------|--------|------|
| 启动指南 | `{module}_startup.md` | `simulation_startup.md`, `brain_startup.md` |
| 配置指南 | `{topic}_guide.md` | `experiment_guide.md`, `foxglove_setup.md` |
| 调试指南 | `{module}_debugging.md` | `holoocean_debugging.md`, `pvs_debugging.md` |
| 高级手册 | `{topic}_full_runbook.md` | `pvs_full_runbook.md` |

---

## 常用命令速查

```bash
# 快速启动（仿真）
bash scripts/start_lin_sim.sh sim

# 快速启动（完整闭环）
bash scripts/start_foxglove_holoocean_ros.sh

# 查看配置
cat config/sim_params.yaml

# 查看日志
tail -f log/sim_*.log

# 重新编译 ROS2
cd brain_linux && colcon build --symlink-install
```

---

## 贡献指南

### 新增文档
1. 在本目录创建新的 `.md` 文件
2. 遵循现有文档的结构（章节标题、代码块、表格）
3. 在上级目录的 [INDEX.md](../INDEX.md) 中添加链接

### 文档规范
- 使用中文标题（如 "## 快速开始"）
- 代码块明确标注语言（如 ```bash、```yaml）
- 包含"常见问题"章节（Q&A 格式）
- 添加"更新日期"在文档末尾

---

**最后更新**：2026-04-25
