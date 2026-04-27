# AUV Decision ROS Package (auv_decision_ros)

本包提供基于 ROS2 的 AUV 决策节点与日志回放工具：
- 核心决策逻辑由 `auv_decision_core` 提供（行为树 + 黑板）。
- ROS2 节点负责订阅 `SensorStatus`，并发布 `ControlGoal`。
- 提供日志回放（从历史文本日志中提取传感数据）以便在没有真实传感器时完成端到端测试。

---

## 目录结构

```
brain_linux/src/auv_control/
├── launch/
│   └── decision_replay.launch.py   # 一键启动回放 + 决策节点
├── auv_decision_ros/
│   ├── decision_node.py             # ROS2 决策节点（行为树 Tick、日志节流）
│   ├── mock_sensor_input.py         # 从 $AUV 文本日志行生成 SensorStatus
│   └── mappers.py                   # ROS 消息与核心数据结构的转换
├── setup.py / setup.cfg / package.xml
└── README.md
```

---

## 先决条件

1. **ROS2 Humble** 已安装（`source /opt/ros/humble/setup.bash`）。
2. 依赖包已编译：
   ```bash
   cd /home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux
   colcon build --packages-select auv_common auv_interfaces auv_decision_core auv_decision_ros
   ```
3. 推荐 `--symlink-install` 以便 Python 代码改动即时生效。

---

## 运行方式

### 1) 通过 Launch 快速启动（推荐）

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux
source install/setup.bash
ros2 launch auv_decision_ros decision_replay.launch.py
```

该命令会：
- 使用 `mock_sensor_input` 读取内置样例日志并发布 `SensorStatus`。
- 启动 `decision_node` 执行行为树并发布 `ControlGoal`。
- 将决策摘要以可读日志输出（包括行为树结构节流）。

### 2) 使用自定义日志文件

```bash
ros2 launch auv_decision_ros decision_replay.launch.py \
  log_file:=/path/to/your/AUV_log.txt
```

仓库内置样例日志位置：
```
/home/gwxie/master_work-tmp/Console上位机软件/auv_console_python/20020101103632.txt
```

### 3) 直接运行决策节点（无回放）

如果你已有传感器节点在发布 `SensorStatus`：

```bash
ros2 run auv_decision_ros decision_node
```

---

## Launch 参数一览

| 参数 | 含义 | 默认值 |
| --- | --- | --- |
| `log_file` | 海试文本日志路径（$AUV 格式） | 自动搜索仓库内置样例 |
| `publish_hz` | 日志回放发布频率 (Hz) | `10.0` |
| `battery_low_voltage_threshold` | 低电压阈值 (V) | `95.0` |
| `seabed_depth_m` | 海底参考深度 (m) | `15.0` |
| `seabed_proximity_margin_m` | 近底告警余量 (m) | `1.5` |
| `confidence_threshold` | 行为树置信度阈值 | `0.7` |
| `bt_status_publish_period` | 行为树状态发布周期 (s) | `0.5` |
| `tree_print_period` | 行为树 Unicode 树图打印周期 (s) | `5.0` |
| `summary_log_period` | 决策摘要日志打印周期 (s) | `2.0` |

### 修改运行参数示例

```bash
ros2 launch auv_decision_ros decision_replay.launch.py \
  publish_hz:=5.0 \
  confidence_threshold:=0.8 \
  tree_print_period:=10.0
```

---

## Topic 订阅/发布

| 方向 | Topic | 消息类型 | 说明 |
| --- | --- | --- | --- |
| 订阅 | `/auv/sensors/status` | `auv_interfaces/SensorStatus` | 传感状态输入 |
| 订阅 | `/auv/control/setpoint` | `auv_interfaces/Setpoint` | 当前设定点（用于深度误差计算） |
| 发布 | `/auv/control/goal` | `auv_interfaces/ControlGoal` | 决策输出目标 |
| 发布 | `/auv/metrics/depth_error` | `std_msgs/Float32` | 深度误差 |
| 发布 | `/auv/metrics/lateral_error` | `std_msgs/Float32` | 横向误差 |
| 发布 | `/auv/display/confidence_text` | `std_msgs/String` | Markdown 格式置信度文本 |
| 发布 | `/auv/display/power_text` | `std_msgs/String` | Markdown 格式电源状态文本 |

---

## 输出日志示例

```text
[mock_sensor_input] 已加载日志: /home/gwxie/.../20020101103632.txt
[mock_sensor_input] 可回放数据行数: 12345
[decision_node] Summary: depth=5.2m, leak=OK, confidence=0.81, vol=25.1V, alarm=0x02, state=DiveToDepth
[decision_node] BehaviorTree:
  ├─ ParallelTracking (SUCCESS)
  │  ├─ DiveToDepth (RUNNING)
  │  └─ EmergencySurface (FAILURE)
```

---

## 验证方法

1. 启动回放 + 决策：
   ```bash
   ros2 launch auv_decision_ros decision_replay.launch.py
   ```
2. 观察终端输出是否出现 `Summary:` 和 `BehaviorTree:` 日志。
3. 确认决策输出有数据：
   ```bash
   ros2 topic echo /auv/control/goal --once
   ```

---

## 常见问题

### `No such file or directory: ...`
确认 `log_file` 路径存在且可读。不传该参数时，`mock_sensor_input` 会自动在仓库内搜索内置样例日志。

### 行为树日志刷屏
调高 `tree_print_period`（默认 5.0s，增大则打印频率更低）。

### `rclpy` 已经 Shutdown
Ctrl+C 后残留进程，重新 `source install/setup.bash` 并重试。

---

## 进一步阅读

- 核心决策逻辑：`auv_decision_core/auv_decision_core/bt_engine.py`
- PVS 仿真联调：[docs/PVS全流程runbook.md](../../../docs/PVS全流程runbook.md)
- 仲裁器与模式切换：[docs/protocol_udp联调复现与模式切换_2026-04-01.md](../../../docs/protocol_udp联调复现与模式切换_2026-04-01.md)
- 仲裁器路线图：[docs/仲裁器长期路线图_2026-04-08.md](../../../docs/仲裁器长期路线图_2026-04-08.md)
- 日志回放实现：`auv_decision_ros/auv_decision_ros/mock_sensor_input.py`
- 接口定义：`auv_interfaces/msg/SensorStatus.msg`、`auv_interfaces/msg/ControlGoal.msg`

---

## 🌟 反馈与扩展

欢迎继续扩展：
- 用真实传感器替换回放输入（通过发布 `SensorStatus`）。
- 增加更多行为树节点，加入任务规划、避障、路径跟踪。
- 将日志输出格式改为 JSON/CSV 以便后续分析。

如果你遇到问题，欢迎打开 issue 或顶部文档中添加说明内容。
