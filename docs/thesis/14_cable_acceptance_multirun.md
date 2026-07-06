# 声磁电缆探测多次运行验收口径

## 1. 目的

本文承接 `12_cable_mag_dlt1278_fullflow.md` 的 `limited` 结论，定义后续多次 fullflow 的验收方法。目标不是让单次报告“看起来合格”，而是让系统能重复地产生可解释的工业证据：

- 单次 run 生成 DL/T 1278 风格报告和验收字段。
- 多次 run 聚合得到 pass ratio、worst run 和 readiness 分布。
- 若任一关键证据不足，报告保持 `limited` 并列出失败项。

## 2. 单次运行命令

短 run 先验证 mission autostart：

```bash
bash scripts/preflight_clean.sh
bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration 60 \
  --record-bag \
  --bag-profile cable_acceptance \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_tracking_config:=/home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/cable_tracking.yaml
```

通过后执行 3 次 120 s fullflow。每次 run 完成后，从 rosbag 抽取 `/auv/cable/tracking`：

```bash
python3 tools/extract_cable_tracking_jsonl.py \
  --bag /auv_data/bags/<TS>/rosbag \
  --output-jsonl results/cable_ops_report/fullflow_<TS>/tracking.jsonl \
  --summary-json results/cable_ops_report/fullflow_<TS>/extraction_summary.json
```

生成单次报告：

```bash
python3 tools/dlt1278_cable_report.py \
  --tracking-jsonl results/cable_ops_report/fullflow_<TS>/tracking.jsonl \
  --output-dir results/cable_ops_report/fullflow_<TS> \
  --max-route-offset-target-m 2.0 \
  --mean-route-offset-target-m 1.0 \
  --confidence-target 0.65 \
  --max-burial-sigma-m 0.15 \
  --min-valid-burial-ratio 0.8 \
  --min-tracking-samples 300
```

生成补充图件：

```bash
python3 tools/plot_cable_tracking_fullflow.py \
  --tracking-jsonl results/cable_ops_report/fullflow_<TS>/tracking.jsonl \
  --output-dir results/cable_ops_report/fullflow_<TS>
```

## 3. 单次验收字段

`inspection_summary.json` 是单次 run 的主要判定文件。关键字段：

| 字段 | 含义 |
|---|---|
| `industrial_acceptance_pass` | 是否通过全部配置阈值 |
| `industrial_conclusion_readiness` | `ready`、`limited` 或 `invalid` |
| `acceptance_checks` | 每个门槛的 PASS/FAIL |
| `data_quality_flags` | 数据证据缺口 |
| `quality_flag_counts` | 子仓或传感器质量 flags 统计 |
| `acceptance_flag_counts` | 主仓 adapter 单样本验收 flags 统计 |
| `route_offset_p95_m` | 横偏 95 分位 |
| `confidence_p05` | 置信度 5 分位 |
| `valid_burial_ratio` | 有效 `burial_sigma_m` 样本比例 |

判定原则：

- 无 tracking 样本：`invalid`。
- 产物存在但任一关键门槛失败：`limited`。
- 样本量、横偏、置信度、埋深 sigma、质量 flags 全部满足：`ready`。

## 4. 多次运行聚合

聚合命令：

```bash
python3 tools/aggregate_cable_acceptance_runs.py \
  results/cable_ops_report/fullflow_<TS1> \
  results/cable_ops_report/fullflow_<TS2> \
  results/cable_ops_report/fullflow_<TS3> \
  --output-dir results/cable_ops_report/acceptance_multirun_<TS>
```

输出文件：

- `acceptance_runs_summary.csv`
- `acceptance_runs_summary.json`
- `acceptance_runs_report.md`

默认初步门槛：

- `run_count >= 3`
- `pass_ratio >= 0.67`

这只是数字孪生阶段的“初步验收可用”门槛，不替代真实海试验收。

## 5. 当前状态

截至本文生成时，已有基线 run：

- `/auv_data/bags/20260705_213816/`
- `results/cable_ops_report/fullflow_20260705_213816/`

该 run 的结论仍应保留为 `limited`，原因包括：

- confidence 固定为 0.5；
- `burial_sigma_m` 缺失；
- route offset 超限；
- 缺少多次运行统计。

后续新增 run 应以本文命令和字段回填，不覆盖旧基线。

## 6. 20260705 增补验收运行

低内存修复后，已完成一次短 run 和三次 120 s 验收 run。

短 run：

- Bag：`/auv_data/bags/20260705_224131/`
- 报告：`results/cable_ops_report/short_20260705_224131/`
- `/auv/cable/tracking`：339 条
- 结论：链路有效，`industrial_conclusion_readiness=limited`

三次 120 s 验收 run：

| Run | Bag | Report | Tracking | Magnetic | Bag size | Readiness | Pass |
|---|---|---|---:|---:|---:|---|---|
| 1 | `/auv_data/bags/20260705_224334/` | `results/cable_ops_report/acceptance_20260705_224334/` | 1012 | 5284 | 8.6 MiB | `limited` | false |
| 2 | `/auv_data/bags/20260705_224549/` | `results/cable_ops_report/acceptance_20260705_224549/` | 1011 | 5254 | 8.6 MiB | `limited` | false |
| 3 | `/auv_data/bags/20260705_224803/` | `results/cable_ops_report/acceptance_20260705_224803/` | 988 | 5169 | 8.4 MiB | `limited` | false |

聚合报告：

- `results/cable_ops_report/acceptance_multirun_20260705_224334_224803/`
- `pass_ratio=0.0`
- `preliminary_acceptance_ready=false`
- `readiness_distribution={"limited": 3}`

已确认修复：

1. `--bag-profile cable_acceptance` 将 120 s bag 控制在约 8.4-8.6 MiB。
2. mission autostart 与 `/auv/cable/mission_command` 可稳定触发 cable tracking。
3. 三次 run 均有 magnetic、tracking、diagnostics 和 setpoint。
4. confidence 不再恒定，三次 run 的 `confidence_span` 约为 0.056-0.067。

仍阻止工业验收 ready 的问题：

1. `burial_sigma_m` 大量超过 0.15 m，三次 run 均触发 `burial_sigma_over_limit`。
2. 前两次 run 的 `max_route_offset_m` 略超过 2 m。
3. 三次 run 均存在 `quality_flags_present` 和 `acceptance_flags_present`。

因此，本轮增补后的工程结论是：全流程验收链路已经可重复运行，且报告能正确阻止过度结论；但当前算法/参数证据仍不足以进入 `ready`。
