# T16 — DL/T 1278 风格评分实现与运维产物

## 1. 本文定位

本文说明当前声磁电缆巡检 ready/pass run 对应的 DL/T 1278 风格评分实现、自动产物链，以及面向运维人员的图像产物。最新有效样本为：

- Bag: `/auv_data/bags/20260705_235221/`
- 报告目录: `results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/`
- `industrial_conclusion_readiness`: `ready`
- `industrial_acceptance_pass`: `true`
- DL/T 风格状态: `注意状态`
- DL/T 风格扣分合计: `24`

这里有两个不同层级：

1. **DL/T 风格评分**：回答“这段海缆状态如何，触发了哪些缺陷/扣分项”。
2. **工业验收 ready/pass**：回答“本次数字孪生产物证据是否完整、起点是否健康、统计窗口是否有效、指标是否满足工程阈值”。

因此 `ready/pass=true` 不等于“无扣分”。本次 run 的证据链可用，但 DL/T 风格评分仍触发“埋深不足”和“埋深精度未达 0.15 m”的扣分项。

## 2. 数据流

当前产物链如下：

```text
rosbag /auv/cable/tracking
  -> tools/extract_cable_tracking_jsonl.py
  -> tracking.jsonl
  -> tools/dlt1278_cable_report.py
  -> CSV / JSON / Markdown report
  -> tools/plot_cable_tracking_fullflow.py
  -> engineering figures
  -> tools/plot_cable_operator_products.py
  -> operator-facing images
```

验收 run 推荐命令：

```bash
bash scripts/start_experiment.sh \
  --preflight-clean \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration 120 \
  --record-bag \
  --bag-profile cable_acceptance \
  --wait-before-record 8 \
  --bag-finalize 15 \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_tracking_config:=/home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/cable_tracking.yaml
```

`--preflight-clean` 是 PVS 验收 run 的必要条件，用于清理 stale process、FastRTPS/DDS shared-memory、zenoh shared-memory 和 Foxglove 端口，避免继承上一 run 尾态。

## 3. DL/T 风格评分实现

实现位置：

- `tools/dlt1278_cable_report.py`

输入：

- `tracking.jsonl`

关键中间表：

- `cable_ops_points.csv`: 电缆估计点、横向偏差、route progress、tracking confidence、有效窗口标记。
- `burial_profile.csv`: route progress、埋深、埋深不确定度、0.15 m 精度目标、有效窗口标记。
- `route_deviation.csv`: route progress、横向偏差、估计电缆坐标、有效窗口标记。

当前已实现的 DL/T 风格项目：

| 项 | 代码字段 | 判定方式 | 当前状态 |
|---|---|---|---|
| 海缆位移 / 路由偏移 | `cross_track_m` | `max_route_offset_m > max_route_offset_target_m` 时触发 II 类扣分 | 本次未触发 |
| 海缆埋深不足 | `burial_depth_m` | `min(burial_depth_m) < burial_target_m` 时触发 III 类扣分 | 本次触发 |
| 埋深估计精度 | `burial_sigma_m` | 存在样本超过 `burial_accuracy_target_m=0.15` 时触发 II 类扣分 | 本次触发 |
| 跟踪置信度 | `confidence` | 进入工业验收检查，不直接映射为 DL/T 扣分项 | 本次通过 |

当前扣分规则是简化的 DL/T 风格映射：

| 扣分项 | 等级 | 基础分 | 权重 | 分数 |
|---|---|---:|---:|---:|
| 海缆位移 | II | 4 | 2 | 8 |
| 海缆埋深不足 | III | 8 | 2 | 16 |
| 埋深估计精度未达 0.15 m | II | 4 | 2 | 8 |

状态映射：

| 条件 | 状态 |
|---|---|
| `worst_single_score >= 30` | `严重状态` |
| `worst_single_score >= 20` | `异常状态` |
| `total_score > 30` 或 `worst_single_score >= 12` | `注意状态` |
| 其它 | `正常状态` |

本次 run：

| 字段 | 值 |
|---|---:|
| `total_score` | 24 |
| `worst_single_score` | 16 |
| `state` | `注意状态` |

## 4. 工业验收实现

工业验收字段同样由 `tools/dlt1278_cable_report.py` 输出，核心字段在 `inspection_summary.json` 中：

| 字段 | 含义 | 本次值 |
|---|---|---:|
| `industrial_conclusion_readiness` | 证据链是否可用于初步工程结论 | `ready` |
| `industrial_acceptance_pass` | 当前 run 是否通过全部验收检查 | `true` |
| `point_count` | 有效巡检窗口样本数 | 784 |
| `burial_sigma_over_limit_ratio` | 埋深不确定度超限比例 | 0.0128 |
| `start_health.pass` | 起点健康检查 | `true` |

当前验收检查：

| 检查项 | 阈值 / 规则 | 本次结果 |
|---|---|---|
| `min_tracking_samples` | 有效窗口样本数 >= 300 | PASS |
| `max_route_offset` | 最大横向偏差 <= 2.0 m | PASS |
| `mean_route_offset` | 平均横向偏差 <= 1.0 m | PASS |
| `confidence_p05` | 5% 分位置信度 >= 0.65 | PASS |
| `valid_burial_ratio` | 有埋深不确定度的样本比例 >= 0.8 | PASS |
| `burial_sigma_over_limit_ratio` | `burial_sigma_m > 0.15` 的比例 <= 0.05 | PASS |
| `quality_flags_clear` | 有效窗口内无 quality flags | PASS |
| `acceptance_flags_clear` | 除埋深 warm-up/瞬态超限外无 acceptance flags | PASS |
| `start_health` | 前 30 样本 route progress <= 20 m 且横向偏差 <= 5 m | PASS |

