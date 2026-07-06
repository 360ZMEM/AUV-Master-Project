# T13 — 声磁电缆探测全流程初步运行与 DL/T 1278 产物

## 1. 定位

本文记录 2026-07-05 在 smoke 基础上完成的声磁电缆探测全流程初步运行。目标不是宣称已经达到最终工业验收，而是确认以下链路是否成立：

- PVS/protocol_udp 数字孪生可以持续输出磁力计数据。
- `auv_cable_tracking_node` 可以接收 mission、调用 `AUV-Master-Mag`、发布 `/auv/cable/tracking` 与 `/auv/control/setpoint`。
- rosbag 可以记录 tracking、magnetic、setpoint 等关键 topic。
- 离线工具可以从 bag 生成 DL/T 1278 风格 CSV、Markdown 报告和可视化图件。
- 指标本身能否支撑工业级结论需要单独判定，不能只看报告是否生成。

## 2. 本轮前置修复

### 2.1 smoke 产物迁移

smoke 报告产物已迁移到：

`docs/thesis/figures/experiments/cable_mag_integration/`

包括：

- `01_cable_burial_profile.png`
- `02_cable_route_deviation.png`
- `03_cable_tracking_confidence.png`
- `dlt1278_report.md`
- `inspection_summary.json`
- CSV 源数据与 manifest

### 2.2 protocol_udp 磁力计链路修复

前序长时调试显示 cable node 已能接收 mission，但不发布 tracking/setpoint。细化日志定位为：

```text
cable tracking waiting for inputs has_odom=True mag_samples=0
```

根因是 protocol_udp 仿真路径使用 `MockAmdUdpServer`，原先仅通过 Zenoh 旁路发布 `ground_truth`，没有发布 `rt/auv/sensors/magnetic`。修复后：

- `sim_holoocean/interfaces/mock_amd_server.py`：从 PVS state 中的 `MagSensorPositionNED` 采样点生成 `B_ned/B_norm`，并通过 magnetic Zenoh 旁路发布。
- `brain_linux/src/auv_bridge/auv_bridge/bridge_backends.py`：protocol_udp side-channel 订阅 `rt/auv/sensors/magnetic`，并复用 `handle_json_sensor_payload()` 转成 ROS2 `/auv/sensors/magnetic`。

该修复不改变 UDP 控制协议帧，只补齐磁探测所需的旁路传感器数据。

## 3. 全流程运行

运行目录：

`/auv_data/bags/20260705_213816/`

核心命令：

```bash
bash scripts/start_experiment.sh \
  --sim-mode both \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --bridge-cfg /home/auv_user/auv_ws/AUV-Master-Project/config/bridge_params.protocol_udp.pvs.yaml \
  --brain-mode stack \
  --arbiter-profile \
  --duration 120 \
  --auto-activate \
  --bag-storage mcap \
  --bag-finalize 30 \
  --wait-before-record 5 \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg cable_tracking_config:=/home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/cable_tracking.yaml
```

mission 发布：

```bash
source /opt/ros/humble/setup.bash
source /home/auv_user/auv_ws/AUV-Master-Project/brain_linux/install/setup.bash
timeout 35s ros2 topic pub -r 2 /auv/mission_command std_msgs/msg/String \
  "{data: \"{\\\"mission_type\\\":\\\"CABLE_TRACKING\\\",\\\"target_depth\\\":12.0,\\\"target_speed_mps\\\":0.8}\"}"
```

必须保留 `--arbiter-profile`。否则 brain 侧会使用默认 `params.yaml`，其中 `zenoh_side_channel_enabled=false`，protocol_udp 磁力计旁路不会打开。

## 4. Bag 证据

MCAP：

`/auv_data/bags/20260705_213816/rosbag/rosbag_0.mcap`

bag 摘要：

| 项目 | 数值 |
|---|---:|
| 时长 | 119.849 s |
| 总消息数 | 79,583 |
| bag 大小 | 391.8 MiB |
| `/auv/sensors/magnetic` | 4,821 |
| `/auv/cable/tracking` | 866 |
| `/auv/cable/diagnostics` | 866 |
| `/auv/control/setpoint` | 1,788 |
| `/auv/mission_command` | 64 |
| `/auv/state/filtered` | 2,016 |

运行日志关键证据：

```text
[bridge] protocol_udp side-channel magnetic sample count=1 keys=['B_ned', 'B_norm', 'sim_time', 'step', 'ts']
cable tracking node ready: enabled=True mission_types=['CABLE_INSPECTION', 'CABLE_TRACKING']
cable mission accepted: CABLE_TRACKING
published cable tracking setpoint count=1 heading_deg=0.00 depth_m=12.00 speed_mps=0.80
published cable tracking setpoint count=850 heading_deg=112.99 depth_m=12.00 speed_mps=0.80
```

未发现：

- `Traceback`
- `ERROR`
- `Bind Error`
- `Address already`

## 5. 离线产物链

新增抽取工具：

`tools/extract_cable_tracking_jsonl.py`

抽取命令：

```bash
python3 tools/extract_cable_tracking_jsonl.py \
  --bag /auv_data/bags/20260705_213816/rosbag \
  --output-jsonl results/cable_ops_report/fullflow_20260705_213816/tracking.jsonl \
  --summary-json results/cable_ops_report/fullflow_20260705_213816/extraction_summary.json
```

报告命令：

```bash
python3 tools/dlt1278_cable_report.py \
  --tracking-jsonl results/cable_ops_report/fullflow_20260705_213816/tracking.jsonl \
  --output-dir results/cable_ops_report/fullflow_20260705_213816 \
  --burial-target-m 1.5 \
  --burial-accuracy-target-m 0.15
```

补充图命令：

