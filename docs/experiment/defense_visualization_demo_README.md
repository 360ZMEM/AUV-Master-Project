# AUV 海底电缆自主巡检答辩演示

> 2026-09-29 当前入口：[仓库差异与可视化迁移](workspace_visualization_review_20260929.md)。本文件和下方脚本保留 Sept19–23 历史演示；当前布局用 `inspection-v2`，主结果用图 71（埋深为空），不要将旧单次深度或解耦急停演示当当前同次任务证据。


本文档对应 2026-09-19 至 2026-09-23 的答辩可视化增强。演示数据来自本机 PVS/ROS2 数字孪生、实时 ROS2 话题或历史 `tracking.jsonl`，不等同于实海验收数据。

全部图片、视频、报告、GUI 演进记录和 PC104 联调附件的独立图录见 [答辩可视化附件总报告](defense_visualization_all_assets_report_20260923.md)。

## 已完成内容

- Foxglove `defense-1080` 布局：主 3D 场景、任务阶段、巡检 ready、海缆置信度、俯视图、横偏/埋深/磁 SNR 趋势。
- 3D 叙事层：搜索廊道、规划 zig-zag、AUV 到海缆测量线、目标点、任务浮动标签。
- 原有海底网格、海缆、AUV、历史轨迹、搜索范围和 TF 均保留。
- PySide6 主页面增加任务摘要；ESTOP 现在同时发送旧协议任务取消包和带锁存语义的 `SURFACE` 命令。
- 可复现的 30 秒和约 100 秒操作视频，以及 Foxglove 登录不可用时的联合回放 fallback。
- 独立 `defense-perception-1366` 布局：真实 v2 搜索/横扫计划、海缆位置估计、2σ 不确定度、磁场矢量、FWHM 跨度和埋深质量门控。
- 急停闭环：上位机真实按钮点击 → Zenoh 控制语义 → ROS2 安全优先级 → 水平停车并上浮 → Foxglove 红色过程状态 → `SURFACED` 绿色安全状态。
- 单次实时巡检 FWHM 证据：保留原始磁场空间剖面、半高交点、宽度、反演埋深、不确定度、质量时序和数字孪生真值误差。

## 一键启动

```bash
cd /home/zmem063/AUV-Master-Project
export AUV_DATA_ROOT="$PWD/.auv_data"
scripts/run_defense_demo.sh --duration 120 --gui
```

无桌面环境时移除 `--gui`。脚本使用 PVS、`protocol_udp`、ROS2 cable tracking、Foxglove bridge 和 MCAP；运行目录写入 `.auv_data`。布局固定输出为：

```text
foxglove_layout_project/output/auv_defense_1080.json
```

Foxglove 数据源使用：

```text
ws://localhost:8765
```

FWHM/感知增强版使用：

```bash
scripts/run_defense_perception_1366.sh --duration 210 --gui
```

其 canonical layout 为 `foxglove_layout_project/output/auv_defense_perception_1366.json`。该脚本运行 `stack-v2`，并保证旧 decision node 不与 v2 节点争用 `/auv/control/setpoint`。

答辩现场的推荐主路径使用独立的物理一致验收脚本：

```bash
scripts/run_defense_assurance.sh --duration 260
```

该路径把真值限制在仿真节点内部，算法只接收导航、磁场和高度 topic。脚本自动检查 `SEARCH → CONFIRM → TRACK`、FWHM 有效性和埋深误差，并输出 `assurance_report.json`；任一条件不满足时退出码非零。PVS 联合链路继续作为系统集成和场景真实性证据，不承担现场必成的埋深精度演示。

默认还会从同一次实时 ROS2 巡检采集 FWHM 证据。若只做快速算法验收，可显式加入 `--no-fwhm-analysis`。

## 上位机急停与紧急上浮

```bash
cd /home/zmem063/AUV-Master-Project
export AUV_DATA_ROOT="$PWD/.auv_data"
scripts/run_emergency_surface_demo.sh
```

脚本启动真实 PySide6 `MainWindow`，随后调用该窗口的 ESTOP 按钮点击事件，不绕过 GUI 直接注入 ROS 命令。上位机持续发布锁存的 `ESTOP + SURFACE` 语义；仿真安全层以高于普通跟踪设定值的优先级执行，令水平速度归零并把目标深度改为 0.5 m。Foxglove 的统一任务状态和三维标签依次显示 `ESTOP · 紧急上浮 / EMERGENCY_SURFACE` 与 `SAFE · 已上浮 / SURFACED`。

验收不是只检查界面文字。`tools/monitor_emergency_surface.py` 同时要求观察到 ESTOP 和 SURFACED、最终深度不大于 0.8 m、上浮距离不小于 8 m、急停期间水平速度不大于 0.05 m/s；任一条件失败，脚本返回非零退出码。

