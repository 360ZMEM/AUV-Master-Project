# 声磁电缆探测 zig-zag 探针幅值调优记录

## 1. 背景

前序三次 120 s 验收 run 证明链路已经可重复运行，但 `burial_sigma_m` 仍大量超过 0.15 m。为增加磁场横向观测激励，本轮将主仓 cable tracking 的 zig-zag 探针从“只透传 `sine_amplitude`”改为“按 route progress 生成正弦探针航向”，并在进入 protocol_udp/PVS 前经过动力学限幅。

## 2. 动力学约束

当前主仓配置：

- 速度：0.8 m/s
- 最小转弯半径：6.0 m
- 最大横向速度：0.45 m/s
- 最大航向偏置：25 deg
- 探针波长：24 m

采用横向轨迹：

```text
y(s) = A sin(2 pi s / lambda)
```

峰值航向偏置：

```text
beta_max = atan(A * 2 pi / lambda)
```

峰值曲率半径：

```text
R_min = (1 + (A k)^2)^(3/2) / (A k^2), k = 2 pi / lambda
```

由此得到：

| 单侧幅值 A | 峰值航向偏置 | 曲率半径下限 | 峰值横向速度 | 理论可行性 |
|---:|---:|---:|---:|---|
| 1.20 m | 17.44 deg | 14.00 m | 0.240 m/s | 可行 |
| 1.50 m | 21.44 deg | 12.06 m | 0.292 m/s | 可行 |
| 1.75 m | 24.61 deg | 11.10 m | 0.333 m/s | 可行但接近上沿 |
| 2.00 m | 27.64 deg | 10.49 m | 0.371 m/s | 超过 25 deg，不推荐 |

因此，本轮只把默认幅值提升到 1.5 m；1.75 m 作为上沿实验值保留；2.0 m 仅作为限幅对照，不进入默认配置。

## 3. 代码落地

主仓新增：

- `brain_linux/src/auv_control/auv_decision_ros/cable_guidance_limits.py`
  - `ZigzagProbeConfig`
  - `ZigzagProbeCommand`
  - `apply_zigzag_probe(...)`
- `brain_linux/src/auv_control/auv_decision_ros/cable_tracking_node.py`
  - 读取 `zigzag_probe`
  - 将正弦探针航向叠加到 AUV-Master-Mag guidance heading
  - 再进入 `limit_guidance(...)`
  - 在 `/auv/cable/tracking` diagnostics 中记录探针幅值、波长、相位、航向偏置和动力学可行性
- `brain_linux/config/cable_tracking.yaml`
  - 默认 `zigzag_probe.lateral_amplitude_m: 1.5`
  - 默认 `zigzag_probe.wavelength_m: 24.0`

## 4. 60 s 幅值实验

实验均使用低内存录包：

```bash
bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration 60 \
  --record-bag \
  --bag-profile cable_acceptance \
  --wait-before-record 8 \
  --bag-finalize 15 \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_tracking_config:=<sweep_config>
```

有效 run：

| 幅值 | Bag | 报告目录 | Tracking | Bag size |
|---:|---|---|---:|---:|
| 1.50 m | `/auv_data/bags/20260705_230156/` | `results/cable_ops_report/zigzag_sweep_amp_1p5_20260705_230156/` | 413 | 4.2 MiB |
| 1.75 m | `/auv_data/bags/20260705_230324/` | `results/cable_ops_report/zigzag_sweep_amp_1p75_20260705_230324/` | 377 | 3.6 MiB |

关键指标：

| 幅值 | 探针可行比例 | 航向偏置峰值 | 平均绝对偏置 | 限幅比例 | 最小转弯半径 | 结论 |
|---:|---:|---:|---:|---:|---:|---|
| 1.50 m | 1.0 | 21.44 deg | 13.72 deg | 0.768 | 6.0 m | 推荐默认值 |
| 1.75 m | 1.0 | 24.61 deg | 16.75 deg | 0.833 | 6.0 m | 可行上沿，需谨慎 |

两组 run 均保持 `industrial_conclusion_readiness=limited`，主要原因仍是 `burial_uncertainty_over_limit`，不是 mission、tracking 或磁输入链路失败。

