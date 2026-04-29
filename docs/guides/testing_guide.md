# 🧪 测试与验证指南

本文档介绍 AUV_Master_Project 的测试策略、单元测试、集成测试和验证方法。

---

## 测试策略概览

```
┌─────────────────────────────────────────────────────────────┐
│ 测试金字塔                                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│         🔺 E2E 测试 (端到端验证)                             │
│         - 完整闭环运行                                         │
│         - 回归测试                                            │
│         - 性能基准                                            │
│                                                             │
│      ┌──────────────────────────────────┐                    │
│      │ 集成测试                          │                    │
│      │ - 协议验证                        │                    │
│      │ - 仿真与决策通信                  │                    │
│      │ - 坐标系换算验证                  │                    │
│      └──────────────────────────────────┘                    │
│                                                             │
│   ┌────────────────────────────────────────────────┐         │
│   │ 单元测试                                        │         │
│   │ - protocol.py, enums.py                       │         │
│   │ - algorithm/* 所有模块                        │         │
│   │ - physics.py 函数                              │         │
│   └────────────────────────────────────────────────┘         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 一、单元测试

### 运行所有单元测试

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
python -m pytest tests/ -v
```

### 运行特定模块测试

```bash
# 协议测试
python -m pytest tests/test_protocol_contract.py -v

# 枚举测试
python -m pytest tests/test_enums.py -v

# 算法测试
python -m pytest tests/test_algorithms/ -v

# 物理函数测试
python -m pytest tests/test_physics.py -v
```

### 测试覆盖率报告

```bash
# 生成覆盖率报告
python -m pytest tests/ --cov=. --cov-report=html

# 查看报告
xdg-open htmlcov/index.html
```

---

## 二、协议验证测试

### 协议正确性检查

```bash
# 验证下行协议（AUV → 水下）
python tests/test_protocol_contract.py::test_downlink_protocol -v

# 验证上行协议（水下 → AUV）
python tests/test_protocol_contract.py::test_uplink_protocol -v

# 验证消息格式
python tests/test_protocol_contract.py::test_message_validation -v
```

### 预期输出

```
test_downlink_protocol PASSED
test_uplink_protocol PASSED
test_message_validation PASSED

================ 3 passed in 0.5s =================
```

---

## 三、坐标系统一验证

### 运行坐标系换算检查

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project
bash scripts/run_sim_equivalence_check.sh
```

**验证内容**：
- UE4 坐标系 → NED 坐标系转换
- 位置、姿态、速度的换算正确性
- 坐标系标注的一致性

### 坐标系测试

```bash
# 运行坐标系单元测试
python -m pytest tests/test_frame_transform.py -v
```

**测试用例**：
```python
def test_ue4_to_ned_position():
    ue4_pos = np.array([0, 0, 0])
    ned_pos = ue4_to_ned(ue4_pos)
    assert np.allclose(ned_pos, np.array([0, 0, 0]))

def test_ue4_to_ned_rotation():
    # 验证旋转矩阵转换
    ue4_rot = Rotation.from_euler('xyz', [0, 0, 0])
    ned_rot = ue4_rotation_to_ned(ue4_rot)
    assert ned_rot.as_euler('xyz').allclose([0, 0, 0])
```

---

## 四、集成测试

### 1. 仿真与桥接通信测试

```bash
# 启动仿真和 Zenoh 桥接
bash scripts/start_lin_sim.sh both

# 在另一个终端运行验证
python tests/integration/test_sim_bridge.py
```

**验证内容**：
- Zenoh topic 发布是否正常
- 消息格式是否正确
- 数据延迟是否在可接受范围

### 2. 决策端与仿真通信测试

```bash
# 终端 1：启动仿真 + 桥接
bash scripts/start_lin_sim.sh both --backend zenoh_json

# 终端 2：启动决策端
bash scripts/start_lin_brain.sh stack --backend zenoh_json

# 终端 3：运行测试
python tests/integration/test_decision_bridge.py
```

### 3. 端到端闭环测试

```bash
# 一键启动完整系统
bash scripts/start_foxglove_holoocean_ros.sh --duration 30

# 等待完成后，运行验证
python tests/integration/test_e2e_closed_loop.py --log-dir log/latest/
```

**验证指标**：
- ✅ 仿真能正常启动
- ✅ 桥接能正常通信
- ✅ 决策端能接收传感数据
- ✅ 决策端能发送控制指令
- ✅ 仿真能接收并执行控制指令
- ✅ 系统无崩溃或异常日志

---

## 五、性能测试

### 消息延迟测试

```bash
python tests/performance/test_message_latency.py --backend zenoh_json
python tests/performance/test_message_latency.py --backend protocol_udp
```

**预期结果**：
- Zenoh JSON: < 50ms
- Protocol UDP: < 20ms

### 仿真帧率测试

```bash
python tests/performance/test_sim_framerate.py --sim-backend holoocean
python tests/performance/test_sim_framerate.py --sim-backend pvs
```

**预期结果**：
- HoloOcean: ≥ 30 FPS
- PVS: ≥ 20 FPS（高保真物理引擎）

---

## 六、回归测试

### 自动化回归脚本

```bash
# 运行完整回归测试套件
bash scripts/run_regression_tests.sh

