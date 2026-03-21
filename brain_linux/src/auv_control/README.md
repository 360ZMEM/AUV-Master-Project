# AUV Decision ROS Package (auv_decision_ros)

本包提供一个基于 ROS2 的 AUV（自主水下航行器）决策节点与日志回放工具：
- 核心决策逻辑由 `auv_decision_core` 提供（行为树 + 黑板）。
- ROS2 节点负责订阅 `SensorStatus`，并发布 `ControlGoal`。
- 提供日志回放（从历史文本日志中提取传感数据）以便在没有传感器输入时完成端到端测试。

---

## 📌 目录结构

- `launch/decision_replay.launch.py`：一键启动回放 + 决策节点。
- `auv_decision_ros/decision_node.py`：ROS2 节点实现，处理订阅/发布、行为树 Tick、日志输出节流。
- `auv_decision_ros/mock_sensor_input.py`：从文本 `$AUV` 日志行生成 `SensorStatus` 消息。
- `auv_decision_ros/mappers.py`：ROS 消息与核心数据结构的转换。

---

## ✅ 先决条件（环境准备）

1. **ROS2 Humble** (或兼容版本) 已安装。
2. 工作区已初始化并可构建：
   ```bash
   cd ~/auv_console_python/ros2_ws
   colcon build
   ```
3. `auv_interfaces`、`auv_decision_core` 已被编译并可用。

> 💡 推荐先运行一次 `colcon build --symlink-install` 并 `source install/setup.bash`。

---

## ▶️ 运行方式（推荐：日志回放 + 决策）

### 1) 通过 Launch 快速启动（推荐）

在工作目录运行：

```bash
cd ~/auv_console_python/ros2_ws
source install/setup.bash
ros2 launch auv_decision_ros decision_replay.launch.py
```

该命令会：
- 使用 `mock_sensor_input.py` 读取日志文件并发布 `SensorStatus`。
- 启动 `decision_node.py` 执行行为树并发布 `ControlGoal`。
- 将决策摘要以可读日志输出（包括行为树结构节流）。

---

## 🧪 日志回放（模拟输入）

### 默认日志文件

默认回放的日志路径（若未指定）为：

- `~/auv_console_python/ros2_ws/src/auv_decision_ros/auv_decision_ros/data/auv_text_logs.txt`（如果存在）

> ⚠️ 如果你使用自己的日志，请通过 launch 参数指定路径。

### 自定义日志文件

```bash
ros2 launch auv_decision_ros decision_replay.launch.py log_file:=/path/to/your/AUV_log.txt
```

### 回放速率控制

- `replay_rate`：控制模拟时间流速（默认 `1.0`，表示 1x 实时）。

例如：

```bash
ros2 launch auv_decision_ros decision_replay.launch.py replay_rate:=2.0
```

---

## 🧠 决策节点配置（决策频率与日志节流）

| 参数 | 含义 | 默认值 |
| --- | --- | --- |
| `decision_tick_hz` | 行为树 Tick 频率（Hz） | `2.0` |
| `tree_log_rate` | 行为树 ASCII 输出的最小间隔（秒） | `5.0` |
| `summary_rate` | 决策摘要输出间隔（秒） | `0.5` |

### 修改运行参数示例

```bash
ros2 launch auv_decision_ros decision_replay.launch.py decision_tick_hz:=1.0 tree_log_rate:=10.0
```

---

## 🔌 直接运行 ROS2 节点（不使用回放）

如果你已经有传感器节点在发布 `auv_interfaces/msg/SensorStatus`，可以直接运行决策节点：

```bash
ros2 run auv_decision_ros decision_node
```

### 订阅/发布的 Topic

- 订阅：`/auv/sensor_status` (`auv_interfaces/msg/SensorStatus`)
- 发布：`/auv/control_goal` (`auv_interfaces/msg/ControlGoal`)

---

## 📄 输出日志与调试信息

节点会输出两类日志：

1. **摘要行（Summary）**：周期性输出当前关键值（例如：深度、电压、警报、行为状态）
2. **行为树结构**：以 ASCII 树形式打印行为树状态（已节流，减少刷屏）。

示例输出：

```text
[decision_node] Summary: depth=5.2m, leak=OK, confidence=0.81, vol=25.1V, alarm=0x02, state=DiveToDepth
[decision_node] BehaviorTree:
  ├─ ParallelTracking (SUCCESS)
  │  ├─ DiveToDepth (RUNNING)
  │  └─ EmergencySurface (FAILURE)
```

---

## 🧩 常见问题与排查

### 1) `No such file or directory: ...`（日志路径问题）
请确认 `log_file` 路径存在且可读，或者不传该参数以使用默认日志。

### 2) 行为树日志刷屏
- 可通过 `tree_log_rate` 调高（更大值，打印频率更低）。
- `summary_rate` 控制摘要输出频率。

### 3) `rclpy` 已经 Shutdown
这通常发生在你在终端用 Ctrl+C 强制停止后，再次启动时残留。请重新 `source install/setup.bash` 并重试。

---

## 🧪 如何验证本包工作正常

1. 运行：
   ```bash
   ros2 launch auv_decision_ros decision_replay.launch.py
   ```
2. 观察终端输出是否出现 `Summary:` 和 `BehaviorTree:` 相关日志。
3. 确认 `/auv/control_goal` Topic 有输出：
   ```bash
   ros2 topic echo /auv/control_goal --once
   ```

---

## 📚 进一步阅读

- 主要决策逻辑来源：`auv_decision_core/auv_decision_core/bt_engine.py`
- 日志回放实现：`auv_decision_ros/auv_decision_ros/mock_sensor_input.py`
- 接口定义：`auv_interfaces/msg/SensorStatus.msg`、`auv_interfaces/msg/ControlGoal.msg`

---

## 🌟 反馈与扩展

欢迎继续扩展：
- 用真实传感器替换回放输入（通过发布 `SensorStatus`）。
- 增加更多行为树节点，加入任务规划、避障、路径跟踪。
- 将日志输出格式改为 JSON/CSV 以便后续分析。

如果你遇到问题，欢迎打开 issue 或顶部文档中添加说明内容。
