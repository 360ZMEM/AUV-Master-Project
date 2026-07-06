# 磁强计杆臂标定

## 配置模型

仿真使用 `sensor_extrinsics_truth.mag`。运行时和部署使用 `sensor_extrinsics_estimated.mag`。

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

## 仿真路径

`PVSSimWrapper` 在应用真值杆臂后发布 `MagSensorPositionNED`。`HoloOceanPhysicsZenohBridge` 在该位置计算磁场，并发布 `sensor_position_ned`。

## 运行时 Bag 证明

ROS2 运行时不会把 `sensor_position_ned` 放入 `/auv/sensors/magnetic`。该话题保持为标准 `sensor_msgs/MagneticField` 数据流。

为了提供 bag 级证明，`auv_bridge` 发布一个低频 JSON 状态话题：

- 话题：`/auv/sensors/magnetic_extrinsics_status`
- 类型：`std_msgs/String`
- 源文件：`brain_linux/src/auv_bridge/auv_bridge/bridge_node.py`
- 运行时配置：`bridge.magnetic_extrinsics_status`
- 外参配置：`sensor_extrinsics_estimated.mag`
- 来源追踪：`metadata.mag_extrinsics_source`

状态 payload 记录磁数据 key、ROS frame、估计平移/旋转、样本数，以及源 payload 中是否存在仅仿真使用的位置字段。它不得重新发布原始 `sensor_position_ned`，也不得导出 `sensor_extrinsics_truth`。

最新 bag 证明：

```bash
AUV_SKIP_BRAIN_BUILD=1 SIM_DELAY_S=5 bash scripts/start_experiment.sh \
  --sim-mode both \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --bridge-cfg /home/auv_user/auv_ws/AUV-Master-Project/config/bridge_params.protocol_udp.pvs.yaml \
  --brain-mode stack \
  --arbiter-profile \
  --brain-arg params_file:=/home/auv_user/auv_ws/AUV-Master-Project/brain_linux/config/params.protocol_udp_arbiter.yaml \
  --duration 20 \
  --auto-activate \
  --brain-ready-topic /auv/sensors/magnetic \
  --brain-ready-timeout 45 \
  --wait-before-record 1 \
  --bag-finalize 10

python3 tools/verify_mag_extrinsics_bag_proof.py \
  --bag /auv_data/bags/20260705_222030/rosbag \
  --output-json results/mag_extrinsics/bagproof_20260705_222030/mag_extrinsics_bag_proof.json
```

结果：

- `/auv/sensors/magnetic`：905 条消息。
- `/auv/sensors/magnetic_extrinsics_status`：19 条消息。
- `validation_status`：`pass`。
- 失败检查：无。

## 标定脚本

```bash
python tools/mag_extrinsics_calibration_run.py \
  --scenario scenarios/scenario_mag_extrinsics_calibration.yaml \
  --output-dir results/mag_extrinsics/smoke
```

输出：

- `estimated_extrinsics.yaml`
- `residuals.csv`
- `calibration_report.md`

只应用到新的配置文件：

```bash
python tools/mag_extrinsics_apply_estimate.py \
  --base-config config/bridge_params.protocol_udp.pvs.yaml \
  --estimate results/mag_extrinsics/smoke/estimated_extrinsics.yaml \
  --output config/bridge_params.protocol_udp.pvs.mag_estimated.yaml
```
