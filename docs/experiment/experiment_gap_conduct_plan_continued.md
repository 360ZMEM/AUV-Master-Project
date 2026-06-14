# 实验缺口 Conduct 计划续写：完整 P1 与代理电缆场景

本文档承接 `docs/experiment/experiment_gap_conduct_plan.md` 的第 11 节之后内容，用于记录本轮“第一类过程导向补充”和“第二类多样代理环境”的执行结果。由于主 conduct 文档在追加时出现缓存拼接污染，本轮新增记录单独落在此续写文件中。

## 12. 执行记录：完整 P1 补齐与代理电缆 smoke

本轮按“第一类过程导向补充、第二类多样环境低成本 smoke”的原则推进。第一类重点是补齐已有 P1/H1 证据链；第二类重点是先证明代理电缆场景可运行和控制指标可聚合，不把 `n=1` smoke 写成统计结论。

关键新增产物：

```text
results/control/terrain_pid_seed_sweep_20260613_162512_terrain_pid_3seed/
results/control/terrain_pid_seed_sweep_20260613_165856_terrain_pid_low_retry/
results/control/terrain_pid_seed_sweep_20260613_170630_terrain_pid_mid_retry/
results/control_aggregates/20260612_170618_p1_sensor_3seed/
results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/
log/proxy_cable_sweep/20260613_171423_cable_proxy_smoke/results.csv
results/control_aggregates/20260613_171423_cable_proxy_smoke/
log/proxy_cable_sweep/20260613_180210_cable_slope_crossing_ua_retry/results.csv
results/control_aggregates/20260613_180210_cable_slope_crossing_ua_retry/
log/thesis_sweep/20260613_173559_h1_uampc_main_ablation_solvetime/results.csv
results/control_aggregates/20260613_173559_h1_uampc_main_ablation_solvetime/
```

Terrain PID 合并口径：主跑中 high 为 3/3 ok，low 和 mid 各只有 1/3 ok；随后仅重跑失败 seed，最终 low/mid/high 均达到 3/3。合并后的 clearance RMSE 分别为 low `0.5868+/-0.1116 m`、mid `0.7094+/-0.0015 m`、high `0.6102+/-0.0810 m`，三档 `<1.5 m` 安全违规率均为 0。论文中必须注明 low/mid 采用主跑 + retry 合并口径。

P1 控制侧聚合：`results/control_aggregates/20260612_170618_p1_sensor_3seed/control_status_counts.csv` 显示 `generated,24`。旧 bag 的 solve time 仍为 `nan`，但 lateral RMSE、fallback rate、control rate RMS 和 safety violation 可用；所有 P1 场景 fallback rate 与 safety violation rate 均为 0。

P1 NIS/R 聚合：`results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/summary_by_scenario_mode.csv` 中 8 个场景均为 3/3 ok，`r_scale_max` 均达到 5，`r_scale_trigger_ratio` 约为 0.2355-0.3610。该表可用于论文中的 NIS/R 触发统计，但必须区分 real NIS 与 DVL/depth proxy NIS。

H1 solve-time 重跑：`log/thesis_sweep/20260613_173559_h1_uampc_main_ablation_solvetime/results.csv` 为 18/18 ok，控制聚合也为 18/18 generated。`mpc_solve_time_*` 字段可用但当前值为 0 ms，说明 debug payload 字段已补录，但控制器填充的计时语义仍需确认，不能据此声称真实求解耗时为 0 ms。

三个核心代理电缆场景 smoke：`cable_s_curve_proxy`、`cable_slope_crossing_proxy`、`combined_cable_extreme_proxy` 的 seed0 x baseline/ua 运行链路可用。初次控制聚合中 `cable_slope_crossing_proxy + ua` 缺 estimated-state samples，单条 retry 后补齐。该结果只作为 `n=1` smoke，不进入 mean+/-std 主结论。

## 13. 下一步：6 个全量代理电缆场景

第二类场景真实性缺口下一步扩展为 6 个全量代理场景：

```text
cable_s_curve_proxy
cable_hairpin_proxy
cable_slope_crossing_proxy
cable_buried_gap_proxy
cable_cross_current_proxy
combined_cable_extreme_proxy
```

第一轮仍执行低成本 smoke：

```bash
python3 tools/run_proxy_cable_sweep.py \
  --scenarios cable_s_curve_proxy,cable_hairpin_proxy,cable_slope_crossing_proxy,cable_buried_gap_proxy,cable_cross_current_proxy,combined_cable_extreme_proxy \
  --seeds 0 \
  --mpc-modes baseline,ua \
  --duration 30 \
  --label cable_proxy_full6_smoke
```

验收口径：12 条 run 中至少 10 条生成非空 MCAP，并能通过 `tools/aggregate_control_metrics.py` 生成控制侧表。若个别 run 仍因 estimated-state samples 缺失导致聚合失败，只做一次单条 retry；若仍失败，保留为待修复，不展开长时间调试。

实际执行结果：

```text
log/proxy_cable_sweep/20260613_182825_cable_proxy_full6_smoke/results.csv
results/control_aggregates/20260613_182825_cable_proxy_full6_smoke/
```

状态：12/12 ok，控制聚合 `generated,12`。所有场景 safety violation rate 均为 0。`cable_cross_current_proxy` 和 `combined_cable_extreme_proxy` 的 lateral RMSE 最大，符合其作为横流/综合压力场景的定位。UA-MPC 在部分场景 lateral RMSE 略低，但 slope crossing、hairpin 和 combined extreme 中 control rate RMS 明显升高，因此本轮只写成 `n=1` smoke 与待统计趋势。