2026-09-23 固化运行结果：初始深度 11.61 m，最终深度 0.69 m，上浮 10.91 m，急停期间最大水平速度 0.00 m/s，结论 `PASS`。答辩资产：

- [上位机 ESTOP 锁存界面](assets/defense_demo/console_estop_emergency_surface.png)
- [Foxglove 紧急上浮过程](assets/defense_demo/foxglove_emergency_surface_active.png)
- [Foxglove 到达安全深度](assets/defense_demo/foxglove_emergency_surface_complete.png)
- [机器可读验收报告](assets/defense_demo/emergency_surface_report.json)

旧二进制协议仍发送 `TASK_CANCEL` 和零推进量，满足旧控制器兼容性；新增语义命令用于 Jetson/ROS2 安全仲裁和 Foxglove 状态同步。复位按钮会发送 `ESTOP_RESET + CLEAR`，防止普通任务心跳未经人工复位便恢复控制。

## 单次实时巡检 FWHM 与真值对比

`tools/capture_fwhm_live_evidence.py` 同时订阅 `/auv/state/filtered`、`/auv/sensors/magnetic` 和 `/auv/cable/tracking`。它只记录本次任务的 `CONFIRM` 横扫阶段，用实时导航位置投影为横扫空间坐标，再对磁场剖面求峰值和左右半高交点。这里没有把“置信度”改名或映射成 FWHM；置信度只作为独立质量指标，FWHM 来自实际采集的磁场—空间样本。

2026-09-23 单次确定性数字孪生巡检共记录 4331 个样本：FWHM 宽度 13.8592 m；垂向距离估计 4.0008 m、真值 4.0000 m；扣除 3.0000 m 高度后得到埋深 1.0008 m、真值 1.0000 m，绝对误差 0.00082 m；有效性 0.9973、置信度 0.9917、覆盖率 1.0000、对称性 0.9867，拒绝原因空。该结果用于证明受控模型中的数据链路、物理关系和反演实现一致，不能替代海试精度结论。

- [FWHM 磁场剖面、真值误差与质量图](assets/defense_demo/fwhm_live/fwhm_live_truth_comparison.png)
- [矢量 PDF](assets/defense_demo/fwhm_live/fwhm_live_truth_comparison.pdf)
- [原始实时样本 CSV](assets/defense_demo/fwhm_live/fwhm_live_samples.csv)
- [质量时序 CSV](assets/defense_demo/fwhm_live/fwhm_quality_timeline.csv)
- [机器可读汇总 JSON](assets/defense_demo/fwhm_live/fwhm_live_summary.json)

答辩时建议先指认磁场剖面的左右半高交点和 FWHM 宽度，再说明无限长直导线模型下宽度与传感器—海缆垂向距离的关系，最后展示埋深误差与质量分解。这样形成“原始测量 → 空间剖面 → 几何特征 → 埋深反演 → 真值校验”的证据链。

## Foxglove 导入

1. 打开 Foxglove Web 或 Desktop 并登录。
2. 添加 `Foxglove WebSocket` 数据源，地址填 `ws://localhost:8765`。
3. 在布局菜单选择 `Import from file`，导入 `foxglove_layout_project/output/auv_defense_1080.json`。
4. 确认 3D 固定坐标系为 `world`。
5. 3D 图层中应能看到以下 topic：

```text
/auv/visual/cable_marker
/auv/visual/history_trail
/auv/visual/search_corridor
/auv/visual/search_pattern
/auv/visual/detection_link
/auv/visual/cable_target
/auv/visual/mission_label
/auv/visual/cable_estimate
/auv/visual/burial_estimate
/auv/visual/position_uncertainty
/auv/visual/magnetic_vector
/auv/visual/fwhm_span
/auv/visual/perception_label
```

当前机器已经完成 Foxglove Desktop 登录，并建立独立个人布局 `AUV Defense Perception 1366`（layout id `lay_0ecaUEHkq4LdDkdb`）。原有布局未覆盖。若换机或清除用户数据，仍按上面的文件导入流程恢复。自动化导入脚本仍可用于截图：

```bash
python3 tools/foxglove_playwright_import_layout.py \
  --layout foxglove_layout_project/output/auv_defense_1080.json \
  --user-data-dir tmp/foxglove_playwright_profile \
  --screenshot docs/experiment/assets/defense_demo/foxglove_defense_1080.png
```

## 上位机

正常启动：

```bash
cd console_soft/auv_console_pyside6
AUV_CONSOLE_THEME=dark python3 main.py --theme dark
```

离屏截图验证：

```bash
cd /home/zmem063/AUV-Master-Project
QT_QPA_PLATFORM=offscreen python3 tools/gui_console_dlt_probe.py \
  --output-dir docs/experiment/assets/defense_demo \
  --width 1600 --height 1000 --theme dark
```

默认 `console_config.yaml` 使用项目内的历史网口地址。如果本机没有该地址，日志会显示 UDP bind 失败，但离线回放和界面截图仍可运行。真实联合控制前应换成正确的本机/PC104 配置。

