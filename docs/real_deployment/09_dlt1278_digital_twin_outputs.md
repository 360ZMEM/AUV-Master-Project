# DL/T 1278 数字孪生产物说明

## 生成文件

`tools/extract_cable_tracking_jsonl.py` 从 MCAP rosbag 的 `/auv/cable/tracking` 话题读取数据，并生成：

- `tracking.jsonl`：供 DL/T 报告生成器消费的 JSONL 源数据。
- `extraction_summary.json`：消息数量、时间跨度、置信度范围、最大路由偏差和源 MCAP 分片统计。

`tools/dlt1278_cable_report.py` 生成：

- `cable_ops_points.csv`：估计电缆点、横向偏差、置信度、模式和有效巡检窗口标记。
- `burial_profile.csv`：route progress、埋深、埋深不确定度、0.15 m 精度目标结果和有效巡检窗口标记。
- `route_deviation.csv`：route progress 和横向路由偏差。
- `inspection_summary.json`：评分摘要、验收阈值/检查项、有效巡检窗口、起点健康检查、数据质量标记、`industrial_acceptance_pass` 和 `industrial_conclusion_readiness`。
- `dlt1278_report.md`：面向运维人员的人可读报告。

`tools/plot_cable_tracking_fullflow.py` 生成补充工程诊断图：

- 电缆局部 XY 平面轨迹：
  ![电缆局部 XY 平面轨迹](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/04_cable_track_xy.png)
- guidance heading 原始值和限幅值：
  ![guidance heading 原始值和限幅值](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/05_cable_guidance_heading.png)
- yaw-rate 与 turn-radius 动力学可行性指标：
  ![yaw-rate 与 turn-radius 动力学可行性指标](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/06_guidance_feasibility_metrics.png)
- route offset 样本分布：
  ![route offset 样本分布](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/07_route_offset_distribution.png)
- quality/acceptance flags 时间线：
  ![quality 和 acceptance flags 时间线](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/08_quality_flags_timeline.png)
- tracking/magnetic confidence 与验收阈值：
  ![tracking 和 magnetic confidence 与验收阈值](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/09_confidence_acceptance_band.png)
- burial sigma 与 0.15 m 精度目标：
  ![burial sigma 与 0.15 m 精度目标](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/10_burial_sigma_acceptance_band.png)
- route offset 与 guidance heading 对照：
  ![route offset 与 guidance heading 对照](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/11_route_offset_vs_guidance.png)
- 有效巡检窗口时间线和排除原因：
  ![有效巡检窗口时间线和排除原因](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/12_inspection_window_timeline.png)
- burial sigma 窗口诊断：
  ![burial sigma 窗口诊断](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/13_burial_sigma_window_diagnosis.png)

`tools/plot_cable_operator_products.py` 读取已有报告目录，并在 `operator_view/` 下生成面向运维人员的图像：

- 运维电缆平面图：
  ![运维电缆平面图](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/operator_view/01_operator_cable_map.png)
- 运维埋深条带图：
  ![运维埋深条带图](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/operator_view/02_operator_burial_strip.png)
- 运维路由偏差图：
  ![运维路由偏差图](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/operator_view/03_operator_route_deviation.png)
- 运维验收摘要图：
  ![运维验收摘要图](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/operator_view/04_operator_acceptance_summary.png)
- `operator_products_manifest.json`：生成图像、输入报告目录和结论字段的机器可读清单。

`tools/aggregate_cable_acceptance_runs.py` 读取多个 `inspection_summary.json` 文件或报告目录，并生成：

- `acceptance_runs_summary.csv`：每个 run 一行。
- `acceptance_runs_summary.json`：pass ratio、readiness 分布、最差 run 和聚合后的路由/置信度/埋深指标。
- `acceptance_runs_report.md`：面向运维人员的多 run 验收报告。

## 工业可用性字段

`industrial_conclusion_readiness` 用于区分“报告是否生成”和“证据是否具备工程结论价值”：

- `ready`：当前证据足以支撑初步工程结论。
- `limited`：产物结构完整，但一个或多个证据通道较弱或缺失。
- `invalid`：没有可用的跟踪证据。

典型 `limited` 原因包括埋深不确定度缺失、置信度恒定或路由偏差过大。

`industrial_acceptance_pass` 更严格，用于记录当前 run 是否通过所有配置阈值：

- 最小跟踪样本数；
- 最大和平均路由偏差；
- 低分位置信度；
- 有效 burial sigma 样本比例；
- 最大 burial sigma；
- burial sigma 超限比例；
- 有效巡检窗口合法性；
- 起点健康检查；
- quality flags 和 acceptance flags 是否清零。

有效巡检窗口用于把可用巡检段与埋深 warm-up 样本、参考路径终点后的 hold/drift 样本分离。全量 run 统计仍保留在 `inspection_summary.json` 中；当报告命令配置窗口参数时，pass/fail 按有效巡检窗口计算。

起点健康检查用于拒绝继承旧仿真尾态或 stale simulator 初始状态。当前验收命令要求前 30 个样本从路由起点附近开始，并位于配置的横向偏差走廊内。

默认的初步多 run 验收规则是至少 3 次 run，且 pass ratio >= 0.67。单次 `ready` run 是有价值证据，但不能单独构成稳定的工业验收结论。

## 最新 Ready/Pass 参考 Run

当前已验证的数字孪生 run：

- Bag：`/auv_data/bags/20260705_235221/`
- 报告目录：`results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/`
- `industrial_conclusion_readiness`：`ready`
- `industrial_acceptance_pass`：`true`
- DL/T 风格状态：`注意状态`
- DL/T 风格总分：`24`

该 run 已通过工业证据检查，但 DL/T 风格评分仍记录两个状态发现：

- `海缆埋深不足`：III 类，16 分。
- `埋深估计精度未达 0.15m`：II 类，8 分。

这个区分是有意保留的：`ready/pass` 表示该 run 可作为证据使用；DL/T 风格评分描述的是基于该证据推断出的电缆状态。

推荐的运维图像重生成命令：

```bash
python3 tools/plot_cable_operator_products.py \
  --report-dir results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221
```

详细实现说明见 [T16](../../docs/thesis/16_cable_dlt1278_scoring_and_operator_products.md)。

## 第一阶段已实现项

- 电缆路由和位移变化。
- 埋深剖面和埋深不足。
- burial sigma 可用时，对照 0.15 m 目标进行埋深精度检查。
- 跟踪置信度和 fallback mode。

## 后续可仿真实施项

- 电缆破损。
- 铠装或外护套磨损。
- 异物缠绕。

## 外部输入项

港口、码头、登陆设施、工井、接地箱、消防、家族缺陷和历史运维记录不是 AUV 数字孪生的自然输出，需要从资产管理系统或人工记录导入。
