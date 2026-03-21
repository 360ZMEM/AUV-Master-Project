# brain_linux

Linux 端 ROS2 Humble 工作区根目录（逐步整合）。

## 当前结构
- src/auv_interfaces: ROS2 消息定义
- src/auv_decision: 已迁入 `auv_decision_core` 包
- src/auv_control: 已迁入 `auv_decision_ros` 包
- src/auv_example: 已迁入 `my_auv_talker` 包
- src/auv_foxglove: 已迁入 Foxglove 布局与联调文档
- src/auv_bridge: Zenoh 适配节点（JSON 桥接）
- src/auv_localization: ES-EKF 定位节点
- src/auv_controller: Setpoint 控制节点

## 约束
- 本层不直接调用 HoloOcean API。

## 快速启动
```bash
cd ../scripts
bash start_lin_brain.sh bootstrap
bash start_lin_brain.sh decision
bash start_lin_brain.sh stack
```
