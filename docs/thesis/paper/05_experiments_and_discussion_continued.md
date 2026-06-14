# 第 5 章实验与结果讨论续写：5.5.3 之后

本文档承接 `05_experiments_and_discussion.md` 的 5.5.3 之后内容，用于规避主文档缓存/拼接污染造成的反复覆盖问题。本文档中的结果均保持证据边界：`n=1` 只作为 smoke，`n>=3` 才进入 mean+/-std 统计结论；代理电缆场景只代表可运行的控制稳定性压力测试，不等价于真实海试。

## 5.5.4 完整 P1 多场景鲁棒性补齐

P1 sensor/chaos sweep 已扩展为 8 个 PVS chaos 场景 x 3 seed，共 24 次运行。数据源为：

```text
log/thesis_sweep/20260612_170618_p1_sensor_3seed/results.csv
results/thesis_sweep_aggregates/20260612_170618_p1_sensor_3seed/
```

| 场景 | ok/total | XY RMSE mean+/-std | Z RMSE mean+/-std | CEP50 mean+/-std |
|---|---:|---:|---:|---:|
| dvl_dropout_10 | 3/3 | 2.9723+/-1.4092 m | 0.2030+/-0.0255 m | 2.9817+/-1.4020 m |
| dvl_dropout_30 | 3/3 | 3.3733+/-0.1340 m | 0.2020+/-0.0092 m | 3.3793+/-0.1340 m |
| dvl_dropout_60 | 3/3 | 2.8863+/-0.4556 m | 0.2203+/-0.0105 m | 2.8950+/-0.4545 m |
| dvl_dropout_90 | 3/3 | 3.5483+/-0.2261 m | 0.1927+/-0.0405 m | 3.5537+/-0.2268 m |
| mag_distortion_light | 3/3 | 2.7580+/-0.3413 m | 0.1807+/-0.0075 m | 2.7640+/-0.3395 m |
| mag_distortion_heavy | 3/3 | 3.4160+/-0.1027 m | 0.2220+/-0.0213 m | 3.4233+/-0.1023 m |
| sonar_clutter | 3/3 | 3.2670+/-1.0586 m | 0.2003+/-0.0297 m | 3.2743+/-1.0540 m |
| combined_stress | 3/3 | 3.2720+/-1.0894 m | 0.2037+/-0.0232 m | 3.2790+/-1.0873 m |

该实验说明 8 个 chaos 场景均能稳定完成闭环，成功率为 24/24。需要注意的是，XY RMSE 并不随扰动强度单调变化。例如 dvl_dropout_60 的 XY RMSE 低于 dvl_dropout_30，combined_stress 也未显著高于所有单因素场景。这说明 30 s 片段、随机 seed、初始状态和观测时序仍会影响结果，不宜把单个场景的数值排序写成扰动强度的物理规律。

## 5.5.5 控制侧指标聚合与 UA-MPC 边界

为补齐 P1/H1 中“定位指标不能直接代表控制性能”的缺口，使用 `tools/aggregate_control_metrics.py` 从 bag 中解析 lateral RMSE、fallback rate、control rate RMS、安全违规率和 solve-time 字段。

P1 控制侧聚合路径：

```text
results/control_aggregates/20260612_170618_p1_sensor_3seed/control_summary_by_scenario_mode.csv
results/control_aggregates/20260612_170618_p1_sensor_3seed/control_aggregate_report.md
```

P1 控制侧状态计数为 `generated,24`，说明 8 场景 x 3 seed 均生成控制指标。旧 P1 bag 中 solve time 仍为 `nan`，但 lateral RMSE、fallback rate、control rate RMS 和 safety violation 可用。所有 P1 场景的 fallback rate 与 safety violation rate 均为 0。

H1 solve-time 重跑路径：

```text
log/thesis_sweep/20260613_173559_h1_uampc_main_ablation_solvetime/results.csv
results/control_aggregates/20260613_173559_h1_uampc_main_ablation_solvetime/control_summary_by_scenario_mode.csv
```