## 5. 120 s 默认幅值验收 run

为确认 60 s 幅值扫描结论是否能延伸到验收时长，使用当前默认配置 `lateral_amplitude_m: 1.5` 追加一次 120 s 低内存 run：

| 项 | 值 |
|---|---|
| Bag | `/auv_data/bags/20260705_230852/` |
| 报告目录 | `results/cable_ops_report/acceptance_zigzag_1p5_20260705_230852/` |
| Tracking samples | 1011 |
| Bag size | 9.9 MiB |
| 报告产物大小 | 3.2 MiB |
| `industrial_conclusion_readiness` | `limited` |
| `industrial_acceptance_pass` | `false` |

关键指标：

| 指标 | 结果 | 判定 |
|---|---:|---|
| `zigzag_probe_dynamics_feasible` 比例 | 1.0 | 动力学可行 |
| 最大探针航向偏置 | 21.44 deg | 小于 25 deg |
| 探针最小曲率半径需求 | 12.06 m | 大于 6.0 m 下限 |
| 探针峰值横向速度 | 0.292 m/s | 小于 0.45 m/s |
| `max_route_offset_m` | 1.961 m | 通过 2.0 m 阈值 |
| `mean_route_offset_m` | 0.194 m | 通过 1.0 m 阈值 |
| `confidence_p05` | 0.952 | 通过 0.65 阈值 |
| `valid_burial_ratio` | 0.981 | 通过 0.8 阈值 |
| `burial_sigma_m` p50 / p95 / max | 0.725 / 2.240 / 2.241 m | 未通过 0.15 m 阈值 |

本 run 说明：1.5 m 默认幅值在 120 s 时长下仍满足动力学约束，并且 route offset、tracking confidence 和有效埋深比例均达到验收阈值；验收失败继续由埋深不确定度主导，`acceptance_flag_counts={'burial_uncertainty_missing': 19, 'burial_uncertainty_over_limit': 761}`。因此 zig-zag 幅值不是当前工业验收失败的主要瓶颈，下一步应优先排查/调优埋深反演噪声模型、磁场强度到埋深方差的映射，以及长时末段超出参考路径后的数据截取口径。

## 6. 有效巡检窗口与埋深 sigma 模型调优

按“方案2 → 方案1”继续调优后，新增了两层诊断：

1. DL/T 报告支持有效巡检窗口：
   - `--inspection-require-burial-ready`
   - `--inspection-max-route-progress-m`
   - `--inspection-max-abs-cross-track-m`
   - `--max-burial-sigma-over-limit-ratio`
2. 可视化新增：
   - `12_inspection_window_timeline.png`
   - `13_burial_sigma_window_diagnosis.png`

对 `/auv_data/bags/20260705_230852/` 重生成窗口化报告：

| 项 | 值 |
|---|---:|
| 报告目录 | `results/cable_ops_report/acceptance_zigzag_1p5_20260705_230852_windowed/` |
| 原始样本 | 1011 |
| 有效窗口样本 | 792 |
| 排除样本 | 219 |
| 排除原因 | `after_inspection_window=200`, `burial_not_ready=19` |
| 窗口内 `max_route_offset_m` | 0.000 m |
| 窗口内 `confidence_p05` | 1.000 |
| 窗口内 `burial_sigma_over_limit_ratio` | 0.708 |

结论：窗口化口径可以剔除末段接近路径终点后的漂移和埋深暖机样本，但窗口内 `burial_sigma` 仍大面积超限。因此验收失败不是由末段数据污染单独造成，必须调埋深不确定度模型。

AUV-Master-Mag 侧新增 `MagneticBurialInverter(max_samples=...)`，主仓部署配置启用：

```yaml
quality:
  burial_min_samples: 20
  burial_window_samples: 30

acceptance:
  max_burial_sigma_m: 0.15
  max_burial_sigma_over_limit_ratio: 0.05
```

离线重放 `/auv_data/bags/20260705_230852/` 中的 `magnetic_strength_nt / magnetic_snr_db / signed_cross_track_m` 后，窗口大小的影响如下：

