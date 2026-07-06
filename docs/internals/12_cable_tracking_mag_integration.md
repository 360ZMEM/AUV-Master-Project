# 电缆跟踪磁探测集成

## 边界划分

主仓库负责车辆安全、仲裁、通信传输、控制器执行、仿真管线和可视化。`AUV-Master-Mag` 负责电缆感知、电缆跟踪状态、route progress、埋深估计和 guidance intent。

## 运行时流程

1. `cable_tracking_node.py` 加载 `brain_linux/config/cable_tracking.yaml`。
2. `cable_prior_adapter.py` 通过 `AUV-Master-Mag.api.CableMap` 加载 CSV、GeoJSON 或 YAML 先验。
3. ROS2 导航和磁场消息转换为 `NavigationInput` 与 `MagneticInput`。
4. `AuvMagTrackingPipeline.step_with_guidance()` 返回 tracking 和 guidance。
5. `cable_guidance_limits.py` 将命令限制在配置的车辆运动包线内。
6. 节点发布 `/auv/control/setpoint`；下层链路保持不变。

## 真值边界

仿真真值字段仍可用于评估和 Foxglove 叠加显示，但在线电缆跟踪不得消费 `ground_truth.cable_closest_ned` 或 `ground_truth.cable_distance_m`。