| 场景 | 模式 | ok/total | lateral RMSE mean+/-std | fallback rate | control rate RMS | solve time mean |
|---|---|---:|---:|---:|---:|---:|
| baseline | baseline-MPC | 3/3 | 0.00604+/-0.00009 m | 0.2991+/-0.0015 | 0.0608+/-0.0027 | 0 ms |
| baseline | UA-MPC | 3/3 | 0.00599+/-0.00007 m | 0.6345+/-0.0053 | 0.1511+/-0.0116 | 0 ms |
| dvl_dropout_60 | baseline-MPC | 3/3 | 0.00620+/-0.00037 m | 0.3423+/-0.0510 | 0.0785+/-0.0346 | 0 ms |
| dvl_dropout_60 | UA-MPC | 3/3 | 0.00612+/-0.00009 m | 0.6308+/-0.0076 | 0.1459+/-0.0231 | 0 ms |
| combined_stress | baseline-MPC | 3/3 | 0.00813+/-0.00069 m | 0.3081+/-0.0274 | 0.0705+/-0.0238 | 0 ms |
| combined_stress | UA-MPC | 3/3 | 0.00755+/-0.00014 m | 0.6470+/-0.0192 | 0.2578+/-0.1317 | 0 ms |

该重跑显示 `/auv/controller/debug` 中 solve-time 字段已经可被聚合工具读取，但当前值为 0 ms，说明字段填充或计时语义仍需进一步确认。因此论文中不能把 0 ms 写成真实求解性能，只能写成“solve-time 字段已补录，计时语义待确认”。

从控制侧结果看，UA-MPC 在 combined_stress 中的 lateral RMSE 低于 baseline-MPC，但 fallback rate 和 control rate RMS 更高。更稳妥的结论是：UA-MPC 在部分复杂扰动下可能改善横向跟踪误差，但当前权重映射会增加降级/高优先级状态比例和控制变化率，需要后续参数灵敏度实验验证。

## 5.5.6 NIS 与自适应 R 触发统计

P1 NIS/R 批量聚合路径：

```text
results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/summary_by_scenario_mode.csv
results/uncertainty_aggregates/20260612_170618_p1_sensor_3seed/aggregate_report.md
```

| 场景 | ok/total | real NIS mean | real NIS p95 | R scale mean | R scale max | R trigger ratio |
|---|---:|---:|---:|---:|---:|---:|
| dvl_dropout_10 | 3/3 | 4.1234 | 20.4055 | 1.6653 | 5.0000 | 0.3024 |
| dvl_dropout_30 | 3/3 | 3.8250 | 20.0011 | 1.6916 | 5.0000 | 0.2945 |
| dvl_dropout_60 | 3/3 | 4.5086 | 21.0347 | 1.8582 | 5.0000 | 0.3610 |
| dvl_dropout_90 | 3/3 | 3.8798 | 19.3713 | 1.5311 | 5.0000 | 0.2355 |
| mag_distortion_light | 3/3 | 3.3565 | 19.4340 | 1.5275 | 5.0000 | 0.2379 |
| mag_distortion_heavy | 3/3 | 4.4912 | 20.5991 | 1.8050 | 5.0000 | 0.3482 |
| sonar_clutter | 3/3 | 3.8976 | 20.0328 | 1.6470 | 5.0000 | 0.2845 |
| combined_stress | 3/3 | 3.9854 | 19.7641 | 1.6847 | 5.0000 | 0.2946 |

`r_scale_max` 在所有场景中均达到 5，`r_scale_trigger_ratio` 约为 0.2355-0.3610，说明自适应 R 机制在 chaos 场景中确实被触发。DVL dropout 60% 和 heavy magnetic distortion 的触发率较高，符合高扰动场景下测量协方差上调的预期。这里仍需区分 real NIS 与 proxy NIS：real NIS 依赖 ground truth，可用于离线评估；DVL/depth proxy NIS 更接近在线诊断量。

## 5.5.7 Terrain PID 多 seed 复验

Terrain PID 原始地形强度消融为 n=1/档。为使其进入论文统计表，本轮执行 low/mid/high x seeds 0,1,2，并对 low/mid 的落盘失败 seed 做 retry。最终合并口径如下：

```text
results/control/terrain_pid_seed_sweep_20260613_162512_terrain_pid_3seed/
results/control/terrain_pid_seed_sweep_20260613_165856_terrain_pid_low_retry/
results/control/terrain_pid_seed_sweep_20260613_170630_terrain_pid_mid_retry/
```

