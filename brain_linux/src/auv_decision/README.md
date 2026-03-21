# AUV Decision Core (auv_decision_core)

`auv_decision_core` 是 AUV 决策逻辑的纯 Python 核心，独立于 ROS2，可用于：

- 在单元测试中验证行为树逻辑
- 作为 ROS2 节点（`auv_decision_ros`）的计算后端
- 作为仿真/离线分析的决策引擎

---

## ✅ 主要内容与目录

- `models.py`：核心数据模型（`SensorStatusData`、`MotionGoal`）
- `behaviors.py`：行为树节点定义（DiveToDepth、EmergencySurface、ZigZagSearch 等）
- `decorators.py`：行为树装饰器（例如：`AnomalySpeedLimiter`，用于异常时降低目标速度）
- `bt_engine.py`：行为树构建、调度、日志与黑板数据管理

---

## 🧠 核心概念（行为树 + 黑板）

### 1) 黑板（Blackboard）
行为树通过黑板共享数据：
- `sensor_status`：来自 `SensorStatusData`
- `motion_goal`：输出给下游的 `MotionGoal`
- `anomaly_detected`：是否出现异常（例如漏水/低压）

### 2) 行为树结构
当前实现包含两大分支：
- **常规任务分支**：根据深度目标调整推进（`DiveToDepth` 等）
- **紧急处理分支**：当检测到异常（漏水、电压过低）时强制上浮（`EmergencySurface`）

树的调度由 `bt_engine` 负责（`tick()` 每次更新输入、执行行为、写回输出）。

### 3) 装饰器（Decorator）
`AnomalySpeedLimiter` 通过黑板变量 `anomaly_detected`，在异常状态时降低目标速度（避免继续任务加重风险）。

---

## ▶️ 运行与测试（本地）

### 1) 安装依赖

本包依赖 `py_trees`（用于行为树），若未安装：

```bash
pip install py_trees
```

> 如果你使用的是 ROS2 工作区（推荐），已在 `ros2_ws` 中通过 `colcon build` 处理依赖。

### 2) 单元测试

在包根目录运行：

```bash
cd ~/auv_console_python/ros2_ws/src/auv_decision_core
pytest -q
```

测试覆盖：
- 核心数据模型读写
- 行为树 Tick 结果（正常 / 异常路径）
- 装饰器对速度下调的影响

---

## 🧩 如何在代码中使用（示例）

### 1) 从传感器数据构建输入

```python
from auv_decision_core.models import SensorStatusData

sensor = SensorStatusData(
    depth_m=3.2,
    leak_level=0,
    total_voltage=24.3,
    system_alarm=0,
    confidence=0.92,
)
```

### 2) 创建并更新行为树

```python
from auv_decision_core.bt_engine import BehaviorTreeEngine

engine = BehaviorTreeEngine()
engine.update(sensor_status=sensor)

# 运行一次 Tick
engine.tick()

# 读取输出（MotionGoal）
goal = engine.blackboard.get('motion_goal')
print(goal)
```

### 3) 处理异常限速（装饰器）

当 `sensor_status.leak_level` 或 `system_alarm` 触发异常时，树会在 `AnomalySpeedLimiter` 内部自动将 `motion_goal.speed_mps` 降为 0.5（或更低），方便外部执行者按需执行。

---

## 🔎 常见修改点（扩展指南）

- 若需新增决策规则：在 `behaviors.py` 中新增 `py_trees.behaviour.Behaviour`，然后在 `bt_engine.py` 中接入树结构。
- 若需增加新的异常判定：在 `bt_engine` 中扩展 `detect_anomaly()` 或把判定增强到黑板输入。
- 若需输出更多诊断日志：修改 `BehaviorTreeEngine.tick()` 中 `log_tree()` 或 `get_summary()` 的内容。

---

## 📚 参考（与 ROS2 的集成点）

- ROS2 包 `auv_decision_ros` 通过 `mappers.py` 将 `SensorStatus`/`ControlGoal` 与此核心数据类型互转。
- `auv_decision_ros/decision_node.py` 每次接收 `SensorStatus` 后调用 `BehaviorTreeEngine.update(...)` 并 `tick()`。