```bash
python3 tools/plot_cable_tracking_fullflow.py \
  --tracking-jsonl results/cable_ops_report/fullflow_20260705_213816/tracking.jsonl \
  --output-dir results/cable_ops_report/fullflow_20260705_213816
```

产物目录：

`results/cable_ops_report/fullflow_20260705_213816/`

论文图件同步目录：

`docs/thesis/figures/experiments/cable_mag_integration/fullflow_20260705_213816/`

## 6. DL/T 1278 风格产物

已生成：

- `tracking.jsonl`
- `extraction_summary.json`
- `cable_ops_points.csv`
- `burial_profile.csv`
- `route_deviation.csv`
- `inspection_summary.json`
- `dlt1278_report.md`

基础图件：

- `01_cable_burial_profile.png`
- `02_cable_route_deviation.png`
- `03_cable_tracking_confidence.png`

补充图件：

- `04_cable_track_xy.png`
- `05_cable_guidance_heading.png`
- `06_guidance_feasibility_metrics.png`
- `07_route_offset_distribution.png`

## 7. 当前指标

来自 `inspection_summary.json` 与 `extraction_summary.json`：

| 指标 | 数值 | 解释 |
|---|---:|---|
| tracking 样本数 | 866 | 足以证明 topic 和离线抽取链路有效 |
| 平均 confidence | 0.5 | 当前为常数，不具备动态可信度解释力 |
| confidence span | 0.0 | 标记为 `constant_tracking_confidence` |
| 最大 route offset | 14.717 m | 明显偏大，标记为 `large_route_offset` |
| 平均 route offset | 3.876 m | 说明本轮初步 tracking 还未达到工程稳态 |
| minimum burial depth | 1.5 m | 当前为先验/固定输出，不能证明埋深估计闭环有效 |
| burial accuracy pass | null | 缺少 `burial_sigma_m`，无法判定 0.15 m 精度 |
| zigzag limited samples | 526 / 866 | guidance 限幅实际生效 |
| DL/T 风格总分 | 8 | 触发“海缆位移”II 类扣分 |
| DL/T 风格状态 | 正常状态 | 这是当前简化评分映射的结果，不应单独作为工业最终结论 |
| 工业结论可用性 | limited | 报告结构完整，但证据项仍不足 |

## 8. 工业级结论

本轮可以给出的结论：

- 全流程工程链路已经打通：PVS 磁力计、protocol_udp side-channel、ROS2 cable tracking、control setpoint、rosbag、离线 DL/T 产物均可运行。
- 产物格式已经具备 DL/T 1278 风格：点位表、埋深剖面、路由偏移、评分摘要、Markdown 报告和图件清单都能自动生成。
- tracking 信息可以形成指标：route progress、cross-track、confidence、guidance heading、yaw-rate、turn radius、限幅状态都已进入 JSONL/图件。
- 当前结果只能称为“初步工业证据链样张”，不能作为真实工业验收结论。

不能直接给出的结论：

- 不能证明埋深估计满足 0.15 m 精度，因为 `burial_sigma_m` 缺失。
- 不能证明置信度模型有效，因为 confidence 全程固定为 0.5。
- 不能宣称路线跟踪达到工程可用，因为最大偏移 14.717 m、平均偏移 3.876 m。
- 不能用当前“正常状态”覆盖上述限制；`industrial_conclusion_readiness=limited` 是更准确的工程判断。

## 9. 增补计划落地状态

基于本轮 `limited` 结论，后续增补已经明确分成两类：先让证据链能准确表达“是否可验收”，再通过多次 fullflow 判断是否真的达到门槛。

已落地或正在落地的增补：

1. `AUV-Master-Mag` public API 增加 `DeploymentPerceptionConfig` 与 deployment quality 层，使 `confidence`、`burial_sigma_m`、`quality_flags`、`magnetic_snr_db` 等字段进入主仓 ROS2 输出。
2. 主仓 `cable_tracking_node.py` 消费 quality/acceptance 配置，并在 `/auv/cable/tracking` 中透传 `acceptance_flags` 与 `industrial_ready`。
3. `auv_stack.launch.py` 增加 cable mission autostart 参数，后续 fullflow 可以通过 `enable_cable_mission_autostart:=true` 自动注入 mission。
4. `tools/dlt1278_cable_report.py` 增加 `industrial_acceptance_pass`、验收阈值、p95/p05、valid burial ratio 和 flags 统计。
5. `tools/aggregate_cable_acceptance_runs.py` 用于聚合 ≥3 次 run，输出 pass ratio、worst run 和 readiness 分布。
6. `tools/plot_cable_tracking_fullflow.py` 增加质量 flags、confidence 验收带、burial sigma 验收带、route offset vs guidance 图。
7. Foxglove layout 增加声磁质量与验收证据曲线，便于同时查看 `/auv/cable/tracking`、`/auv/cable/diagnostics` 与核心指标。

仍待通过新实验验证：

1. 短 run 验证 mission autostart 是否稳定触发 `cable mission accepted`。
2. 追加 3 次 120 s fullflow，分别生成单次报告。
3. 聚合多 run，检查 `confidence_span > 0`、`valid_burial_ratio`、`route_offset_p95_m` 和 `industrial_acceptance_pass`。
4. 若 route offset 仍超限，报告应继续保持 `limited` 并列出失败项；不能通过降低阈值制造 ready。

可作为答辩材料的阶段性表述：

> 本阶段已经完成从数字孪生磁力计、专用声磁探测仓库、ROS2 控制接口到 DL/T 1278 风格报告产物的端到端合龙。当前报告可作为产物链和工程闭环的证明，但由于埋深不确定度与动态置信度尚未接入，工业状态结论仍标记为 limited，需要后续用多次实验和真实不确定度估计补强。