# 仅运行快速回归（跳过长时间测试）
bash scripts/run_regression_tests.sh --quick
```

### 回归测试清单

| 测试项 | 说明 | 频率 |
|--------|------|------|
| 单元测试 | 验证所有模块单元正确性 | 每次代码提交 |
| 协议测试 | 验证协议格式不变 | 每次代码提交 |
| 坐标系测试 | 验证坐标换算正确性 | 每次代码提交 |
| 集成测试 | 验证模块间通信 | 每日构建 |
| E2E 测试 | 验证完整闭环 | 每周回归 |
| 性能测试 | 验证无性能回退 | 每周回归 |

---

## 七、模拟数据测试（Mock 测试）

### 使用 Mock 数据测试决策端

```bash
# 使用 Mock AMD 数据测试
python -m pytest tests/test_mock_amd_*.py -v
```

**Mock 数据来源**：
- `tests/mock_data/imu_mock.json`
- `tests/mock_data/dvl_mock.json`
- `tests/mock_data/telemetry_mock.json`

### 生成 Mock 数据

```bash
# 从真实运行记录生成 Mock 数据
python tools/generate_mock_data.py --log-dir log/real_run_001/

# 输出
# → tests/mock_data/imu_mock.json
# → tests/mock_data/dvl_mock.json
# → tests/mock_data/telemetry_mock.json
```

---

## 八、CI/CD 集成

### GitHub Actions 配置

创建 `.github/workflows/test.yml`：

```yaml
name: AUV Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov

      - name: Run unit tests
        run: pytest tests/ --cov=. --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## 九、故障排查

### 测试失败常见原因

#### 1. 导入错误

```bash
ModuleNotFoundError: No module named 'common'
```

**解决**：
```bash
# 确保 PYTHONPATH 正确设置
export PYTHONPATH=/home/gwxie/master_work-tmp/AUV_Master_Project:$PYTHONPATH
```

#### 2. 端口占用

```bash
OSError: [Errno 48] Address already in use
```

**解决**：
```bash
# 查找并关闭占用进程
lsof -i :7447  # Zenoh 默认端口
kill -9 <PID>
```

#### 3. 测试超时

```bash
TimeoutError: Test timed out after 30 seconds
```

**解决**：
```bash
# 增加超时时间
pytest tests/ --timeout=60
```

---

## 十、测试最佳实践

### 1. 编写测试用例

```python
# good_test_example.py
import pytest
from common.protocol import validate_sensor_payload

def test_validate_sensor_payload_valid():
    """验证有效的传感器负载能通过验证"""
    topic = "rt/auv/sensors/imu"
    payload = {
        "timestamp": 1234567890.0,
        "linear_acceleration": {"x": 0.1, "y": 0.2, "z": 9.8},
        "angular_velocity": {"x": 0.01, "y": 0.02, "z": 0.03}
    }

    is_valid, errors = validate_sensor_payload(topic, payload)
    assert is_valid is True
    assert len(errors) == 0

def test_validate_sensor_payload_missing_field():
    """验证缺少必要字段时能检测到错误"""
    topic = "rt/auv/sensors/imu"
    payload = {
        "timestamp": 1234567890.0,
        # 缺少 linear_acceleration
        "angular_velocity": {"x": 0.01, "y": 0.02, "z": 0.03}
    }

    is_valid, errors = validate_sensor_payload(topic, payload)
    assert is_valid is False
    assert "missing field" in str(errors).lower()
```

### 2. 使用 Fixture

```python
# conftest.py
import pytest

@pytest.fixture
def mock_imu_data():
    return {
        "timestamp": 1234567890.0,
        "linear_acceleration": {"x": 0.1, "y": 0.2, "z": 9.8},
        "angular_velocity": {"x": 0.01, "y": 0.02, "z": 0.03}
    }

# test_usage.py
def test_with_fixture(mock_imu_data):
    from common.protocol import validate_sensor_payload
    is_valid, _ = validate_sensor_payload("rt/auv/sensors/imu", mock_imu_data)
    assert is_valid is True
```

### 3. 测试隔离

```python
# 每个测试使用独立的临时目录
import tempfile
import os

def test_with_temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test.txt")
        with open(test_file, "w") as f:
            f.write("test content")

        # 测试完成后，临时目录自动删除
        assert not os.path.exists(test_file)
```

---

## 相关资源

- [单元测试示例](../tests/test_protocol_contract.py)
- [集成测试示例](../tests/integration/)
- [性能测试示例](../tests/performance/)
- [Mock 测试示例](../tests/test_mock_amd_*.py)
- [GitHub Actions 配置](../.github/workflows/)

---

**更新日期**：2026-04-25
