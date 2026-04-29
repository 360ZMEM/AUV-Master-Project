# 算法透明度分级（Algorithm Transparency Levels）

> **文档版本**: v1.1 | 2026-04-27
> **适用范围**: `brain_linux/src/auv_decision/auv_decision_core`、`auv_decision_ros`、`auv_bridge`、`auv_interfaces`、`common`
> **目标读者**: 联调工程师、算法开发者、系统集成测试、现场验收人员

---

## 1. 背景与目标

### 1.1 问题

当前 Jetson 决策栈的主要问题不是“没有算法”，而是“算法粒度过粗”。一旦行为树启动，系统会从完整任务流直接开始执行：下潜、海底安全、路由选择、巡检/搜索全部串在一起。这样带来的直接结果是：

- PID、LOS 导引律、感知闭环被绑在同一个运行路径里，单点失效很难隔离。
- 首次联调必须假设所有模块同时正常，调试成本高，回退路径少。
- 没有一个“稳定但功能最小”的控制基线，无法逐级验收。
- 仿真时间、桥接时间和 Jetson 本地时间没有统一基准，轨迹采样和调试日志难以对齐。

### 1.2 设计目标

本方案引入四级控制模式，从最保守的安全层逐步提升到完整任务流：

1. 每一级都能单独运行和验收。
2. 每一级只引入一类新能力，方便隔离问题。
3. 安全逻辑始终优先，不因分级而弱化。
4. 现有控制协议和桥接逻辑保持兼容。
5. 引入统一的 Mock AMD 时间基准，保证解析轨迹可复现。

### 1.3 设计原则

- **L0 永远优先**：漏水、低电、穿底等安全问题必须直接抢占控制权。
- **低层先验收，高层后开放**：Hold 通过后再验证 AnalyticalPath，最后才回到完整任务流。
- **核心层无 ROS 依赖**：行为节点和数据模型保留纯 Python，可单元测试。
- **桥接层只做转换**：时间戳、消息和协议字段在桥接层统一处理。
- **决策层负责过渡**：模式切换时的平滑插值在决策节点完成，控制器尽量无感知。

---

## 2. 四级模式总览

### 2.1 Level 定义

| Level | 名称 | 核心目标 | 典型输出 | 主要用途 |
|---|---|---|---|---|
| L0 | Emergency | 安全保护 | `EMERGENCY_SURFACE` | 漏水/低电/穿底应急 |
| L1 | Hold | PID 稳定性验证 | `STABILIZE_HOLD` | 定深定航、零速度保持 |
| L2 | AnalyticalPath | LOS 导引验证 | `ANALYTICAL_PATH` | 按解析轨迹采样并跟踪 |
| L3 | Full Mission | 完整任务流 | `DIVE_TO_DEPTH`、`PARALLEL_TRACKING`、`ZIGZAG_SEARCH` | 正常自主巡检 |

### 2.2 递进关系

```text
L0 Emergency
  └─ 始终最高优先级，任何模式下都能打断其它分支

L1 Hold
  └─ 验证 PID 控制稳定性

L2 AnalyticalPath
  └─ 验证 LOS 导引与解析轨迹跟踪

L3 Full Mission
  └─ 恢复完整行为树任务流
```

### 2.3 推荐使用顺序

1. 先在离线或低风险环境验证 L1。
2. 再使用统一时钟验证 L2。
3. 最后回到 L3 做完整任务流联调。

---

## 3. 运行时蓝图

### 3.1 数据流

```text
Mock AMD / 仿真 / 海试日志
    └─ bridge_backends.py / mock_amd_server.py
        └─ /auv/mock_amd/time
            └─ decision_node.py
                └─ auv_decision_core.bt_engine
                    └─ behaviors.py
                        └─ MotionGoal / SensorStatusData
                            └─ auv_interfaces 消息
                                └─ controller / bridge / visualization
```

### 3.2 统一时间基准

当前实现将协议 `Para1` 作为 Mock AMD Unix 微秒时间戳使用：

- 下行报文在桥接层写入 `mock_amd_timestamp_us`。
- 决策节点订阅 `/auv/mock_amd/time`。
- 首次收到时间戳前，决策 tick 保持等待。
- 若时间戳超时，节点允许回退到系统时间并记录告警。

### 3.3 决策结构映射

| 模块 | 职责 |
|---|---|
| `common/enums.py` | 共用枚举：BehaviorMode、WorkInstruction、DebugLevel、DenyReason |
| `common/protocol.py` | 协议键名、Para 偏移、时间戳字段、报文解析 |
| `auv_decision_core/models.py` | 纯业务数据模型，承载 `debug_level`、`heading_rad`、`mock_amd_timestamp_us` |
| `auv_decision_core/behaviors.py` | 四级行为节点实现 |
| `auv_decision_core/bt_engine.py` | 行为树装配与分支路由 |
| `auv_decision_ros/decision_node.py` | ROS2 参数、订阅、时间同步、过渡平滑 |
| `auv_bridge/autonomy_guard.py` | 自主接管/撤销判定 |

