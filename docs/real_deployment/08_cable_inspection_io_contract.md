# 电缆巡检工业输入/输出契约

## 必需输入

- 电缆先验：CSV、GeoJSON 或 YAML 点列，坐标应使用本地 NED/工程坐标。在线代码不得消费仿真真值字段。
- 导航状态：`/auv/state/filtered`，消息类型为 `nav_msgs/Odometry`，运行时转换为 `NavigationInput`。
- 磁强计：`/auv/sensors/magnetic`，消息类型为 `sensor_msgs/MagneticField`，从 Tesla 转换为 nT 后进入磁探测链路。
- 可选声呐：当真实 ROS 话题可用时，转换为 `SonarInput`。
- 传感器外参：仿真使用 `sensor_extrinsics_truth`，部署/运行时标定使用 `sensor_extrinsics_estimated`。

## 运行时输出

- `/auv/control/setpoint`：高层电缆跟踪命令，仍受 controller、bridge、arbiter 和 guard 链路保护。
- `/auv/cable/tracking`：来自 `AUV-Master-Mag` 的 JSON 跟踪输出，以及限幅后的 guidance。
- `/auv/cable/diagnostics`：置信度、模式、磁数据使用情况、route progress、埋深和限幅原因。
- `/auv/sensors/magnetic_extrinsics_status`：低频 bag 证明话题，用于证明磁强计安装位姿/外参状态。该话题记录估计外参、来源文件、磁数据 frame/key 和样本数；不得广播原始 `sensor_position_ned`，也不得广播任何 `sensor_extrinsics_truth` 值。

## 真机部署时需要替换的配置文件

- `brain_linux/config/cable_tracking.yaml`
- 包含 `sensor_extrinsics_estimated.mag` 的 brain 运行时参数文件，当前为 `brain_linux/config/params.protocol_udp_arbiter.real.yaml`
- 数字孪生运行中包含 `sensor_extrinsics_estimated.mag` 的 bridge/仿真配置
- `prior.path` 指向的真实电缆先验文件

磁强计杆臂标定完成后，应使用 `tools/mag_extrinsics_apply_estimate.py` 生成新的配置文件并写入估计值。不要原地覆盖基础配置。生成配置应保留 `metadata.mag_extrinsics_source`，便于现场运维人员追踪本次运行使用了哪一个标定结果。

真机闭环巡检前，应将 `brain_linux/config/params.protocol_udp_arbiter.real.yaml` 中示例性的 `sensor_extrinsics_estimated.mag` 替换为现场标定结果。保持 `bridge.magnetic_extrinsics_status.enabled=true`，让每个 rosbag 都能证明当时启用的是哪组估计外参。

## Bag 证明验收

每次联调 bag 结束后运行：

```bash
python3 tools/verify_mag_extrinsics_bag_proof.py \
  --bag /path/to/rosbag \
  --output-json /path/to/mag_extrinsics_bag_proof.json
```

验收要求：

- `/auv/sensors/magnetic` 有样本。
- `/auv/sensors/magnetic_extrinsics_status` 有低频样本。
- `uses_estimated_extrinsics=true`。
- `estimated_extrinsics_source` 存在。
- `truth_extrinsics_exported=false`。
- status 话题没有重新发布原始 `sensor_position_ned` 字段。

## 禁止进入在线链路的输入

- `ground_truth.cable_closest_ned`
- `ground_truth.cable_distance_m`
- 任何 `evaluation_*` 字段或仅仿真可用的真实电缆状态
- 真机上的 `sensor_extrinsics_truth.*`
- 用高频广播所有传感器相对位置的方式替代经过标定的部署配置
