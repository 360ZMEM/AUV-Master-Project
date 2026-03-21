# Foxglove SDK 阅读、入门、实施与注意事项指南

> 适用范围：`/home/zmem063/auv_console_python` 当前工作区  
> 目标：为 `ros2_ws` 的 AUV 模拟数据构建“纯 Python 参数化布局生成”方案

---

## 1. 只读调研结论（核心）

1. `foxglove-sdk` 的 Python 包中已经提供了**布局模型 API**，位于：
   - `foxglove-sdk/python/foxglove-sdk/python/foxglove/layouts/__init__.py`
2. `Layout`、`SplitContainer`、`PlotPanel`、`ThreeDeePanel`、`MapPanel`、`RawMessagesPanel` 等类型可直接在 Python 中构建布局，再 `to_json()` 导出。
3. `foxglove-sdk-examples` 主要展示数据发布与可视化流（server/channel/schema），并未提供完整 AUV 布局生成脚本模板。
4. `ros2_ws` 已有现成数据发布节点与静态布局示例（`foxglove_layout.json`），可作为参数化迁移基线。
5. 推荐路径：
   - 使用 `foxglove.layouts` 生成布局 JSON；
   - 将话题定义与字段路径分离到单独配置文件（本次已确认采用）。

---

## 2. 阅读路线（建议顺序）

### 第 1 层：理解 SDK 的能力边界

- `foxglove-sdk/README.md`
- `foxglove-sdk/python/foxglove-sdk/README.md`

关注点：
- Python SDK 主要能力：WebSocket live、MCAP 写入、schema 支持；
- 是否存在官方布局相关能力（结论：有，见 `foxglove.layouts`）。

### 第 2 层：布局 API 关键入口

- `foxglove-sdk/python/foxglove-sdk/python/foxglove/layouts/__init__.py`

重点符号：
- `class Layout`
- `class SplitContainer`, `class SplitItem`
- `class PlotPanel`, `class PlotConfig`, `class PlotSeries`
- `class ThreeDeePanel`, `class ThreeDeeConfig`
- `class MapPanel`, `class MapConfig`
- `class RawMessagesPanel`, `class RawMessagesConfig`

关键事实：
- `Layout.to_json()` 直接返回布局 JSON 字符串；
- 面板 `panelType` 在序列化时自动写入；
- 支持组合容器（分栏、堆叠、标签页）构建复杂布局。

### 第 3 层：示例的“数据链路”而非“布局模板”

- `foxglove-sdk/python/foxglove-sdk-examples/quickstart/main.py`
- `foxglove-sdk/python/foxglove-sdk-examples/live-visualization/main.py`

关注点：
- `foxglove.start_server()` 的使用方法；
- Channel/schema 发布数据方式；
- 示例可作为“端到端可视化联通”验证脚手架。

### 第 4 层：与本项目 ROS2 数据源对齐

- `ros2_ws/src/my_auv_talker/my_auv_talker/auv_data_publisher.py`
- `ros2_ws/README.md`
- `ros2_ws/foxglove_layout.json`

关注点：
- 当前 AUV 话题与消息类型；
- 现有静态布局里的 panel 与 topic 映射；
- 后续参数化生成需要覆盖的最小集合。

---

## 3. AUV 话题基线（来自 ROS2 发布节点）

发布节点：`AUVDataPublisher`

- `/auv/pose` → `geometry_msgs/PoseStamped`
- `/auv/twist` → `geometry_msgs/TwistStamped`
- `/auv/gps` → `sensor_msgs/NavSatFix`
- `/auv/imu` → `sensor_msgs/Imu`
- `/auv/pressure` → `sensor_msgs/FluidPressure`
- `/auv/temperature` → `sensor_msgs/Temperature`
- `/auv/depth` → `std_msgs/Float32`
- `/auv/status` → `std_msgs/String`

发布频率：10Hz（`create_timer(0.1, ...)`）

---

## 4. 入门：参数化布局生成最小知识

### 4.1 目标结构（已创建）