---

## 4. 各级详细蓝图

### 4.1 L0 - Emergency

**定位**：最高优先级安全层，任何时候都应抢占。

**触发条件**：

- 漏水：`leak_level > 0`
- 低电：`battery_low == True`
- 穿底：`seabed_penetration_warning == True`

**典型输出**：

```python
MotionGoal(
    mode='EMERGENCY_SURFACE',
    target_depth_m=0.0,
    target_speed_mps=0.8,
    high_priority=True,
    note='检测到安全风险，执行紧急上浮。',
)
```

**验收标准**：

- 任意 `debug_level` 下都能触发。
- 高优先级标记必须为真。
- 不依赖 Mock AMD 时间。

### 4.2 L1 - Hold

**定位**：验证控制器最小闭环能力，重点看 PID 是否稳。

**行为特征**：

- 初始化时抓取当前深度和航向。
- 后续持续保持当前姿态，不再主动推进速度。
- 输出速度应为 0 或接近 0。

**典型输出**：

```python
MotionGoal(
    mode='STABILIZE_HOLD',
    target_depth_m=current_depth,
    target_speed_mps=0.0,
    target_heading_rad=current_heading,
    note='L1 Hold 模式：定深定航稳定。',
)
```

**验收标准**：

- 切到 `debug_level=1` 后，系统进入 Hold。
- 航向和深度目标来源于当前状态。
- 可重复 tick，目标不应漂移。

### 4.3 L2 - AnalyticalPath

**定位**：验证 LOS 导引和解析轨迹采样。

**行为特征**：

- 基于 Mock AMD 时间进行轨迹采样。
- 输出包含轨迹点坐标、目标深度、目标航向和速度。
- 依赖统一时间基准，便于复现。

**典型输出**：

```python
MotionGoal(
    mode='ANALYTICAL_PATH',
    target_x_m=..., 
    target_y_m=..., 
    target_depth_m=..., 
    target_heading_rad=..., 
    target_speed_mps=..., 
    note='L2 AnalyticalPath 模式：跟踪解析式轨迹。',
)
```

**验收标准**：

- Mock AMD 时间已同步时可稳定采样。
- 轨迹点在不同运行之间应可复现。
- 当轨迹生成失败或时间未同步时，应回落到安全可运行路径。

### 4.4 L3 - Full Mission

**定位**：保持现有完整任务流，作为最终运行态。

**典型分支**：

- `DIVE_TO_DEPTH`
- `PARALLEL_TRACKING`
- `ZIGZAG_SEARCH`

**验收标准**：

- 高置信度时进入并行跟踪。
- 低置信度时进入之字形搜索。
- 紧急条件仍然可以覆盖。

---

## 5. 现有实现映射

### 5.1 核心代码位置

- `common/enums.py`: 增加 `BehaviorMode`、`WorkInstruction`、`DebugLevel`、`DenyReason` 相关枚举。
- `common/protocol.py`: 增加 `KEY_MOCK_AMD_TIMESTAMP`、`Z_PATH_MOCK_AMD_TIME`、Para 偏移常量。
- `auv_decision_core/models.py`: `SensorStatusData` 增加 `heading_rad`、`mock_amd_timestamp_us`、`debug_level`，`MotionGoal` 增加解析轨迹字段。
- `auv_decision_core/behaviors.py`: 实现 `HoldCurrentPoseBehavior`、`TrackAnalyticalTrajectoryBehavior`、`DebugLevelCondition`。
- `auv_decision_core/bt_engine.py`: 构建 L0/L1/L2/L3 路由树。
- `auv_decision_ros/decision_node.py`: 订阅 Mock AMD 时间、处理过渡平滑、处理参数切换。
- `auv_bridge/bridge_backends.py`: 传播 Mock AMD 时间戳，写入下行 Para1。
- `mock_amd_server.py`: 回显时间戳，保证联调时钟闭环。

### 5.2 行为树路由

当前行为树的关键策略是：

1. `EmergencySequence` 永远位于根选择器最前。
2. `HoldSequence` 仅在 L1 目标开启时生效。
3. `AnalyticalPathSequence` 仅在 L2 目标开启时生效。
4. `MainMissionSequence` 作为 L3 回退和默认完整任务流。

### 5.3 决策节点的运行约束

- 初次启动时，若尚未收到 Mock AMD 时间戳，决策节点应等待。
- 若时间戳长时间未更新，节点允许回退到系统时间，但要打日志。
- 模式切换时，如果目标位移超过阈值，应进行线性平滑过渡。

---

## 6. 参数与接口

### 6.1 ROS2 参数

| 参数名 | 默认值 | 作用 |
|---|---:|---|
| `debug_level` | 0 | 算法透明度级别 |
| `mock_amd_timeout_s` | 5.0 | Mock AMD 时间同步超时 |
| `transition_threshold_m` | 2.0 | 触发平滑过渡的跳变阈值 |
| `transition_duration_s` | 3.0 | 平滑过渡持续时间 |
| `confidence_threshold` | 0.7 | 高置信度分支阈值 |

