# 电缆磁探测集成图像

- 来源目录：`/home/auv_user/auv_ws/AUV-Master-Project/results/cable_ops_report/fullflow_20260705_213816`
- 复制文件：cable_ops_points.csv, burial_profile.csv, route_deviation.csv, inspection_summary.json, dlt1278_report.md
- 生成文件：01_cable_burial_profile.png, 02_cable_route_deviation.png, 03_cable_tracking_confidence.png

## 图内中文化重跑（2026-08-06）

- 图 04-13（`tools/plot_cable_tracking_fullflow.py`）已完成图内统一中文（文泉驿正黑，`axes.unicode_minus=False`，字体块在 `main()` 内 matplotlib 导入后注入）。
- 数据依赖型：源 `tracking.jsonl`（866 行 / 944KB，数据在位）。重跑命令：
  `python3 tools/plot_cable_tracking_fullflow.py --tracking-jsonl results/cable_ops_report/fullflow_20260705_213816/tracking.jsonl --output-dir docs/thesis/figures/experiments/cable_mag_integration/fullflow_20260705_213816`
- 术语：burial sigma → 埋深 sigma；confidence → 置信度；route progress → 航迹进度；inspection window → 巡检窗口；magnetic SNR → 磁场信噪比。
- **C 类弱数据证据（暂只中文化不整改，交实验分支决定）**：
  - 图 03/09 跟踪置信度恒为 0.5（未随进度变化）。
  - 图 10/13 埋深 sigma 序列全为空（NaN），仅剩目标线与退化坐标轴。
  - 图 12 航迹偏移在 ~60m 后单调发散、末端跳变至 ~14m，远超偏移目标 2m。
- 图 01-03 由另一脚本（首流程报告）生成，本轮未改；正文引用其中部分。