有效巡检窗口：

| 项 | 值 |
|---|---:|
| 原始 tracking 样本 | 999 |
| 有效窗口样本 | 784 |
| 排除样本 | 215 |
| `after_inspection_window` | 196 |
| `burial_not_ready` | 19 |

窗口化的目的不是“裁剪到通过”，而是把末段到达参考路径终点后的 hold/drift 和埋深 warm-up 样本从有效巡检证据中分离。全量 run 统计仍保留在 `full_run_summary` 中。

## 5. 自动产物清单

最新报告目录：

`results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/`

核心产物：

| 文件 | 用途 |
|---|---|
| `tracking.jsonl` | 从 rosbag 提取的 `/auv/cable/tracking` 原始 JSONL |
| `extract_summary.json` | 抽取统计：消息数、时间范围、confidence、offset、sigma |
| `inspection_summary.json` | 主判定文件：评分、验收检查、窗口、起点健康、ready/pass |
| `dlt1278_report.md` | Markdown 人可读报告 |
| `cable_ops_points.csv` | 运维点位表 |
| `burial_profile.csv` | 埋深剖面表 |
| `route_deviation.csv` | 路由偏移表 |

工程诊断图：

- 算法视角电缆平面轨迹：
  ![算法视角电缆平面轨迹](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/04_cable_track_xy.png)
- guidance heading：
  ![guidance heading](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/05_cable_guidance_heading.png)
- yaw-rate / turn radius：
  ![yaw-rate / turn radius](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/06_guidance_feasibility_metrics.png)
- route offset 分布：
  ![route offset 分布](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/07_route_offset_distribution.png)
- flags 统计：
  ![flags 统计](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/08_quality_flags_timeline.png)
- confidence 验收带：
  ![confidence 验收带](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/09_confidence_acceptance_band.png)
- burial sigma 验收带：
  ![burial sigma 验收带](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/10_burial_sigma_acceptance_band.png)
- route offset 与 guidance 对照：
  ![route offset 与 guidance 对照](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/11_route_offset_vs_guidance.png)
- 有效巡检窗口时间线：
  ![有效巡检窗口时间线](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/12_inspection_window_timeline.png)
- burial sigma 与窗口诊断：
  ![burial sigma 与窗口诊断](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures/13_burial_sigma_window_diagnosis.png)

## 6. 运维人员图像产物

新增脚本：

- `tools/plot_cable_operator_products.py`

生成命令：

```bash
python3 tools/plot_cable_operator_products.py \
  --report-dir results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221
```

输出目录：

`results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/operator_view/`

输出图像：

- 电缆平面图；彩色为有效巡检段，灰色为 warm-up 或末段剔除样本：
  ![运维电缆平面图](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/operator_view/01_operator_cable_map.png)
- 沿 route progress 的埋深和 burial sigma，含目标线：
  ![运维埋深条带图](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/operator_view/02_operator_burial_strip.png)
- 沿 route progress 的横向偏差，含 2 m 阈值线：
  ![运维路由偏差图](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/operator_view/03_operator_route_deviation.png)
- ready/pass、DL/T 风格状态、扣分合计、扣分项、验收检查汇总：
  ![运维验收摘要图](../../results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/operator_view/04_operator_acceptance_summary.png)
- `operator_products_manifest.json`：记录输入报告目录、生成文件和结论摘要。

这些图像不替代工程诊断图。它们的用途是让非算法人员快速判断：

1. 本次是否是有效巡检段。
2. 电缆位置和巡检覆盖到哪里。
3. 埋深/不确定度是否有明显问题。
4. 是否可以把该 run 作为运维报告附件。

## 7. 当前限制

- 当前 DL/T 风格评分只覆盖路由偏移、埋深、埋深精度和 tracking confidence 相关证据。
- 电缆破损、铠装/外护套磨损、异物缠绕等项目仍属于后续可仿真实施项。
- 港口、码头、陆上终端、工井、接地箱、消防、家族缺陷、历史运维记录等不能由 AUV 数字孪生自然生成，需要资产管理系统或人工记录输入。
- 本次 run 的 `constant_tracking_confidence` 仍作为 data quality flag 保留；它不阻断 ready/pass，但提示后续应继续改进动态置信度表达。

## 8. 复现命令

从 bag 到完整产物：

```bash
python3 tools/extract_cable_tracking_jsonl.py \
  --bag /auv_data/bags/20260705_235221/rosbag \
  --output-jsonl results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/tracking.jsonl \
  --summary-json results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/extract_summary.json

python3 tools/dlt1278_cable_report.py \
  --tracking-jsonl results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/tracking.jsonl \
  --output-dir results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221 \
  --inspection-require-burial-ready \
  --inspection-max-route-progress-m 50 \
  --inspection-max-abs-cross-track-m 2.0 \
  --max-burial-sigma-over-limit-ratio 0.05 \
  --start-health-sample-count 30 \
  --start-max-route-progress-m 20 \
  --start-max-abs-cross-track-m 5

python3 tools/plot_cable_tracking_fullflow.py \
  --tracking-jsonl results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/tracking.jsonl \
  --output-dir results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/figures \
  --inspection-require-burial-ready \
  --inspection-max-route-progress-m 50 \
  --inspection-max-abs-cross-track-m 2.0

python3 tools/plot_cable_operator_products.py \
  --report-dir results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221
```
