# 测试指南

本文档介绍如何运行AUV项目的各种测试，包括单元测试、集成测试和端到端测试。

## 测试概述

AUV项目有完整的测试覆盖，主要测试位于 `tests/` 目录。

### 测试类型

| 测试类型 | 目录/文件 | 说明 |
|---------|---------|------|
| 协议测试 | `test_protocol_contract.py` | 测试数据协议正确性 |
| Mock AMD测试 | `test_mock_amd_*.py` | 测试硬件模拟功能 |
| 硬件行为测试 | `test_hardware_behavior.py` | 测试物理和控制行为 |
| 攻击站测试 | `test_attacker_station.py` | 测试攻击站工具 |

---

## 快速开始

### 运行所有测试

```bash
cd /home/auv_user/auv_ws/AUV-Master-Project
/usr/bin/python3 -m pytest tests/ -v
```

### 运行特定测试文件

```bash
# 只运行协议测试
/usr/bin/python3 -m pytest tests/test_protocol_contract.py -v

# 只运行Mock AMD测试
/usr/bin/python3 -m pytest tests/test_mock_amd_server.py -v
```

### 运行特定测试用例

```bash
# 运行特定测试函数
/usr/bin/python3 -m pytest tests/test_protocol_contract.py::test_downlink_roundtrip -v
```

---

## 详细测试说明

### 1. 协议合同测试 (test_protocol_contract.py)

**测试目的**
验证协议编码/解码的正确性，确保上行和下行数据能正确往返。

**包含的测试用例**
- `test_downlink_payload_roundtrip_preserves_auxiliary_fields`: 测试载荷往返
- `test_bridge_telemetry_payload_adds_arbiter_metadata`: 测试仲裁器元数据
- `test_downlink_endianness`: 测试字节序
- `test_downlink_scaling`: 测试比例缩放
- `test_downlink_checksum`: 测试校验和
- `test_uplink_endianness`: 测试上行字节序
- `test_uplink_checksum`: 测试上行校验和
- `test_uplink_anomaly_bitmap`: 测试异常位图

**运行方法**
```bash
/usr/bin/python3 -m pytest tests/test_protocol_contract.py -v
```

### 2. Mock AMD 服务器测试 (test_mock_amd_server.py)

**测试目的**
验证Mock AMD服务器的核心功能，包括初始化、命令处理和遥测生成。

**包含的测试用例**
- `test_init_enables_mock_components`: 测试初始化启用组件
- `test_poll_command_packet_drains_delayed_commands`: 测试命令队列处理
- `test_build_uplink_packet_uses_sensor_cache`: 测试传感器缓存使用
- `test_build_uplink_packet_applies_chaos`: 测试故障注入应用

**运行方法**
```bash
/usr/bin/python3 -m pytest tests/test_mock_amd_server.py -v
```

### 3. Mock AMD 故障注入测试 (test_mock_amd_chaos.py)

**测试目的**
验证PVS的故障注入功能，包括传感器故障、通信故障等。

**包含的测试用例**
- DVL冻结测试
- IMU漂移测试
- 深度脉冲测试
- 磁力计饱和测试
- 数据包丢包测试
- 数据包重排序测试

**运行方法**
```bash
/usr/bin/python3 -m pytest tests/test_mock_amd_chaos.py -v
```

### 4. Mock AMD 延迟队列测试 (test_mock_amd_delay.py)

**测试目的**
验证延迟队列功能，模拟真实通信延迟。

**包含的测试用例**
- `TestTransportDelayQueueConstruct`: 构造函数测试
- `TestTransportDelayQueueEnqueueDequeue`: 入队/出队测试
- `TestTransportDelayQueueOverflow`: 队列溢出测试
- `TestTransportDelayQueueJitter`: 抖动测试
- `TestTransportDelayQueueReset`: 重置测试

**运行方法**
```bash
/usr/bin/python3 -m pytest tests/test_mock_amd_delay.py -v
```

### 5. Mock AMD 传感器缓存测试 (test_mock_amd_sensor_cache.py)

**测试目的**
验证传感器缓存机制，模拟多速率传感器采样。

**包含的测试用例**
- `TestSensorSnapshot`: 传感器快照测试
- `TestSensorSampleCacheConstruct`: 缓存构造测试
- `TestSensorSampleCacheClocks`: 多速率时钟测试
- `TestSensorSampleCacheReset`: 重置测试

**运行方法**
```bash
/usr/bin/python3 -m pytest tests/test_mock_amd_sensor_cache.py -v
```

### 6. 硬件行为测试 (test_hardware_behavior.py)

**测试目的**
验证物理和控制行为的正确性。

**包含的测试用例**
- `test_pid_depth_error_deflects_port_and_starboard_surfaces_in_opposite_directions`: 测试深度控制器
- `test_pid_yaw_error_deflects_horizontal_surfaces_in_opposite_directions`: 测试航向控制器
- `test_protocol_backend_scales_thrust_percent_to_main_motor_rpm`: 测试推力缩放