| terrain | ok/total | clearance RMSE mean+/-std | clearance mean+/-std | min clearance mean+/-std | violation < 1.5 m |
|---|---:|---:|---:|---:|---:|
| low | 3/3 | 0.5868+/-0.1116 m | 3.5461+/-0.1455 m | 3.2594+/-0.3881 m | 0.0000 |
| mid | 3/3 | 0.7094+/-0.0015 m | 3.7094+/-0.0015 m | 3.7083+/-0.0018 m | 0.0000 |
| high | 3/3 | 0.6102+/-0.0810 m | 3.5830+/-0.1117 m | 3.2283+/-0.2053 m | 0.0000 |

三档地形均无 `<1.5 m` 安全违规，说明 PID terrain 在当前 PVS 地形模型下具有稳定的近底安全性。需要在论文脚注中说明：low/mid 的 3 seed 统计由主跑的成功 seed 与 retry 成功 seed 合并得到，retry 原因是 bag/analysis 落盘不稳定，不是算法闭环失败。

## 5.6 代理电缆巡检环境与低成本 smoke

为补足第二类“场景真实性不足”缺口，本轮采用可运行代理路线，而不是扩展 PVS 后端。代理场景通过以下字段组合表达电缆巡检压力：

- `cable_path.points_ned`：电缆中心线几何。
- `digital_twin.terrain_noise_*` 与 `terrain_slope_deg`：近底地形复杂度。
- `perception.noise` 与 `perception.sonar`：声磁观测质量。
- `pvs.current_speed_mps/current_direction_deg`：横流压力。

已完成 3 个核心代理场景 smoke：

```text
cable_s_curve_proxy
cable_slope_crossing_proxy
combined_cable_extreme_proxy
```

运行路径：

```text
log/proxy_cable_sweep/20260613_171423_cable_proxy_smoke/results.csv
results/control_aggregates/20260613_171423_cable_proxy_smoke/
log/proxy_cable_sweep/20260613_180210_cable_slope_crossing_ua_retry/results.csv
results/control_aggregates/20260613_180210_cable_slope_crossing_ua_retry/
```

| 场景 | 模式 | 聚合状态 | lateral RMSE | control rate RMS | safety violation |
|---|---|---:|---:|---:|---:|
| cable_s_curve_proxy | baseline | 1/1 | 2.0428 m | 0.1108 | 0.0000 |
| cable_s_curve_proxy | UA-MPC | 1/1 | 2.0886 m | 0.1988 | 0.0000 |
| cable_slope_crossing_proxy | baseline | 1/1 | 1.4483 m | 0.9864 | 0.0000 |
| cable_slope_crossing_proxy | UA-MPC | 1/1 retry | 1.4479 m | 25.2183 | 0.0000 |
| combined_cable_extreme_proxy | baseline | 1/1 | 3.8501 m | 1.4724 | 0.0000 |
| combined_cable_extreme_proxy | UA-MPC | 1/1 | 4.3672 m | 8.9076 | 0.0000 |

这些结果说明代理电缆链路可以运行，并能生成控制侧指标。由于每个组合只有 seed0，不能写成 baseline-MPC 与 UA-MPC 的统计优劣。尤其是 slope crossing 的 UA-MPC retry 中 control rate RMS 明显偏高，应作为后续参数调节和稳定性分析的重点。

## 5.7 极端电缆巡检场景全量扩展计划

3 个核心场景通过后，下一步扩展为 6 个全量代理电缆场景：

| 场景 | 配置文件 | 主要压力 | 第一轮预算 |
|---|---|---|---|
| `cable_s_curve_proxy` | `config/bridge_params.protocol_udp.pvs.cable_s_curve_proxy.yaml` | 连续反向转弯 | 30s x seed0 x baseline/ua |
| `cable_hairpin_proxy` | `config/bridge_params.protocol_udp.pvs.cable_hairpin_proxy.yaml` | 近 180 deg 掉头 | 30s x seed0 x baseline/ua |
| `cable_slope_crossing_proxy` | `config/bridge_params.protocol_udp.pvs.cable_slope_crossing_proxy.yaml` | 坡面穿越与深度变化 | 30s x seed0 x baseline/ua |
| `cable_buried_gap_proxy` | `config/bridge_params.protocol_udp.pvs.cable_buried_gap_proxy.yaml` | 弱声磁观测代理 | 30s x seed0 x baseline/ua |
| `cable_cross_current_proxy` | `config/bridge_params.protocol_udp.pvs.cable_cross_current_proxy.yaml` | 0.5 m/s 横流 | 30s x seed0 x baseline/ua |
| `combined_cable_extreme_proxy` | `config/bridge_params.protocol_udp.pvs.combined_cable_extreme_proxy.yaml` | 急弯、坡度、横流、声磁噪声和 combined stress | 30s x seed0 x baseline/ua |