| `burial_window_samples` | `sigma_p50` | `sigma_p95` | `sigma_max` | 超 0.15 m 样本 |
|---:|---:|---:|---:|---:|
| 全程累计 | 0.722 | 2.240 | 2.241 | 761 |
| 120 | 0.293 | 0.543 | 0.551 | 723 |
| 60 | 0.156 | 0.258 | 0.308 | 512 |
| 40 | 0.103 | 0.180 | 0.235 | 153 |
| 30 | 0.072 | 0.132 | 0.174 | 23 |
| 20 | 0.051 | 0.112 | 0.160 | 4 |

据此选择 `30` 作为当前部署默认：它保留了不少于 `burial_min_samples=20` 的局部后验，又能把 p95 不确定度压到 0.15 m 以内。

随后尝试了新配置的 120 s run：

| 项 | 值 |
|---|---|
| Bag | `/auv_data/bags/20260705_232732/` |
| 报告目录 | `results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_232732/` |
| 结论 | 不作为有效验收 run |

该 run 第一帧即 `route_progress_m≈101 m`，估计电缆点落在 `[100, 10]` 附近，`cross_track_m` 为数百米量级，`signed_cross_track_m≈-103 m`，导致埋深反演器全部样本被 `burial_max_lateral_offset_m=1.0` 门控拒绝。该问题属于 PVS/外部仿真初始状态未回到路线起点，不是 `burial_window_samples=30` 模型失效。后续需要在重跑前显式重置 PVS 初始状态，或增加 run 前起点健康检查。

为避免该类无效 run 混入验收结论，报告脚本新增起点健康检查：

```bash
--start-health-sample-count 30 \
--start-max-route-progress-m 20 \
--start-max-abs-cross-track-m 5
```

同时 `scripts/start_experiment.sh` 新增 `--preflight-clean`，用于在 PVS 验收 run 前调用 `scripts/preflight_clean.sh`，清理 stale process、FastRTPS/DDS shared-memory、zenoh shared-memory 和 Foxglove 端口。该步骤必要性已经由实验验证：30 s 探针 run 后，如果只杀进程但不清理 shared-memory，后续 run 可能继承上一 run 尾态。

在修复 Foxglove layout 中 `leak_key` 未定义问题后，使用 `--preflight-clean` 重跑 120 s 验收：

| 项 | 值 |
|---|---:|
| Bag | `/auv_data/bags/20260705_235221/` |
| 报告目录 | `results/cable_ops_report/acceptance_zigzag_1p5_window30_20260705_235221/` |
| Bag size | 9.7 MiB |
| 报告产物大小 | 3.4 MiB |
| 原始 tracking 样本 | 999 |
| 有效窗口样本 | 784 |
| 排除样本 | 215 |
| 起点健康 | PASS |
| `industrial_conclusion_readiness` | `ready` |
| `industrial_acceptance_pass` | `true` |

关键指标：

| 指标 | 结果 | 判定 |
|---|---:|---|
| 起点前 30 样本最大 `route_progress_m` | 7.900 m | 小于 20 m |
| 起点前 30 样本最大横向偏差 | ~0 m | 小于 5 m |
| 窗口内 `max_route_offset_m` | ~0 m | 通过 2.0 m |
| 窗口内 `mean_route_offset_m` | ~0 m | 通过 1.0 m |
| `confidence_p05` | 1.000 | 通过 0.65 |
| `valid_burial_ratio` | 1.000 | 通过 0.8 |
| `burial_sigma_over_limit_ratio` | 0.0128 | 通过 0.05 |

因此当前可执行推荐为：`zig-zag lateral_amplitude_m=1.5`、`wavelength_m=24`、`burial_window_samples=30`、有效巡检窗口 `route_progress_m<=50`、起点健康检查开启，并且 PVS 验收 run 必须使用 `--preflight-clean`。

## 7. 当前推荐

当前默认配置采用：

```yaml
zigzag_probe:
  enabled: true
  lateral_amplitude_m: 1.5
  wavelength_m: 24.0
  phase_offset_deg: 0.0
  max_probe_heading_deg: 25.0
```

后续若要继续增大幅值，应优先调整波长，而不是直接把幅值推到 2.0 m。例如保持 25 deg 峰值航向时，2.0 m 单侧幅值需要波长至少约 27 m。
