# 09 — DL/T 1278 数字孪生输出

> 本页说明海缆巡检链路从 MCAP bag 到 DL/T 1278 风格验收报告的**离线产物**：哪个工具生成哪些文件、每个字段是什么含义、当前最新的 ready/pass 参考 run 是哪一次。
> 目标读者：跑完 bag 后要生成验收报告、给操作员出图、或做多 run 聚合的验收人员。
>
> 最新状态（2026-07-09）：在数字孪生 clean-prior（§5.5.10）之外，distorted-prior 的 **PVS 六自由度闭环恢复**（§5.5.11(3f)）已用 recovery-gate 两阶段评分口径达成 mid/heavy 各 3/3 ready/pass，见 §5「最新 ready/pass 参考 run」。

---

## 1. 生成的文件

`tools/extract_cable_tracking_jsonl.py` 从 MCAP rosbag 读取 `/auv/cable/tracking`，写出：

- `tracking.jsonl`：DL/T 报告生成器消费的 JSONL 源。
- `extraction_summary.json`：消息数、时间跨度、置信度范围、最大 route offset、源 MCAP chunk。

`tools/dlt1278_cable_report.py` 写出：

- `cable_ops_points.csv`：估计电缆点、横偏、置信度、模式、有效巡检窗口标记。
- `burial_profile.csv`：route progress、埋深、burial sigma、0.15 m 精度目标结果、有效巡检窗口标记。
- `route_deviation.csv`：route progress 与横向偏差。
- `inspection_summary.json`：评分摘要、验收阈值/检查、有效巡检窗口、start-health 检查、数据质量标志、`industrial_acceptance_pass`、`industrial_conclusion_readiness`。
- `dlt1278_report.md`：面向操作员的报告。

`tools/plot_cable_tracking_fullflow.py` 写出补充工程图：

- `04_cable_track_xy.png`：本地 XY 坐标下的估计电缆轨迹。
- `05_cable_guidance_heading.png`：原始与限幅后的期望航向。
- `06_guidance_feasibility_metrics.png`：yaw-rate 与转弯半径指标。
- `07_route_offset_distribution.png`：route offset 样本分布。
- `08_quality_flags_timeline.png`：质量与验收标志计数。
- `09_confidence_acceptance_band.png`：跟踪/磁场置信度相对验收门限。
- `10_burial_sigma_acceptance_band.png`：burial sigma 相对 0.15 m 目标。
- `11_route_offset_vs_guidance.png`：route offset 相对请求制导航向。
- `12_inspection_window_timeline.png`：有效巡检窗口纳入/排除原因。
- `13_burial_sigma_window_diagnosis.png`：burial sigma 诊断，分离排除的 warm-up/末段样本。

`tools/plot_cable_operator_products.py` 读取已有报告目录，在 `operator_view/` 下写出面向操作员的图：

- `01_operator_cable_map.png`：本地 XY 坐标下的电缆地图；有效巡检样本与 warm-up/末段样本分离。
- `02_operator_burial_strip.png`：沿 route progress 的埋深与 burial sigma 带，含目标线。
- `03_operator_route_deviation.png`：沿 route progress 的 route deviation，含验收目标。
- `04_operator_acceptance_summary.png`：readiness、pass/fail、DL/T 风格状态、评分项、验收检查摘要。
- `operator_products_manifest.json`：生成图产物与结论字段的机器可读清单。

`tools/aggregate_cable_acceptance_runs.py` 读取多个 `inspection_summary.json` 或报告目录，写出：

- `acceptance_runs_summary.csv`：每 run 一行。
- `acceptance_runs_summary.json`：pass 比例、readiness 分布、worst run、聚合 route/confidence/burial 指标。
- `acceptance_runs_report.md`：面向操作员的多 run 验收报告。

---

## 2. 工业就绪字段

`industrial_conclusion_readiness` 把「报告生成」与「工程有效性」分开：

- `ready`：当前证据足以支撑初步工程结论。
- `limited`：产物结构完整，但一个或多个证据通道弱或缺失。
- `invalid`：没有可用的跟踪证据。

典型的 `limited` 成因包括缺失埋深不确定度、置信度恒定、或 route offset 过大。

`industrial_acceptance_pass` 更严格，记录当前 run 是否通过所有配置的阈值：

- 最小跟踪样本数，
- 最大与平均 route offset，
- 低分位置信度，
- 有效 burial sigma 比例，
- 最大 burial sigma，
- burial sigma 超限比例，
- 有效巡检窗口有效性，
- start-health 有效性，
- 无质量与验收标志。

有效巡检窗口把可用巡检段与 burial warm-up 样本、参考航线终点之后或 hold/drift 段的样本分开。全程统计仍保留在 `inspection_summary.json` 中，但当报告命令配置了窗口参数时，pass/fail 在有效窗口上评估。

start-health 检查拒绝继承的或陈旧的仿真器初始状态。对当前验收命令，前 30 个样本必须从航线原点附近开始，并落在配置的横偏廊道内。

默认初步多 run 规则是至少 3 次 run 且 pass 比例 ≥ 0.67。单次 `ready` run 是有用证据，但本身不构成稳定的工业验收结论。

---

## 3. recovery-gate 两阶段评分（distorted-prior 专用口径）

distorted-prior 场景起始横偏被人工注入（heavy 约 −10.25 m），车辆需要一段恢复过程才能进廊道。若用普通 start-health 口径，起始段会直接把整 run 判为 `invalid`。因此 distorted-prior 评分改用 recovery-gate 两阶段口径（`tools/dlt1278_cable_report.py` 的 recovery 参数）：