---

---

## 🧩 可配置规则（YAML / JSON）

如果想把决策逻辑变成可调整的参数（例如阈值、目标深度、速度等），可以通过配置文件来驱动核心逻辑，避免频繁改动代码。

### 1) 推荐的配置结构（YAML 示例）

```yaml
# config/decision_rules.yaml
thresholds:
  leak_level_warn: 1
  leak_level_critical: 2
  low_voltage_v: 22.0

motion:
  normal_speed_mps: 1.0
  anomaly_speed_mps: 0.5
  max_depth_m: 60.0
```

### 2) 在代码中加载配置

```python
import yaml
from pathlib import Path
from auv_decision_core.bt_engine import BehaviorTreeEngine

config_path = Path('config/decision_rules.yaml')
with config_path.open('r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

engine = BehaviorTreeEngine()
engine.blackboard.set('config', config)  # 注入配置

# 后续更新和 Tick 如常
engine.update(sensor_status=sensor)
engine.tick()
```

### 3) 在行为逻辑中使用配置

在 `behaviors.py` 或 `bt_engine.py` 中，从黑板读取已加载的配置并在决策中使用：

```python
from py_trees.common import Status

class DiveToDepth(py_trees.behaviour.Behaviour):
    def update(self) -> Status:
        config = self.blackboard.get('config', {})
        max_depth = config.get('motion', {}).get('max_depth_m', 60.0)
        ...
```

> 📌 Tip：如果你更喜欢 JSON 格式，将 `yaml.safe_load()` 替换为 `json.load()` 即可。

---

## 🗃️ 结构化日志（JSON / CSV）

将决策输出写成结构化格式有利于离线分析、可视化与回放验证。

### 1) 输出 JSON Lines（`.jsonl`）

```python
import json
from datetime import datetime

from auv_decision_core.bt_engine import BehaviorTreeEngine

engine = BehaviorTreeEngine()

# 运行 Tick 后写入一条记录
record = {
    'timestamp': datetime.utcnow().isoformat() + 'Z',
    'sensor': engine.blackboard.get('sensor_status').__dict__,
    'motion_goal': engine.blackboard.get('motion_goal').__dict__,
    'anomaly': engine.blackboard.get('anomaly_detected'),
    'state': engine.get_summary(),
}

with open('decision_log.jsonl', 'a', encoding='utf-8') as f:
    f.write(json.dumps(record, ensure_ascii=False) + '\n')
```

> ✅ JSON Lines 格式便于使用 `jq`、Python、Pandas 等工具直接处理。

### 2) 输出 CSV 日志

```python
import csv
from datetime import datetime

from auv_decision_core.bt_engine import BehaviorTreeEngine

engine = BehaviorTreeEngine()

with open('decision_log.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'timestamp', 'depth_m', 'leak_level', 'total_voltage',
        'motion_speed_mps', 'anomaly', 'state',
    ])
    writer.writeheader()

    writer.writerow({
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'depth_m': engine.blackboard.get('sensor_status').depth_m,
        'leak_level': engine.blackboard.get('sensor_status').leak_level,
        'total_voltage': engine.blackboard.get('sensor_status').total_voltage,
        'motion_speed_mps': engine.blackboard.get('motion_goal').speed_mps,
        'anomaly': engine.blackboard.get('anomaly_detected'),
        'state': engine.get_summary(),
    })
```

---

## 🧩 YAML 定义行为树节点模板 + 自动构建

你可以把行为树结构写成 YAML，再在启动时解析并构建树，有利于快速迭代与测试不同策略。

### 1) 示例 YAML 模板

```yaml
# config/bt_template.yaml
root:
  type: parallel
  name: "root_parallel"
  children:
    - type: sequence
      name: "mission_sequence"
      children:
        - type: action
          name: "DiveToDepth"
        - type: action
          name: "ZigZagSearch"
    - type: action
      name: "EmergencySurface"
```

### 2) 解析器示例（自动构建行为树）