## 视频复现

上位机 30 秒素材：

```bash
QT_QPA_PLATFORM=offscreen python3 tools/record_console_operator_video.py \
  --tracking-jsonl .auv_data/aux-smoke/tracking.jsonl \
  --output-dir docs/experiment/assets/defense_demo \
  --basename auv_console_short_30s --fps 6 --max-frames 180 \
  --width 1600 --height 1000 --theme dark
```

数字孪生战术视图：

```bash
python3 tools/render_defense_mission_video.py \
  --tracking-jsonl .auv_data/aux-smoke/tracking.jsonl \
  --output docs/experiment/assets/defense_demo/mission_tactical_short_30s.mp4 \
  --fps 6 --max-frames 180
```

登录 Foxglove 前，`auv_joint_demo_30s.mp4` 与 `auv_joint_demo_full_100s.mp4` 可作为答辩 fallback。左侧明确是数字孪生遥测回放，右侧是实际 PySide6 界面。登录后建议录制真实 Foxglove 左窗，再沿用相同的 `ffmpeg hstack` 方式替换左侧素材。

## 运行检查

```bash
source /opt/ros/humble/setup.bash
source brain_linux/install/setup.bash
ros2 node list | rg 'foxglove_bridge|zenoh_viz_bridge'
ros2 topic echo /auv/visual/mission_label --once
ss -ltnp | rg ':8765'
```

`mission_label.header.frame_id` 应为 `world`。Marker 正常频率约为 10 Hz；Foxglove 页面为空时，优先检查固定坐标系、WebSocket 端口和 3D topic 可见性。

v2 演示还应检查：

```bash
ros2 topic info /auv/control/setpoint -v
ros2 topic echo /auv/cable/diagnostics --once
```

第一个命令的 publisher count 必须为 1。`fwhm_valid=false` 时埋深仪表留空是预期质量门控，不应改成伪造值。当前联合验证的量化结果和边界见 `zigzag_fwhm_visualization_20260919.md`。

新版 1366 布局不再使用无刻度彩条。顶部三个状态灯分别回答“任务处于什么阶段、车辆是否已回到巡检线、FWHM 是否允许发布埋深”；其余区域只保留俯视几何、米制位置/埋深曲线、nT 磁场曲线和 0–1 算法质量曲线。

答辩讲解按以下顺序进行：

1. `SEARCH`：先验只限定走廊，AUV 执行有界搜索。
2. `CONFIRM`：检测到磁异常后，沿海缆法向主动横扫，采集空间剖面。
3. FWHM：展示峰值、左右半高交点、宽度、有效性和不确定度。
4. 扫描收束：FWHM 通过后仍保持 `CONFIRM`，先返回横扫中心，避免从扫描端点直接切换任务。
5. `TRACK`：先以 `rejoin_estimated_cable` 就近回归估计电缆线，再以 `inspect_along_cable` 沿线前视巡检，并持续回传埋深和置信度。
6. 异常路径：若缺少一侧交点，则按峰值重新居中并扩大横扫；多次失败则保持拒绝，不发布伪埋深。

## 已验证基线（2026-09-19）

确定性 ROS2 联合验收连续通过。固化报告位于 `assets/defense_demo/defense_assurance_report.json`，摘要位于 `assets/defense_demo/defense_assurance_summary.tsv`。最终一次算法基线数据为：

- 状态时序：`SEARCH 0.12 s → CONFIRM 18.12 s → TRACK 104.82 s`；
- FWHM 宽度：`13.860 m`，覆盖率 `1.000`，拒绝原因空；
- 埋深估计：`1.0011 m`，仿真真值 `1.0000 m`；
- 有效性 `0.9976`，置信度 `0.9920`；
- 完成原因：`fwhm_evidence_complete+center_returned`；
- TRACK 初段：`rejoin_estimated_cable`，随后才进入沿线巡检。

该结果证明受控数字孪生中的算法闭环与物理关系一致。`industrial_ready=false` 在回线初段仍可能出现，因为横偏和埋深不确定度采用更严格的工程验收阈值；界面会如实显示 `REJOIN`，不把算法成功包装成海试验收通过。

## 答辩讲解顺序

1. 上位机任务配置：目标深度、巡检距离、自动/手动模式。
2. Foxglove 搜索阶段：青色廊道与橙色 zig-zag 表示搜索约束与计划。
3. 目标发现：绿色目标点和 AUV—海缆连线说明相对观测关系。
4. 跟踪阶段：蓝色 AUV 轨迹贴合黄色海缆，横偏下降、置信度保持稳定。
5. 状态回传：上位机显示任务阶段、进度、横偏、置信度与 DL/T 风险状态。
6. 结尾主动说明数字孪生边界，并把 MCAP、JSONL、截图和视频作为可追溯证据链。
