# 代码修改指南

本文档说明如何正确修改代码，避免引入问题。

## 黄金法则

### 1. 先改 common，再改其他

**错误做法**:
```python
# ❌ 直接在 ROS2 侧添加新字段
msg.new_field = 1.0  # 字段定义不统一！
```

**正确做法**:
```python
# ✅ 第一步：在 common/ 定义
# common/protocol.py
NEW_FIELD_KEY = "new_field"

# ✅ 第二步：仿真侧使用
payload[NEW_FIELD_KEY] = value

# ✅ 第三步：ROS2 侧使用
msg.new_field = payload[NEW_FIELD_KEY]
```

### 2. 保持环境分离

**禁止**:
```python
# ❌ 在 ROS2 节点中直接调用 HoloOcean API
from holoocean import holoocean  # 不要这样做！
```

**正确**:
```python
# ✅ 通过通信接口获取数据
from sensor_msgs.msg import Imu
def imu_callback(msg: Imu):
    # 处理 IMU 数据
    pass
```

### 3. 做通信边界校验

**必须**:
```python
# ✅ 发布前校验
from common.protocol import validate_sensor_payload

if validate_sensor_payload(topic, payload):
    zenoh_pub.publish(topic, payload)
```

## 修改场景指南

### 场景 1: 添加新的传感器

#### 步骤 1: 定义 Topic
```python
# common/protocol.py
class Topics:
    NEW_SENSOR = "rt/auv/sensors/new_sensor"
```

#### 步骤 2: 定义字段
```python
# common/protocol.py
class SensorKeys:
    NEW_SENSOR_VALUE = "value"
    NEW_SENSOR_UNIT = "unit"
```

#### 步骤 3: 添加校验
```python
# common/protocol.py
def validate_new_sensor(payload: dict) -> bool:
    required = ['step', 'sim_time', 'ts', 'value', 'unit']
    return all(k in payload for k in required)
```

#### 步骤 4: 仿真侧实现
```python
# sim_holoocean/interfaces/holoocean_physics_bridge.py
from common.protocol import Topics, SensorKeys

def publish_new_sensor(state):
    payload = {
        'step': state.step,
        'sim_time': state.sim_time,
        'ts': time.time(),
        SensorKeys.NEW_SENSOR_VALUE: state.new_sensor_value,
        SensorKeys.NEW_SENSOR_UNIT: "V"
    }
    zenoh_pub.publish(Topics.NEW_SENSOR, payload)
```

#### 步骤 5: ROS2 侧接收
```python
# brain_linux/src/auv_bridge/auv_bridge/bridge_node.py
from auv_interfaces.msg import NewSensor

def new_sensor_callback(self, msg):
    self.new_sensor_pub.publish(msg)
```

### 场景 2: 修改控制参数

#### 步骤 1: 修改配置文件
```yaml
# brain_linux/config/params.yaml
control:
  depth:
    kp: 0.5  # 修改这里
    ki: 0.01
    kd: 0.1
```

#### 步骤 2: 验证参数范围
```python
# 确保参数在合理范围内
# common/physics.py
def validate_pid_params(kp, ki, kd):
    assert 0 <= kp <= 10, "kp 超出范围"
    assert 0 <= ki <= 1, "ki 超出范围"
    assert 0 <= kd <= 5, "kd 超出范围"
```

#### 步骤 3: 测试
```bash
# 使用新参数测试
ros2 run auv_controller controller_node \
  --ros-args \
  -p params_file:=brain_linux/config/params.yaml
```

### 场景 3: 添加新的行为模式

#### 步骤 1: 定义枚举
```python
# common/enums.py
class BehaviorMode(Enum):
    NEW_MODE = "NEW_MODE"  # 添加新模式
```

#### 步骤 2: 实现行为
```python
# brain_linux/src/auv_decision/auv_decision_core/behaviors.py
class NewMode(Behavior):
    def __init__(self):
        super().__init__()
        self.name = "NewMode"

    def update(self):
        # 实现行为逻辑
        return py_trees.common.Status.SUCCESS
```

#### 步骤 3: 注册行为树
```python
# brain_linux/src/auv_decision/auv_decision_core/trees.py
def create_behavior_tree():
    root = py_trees.composites.Sequence("Root")
    new_mode = NewMode()
    root.add_child(new_mode)
    return root
```

### 场景 4: 修改仲裁逻辑

#### 步骤 1: 更新共享契约
```python
# common/enums.py
class ArbiterMode(Enum):
    NEW_MODE = "NEW_MODE"  # 新仲裁模式
```

#### 步骤 2: 修改仲裁器
```python
# brain_linux/src/auv_bridge/auv_bridge/arbiter.py
class CommandArbiter:
    def arbitrate(self):
        if self.mode == ArbiterMode.NEW_MODE:
            # 实现新仲裁逻辑
            pass
```

#### 步骤 3: 添加测试
```python
# brain_linux/src/auv_bridge/test/test_arbiter.py
def test_new_arbiter_mode():
    arbiter = CommandArbiter()
    arbiter.mode = ArbiterMode.NEW_MODE
    # 测试新模式
    assert arbiter.arbitrate() is not None
```

## 命名规范

### 文件命名
```
snake_case.py        # Python 文件
snake_case_test.py   # 测试文件
snake_case.yaml      # 配置文件
```

### 变量命名
```python
# 常量：全大写
MAX_THRUST = 100.0

# 变量：小写下划线
target_depth = 5.0

# 类名：大驼峰
class PIDController:
    pass

# 私有方法：前缀下划线
def _private_method(self):
    pass
```

### Topic 命名
```
/auv/sensors/imu       # 传感器数据
/auv/state/filtered    # 状态估计
/auv/control/setpoint  # 控制目标
/cmd_vel               # 底层控制
```

## 代码审查清单

提交代码前检查：

- [ ] 是否修改了 `common/`？
- [ ] 是否更新了所有相关子系统？
- [ ] 是否添加了校验逻辑？
- [ ] 是否更新了文档？
- [ ] 是否添加了测试？
- [ ] 是否保持了环境分离？
- [ ] 是否遵循了命名规范？

## 测试要求

### 单元测试
```python
# tests/test_protocol_contract.py
def test_new_sensor_validation():
    payload = {
        'step': 1,
        'sim_time': 0.1,
        'ts': 0.0,
        'value': 1.0,
        'unit': 'V'
    }
    assert validate_new_sensor(payload)
```

### 集成测试
```bash
# 测试完整链路
bash scripts/start_experiment.sh --duration 10
```

## 常见错误

### 错误 1: 直接硬编码值
```python
# ❌ 错误
topic = "rt/auv/sensors/imu"  # 硬编码！

# ✅ 正确
from common.protocol import Topics
topic = Topics.IMU
```

### 错误 2: 不做校验
```python
# ❌ 错误
zenoh_pub.publish(topic, payload)  # 没有校验！

# ✅ 正确
if validate_sensor_payload(topic, payload):
    zenoh_pub.publish(topic, payload)
```

### 错误 3: 混用环境
```python
# ❌ 错误
# 在 ROS2 代码中导入 HoloOcean
import holoocean

# ✅ 正确
# 通过通信接口
from sensor_msgs.msg import Imu
```

## 相关文档

- [代码规范](02_coding_standards.md) - 详细的编码规范
- [测试指南](04_testing_guide.md) - 如何编写测试
- [常见问题](../01_getting_started/04_faq.md) - 常见修改问题
