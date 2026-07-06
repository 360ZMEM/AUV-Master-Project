# T14 — 磁传感器杆臂改正全程验证

## 1. 目标

本文记录磁传感器杆臂改正从配置、仿真采样、标定估计、配置应用到验证产物的全流程。这里讨论的是磁传感器 `mag` 的杆臂与安装角，不是此前 F2 中 DVL/Depth 外参敏感度实验。

本轮目标：

- 明确 `sensor_extrinsics_truth.mag` 与 `sensor_extrinsics_estimated.mag` 的职责。
- 验证 PVS/protocol_udp 路径使用磁传感器杆臂后的采样点。
- 运行模拟标定脚本，生成估计外参。
- 将估计值写入新配置文件，不覆盖原始部署配置。
- 生成误差、残差和图件，形成可归档证据。
- 增加可录 bag 的低频杆臂/外参状态证据，不高频广播所有相对位置。

## 2. 配置模型

基础配置：

`config/bridge_params.protocol_udp.pvs.yaml`

当前 truth/estimated：

```yaml
sensor_extrinsics_truth:
  mag:
    translation_b_m: [0.30, 0.00, -0.05]
    rotation_rpy_deg: [0.0, 0.0, 2.0]

sensor_extrinsics_estimated:
  mag:
    translation_b_m: [0.20, 0.03, -0.02]
    rotation_rpy_deg: [0.0, 0.0, 0.5]
```

语义：

- `sensor_extrinsics_truth.mag`：仿真真值，只能用于数字孪生生成传感器观测。
- `sensor_extrinsics_estimated.mag`：运行和部署侧估计值，可由标定输出替换。
- 所有外参均为 6D：`translation_b_m` + `rotation_rpy_deg`。

## 3. 仿真与运行时链路

代码路径：

- `common/sensor_extrinsics.py`
  - `base_position_to_sensor_world()` 根据 `p_base_n + R_nb @ translation_b_m` 计算传感器世界坐标。
- `sim_holoocean/interfaces/pvs_sim_wrapper.py`
  - 读取 `sensor_extrinsics_truth.mag`。
  - 输出 `MagSensorPositionNED`。
- `sim_holoocean/interfaces/holoocean_physics_bridge.py`
  - 使用 `MagSensorPositionNED` 作为磁场计算位置。
  - JSON payload 中包含 `sensor_position_ned`。
- `sim_holoocean/interfaces/mock_amd_server.py`
  - protocol_udp/PVS 路径同样优先使用 `MagSensorPositionNED` 生成磁力计 payload。
- `brain_linux/src/auv_bridge/auv_bridge/bridge_backends.py`
  - protocol_udp side-channel 订阅 `rt/auv/sensors/magnetic`。
- `brain_linux/src/auv_bridge/auv_bridge/bridge_node.py`
  - 将 magnetic JSON 转成 ROS2 `/auv/sensors/magnetic`。
  - 低频发布 `/auv/sensors/magnetic_extrinsics_status`，记录 magnetic 来源、frame、estimated 外参和来源文件。

bag 证明边界：

`sensor_msgs/MagneticField` 只保留磁场矢量，不携带 `sensor_position_ned`。为避免在分立实机部署中广播所有相对位置，运行侧新增低频 `std_msgs/String` topic `/auv/sensors/magnetic_extrinsics_status`。该 topic 不发布原始 `sensor_position_ned`，只发布：

- `schema_version`
- `magnetic_topic`
- `magnetic_key`
- `magnetic_msg_frame_id`
- `uses_estimated_extrinsics`
- `estimated_extrinsics_source`
- `estimated_translation_b_m`
- `estimated_rotation_rpy_deg`
- `truth_extrinsics_exported`
- `sample_count`
- `payload_has_sensor_position_ned`
- `simulator_position_present`

因此，ROS bag 证明目标从“广播每个采样点坐标”改为“证明磁场 topic 存在、运行侧使用 estimated 外参、truth 没有在线导出、仿真专用 raw position 没有进入 ROS2 诊断流”。

## 4. 测试与验证命令

语法检查：

```bash
python3 -m py_compile \
  tools/mag_extrinsics_calibration_run.py \
  tools/mag_extrinsics_apply_estimate.py \
  tools/plot_mag_extrinsics_validation.py \
  tools/verify_mag_extrinsics_bag_proof.py \
  common/sensor_extrinsics.py \
  sim_holoocean/interfaces/pvs_sim_wrapper.py \
  sim_holoocean/interfaces/mock_amd_server.py \
  sim_holoocean/interfaces/holoocean_physics_bridge.py
```

聚焦测试：

```bash
PYTHONPATH=. python3 -m pytest -q \
  tests/test_sensor_extrinsics.py \
  tests/test_es_ekf_extrinsics.py \
  tests/test_mag_sensor_extrinsics.py \
  tests/test_pvs_time_scale_config.py \
  tests/test_mag_extrinsics_bag_proof.py \
  brain_linux/src/auv_bridge/test/test_magnetic_extrinsics_status.py
```

结果：

```text
bag proof focused tests: 4 passed in 0.28s
```

## 5. 标定全流程

标定场景：

`scenarios/scenario_mag_extrinsics_calibration.yaml`

运行：

```bash
python3 tools/mag_extrinsics_calibration_run.py \
  --scenario scenarios/scenario_mag_extrinsics_calibration.yaml \
  --output-dir results/mag_extrinsics/fullflow_20260705_2145
```

应用估计值到新配置：