- **第一阶段（恢复段）**：从起点到恢复门（连续 20 帧落入 recovery 廊道且 burial-ready）之间的样本**不计入** DL/T 巡检证据。
- **第二阶段（巡检段）**：从恢复门起、50 m 巡检窗口内、burial-ready，再套用正常巡检廊道与验收阈值。

关键参数（`scripts/score_cable_closedloop_recovery_runs.sh` 的默认值）：

| 参数 | 默认 | 含义 |
|---|---|---|
| `--recovery-start-max-abs-cross-track-m` | 3.4 | 恢复门横偏廊道 |
| `--recovery-start-require-burial-ready` | on | 恢复门须 burial-ready |
| `--recovery-start-consecutive-samples` | 20 | 恢复门连续帧数 |
| `--inspection-route-progress-origin` | recovery | 巡检窗口起点为恢复门 |
| `--inspection-max-route-progress-m` | 50.0 | 巡检窗口长度 |
| `--inspection-max-abs-cross-track-m` | 3.4 | 巡检廊道 |
| `--max-route-offset-target-m` | 3.4 | 验收阈值：max route offset |
| `--mean-route-offset-target-m` | 2.5 | 验收阈值：mean route offset |
| `--max-burial-sigma-m` | 1.2 | 验收阈值：max burial sigma |
| `--start-health-sample-count` | 0 | 关闭普通 start-health（改用 recovery gate） |

该口径**不放宽物理阈值**：corridor 取满足样本充足与三项指标同时达标的较小值 3.4 m（不放到 5 m）。它只是把「恢复过程」与「稳定巡检」分成两段计分，避免起始注入偏差污染巡检段证据。

---

## 4. clean-prior 参考 run（§5.5.10 数字孪生验收）

当前已验证的 clean-prior 数字孪生 run：

- Bag：`/auv_data/bags/20260705_235221/`
- 报告目录：`results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/`
- `industrial_conclusion_readiness`：`ready`
- `industrial_acceptance_pass`：`true`
- DL/T 风格状态：`注意状态`
- DL/T 风格扣分合计：`24`

该 run 通过工业证据检查，而 DL/T 风格评分仍记录两项条件发现：

- `海缆埋深不足`：III 类，16 分。
- `埋深估计精度未达 0.15m`：II 类，8 分。

这一区分是有意的：`ready/pass` 表示该 run 可作为证据；DL/T 风格评分描述的是从该证据推断出的电缆状态。

推荐的操作员图重生成命令：

```bash
python3 tools/plot_cable_operator_products.py \
  --report-dir results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221
```

详细实现说明见 [T16](../thesis/16_cable_dlt1278_scoring_and_operator_products.md)。

---

## 5. 最新 ready/pass 参考 run（§5.5.11(3f) distorted-prior 闭环恢复）

distorted-prior 的 PVS 六自由度闭环恢复，用 recovery-gate 口径评分后 mid/heavy 各 3/3 达 ready/pass：

- 报告目录：`results/cable_ops_report/closedloop_e2e/`（逐 run：`cl_{mid,heavy}_run{1,2,3}_recovery/`）
- 聚合目录：`_agg_mid_recovery/`、`_agg_heavy_recovery/`
- 聚合 `preliminary_acceptance_ready`：`true`（两档）

| tier | run ready/pass | 窗口内点数（min–max） | max route offset（worst，m） | mean route offset（worst，m） | valid_burial_ratio | conf_p05（min） |
|---|---|---:|---:|---:|---:|---:|
| mid | 3/3 | 328–1029 | 3.395（阈 3.4） | 2.412（阈 2.5） | 1.000 | 0.902 |
| heavy | 3/3 | 320–725 | 3.394（阈 3.4） | 2.318（阈 2.5） | 1.000 | 0.902 |

同源对照（在线修正关闭的 `*_prioroff` baseline）：mid/heavy 全程 `max_route_offset` 约 15.3/20.1 m、窗口内点数为 0、0/3 invalid。

复现命令见 [08_cable_inspection_io_contract.md](08_cable_inspection_io_contract.md) §6.5；探索历史（负结果 (3d) → 正结果 (3f)）见 [docs/experiment/cable_distorted_prior_closedloop_20260707.md](../experiment/cable_distorted_prior_closedloop_20260707.md)。

**诚实边界**：本参考 run 为数字孪生确定性先验、人工注入静态位姿扭曲、缆在车下满足直线埋缆前提、窗口内判定、n=3/档。全程含末段离窗漂移时 full-run readiness 仍为 `limited`（如 heavy run3 全程 `max_route_offset=10.26 m`），这是预期边界，不能被误读为 3f 失败。**不得**写成「通过真实海缆检测精度验收」。

---

## 6. 已实现的第一阶段项

- 电缆路由与位移变化。
- 埋深剖面与埋深不足。
- 有 sigma 时对 0.15 m 目标的埋深精度检查。
- 跟踪置信度与 fallback 模式。

---

## 7. 后续可仿真项

- 电缆损伤。
- 铠装或护套磨损。
- 异物缠绕。

---

## 8. 外部输入项

港口、终端、登陆设施、人孔、接地箱、消防、家族缺陷和历史维护记录不是 AUV 数字孪生的自然输出，必须从资产管理或运维记录导入。