```python
import yaml
import py_trees
from auv_decision_core import behaviors

NODE_MAP = {
    'DiveToDepth': behaviors.DiveToDepth,
    'EmergencySurface': behaviors.EmergencySurface,
    'ZigZagSearch': behaviors.ZigZagSearch,
}

def build_tree_from_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        spec = yaml.safe_load(f)

    def _build(node_spec):
        node_type = node_spec['type']
        name = node_spec.get('name', 'node')

        if node_type == 'parallel':
            node = py_trees.composites.Parallel(name=name)
        elif node_type == 'sequence':
            node = py_trees.composites.Sequence(name=name)
        elif node_type == 'selector':
            node = py_trees.composites.Selector(name=name)
        elif node_type == 'action':
            action_cls = NODE_MAP[node_spec['name']]
            node = action_cls(name=node_spec.get('name', 'action'))
        else:
            raise ValueError(f"Unsupported node type: {node_type}")

        for child in node_spec.get('children', []):
            node.add_child(_build(child))

        return node

    root_spec = spec['root']
    return _build(root_spec)

# 使用
root = build_tree_from_yaml('config/bt_template.yaml')
tree = py_trees.trees.BehaviourTree(root)
```

### 3) 扩展

- 链接 `config/decision_rules.yaml` 中变量，行为节点可读取 `blackboard.get('config')` 以实现参数化。
- 可以增加 `decorator` 字段，支持 `success`, `failure`, `inverter` 等行为树修饰器。

---

## 🔌 日志入口：ROS Topic 与文件流

本模块可支持两类输入：

1. **ROS Topic 输入**（实时）
2. **文件流输入**（回放与离线分析）

### 1) ROS Topic 输入（实时）

在 `auv_decision_ros` 中，`decision_node` 已经订阅：
- `/auv/sensor_status`（`auv_interfaces/msg/SensorStatus`）

你可以创建一个测试发布节点：

```python
import rclpy
from rclpy.node import Node
from auv_interfaces.msg import SensorStatus

class SensorTestPublisher(Node):
    def __init__(self):
        super().__init__('sensor_test_publisher')
        self.pub = self.create_publisher(SensorStatus, '/auv/sensor_status', 10)
        self.timer = self.create_timer(0.5, self.publish_data)

    def publish_data(self):
        msg = SensorStatus()
        msg.depth_m = 5.0
        msg.leak_level = 0
        msg.total_voltage = 25.0
        msg.system_alarm = 0
        msg.confidence = 0.9
        self.pub.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = SensorTestPublisher()
    rclpy.spin(node)

if __name__ == '__main__':
    main()
```

### 2) 文件流输入（回放）

可用已有 `auv_decision_ros/mock_sensor_input.py`，从历史日志读取 `$AUV` 数据，发布 `SensorStatus`。

```bash
ros2 launch auv_decision_ros decision_replay.launch.py log_file:=/path/to/log.txt replay_rate:=1.0
```

也可以自己实现简单文件流发布：

```python
from pathlib import Path
from auv_interfaces.msg import SensorStatus

def parse_line(line):
    # 提取深度、漏水、电压、警报、可信度等字段（你可按实际格式实现）
    return SensorStatus(depth_m=..., leak_level=..., total_voltage=..., system_alarm=..., confidence=...)

for line in Path('/path/to/log.txt').read_text().splitlines():
    msg = parse_line(line)
    publisher.publish(msg)
    time.sleep(0.5)
```

> 🔧 Tip：若你希望同一套核心模块支持“单机回放”和“在线 ROS Topic”，建议抽象出一个 `SensorInputSource` 接口，包含 `get_next()` 和 `is_running()`，然后两种方式都实现该接口，决策主循环只读取统一接口。

---

## 📚 参考（与 ROS2 的集成点）

- ROS2 包 `auv_decision_ros` 通过 `mappers.py` 将 `SensorStatus`/`ControlGoal` 与此核心数据类型互转。
- `auv_decision_ros/decision_node.py` 每次接收 `SensorStatus` 后调用 `BehaviorTreeEngine.update(...)` 并 `tick()`。

---

如需我再补充其他内容（例如：如何将行为树逻辑直接配置在 YAML 中、如何在 ROS2 主题上输出结构化日志等），随时告诉我。
