# holoocean <-> brain_linux 联调指南（2026-03-21）

## 目标
- 在 `AUV_Master_Project` 代码仓库中，完成仿真侧（holoocean/Zenoh桥）与脑端 ROS2 侧（brain_linux）的端到端联调。
- 使用系统 Python (`/usr/bin/python3`)，避免 Anaconda/conda 污染。

## 环境准备
1. 切换到项目根目录：
```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
```
2. 确认系统 Python：
```bash
which python3
# 期望输出 /usr/bin/python3
```
3. ROS2 Humble：
```bash
source /opt/ros/humble/setup.bash
```
4. 依赖安装（系统 Python）：
```bash
/usr/bin/python3 -m pip install py_trees zenoh pyyaml rclpy geometry_msgs sensor_msgs std_msgs
```
5. 关闭 conda 污染（如已激活）：
```bash
conda deactivate
```

## 1) 启动仿真侧（bridge）
```bash
bash scripts/start_lin_sim.sh bridge
```
- 启动结果应输出 Zenoh 传感器数据（IMU/DVL/Depth）和 cmd_vel 监听。

## 2) 启动脑端 ROS2 侧（stack）
```bash
bash scripts/start_lin_brain.sh stack
```
- 脚本内已实现：
  - 加 `--cmake-clean-cache`
  - 强制 `/usr/bin/python3`（`DPython3_EXECUTABLE` / `DPYTHON_EXECUTABLE`）
  - `source` 过程禁用 `nounset` 错误
  - 选项式节点：`enable_bridge`, `enable_localization`, `enable_controller`, `enable_decision`

## 3) 验证 ROS2 话题
先 source 环境（可在新 shell）：
```bash
source /opt/ros/humble/setup.bash
source /home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux/install/setup.bash
```

列话题：
```bash
ros2 topic list | sort
```
关键话题：
- `/auv/sensors/imu`
- `/auv/sensors/dvl`
- `/auv/sensors/depth`
- `/auv/control/setpoint`
- `/cmd_vel`
- `/auv/state/filtered`
- `/auv/control/cmd`

抽样命令：
```bash
ros2 topic echo /auv/sensors/imu --once
ros2 topic echo /auv/sensors/dvl --once
ros2 topic echo /auv/sensors/depth --once
ros2 topic echo /auv/control/setpoint --once
ros2 topic echo /cmd_vel --once
```

## 4) 关闭流程
1. 在 brain 运行窗口按 `Ctrl+C` 停掉 launch。
2. 在 sim 运行窗口按 `Ctrl+C` 停掉桥。

## 5) 常见问题与调试建议
- 重点：`which python` 必须是 `/usr/bin/python` 或 `/usr/bin/python3`，避免 conda 环境。
- 若报 `ModuleNotFoundError: no module named 'zenoh'`/`py_trees` 等：确保系统 pip 安装成功，并且 `pip` 是 `/usr/bin/python3 -m pip`。
- 若运行失败定位模块路径问题（安装 vs 源码）:
  - 可设置 `AUV_PROJECT_ROOT=/home/gwxie/master_work-tmp/AUV_Master_Project`。
  - 或检查 `brain_linux/src/auv_*/*_node.py` 中项目路径发现逻辑。

## 6) 性能观察（示例）
- 桥延迟：`[bridge] mean sensor ingress latency: 0.32 ms`。
- 状态融合延迟：`9.61 ms`。
- 控制延迟：`21.15 ms`。

---

> 这个文档为 2026-03-21 的一次性联调流程记录，后续可沿用固化为 `docs/联调步骤.md` 并补充长期稳定性测试结果。