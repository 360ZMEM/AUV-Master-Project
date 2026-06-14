# 控制侧指标聚合

本文档说明如何从实验 bag 或 `run_thesis_sweep.py` 的 `results.csv` 中批量解析控制侧指标。

适用场景：

- UA-MPC / baseline-MPC 消融后，需要补充控制性能表。
- 已有 PVS sweep 的 `results.csv`，希望直接按 `scenario/mpc_mode` 聚合控制指标。
- 单个 `.mcap` bag 需要快速检查 lateral RMSE、fallback rate、控制量变化率和安全违规率。

## 核心命令

批量聚合一次 thesis sweep：

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/thesis_sweep/20260612_172535_h1_uampc_main_ablation/results.csv \
  --output-dir results/control_aggregates/20260612_172535_h1_uampc_main_ablation
```

分析单个 bag：

```bash
python3 tools/aggregate_control_metrics.py \
  --bag /auv_data/bags/20260612_172536/rosbag/rosbag_0.mcap \
  --output-dir results/control_aggregates/single_bag_check
```

复用已有 `summary_statistics.csv`，不重新运行 `tools/analyze_bag.py`：

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/thesis_sweep/20260612_172535_h1_uampc_main_ablation/results.csv \
  --output-dir results/control_aggregates/20260612_172535_h1_uampc_main_ablation \
  --reuse-analysis
```

只读取已有分析产物，缺失时不补跑 bag 分析：

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/thesis_sweep/20260612_172535_h1_uampc_main_ablation/results.csv \
  --output-dir results/control_aggregates/check_existing \
  --skip-analyze-bag
```

## 输出文件

| 文件 | 说明 |
|------|------|
| `control_metrics_by_run.csv` | 逐 run 控制侧指标表，包含可用性字段和错误信息 |
| `control_summary_by_scenario_mode.csv` | 按 `scenario/mpc_mode` 聚合的 mean/std 表 |
| `control_status_counts.csv` | 聚合状态计数，用于快速确认成功率 |
| `merged_control_results.csv` | 原 sweep `results.csv` 与控制指标的合并表，不原地覆盖源文件 |
| `control_aggregate_report.md` | 面向论文记录的 Markdown 摘要 |
| `bag_analysis/*/summary_statistics.csv` | 每个 bag 的 `tools/analyze_bag.py --stats-only` 输出 |

## 指标来源

| 指标 | 来源 | 缺失时行为 |
|------|------|------------|
| `lateral_error_rmse_m` | `/auv/diagnostics`，由 `tools/analyze_bag.py` 统计 | `nan` |
| `lateral_error_mean_abs_m` | `/auv/diagnostics` | `nan` |
| `mpc_solve_time_mean_ms` / `p95` / `max` | `/auv/controller/debug` 中的 `solve_time_ms` | `nan` |
| `fallback_rate` | `/auv/controller/debug` 中的 `solver_status`、`fallback_reason`、`state_source_fallback` | `nan` 或 0 |
| `state_source_fallback_rate` | `/auv/controller/debug` 中的 `state_source_fallback` | `nan` |
| `control_rate_rms_per_s` | 优先 `/auv/control/mpc_cmd`，否则 `/cmd_vel` | `nan` |
| `control_rate_mean_abs_per_s` | 同上 | `nan` |
| `control_effort_mean` | 同上 | `nan` |
| `safety_violation_rate` | `seabed_clearance_safety_violation_ratio_1p5m` 与 `seabed_penetration_ratio` 的最大值 | `nan` |
| `seabed_*` / `high_priority_ratio` | `/auv/diagnostics` | `nan` |

逐 run 表中有三个关键可用性字段：

- `diagnostics_available`：是否拿到了 `summary_statistics.csv`。
- `debug_available`：是否读到了 `/auv/controller/debug`。
- `control_available`：是否读到了 `/auv/control/mpc_cmd` 或 `/cmd_vel`。

## MPC solve time 注意事项

旧 bag 可能存在 `/auv/controller/debug`，但没有 `solve_time_ms` 字段。这种情况下：

- `debug_available=true`
- `mpc_solve_sample_count=0`
- `mpc_solve_time_* = nan`

这是录制字段缺失，不代表聚合脚本失败。后续新实验需要使用已经补充过 debug payload 的控制节点，使 `solve_time_ms`、`solver_status` 和 `fallback_reason` 进入 bag。

## H1 示例结果

已验证命令：

```bash
python3 tools/aggregate_control_metrics.py \
  --sweep-results log/thesis_sweep/20260612_172535_h1_uampc_main_ablation/results.csv \
  --output-dir results/control_aggregates/20260612_172535_h1_uampc_main_ablation
```

状态：

```text
generated,18
```

报告位置：

```text
results/control_aggregates/20260612_172535_h1_uampc_main_ablation/control_aggregate_report.md
```

该 H1 批次能解析 lateral RMSE、fallback rate、控制量变化率和安全违规率。MPC solve time 在旧 bag 中为 `nan`，需要后续重跑实验后补齐。

## 常用排查

如果 `control_parse_status=error`，先看 `control_metrics_by_run.csv` 的 `error` 列。

如果控制量变化率为 `nan`，检查 bag 是否录制了：

```text
/auv/control/mpc_cmd
/cmd_vel
```

如果 lateral 或安全指标为 `nan`，检查 bag 是否录制了：

```text
/auv/diagnostics
```

如果 solve time 为 `nan`，检查 `/auv/controller/debug` 的 JSON 是否包含：

```json
{"solve_time_ms": 12.3, "solver_status": "SOLVED"}
```
