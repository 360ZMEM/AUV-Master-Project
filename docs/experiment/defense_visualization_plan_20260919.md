# 毕业答辩可视化增强分级计划（2026-09-19）

## 目标与边界

把现有 PVS/protocol_udp/ROS2/Foxglove/PySide6 链路组织成可复现的“海底电缆自主巡检数字演示平台”。保留现有海缆、轨迹、搜索、DL/T 1278 和安全控制能力；新增内容只服务展示与取证，不改变控制、感知或验收阈值。

## 当前能力盘点

- Foxglove 已有 `classic`、`probe`、`mentor-demo`、`pilot-1366`、`acceptance-1366` 五套布局；当前推荐数据形态是 `configById + layout`。
- `zenoh_viz_bridge_node` 已发布海底网格/点云、海缆、AUV 本体、真值箭头、历史轨迹、搜索范围和 TF。
- cable tracking 已发布 JSON 与 typed topics，可直接展示横向偏移、埋深、置信度、磁 SNR、ready/pass 和 DL/T 状态。
- PySide6 已有主页面、任务配置、诊断页、深浅色主题、Zenoh side channel、电缆巡检监控及安全按钮。
- 已有 layout Playwright 导入、IndexedDB 注入、GUI 离屏探针、上位机视频、MCAP 回放视频等脚本。

## 缺失项

- 3D 场景缺少可一眼读懂的搜索走廊、zig-zag 计划路径、感知连线和任务阶段浮标。
- Foxglove 当前 profile 偏调试或验收，没有专为 1920×1080 答辩投屏设计的任务叙事布局。
- 上位机与 Foxglove 缺少统一的一键启动、窗口排布、录制和资产归档入口。
- GUI 的任务状态分散在多个区域，主界面缺少演示标题、阶段、关键指标和任务进度的集中摘要。
- 线上 Foxglove layout 导入仍可能受登录态阻塞，需要离线/桌面 fallback 和人工清单。

## 分级实施

### L0：静态资产闭环（无登录、无实车）

1. 新增 `defense-1080` Foxglove profile，保留全部海缆 3D 图层并突出任务阶段、核心指标和趋势。
2. 生成 canonical layout、mock topics、结构审计报告和布局示意图。
3. PySide6 生成 1920×1080 主页面与诊断页截图。
4. 输出 30 秒静态/回放短片，作为无法登录 Foxglove 时的答辩 fallback。

通过判据：布局 JSON 可生成、所有叶节点在 `configById` 中存在、关键 topic 无硬编码漂移、截图和视频可打开。

### L1：实时数字孪生展示（本机 ROS2）

1. 扩展可视化桥，新增搜索走廊、zig-zag 计划路径、感知连线、目标点和任务阶段文字 marker。
2. 启动 PVS/protocol_udp/ROS2/MCAP/Foxglove bridge，核对关键 topic、频率、frame 和 marker。
3. 导入 `defense-1080` 布局并截图迭代。

通过判据：ROS2 主链不回归；新增 marker 在 `world`/`map` 一致坐标系中发布；海缆、轨迹和原有图层仍存在。

### L2：PySide6 + Foxglove 联合操作

1. 在 PySide6 增加紧凑的任务摘要区：阶段、任务、深度、航程、置信度、链路状态。
2. 增加安全的 demo profile 和联合启动脚本，只连接本机仿真链路。
3. 支持窗口自动排布、启动前检查、运行日志和截图归档。

通过判据：GUI 可下达任务或由演示脚本复现同一任务；Foxglove 同步显示 SEARCH→TRACK 等阶段；不触发真实 PC104 执行器。

### L3：答辩视频与交付

1. 录制 30 秒精华片段和 1–3 分钟完整任务片段。
2. 生成字幕/片头/阶段章节点，并保留无字幕原始录屏。
3. 输出操作 README、人工登录/导入清单、常见错误和答辩讲解建议。

通过判据：视频可由仓库脚本复现；资产带时间戳和来源；明确数字孪生边界，不写成真实海缆验收。

## 修改范围与风险

| 范围 | 预计文件 | 风险与控制 |
|---|---|---|
| Foxglove profile | `foxglove_layout_project/config/topics.py`、`generator/layout_builder.py`、`generator/build_layout.py` | Panel schema 随版本变化；沿用已验证 panel 类型并做结构测试 |
| ROS marker | `brain_linux/src/auv_viz_bridge/auv_viz_bridge/zenoh_viz_bridge_node.py` | frame/坐标错误；复用 NED→display 转换并加单元测试 |
| PySide6 | `console_soft/auv_console_pyside6/src/ui/main_window.py` | 旧功能拥挤或误触；只增加只读摘要，控制按钮与协议不改 |
| 联合演示 | `scripts/`、`tools/` | 登录、窗口系统、CPU；提供 headless/offline fallback |
| 资产与说明 | `docs/experiment/assets/defense_visualization/`、本文件及 README | 大文件与可复现性；保留生成命令，视频按资产策略落盘 |

## 当前执行顺序

`L0 layout/profile → L1 marker/topic → L2 GUI/联合脚本 → L3 录屏与文档`。每级先做最小可运行版本，再用截图和录包证据迭代。

## 执行结果（2026-09-19）

- L0：完成。`defense-1080` 布局、canonical JSON、mock topics、上位机截图均已生成。
- L1：完成。新增五类任务叙事 Marker，统一到 `world`，ROS2 实测发布且 Foxglove bridge 已广告全部新增 channel。
- L2：完成本机链路和上位机联合启动脚本；云端 Foxglove 导入停在账户登录页，登录后的导入命令已固化到操作 README。
- L3：完成 30 秒与 100 秒上位机视频、战术回放视频、联合演示视频和复现文档。当前联合视频左侧采用明确标注的数字孪生遥测回放；登录后可换成真实 Foxglove 录屏。
- L4：完成 FWHM 感知增强。Foxglove Desktop 已登录并创建独立 1366 布局；v2 改为唯一控制发布者，真实横扫计划、位置/磁场/FWHM/埋深质量门控已接入并完成 210 秒联合验证。当前仿真产生 23.71 m 宽度候选但未通过有效性门控，因此埋深保持空值。

运行证据位于 `.auv_data/bags/20260919_172019`。30 秒 PVS/protocol_udp/ROS2 启动验证到达规定时长，Foxglove bridge 广告 72 个 channel；关闭阶段 `sensor_supervisor_node` 在收到全栈终止信号时记录 `exit code -11`，发生于演示结束清理而非运行中断，后续若用于长时间无人值守演示应单独修复其 shutdown 路径。
