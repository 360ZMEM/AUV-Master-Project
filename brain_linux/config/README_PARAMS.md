# AUV 参数与旁路控制手册

本文档解释了 AUV 决策栈的参数和旁路特征开关 (`feature_flags.yaml`)。这些参数用于控制不同算法模块的开启/关闭，或者强制 AUV 运行在某些特定的调试/保底状态。

## 1. 旁路架构（Bypass Architecture）

系统目前支持三级旁路控制：

1. **决策旁路 (Decision Bypass)**
   - 跳过复杂的行为树，直接下发原始的 Setpoint 目标位姿。
   - 适用于排查行为树逻辑错误时，直接测试“给定目标位姿”的响应。

2. **导引旁路 (Guidance Bypass)**
   - 跳过地形跟随、磁寻迹或解析轨迹等高阶导引算法，直接输出固定的目标深度或航向。
   - 适用于单独验证底层 PID 闭环的稳定性。

3. **控制旁路 (Control Bypass / Zero Effort)**
   - 跳过所有本地控制计算，强制输出零推力、零舵角。
   - 用于作为“被动节点”只翻译/转发数据，或者维持与底层 UDP 通信心跳，而不干扰外部控制。

## 2. 参数列表与解释

所有特征开关均定义在 `brain_linux/config/feature_flags.yaml` 中。您也可以通过 `ros2 param set` 实时修改这些参数（除个别需重启生效的参数外）。

### 决策层开关 (`auv_decision_node`)

| 参数名 | 类型 | 默认值 | 描述 |
| ------ | ---- | ------ | ---- |
| `enable_behavior_tree` | `bool` | `true` | 是否启动行为树逻辑。若为 `false`，决策节点完全静默。 |
| `bypass_to_manual_setpoint` | `bool` | `false` | 开启后，决策节点订阅 `/auv/manual/setpoint` 并将其原样包装后下发，完全无视行为树的输出。 |

### 控制层开关 (`auv_controller_node`)

| 参数名 | 类型 | 默认值 | 描述 |
| ------ | ---- | ------ | ---- |
| `depth_mode` | `string` | `'CONSTANT'` | 深度源模式。支持 `'CONSTANT'` (定深), `'SINE_WAVE'` (正弦波), `'TERRAIN_FOLLOWING'` (地形跟随)。 |
| `heading_mode` | `string` | `'CONSTANT'` | 航向源模式。支持 `'CONSTANT'` (定航), `'TRAJECTORY'` (轨迹), `'MAGNETIC_TRACKING'` (磁寻迹)。 |
| `constant_depth_m` | `float` | `2.0` | 当 `depth_mode` 为 `'CONSTANT'` 或 `'SINE_WAVE'` 时生效的基准深度 (米)。 |
| `constant_heading_rad` | `float` | `0.0` | 当 `heading_mode` 为 `'CONSTANT'` 时生效的目标航向 (弧度)。 |
| `bypass_zero_effort` | `bool` | `false` | 若开启，强制覆盖所有计算结果，输出零推力、零舵角的保底指令。 |

### 桥接层开关 (`zenoh_json_bridge_node`)

| 参数名 | 类型 | 默认值 | 描述 |
| ------ | ---- | ------ | ---- |
| `passive_mode` | `bool` | `false` | 影子模式/监听模式。开启后，仅接收和转发遥测数据，**不下发任何控制指令到下位机**。 |

## 3. 一键降级模式 (Minimal Mode)

为了快速测试 AUV 系统的基础连通性（如 UDP 链路是否正常，ROS 话题是否能收到传感器数据），可以启动 `minimal` 模式：

```bash
ros2 launch auv_stack auv_stack.launch.py minimal:=true
```

**在该模式下，Launch 脚本会强制覆盖以下参数：**
- `passive_mode = true`（桥接层不发送下行指令）
- `bypass_zero_effort = true`（控制层仅输出 0 推力 0 舵角）
- `enable_behavior_tree = false`（决策层静默）

**预期效果**：所有高级节点处于静默或转发模式。Jetson 仅仅作为一个 UDP 到 ROS 消息的翻译器。

## 4. 运行时参数修改示例

你可以在系统运行时，动态修改参数以排查问题：

**1. 隔离测试定深 PID：**
```bash
ros2 param set /auv_controller_node depth_mode CONSTANT
ros2 param set /auv_controller_node constant_depth_m 3.0
```
*预期：系统将无视 DVL 高度变化，固定下潜到 3.0 米。*

**2. 开启/关闭保底指令：**
```bash
ros2 param set /auv_controller_node bypass_zero_effort true
```
*预期：推力器立即停转，舵机回中。*