执行命令：

```bash
python3 tools/run_proxy_cable_sweep.py \
  --scenarios cable_s_curve_proxy,cable_hairpin_proxy,cable_slope_crossing_proxy,cable_buried_gap_proxy,cable_cross_current_proxy,combined_cable_extreme_proxy \
  --seeds 0 \
  --mpc-modes baseline,ua \
  --duration 30 \
  --label cable_proxy_full6_smoke
```

验收口径为 12 条 run 中至少 10 条生成非空 MCAP，并且 `tools/aggregate_control_metrics.py` 能输出控制侧表。若某个组合因 estimated-state samples 缺失而聚合失败，只允许一次单条 retry；若仍失败，保留为待修复，避免把时间消耗在长时间调试上。

本轮已完成 6 场景 full smoke：

```text
log/proxy_cable_sweep/20260613_182825_cable_proxy_full6_smoke/results.csv
results/control_aggregates/20260613_182825_cable_proxy_full6_smoke/control_summary_by_scenario_mode.csv
results/control_aggregates/20260613_182825_cable_proxy_full6_smoke/control_aggregate_report.md
```

运行状态为 12/12 ok，控制聚合状态为 `generated,12`。关键控制指标如下：

| 场景 | 模式 | lateral RMSE | control rate RMS | safety violation |
|---|---|---:|---:|---:|
| cable_s_curve_proxy | baseline | 2.1037 m | 0.1599 | 0.0000 |
| cable_s_curve_proxy | UA-MPC | 2.0761 m | 0.0158 | 0.0000 |
| cable_hairpin_proxy | baseline | 1.9935 m | 0.4418 | 0.0000 |
| cable_hairpin_proxy | UA-MPC | 1.8406 m | 1.0908 | 0.0000 |
| cable_slope_crossing_proxy | baseline | 1.3978 m | 0.6837 | 0.0000 |
| cable_slope_crossing_proxy | UA-MPC | 1.4551 m | 9.7474 | 0.0000 |
| cable_buried_gap_proxy | baseline | 1.4863 m | 0.4732 | 0.0000 |
| cable_buried_gap_proxy | UA-MPC | 1.4465 m | 1.0797 | 0.0000 |
| cable_cross_current_proxy | baseline | 5.2688 m | 0.2583 | 0.0000 |
| cable_cross_current_proxy | UA-MPC | 5.1426 m | 0.8937 | 0.0000 |
| combined_cable_extreme_proxy | baseline | 4.2081 m | 1.5455 | 0.0000 |
| combined_cable_extreme_proxy | UA-MPC | 4.0706 m | 6.2097 | 0.0000 |

从 smoke 结果看，6 个代理电缆场景均能生成非空 MCAP 和控制侧指标。横流场景和 combined extreme 的 lateral RMSE 明显更大，符合其作为控制压力场景的定位。UA-MPC 在多个场景中 lateral RMSE 略低，但在 slope crossing、hairpin 和 combined extreme 中 control rate RMS 明显升高，因此这里只能写成“可运行压力测试和待统计趋势”，不能写成 UA-MPC 稳定优于 baseline-MPC。

## 5.8 当前实验闭环与剩余缺口

到目前为止，第一类缺失实验已基本闭环：P1 sensor/chaos 3 seed、P1 控制侧聚合、P1 NIS/R 聚合、terrain PID 3 seed、H1 UA-MPC 主消融和 H1 solve-time 重跑均已有可引用产物。主要边界是 H1 solve-time 的计时语义仍需确认，不能用 0 ms 作为求解时间结论。

第二类缺失实验已经完成 3 个核心代理电缆 smoke，并规划扩展到 6 个全量代理场景。该方向的下一步不是直接写强结论，而是先完成 6 场景 seed0 smoke，再按成功率决定是否扩到 3 seed mean+/-std。

第三类硬件与实物证据仍未完成，包括 Jetson 真机算力、AMD UDP 时延、转台磁标定、10A 电缆台和 HSF-500 埋深反演。这些实验依赖现场条件，短期内应写成实验方案、验收指标和未来工作，不能混入已完成软件实验结论。
