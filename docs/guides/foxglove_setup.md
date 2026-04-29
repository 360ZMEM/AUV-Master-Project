# 👁️ Foxglove 可视化配置指南

本文档介绍如何配置和使用 Foxglove 可视化界面。

---

## 快速启动

### 一键启动（推荐）

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/start_foxglove_holoocean_ros.sh
```

系统会自动：
1. 启动 HoloOcean 仿真
2. 启动 ROS2 决策栈
3. 启动 Foxglove 桥接
4. 打开浏览器在 `http://localhost:3000`

### 手动启动 Foxglove 桥接

```bash
source /opt/ros/humble/setup.bash
bash scripts/start_lin_brain.sh foxglove
```

然后在浏览器中访问 `http://localhost:3000`

---

## 界面配置

### Foxglove 布局生成

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/foxglove_layout_project

# 生成基础布局
python -m foxglove_layout_project.generator.build_layout --pretty

# 生成带 mock 数据的布局（便于离线测试）
python -m foxglove_layout_project.generator.build_layout --with-mock-topics --pretty

# 输出位置
cat output/auv_layout.generated.*.json
```

### 导入布局到 Foxglove

1. 在 Foxglove 主界面，点击 "Import layout"
2. 选择生成的 JSON 文件
3. 系统自动加载所有 panel、3D 可视化、chart

---

## 常见 Panel 说明

| Panel | 用途 | 订阅 Topic |
|-------|------|----------|
| **3D Scene** | 车体位置与方向 | `/tf` (transforms) |
| **Map** | 俯视图轨迹 | `/auv/telemetry` |
| **Gauge** | 深度仪表 | `/auv/state/filtered` |
| **State Indicator** | 控制状态 | `/auv/control/setpoint` |
| **Plot** | 时间序列数据 | 任意 numeric topic |
| **Diagnostics** | 系统诊断 | `/diagnostics` |

---

## 实时参数调整

### 在 Foxglove 中修改 ROS2 参数

虽然 Foxglove 本身不直接修改参数，但可以通过以下方式：

```bash
# 在终端中动态修改
ros2 param set /auv_controller control.depth.kp 0.50
ros2 param set /auv_controller control.yaw.kp 12.0

# 验证修改
ros2 param list /auv_controller
```

然后在 Foxglove 中观察对应 topic 的变化。

---

## 数据订阅与可视化

### 添加新的 Topic 到 Foxglove

1. 在左侧 "Topics" 面板中，搜索要显示的 topic
2. 拖放到合适的 panel 上
3. 自动选择合适的可视化方式

### 常用 Topic 快速查询

```bash
# 列出所有可用 topic
ros2 topic list

# 查看某个 topic 的数据类型
ros2 topic info /auv/state/filtered -v

# 实时查看内容
ros2 topic echo /auv/state/filtered
```

---

## 常见问题

### Q: Foxglove 连接不上 ROS2

**解决步骤**：
1. 确保 ROS2 本地网络配置：`export ROS_DOMAIN_ID=0`
2. 确保 Foxglove 桥接在运行：`ps aux | grep foxglove`
3. 检查防火墙：`sudo ufw status`
4. 重启桥接：`bash scripts/start_lin_brain.sh foxglove`

### Q: 3D 可视化中车体位置不对

**原因**：坐标系或 transform 配置错误

**检查**：
```bash
# 查看 transform tree
ros2 run tf2_tools view_frames
cat /tmp/frames.pdf  # 打开 PDF 查看坐标系关系
```

### Q: 实时数据更新太快/太慢

**调整**：
1. 在 Foxglove Panel 中点击 ⚙️ 图标
2. 调整 "Update frequency" 或 "Buffer size"
3. 重新加载 panel

### Q: 某个 Panel 数据显示为空

**解决**：
1. 检查 topic 是否发布数据：`ros2 topic hz /topic_name`
2. 检查数据类型是否匹配 panel 期望类型
3. 尝试用 `Plot` panel 通用显示

---

## 导出与记录

### 在 Foxglove 中导出数据

1. 启动回放时，选择 rosbag 文件
2. 在 Foxglove 中打开，数据会从 bag 中读取
3. 可以截图或录屏保存可视化结果

### 录制会话

```bash
# Foxglove 内置录制功能
# 点击右上角红色录制按钮，保存所有 topic 数据
```

---

## 高级配置

### 自定义主题颜色

```bash
# 编辑布局 JSON（高级用户）
cat output/auv_layout.generated.*.json | jq '.theme'
```

### 添加自定义计算 Panel

对于复杂的可视化，可以使用 Foxglove 提供的自定义 script panel（需要基础 JavaScript 知识）。

---

## 下一步

- 若布局生成有问题，查看 [docs_backup/Foxglove整合落地计划_2026-03-24.md](../docs_backup/Foxglove整合落地计划_2026-03-24.md)
- 若 schema 有问题，查看 [docs_backup/foxglove/布局生成器调试上下文_2026-03-25.md](../docs_backup/foxglove/布局生成器调试上下文_2026-03-25.md)

---

**更新日期**：2026-04-25
