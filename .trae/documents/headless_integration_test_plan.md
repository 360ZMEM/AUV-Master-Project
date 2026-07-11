# 上位机无头自动化集成测试计划

## 一、现状分析与解耦审查 (Decoupling Check)

### 1.1 现有架构审查

| 组件 | 文件 | 职责 | 与UI耦合程度 |
|------|------|------|-------------|
| ZenohSideChannel | `console_soft/auv_console_pyside6/src/communication/zenoh_side_channel.py` | Zenoh 发布/订阅，JSON打包 | **强耦合**：继承 `QObject`，使用 `Signal` |
| CommunicationManager | `console_soft/auv_console_pyside6/src/communication/comm_manager.py` | 通信模式切换，路由 | **强耦合**：继承 `QObject`，使用 `Signal` |
| CommandArbiter | `brain_linux/src/auv_bridge/auv_bridge/arbiter.py` | 仲裁决策 | **完全解耦**：纯Python类，无Qt依赖 |
| AutonomyGuard | `brain_linux/src/auv_bridge/auv_bridge/autonomy_guard.py` | 守卫检查 | **完全解耦**：纯Python类，无Qt依赖 |
| AUVBridgeNode | `brain_linux/src/auv_bridge/auv_bridge/bridge_node.py` | 桥接节点 | **强耦合**：继承 `rclpy.node.Node` |

### 1.2 关键发现：上位机缺乏独立的 Backend 类

**问题**：`main.py` 直接依赖 `MainWindow`（Qt UI）和 `UDPReceiverThread`（Qt 线程），**没有**类似 `ConsoleBackend` 的独立后端类。`ZenohSideChannel` 继承自 `QObject` 且使用 `Signal`，无法脱离 Qt 事件循环运行。

**解决方案**：在无头测试脚本中创建一个轻量级的 `ConsoleBackend` 类，它：
- 封装 `ZenohSideChannel` 的核心功能但剥离 `QObject`/`Signal` 依赖
- 使用纯 Python `threading` + `queue` 代替 Qt 信号
- 实现心跳发送、JSON命令下发、遥测监听等必需功能

### 1.3 Mock AMD 状态机分析

Mock AMD 服务器（`sim_holoocean/interfaces/mock_amd_server.py`）本身**不实现** AutoState/ArbiterMode 状态机——它只是透明转发 UDP 命令。状态机逻辑在 `auv_bridge` 的 `arbiter.py` 和 `autonomy_guard.py` 中。

因此测试场景中的"验证 auto_state 变化"等断言，实际是验证 **Jetson Bridge（arbiter + guard）** 的行为，而非 Mock AMD。

---

## 二、实施步骤

### Step 1: 创建独立的后端抽象 (`tests/headless_console_backend.py`)

在 `tests/` 目录创建一个纯 Python 后端类 `HeadlessConsoleBackend`，它：
- 直接使用 `zenoh` Python 库（不依赖 PySide6）
- 使用 `threading.Timer` 实现 10Hz 心跳
- 使用 `threading.Lock` + 回调队列实现遥测数据收集
- 实现 JSON 命令构建和下发
- **不**包含任何 `QWidget`、`Signal`/`Slot`、UI 阻塞代码

核心方法：
```python
class HeadlessConsoleBackend:
    def __init__(self, zenoh_ip, zenoh_port): ...
    def connect(self) -> bool: ...
    def start_heartbeat(self, hz=10) -> None: ...
    def stop_heartbeat(self) -> None: ...
    def send_control_command(self, control_mode_byte, thrust=0.0, work_cmd=0x00, ...) -> bool: ...
    def get_latest_telemetry(self, timeout=2.0) -> dict | None: ...
    def close(self) -> None: ...
```

### Step 2: 编写无头测试脚本 (`tests/test_headless_integration.py`)

实现 5 个测试场景，使用 `pytest` 框架：

#### Scene 1: 透传与心跳 (Manual Passthrough)
- 启动 backend，开始 10Hz 心跳
- 下发 `Control_Mode_Byte=0x01`, `Thrust=10.0`
- 监听 `rt/auv/telemetry`，验证 `main_motor_rpm ≈ 150`（Scale=15）
- 验证 `active_arbiter == "REMOTE"`

#### Scene 2: 授权与接管 (Autonomy Handshake)
- 下发 `Control_Mode_Byte=0xEE`（申请自主）
- 监听 `rt/auv/telemetry`，验证状态流转：`REQUESTING → ACTIVE`
- 验证 `active_arbiter == "AUTONOMOUS"`

#### Scene 3: 紧急切断 (ESTOP Override)
- 在 `ACTIVE` 状态下，下发 `Work_Cmd=0x02`（TASK_CANCEL）
- 验证下行推力归 `0`
- 验证 `auto_state == "LOCKED"`，`deny_reason == "MANUAL_OVERRIDE"`

#### Scene 4: ESTOP 复位安全锁 (Hardware Reset Lock)
- 在 ESTOP 状态下，尝试带推力解除 ESTOP（`Work_Cmd=0x00`, `Thrust=10.0`）
- 验证系统拒绝复位，继续保持 `LOCKED`
- 只有 `Thrust=0` + `Work_Cmd=0x00` 才允许回到 `REMOTE`

#### Scene 5: 链路超时自救 (Link Brown-out)
- `sleep(2.0)` 停止发送心跳
- 观察是否在 1.5s 后降级为 `REMOTE` 模式并停机

### Step 3: 环境准备

需要确认：
- Zenoh router 已在运行（通常由 `start_foxglove_pvs_ros.sh` 启动）
- Mock AMD 服务器已在运行
- `auv_bridge` 节点已以 `zenoh_json` 后端启动
- 相关 Python 包已安装（`zenoh`, `pytest`）

### Step 4: 执行测试并记录日志

运行测试，同时捕获：
- Mock AMD 日志
- Bridge 节点日志
- 测试脚本日志

### Step 5: 生成调试文档

在 `docs/` 目录创建 `上位机无头集成测试报告_2026-05.md`，包含：
1. 时序分析（Mermaid 或文本箭头）
2. 缺陷揭露（发现的 Bug 及修复）
3. 状态机覆盖率表

---

## 三、关键决策

1. **测试框架**：使用 `pytest`（标准、易集成），而非 `unittest`
2. **Zenoh 连接**：通过环境变量或配置文件指定 Zenoh router IP（默认 `127.0.0.1:7447`）
3. **超时策略**：每个场景设置 5s 超时，避免阻塞
4. **日志时间戳对齐**：统一使用 `time.time()` 作为基准时间

## 四、风险与应对

| 风险 | 应对 |
|------|------|
| Zenoh router 未运行 | 测试前置检查，给出明确错误提示 |
| Mock AMD 端口被占用 | 使用配置化端口，默认 52364/52365 |
| 测试时序不稳定（竞态条件） | 增加重试机制和合理超时 |
| `autonomy_guard` 需要真实的 sensor status 才能允许激活 | 测试脚本需通过 UDP 发送模拟遥测数据 |