### 6.2 WorkInstruction 处理

当前设计中：

- `0xA1` 对应 `HOLD_DEBUG`
- `0xA2` 对应 `ANALYTICAL_PATH_DEBUG`

约束：

- 仅在 `debug_level=0` 时允许通过仲裁器切换。
- 一旦手动切到 L1/L2，不应被普通任务流覆盖。

### 6.3 消息字段

- `SensorStatus.msg` 增加 `heading_rad`、`mock_amd_timestamp_us`、`debug_level`。
- `Setpoint.msg` 增加 `target_x_m`、`target_y_m`。
- 核心层对应字段已同步到 dataclass。

---

## 7. 验证与验收

### 7.1 已执行验证

以下验证已经通过：

- `colcon build --packages-select auv_common auv_interfaces auv_decision_core auv_decision_ros auv_bridge`
- `colcon test --packages-select auv_decision_core auv_interfaces`
- `colcon test --packages-select my_auv_talker`
- `colcon test --event-handlers console_direct+`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/bin/python3 -m pytest tests -q`

### 7.2 当前回归状态

- `auv_decision_core`：通过。
- `auv_bridge`：通过。
- `auv_controller`：通过。
- `auv_interfaces`：通过。
- `my_auv_talker`：风格测试已修复并通过。
- 根目录 Python tests：通过。

### 7.3 级别验收清单

| 检查项 | 期望结果 |
|---|---|
| L0 安全抢占 | 漏水/低电/穿底立即触发紧急上浮 |
| L1 定深定航 | 进入 Hold 后速度归零、目标姿态稳定 |
| L2 轨迹跟踪 | 使用 Mock AMD 时间后能稳定采样轨迹 |
| L3 完整任务 | 高/低置信度分支与原任务流一致 |
| 时间同步 | 首次等待时间戳，超时可降级告警 |
| 平滑过渡 | 大跳变时以线性插值过渡，而不是硬切 |

---

## 8. 故障排查

### 8.1 收不到 Mock AMD 时间

现象：决策节点一直等待或频繁提示同步失败。

处理：

- 确认桥接层是否发布 `/auv/mock_amd/time`。
- 确认下行报文 `Para1` 是否已经写入时间戳。
- 确认模拟端回显链路是否通畅。

### 8.2 L1 没有进入 Hold

现象：切换 `debug_level=1` 后仍然停留在主任务流。

处理：

- 检查 `SensorStatusData.debug_level` 是否已写入。
- 检查行为树路由是否还保留旧条件。
- 确认没有被紧急分支抢占。

### 8.3 L2 轨迹不稳定

现象：解析轨迹输出跳变大，或者轨迹点不可复现。

处理：

- 检查 Mock AMD 时间是否稳定更新。
- 检查轨迹生成器输入是否依赖系统时间。
- 检查过渡平滑阈值是否过小。

### 8.4 全量 colcon 失败

若再次出现全量失败，优先按以下顺序排查：

1. `common/enums.py` 是否与桥接层保持一致。
2. `auv_interfaces` 新增字段是否同步到 mappers。
3. `my_auv_talker` 等示例包是否仍存在风格问题。
4. 决策层行为节点是否仍有旧黑板键或旧分支引用。

---

## 9. 推荐运行方式

### 9.1 L1 Hold 联调用法

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux
colcon test --packages-select auv_decision_core --event-handlers console_direct+
```

### 9.2 L2 AnalyticalPath 联调用法

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux
colcon build --packages-select auv_interfaces auv_decision_core auv_decision_ros auv_bridge
```

### 9.3 全量回归

```bash
cd /home/gwxie/master_work-tmp/AUV_Master_Project/brain_linux
colcon test --event-handlers console_direct+
```

---

## 10. 当前状态与后续建议

### 10.1 当前状态

- L0-L3 蓝图已经落地到核心实现。
- 决策节点支持 Mock AMD 时间同步、过渡平滑和参数化切换。
- 全量测试已验证通过，示例包风格问题已修复。

### 10.2 后续建议

1. 为 L1/L2 增加更细的集成测试，例如 Mock AMD 时钟抖动、轨迹中断重连和过渡平滑曲线。
2. 将文档中的验收表同步到联调记录，形成现场操作手册。
3. 如果后续要扩展更细等级，可在 `DebugLevel` 基础上再细分子模式，但不要破坏当前四级边界。

---

## 11. 参考文件

- `common/enums.py`
- `common/protocol.py`
- `brain_linux/src/auv_decision/auv_decision_core/behaviors.py`
- `brain_linux/src/auv_decision/auv_decision_core/bt_engine.py`
- `brain_linux/src/auv_control/auv_decision_ros/decision_node.py`
- `brain_linux/src/auv_bridge/auv_bridge/autonomy_guard.py`
- `brain_linux/src/auv_bridge/auv_bridge/bridge_backends.py`
- `brain_linux/src/auv_interfaces/msg/SensorStatus.msg`
- `brain_linux/src/auv_interfaces/msg/Setpoint.msg`
