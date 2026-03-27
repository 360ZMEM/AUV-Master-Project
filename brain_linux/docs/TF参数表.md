# TF 参数表

本文档整理 `auv_stack.launch.py` 中与 TF 相关的参数，便于联调时快速查阅和调整。

## 默认 TF 结构

- `world -> auv/base_link`：`auv_localization` 发布的动态 TF
- `auv/base_link -> auv/imu_link`：IMU 静态 TF
- `auv/base_link -> auv/dvl_link`：DVL 静态 TF
- `auv/base_link -> auv/depth_link`：深度计静态 TF
- `auv/base_link -> auv/camera_link`：相机占位静态 TF，默认关闭
- `auv/base_link -> auv/sonar_link`：声呐占位静态 TF，默认关闭

## 参数总表

| 参数名 | 默认值 | 作用 | 备注 |
| --- | --- | --- | --- |
| `world_frame_id` | `world` | 动态 TF 根坐标系 | 与 Foxglove 3D 视图固定坐标一致 |
| `base_frame_id` | `auv/base_link` | AUV 本体坐标系 | 动态 TF 子坐标系 |
| `imu_frame_id` | `auv/imu_link` | IMU 静态坐标系名 | 由 `publish_imu_tf` 控制 |
| `dvl_frame_id` | `auv/dvl_link` | DVL 静态坐标系名 | 由 `publish_dvl_tf` 控制 |
| `depth_frame_id` | `auv/depth_link` | 深度计静态坐标系名 | 由 `publish_depth_tf` 控制 |
| `camera_frame_id` | `auv/camera_link` | 相机预留坐标系名 | 默认不发布 |
| `sonar_frame_id` | `auv/sonar_link` | 声呐预留坐标系名 | 默认不发布 |
| `imu_frame_offset_xyz` | `0.0,0.0,0.0` | IMU 外参偏移 | 逗号分隔 `x,y,z` |
| `dvl_frame_offset_xyz` | `0.0,0.0,0.0` | DVL 外参偏移 | 逗号分隔 `x,y,z` |
| `depth_frame_offset_xyz` | `0.0,0.0,0.0` | 深度计外参偏移 | 逗号分隔 `x,y,z` |
| `camera_frame_offset_xyz` | `0.0,0.0,0.0` | 相机外参偏移 | 仅在启用时生效 |
| `sonar_frame_offset_xyz` | `0.0,0.0,0.0` | 声呐外参偏移 | 仅在启用时生效 |
| `publish_tf` | `true` | 是否发布动态 `world -> base_link` | 关闭后只保留里程计输出 |
| `publish_static_tf` | `true` | 是否发布所有静态 TF | 建议保持开启 |
| `publish_imu_tf` | `true` | 是否发布 IMU 静态 TF | 传感器真实挂载后可改 |
| `publish_dvl_tf` | `true` | 是否发布 DVL 静态 TF | 传感器真实挂载后可改 |
| `publish_depth_tf` | `true` | 是否发布深度计静态 TF | 传感器真实挂载后可改 |
| `publish_camera_tf` | `false` | 是否发布相机静态 TF | 预留扩展，默认关闭 |
| `publish_sonar_tf` | `false` | 是否发布声呐静态 TF | 预留扩展，默认关闭 |
| `publish_sensor_status` | `true` | 是否发布 live `/auv/sensors/status` | 让 Foxglove 和决策节点共享状态源 |

## 推荐调参顺序

1. 先确认 `world_frame_id` 和 `base_frame_id`，确保 Foxglove 3D 视图不漂移。
2. 再校准 `imu_frame_offset_xyz`、`dvl_frame_offset_xyz`、`depth_frame_offset_xyz`。
3. 如新增相机或声呐，再打开 `publish_camera_tf` 或 `publish_sonar_tf` 并填外参。
4. 如果只想调试 TF，不想让决策吃 live 状态，可临时关闭 `publish_sensor_status`。

## 现场检查命令

```bash
ros2 topic echo /tf --once
ros2 topic echo /tf_static --once
ros2 topic echo /auv/sensors/status --once
ros2 topic info /auv/sensors/status
```

## 说明

当前 live stack 中，`/auv/sensors/status` 由 `auv_localization` 发布，使用滤波状态构造最小可用消息；回放模式下则由 `mock_sensor_input` 发布。两者共享同一话题名，方便 Foxglove 与决策节点切换工作模式。