# AUV 海缆巡检答辩保障策略

> 2026-09-29 版本提示：本文件是早期答辩保障策略；当前受限磁巡检仿真已收口，最新保留／清理和界面语义见 [当前审阅](workspace_visualization_review_20260929.md)，PPT 主讲以其同步报告为准。


配套的全部图片、视频与机器可读证据索引见 [答辩可视化附件总报告](defense_visualization_all_assets_report_20260923.md)。

## 目标

现场主演示必须稳定形成：任务下达 → 先验引导搜索 → 磁异常检测 → 主动横扫 → FWHM 与埋深估计 → 扫描收束 → 回归估计电缆线 → 沿线跟踪。所有阶段由真实 ROS2 topic 驱动，质量门控失败时不发布埋深。

## 三层证据

### 主路径：确定性算法验收

`scripts/run_defense_assurance.sh` 使用解析无限直导线磁源、运动学 AUV 和动态高度 topic。真值只用于仿真与最终验收，不进入 v2 估计器。脚本以状态链、FWHM 有效性及埋深误差为硬判据，适合答辩现场和录制主视频。

### 扩展路径：PVS 全系统联合运行

`scripts/run_defense_perception_1366.sh` 展示 protocol UDP、控制器、定位、可视化桥和 PVS 的完整集成。它用于说明工程部署链路和复杂场景行为；PVS 场形、深度和海床参数没有标定到受控试验精度，因此不作为现场埋深必成路径。

### 安全路径：拒绝、重扫与回放

算法在缺少双侧交点、SNR 低、场形残差高、沿缆漂移过大或垂距小于高度时拒绝埋深。可靠峰值存在但只缺一侧交点时，扩大扫描会以峰值重新居中。预录 MCAP、30 秒联合视频和 100 秒完整视频用于设备或登录故障时回放。

## 已实施的算法修复

1. 曲线形状尺度与 FWHM—垂距标定系数分离，标定不再反向改变模型残差。
2. 单侧交点缺失且峰值可信时，下一轮横扫以实测峰值重新居中。
3. 双侧交点和覆盖裕量充分时支持提前结束采样，同时保留全部质量门控。
4. 有效 FWHM 产生后先执行第三个航点返回横扫中心，避免从扫描端点直接进入 TRACK。
5. v2 成为 `/auv/control/setpoint` 的唯一发布者，避免旧决策航向与横扫航向竞争。
6. 答辩 profile 使用与 `physical_single_wire` FWHM 关系一致的解析磁源，并单独发布离底高度。
7. TRACK 分为 `rejoin_estimated_cable` 与 `inspect_along_cable`：先就近回到观测修正后的电缆线，再沿线前视，运动叙事不再是难以解释的斜向捷径。

## 界面语义

布局不使用无刻度 Gauge。三个状态灯表示任务阶段、回线状态和 FWHM 发布门控；三张曲线分别使用 m、nT 和 0–1 量纲。3D 主视图只承担环境、海缆、AUV、规划路径、估计点和不确定度的空间关系展示。

## 现场操作

```bash
cd /home/zmem063/AUV-Master-Project
export AUV_DATA_ROOT="$PWD/.auv_data"
scripts/run_defense_assurance.sh --duration 260
```

Foxglove 保持连接 `ws://localhost:8765`，使用 `AUV Defense Perception 1366`。看到脚本输出 `status PASS` 后，保留生成的 MCAP、`assurance_report.json` 和截图作为本场答辩证据。

## 验收结果

2026-09-19 最终基线在 104.82 秒进入 TRACK；FWHM 宽度 13.860 m，埋深估计 1.0011 m（真值 1.0000 m），有效性 0.9976，置信度 0.9920，覆盖率 1.0，拒绝原因空。可追溯副本为 `docs/experiment/assets/defense_demo/defense_assurance_report.json`。