```bash
python3 tools/mag_extrinsics_apply_estimate.py \
  --base-config config/bridge_params.protocol_udp.pvs.yaml \
  --estimate results/mag_extrinsics/fullflow_20260705_2145/estimated_extrinsics.yaml \
  --output results/mag_extrinsics/fullflow_20260705_2145/bridge_params.protocol_udp.pvs.mag_estimated.yaml
```

绘图：

```bash
python3 tools/plot_mag_extrinsics_validation.py \
  --input-dir results/mag_extrinsics/fullflow_20260705_2145 \
  --output-dir results/mag_extrinsics/fullflow_20260705_2145
```

应用后配置兼容性短跑：

```bash
bash scripts/start_experiment.sh \
  --sim-mode both \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --bridge-cfg /home/auv_user/auv_ws/AUV-Master-Project/results/mag_extrinsics/fullflow_20260705_2145/bridge_params.protocol_udp.pvs.mag_estimated.yaml \
  --brain-mode stack \
  --arbiter-profile \
  --no-record-bag \
  --duration 40 \
  --auto-activate
```

## 6. 产物

结果目录：

`results/mag_extrinsics/fullflow_20260705_2145/`

图件同步目录：

`docs/thesis/figures/experiments/mag_lever_arm_fullflow_20260705_2145/`

产物：

- `estimated_extrinsics.yaml`
- `validation_summary.json`
- `residuals.csv`
- `calibration_report.md`
- `bridge_params.protocol_udp.pvs.mag_estimated.yaml`
- `01_mag_extrinsics_residual.png`
- `02_mag_extrinsics_error_reduction.png`

## 7. 指标

来自 `validation_summary.json`：

| 指标 | 初值 | 估计后 | 改善 |
|---|---:|---:|---:|
| translation error | 0.1086 m | 0.0041 m | 96.27 % |
| rotation error | 1.5000 deg | 0.0704 deg | 95.31 % |

其它参数：

| 项目 | 数值 |
|---|---:|
| duration | 120.0 s |
| dt | 0.1 s |
| samples | 1201 |
| residual start | 0.1086 m |
| residual end | 0.0048 m |
| validation status | pass |

应用后配置短跑：

| 项目 | 结果 |
|---|---|
| run dir | `/auv_data/bags/20260705_220040/` |
| duration | 40 s |
| record bag | false |
| bridge config | `results/mag_extrinsics/fullflow_20260705_2145/bridge_params.protocol_udp.pvs.mag_estimated.yaml` |
| magnetic side-channel | subscribed, sample count reached 800 |
| error keywords | no `Traceback` / `ERROR` / `Bind Error` / `Address already` / `Exception` matched |

bag 闭环证明：

| 项目 | 结果 |
|---|---|
| run dir | `/auv_data/bags/20260705_222030/` |
| rosbag | `/auv_data/bags/20260705_222030/rosbag/rosbag_0.mcap` |
| proof summary | `results/mag_extrinsics/bagproof_20260705_222030/mag_extrinsics_bag_proof.json` |
| duration | 19.83 s |
| `/auv/sensors/magnetic` | 905 messages |
| `/auv/sensors/magnetic_extrinsics_status` | 19 messages |
| status/magnetic ratio | 0.02099 |
| validation status | pass |

校验命令：

```bash
python3 tools/verify_mag_extrinsics_bag_proof.py \
  --bag /auv_data/bags/20260705_222030/rosbag \
  --output-json results/mag_extrinsics/bagproof_20260705_222030/mag_extrinsics_bag_proof.json
```

估计结果：

```yaml
sensor_extrinsics_estimated:
  mag:
    translation_b_m:
      - 0.30001230153357483
      - 0.002987455375084699
      - -0.05274137855362218
    rotation_rpy_deg:
      - -0.04452959193786371
      - -0.02273353925858613
      - 1.950417672250177
```

## 8. 结论

本轮可以确认：

- 磁传感器杆臂配置模型已经明确区分 truth 与 estimated。
- PVS 路径会把 base 位置通过 truth 杆臂转换到 `MagSensorPositionNED`。
- protocol_udp/PVS 磁力计 payload 使用 `MagSensorPositionNED` 作为磁场采样位置。
- 标定脚本可以从有偏初值收敛到接近 truth 的估计值。
- 应用脚本只写新配置，不覆盖原配置，满足部署安全要求。
- 验证结果为 `pass`，平移和旋转误差均显著下降。
- 使用估计外参写出的新配置可以启动 PVS/protocol_udp 40 秒短跑，磁力计 side-channel 正常。
- 新增 bag proof 基础设施后，`/auv/sensors/magnetic_extrinsics_status` 以低频记录 estimated 外参、来源文件、frame 和 sample count。
- bag `20260705_222030` 的离线校验结果为 `pass`：磁场 topic 有样本，status topic 低频有样本，使用 estimated 外参，未导出 `sensor_extrinsics_truth`，未重发布 raw `sensor_position_ned`。

仍需保留的边界：

- 当前标定是第一阶段模拟标定 scaffold，不是实船外场标定算法。
- ROS2 `/auv/sensors/magnetic` 当前不携带 `sensor_position_ned`；bag 级闭环证据由 `/auv/sensors/magnetic_extrinsics_status` 提供。
- 当前验证证明“杆臂改正链路和文件契约成立”，不能替代真实磁传感器安装误差的外场标定。

可写入论文/答辩的阶段性表述：

> 本阶段完成了磁传感器杆臂改正从配置、仿真采样、模拟标定到估计配置应用的端到端验证。仿真标定中，平移误差由 0.1086 m 降至 0.0041 m，安装角误差由 1.5000 deg 降至 0.0704 deg，说明当前软件链路具备承载实际杆臂标定结果的工程能力；但真实部署仍需外场数据完成最终标定。