- `ros2_ws/foxglove_layout_project/config/`
- `ros2_ws/foxglove_layout_project/generator/`
- `ros2_ws/foxglove_layout_project/templates/`
- `ros2_ws/foxglove_layout_project/output/`
- `ros2_ws/foxglove_layout_project/examples/`
- `ros2_ws/foxglove_layout_project/docs/`

### 4.2 推荐运行模型

1. `config/topics.py` 维护所有 topic 名称、字段路径、颜色、标题；
2. `generator/layout_builder.py` 按参数构建 `Layout` 对象；
3. `generator/build_layout.py` 导出 JSON 到 `output/`；
4. 导入 Foxglove 验证。

### 4.3 为什么“topic 配置单文件”很关键

- ROS 节点重命名或 namespace 调整时，单点修改即可；
- 布局脚本可跨场景复用（仿真/真机）；
- 避免 panel 配置中硬编码散落。

---

## 5. 实施设计（纯 Python 参数化）

> 以下是实施蓝图，不涉及当前文档阶段的具体业务代码细节。

### 5.1 配置层（`config/topics.py`）

建议包含：
- `TOPICS`：统一管理 `/auv/*` 名称
- `PLOT_FIELDS`：曲线字段（如 `data`, `temperature`, `fluid_pressure`）
- `RAW_TOPICS`：原始消息面板列表
- `PANEL_STYLE`：颜色、标题、轴标签

### 5.2 生成层（`generator/layout_builder.py`）

建议职责：
- `build_layout(topic_cfg, style_cfg) -> Layout`
- 组装容器结构（主分栏 + 子分栏）
- 输出 panel 树：
  - 3D (`ThreeDeePanel`)
  - Plot ×3（深度/温度/压力）
  - Raw Messages ×4（GPS/IMU/状态/速度）
  - 可选 Map（GPS 跟踪）

### 5.3 导出层（`generator/build_layout.py`）

建议职责：
- 加载配置
- 调用 `build_layout(...)`
- `layout.to_json()` 写入 `output/auv_layout.generated.json`
- 支持 CLI 参数（输出路径、是否含 Map 面板、主题前缀）

### 5.4 验证层（`examples/`）

建议提供：
- 最小生成示例
- 说明如何在 Foxglove 中导入并检查 topic 绑定

---

## 6. 注意事项（高优先级）

1. **布局 JSON 兼容性**：
   Foxglove 桌面版本变更可能导致某些 panel 字段兼容差异。建议优先使用 `foxglove.layouts` 生成，尽量减少手写低层字段。

2. **Topic 字段路径必须匹配消息结构**：
   例如：
   - `std_msgs/Float32` 用 `data`
   - `sensor_msgs/Temperature` 用 `temperature`
   - `sensor_msgs/FluidPressure` 用 `fluid_pressure`

3. **frame_id 与 3D/Map 体验相关**：
   `PoseStamped` 使用 `auv_base_link`，GPS 使用 `gps`；后续若要做更强 3D 语义，建议补 TF 流。

4. **桥接模式约束**：
   当前可视化链路基于 `foxglove_bridge`（`ws://<ip>:8765`）。需确认网络连通、防火墙、ROS_DOMAIN_ID。

5. **保持与现有静态布局对齐**：
   `ros2_ws/foxglove_layout.json` 是验证基线，参数化版本应先做到功能等价，再做增强。

6. **不要依赖 build/install 目录源码副本**：
   开发以 `ros2_ws/src/my_auv_talker/...` 为唯一真实源。

---

## 7. 分阶段实施建议

### 阶段 A（已完成）
- 创建结构目录
- 输出阅读/入门/实施/注意事项文档

### 阶段 B（下一步）
- 创建 `config/topics.py`
- 创建 `generator/layout_builder.py`
- 创建 `generator/build_layout.py`

### 阶段 C
- 生成首版 `output/auv_layout.generated.json`
- 对照 `ros2_ws/foxglove_layout.json` 做等价性检查

### 阶段 D
- 增强可选面板（Map、Table、Log）
- 支持多个 profile（仿真/实机）

---

## 8. 一句话执行口令（给后续实现阶段）

- 原则：**先配置，后生成；先等价，后增强；先可导入，后美化。**