**运行方法**
```bash
/usr/bin/python3 -m pytest tests/test_hardware_behavior.py -v
```

### 7. 攻击站测试 (test_attacker_station.py)

**测试目的**
验证攻击站工具功能，用于注入故障和测试鲁棒性。

**包含的测试用例**
- `test_build_profile_payload_heartbeat_zeroes_controls`: 心跳载荷测试
- `test_build_profile_payload_sweep_cycles_boundary_case`: 边界测试
- `test_transact_once_sends_real_protocol_frame_and_parses_response`: 交易测试
- `test_format_summary_reports_percentiles`: 摘要报告测试

**运行方法**
```bash
/usr/bin/python3 -m pytest tests/test_attacker_station.py -v
```

---

## 集成测试

除了单元测试，还可以运行集成测试来验证整个系统：

### 运行 PVS 集成测试

```bash
# 启动 PVS 仿真（限定时间）
cd /home/auv_user/auv_ws/AUV-Master-Project/scripts
timeout 30s bash start_lin_sim.sh sim --sim-backend pvs
```

### 运行完整链路测试

```bash
# 终端1：启动 PVS 仿真 + 桥接
cd /home/auv_user/auv_ws/AUV-Master-Project/scripts
bash start_lin_sim.sh both --sim-backend pvs

# 终端2：启动 ROS2 决策层
cd /home/auv_user/auv_ws/AUV-Master-Project/scripts
bash start_lin_brain.sh stack
```

---

## PVS 烟雾测试

PVS 的完整烟雾测试流程：

### 步骤1：运行所有单元测试
```bash
cd /home/auv_user/auv_ws/AUV-Master-Project
/usr/bin/python3 -m pytest tests/ -v
```

预期结果：81个测试全部通过。

### 步骤2：运行 PVS 独立仿真
```bash
cd /home/auv_user/auv_ws/AUV-Master-Project/scripts
bash start_lin_sim.sh sim --sim-backend pvs
```

预期结果：
- PVS 正常启动
- 仿真运行完成
- 输出性能指标（RMS、误差等）
- RMS < 2.5m 表示通过

### 步骤3：测试 Protocol UDP 模式
```bash
cd /home/auv_user/auv_ws/AUV-Master-Project/scripts
timeout 15s bash start_lin_sim.sh both --sim-backend pvs --backend protocol_udp
```

预期结果：
- Mock AMD 服务器启动
- 显示 $AUV 上行和 $CKTH 下行协议帧
- 校验和验证通过

---

## 测试输出解读

### PVS 仿真输出解读

典型的PVS仿真输出包括：

```
[PVS] Starting simulation...
[PVS] Control mode: depthHeadingAutopilot
[PVS] Initial depth: 12.0m
[PVS] Initial speed: 0.5m/s
...
[PVS] Step 100: depth=12.0m, yaw=0.0deg, u=1.1m/s
...
[PVS] Simulation complete
[PVS] RMS error: 1.25m
[PVS] Pass RMS: True
```

关键指标：
- **RMS error**: 轨迹跟踪均方根误差
- **Pass RMS**: 是否通过RMS阈值（<2.5m）
- **Axis ratio**: 轴比率（<2%为好）

### Protocol UDP 输出解读

在Protocol UDP模式下，PVS输出协议帧信息：

```
[Mock AMD] Listening on 0.0.0.0:52364
[Mock AMD TX] Frame 1: AUV=1, Mode=AUTONOMOUS
  Depth: 12.00m, Heading: 0.0deg, Voltage: 48.0V
  Checksum: OK
```

---

## 常见测试问题

### 问题1: 测试提示缺少依赖

确保已安装所有测试依赖：

```bash
/usr/bin/python3 -m pip install pytest
```

### 问题2: PVS仿真无法启动

检查PVS配置文件：

```bash
# 验证配置文件存在
ls /home/auv_user/auv_ws/AUV-Master-Project/config/sim_params.pvs.yaml
```

### 问题3: 协议测试失败

确保使用了正确的Python环境：

```bash
which python3  # 应该是 /usr/bin/python3
```

---

## CI/CD 集成

PVS 测试设计用于 CI/CD 环境：

```yaml
# GitLab CI 示例
test_pvs:
  stage: test
  script:
    - cd /home/auv_user/auv_ws/AUV-Master-Project
    - /usr/bin/python3 -m pytest tests/ -v --junitxml=test-results.xml
  artifacts:
    reports:
      junit: test-results.xml
```

---

## 下一步

- 学习如何使用 [PVS 后端](../02_architecture/02_pvs_architecture.md)
- 阅读 [运行模式切换](../05_operations/01_mode_switching.md) 了解不同通信模式
