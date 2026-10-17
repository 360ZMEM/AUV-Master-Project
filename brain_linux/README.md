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

## 独立磁算法包依赖

`auv_cable_tracking_v2` 的 ROS 入口会导入子仓 `AUV-Master-Mag/src/auv_mag_tracking`。仅构建、source `brain_linux/install` 不会安装这个独立 Python 包；隔离仿真脚本自行修改 `sys.path`，不能代替节点部署检查。开发机可从项目根目录运行：

```bash
/usr/bin/python3 -m pip install --user --no-deps -e AUV-Master-Mag
source /opt/ros/humble/setup.bash
source brain_linux/install/setup.bash
cd /tmp
/usr/bin/python3 -c 'from auv_mag_tracking.v2 import FlythroughConfig; from auv_cable_tracking_v2.cable_tracking_v2_node import CableTrackingV2Node; print("v2 imports ready")'
```

本机已从 `/tmp` 在无临时 `PYTHONPATH` 下通过导入，并由安装空间节点读取新的运行时身份授权配置；12 s 无任务 `ros2 launch` 也同时启动了巡检与 PID 节点。实际 Jetson 服务应把磁算法固定版本安装到**节点使用的同一 Python 解释器/用户环境**，启动前复核导入路径与版本；开发机的 editable 安装不是现场发布包。

## 快速启动
```bash
cd ../scripts
bash start_lin_brain.sh bootstrap
bash start_lin_brain.sh decision
bash start_lin_brain.sh stack
```
