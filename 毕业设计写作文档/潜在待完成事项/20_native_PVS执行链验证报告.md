# native PVS 执行链验证报告

> 日期：2026-08-10  
> 对象：PVS 后端 `depthHeadingAutopilot` 原生执行链  
> 证据包：`results/control/native_pvs_execution_chain_constant_feature_smoke_20260810/20260810_225652/`  
> 审计状态：`passed`

## 1. 验证目的

本次验证回答一个窄而关键的问题：ROS2 侧生成的控制目标和 MPC/arbiter 输出，是否真正经由 `protocol_udp` 二进制下行、Mock AMD 的 AUTO 调度，进入 PVS 原生 `depthHeadingAutopilot()` 内层自动驾驶路径，而不是绕到既有的 `kinematic_setpoint` 运动学代理。

该问题独立于 R22 离线原生因子闭环矩阵。R22 已证明声磁、地形和横流因子能进入制导级离线闭环，但其数据层是 `offline simulation_proxy`，不调用 PVS 原生 `depthHeadingAutopilot`。因此本报告只关闭“执行链是否接入 native PVS 内层自动驾驶”的接口风险，不重写 R22 的性能统计结论。

## 2. 被验证执行链

本次 smoke 期望闭合的执行链如下：

```text
ROS2 feature flags / setpoint
  -> auv_controller_node / MPC debug
  -> auv_bridge arbiter
  -> protocol_udp binary downlink
  -> Mock AMD AUTO dispatch
  -> PVSSimWrapper.set_reference()
  -> PVS depthHeadingAutopilot()
  -> PVS dynamics/state
  -> uplink telemetry
  -> ROS2 filtered state / MCAP
```

关键判据包括：

1. 桥接配置必须是 `bridge.backend=protocol_udp`。
2. PVS 配置必须是 `pvs.control_mode=depthHeadingAutopilot`。
3. PVS 运动模型必须是 `pvs.autonomy_motion_model=native`，不能是 `kinematic_setpoint`。
4. 日志中必须观测到 AUTO 模式和 native PVS backend open。
5. MCAP 中必须同时存在 setpoint、MPC command、arbiter 状态和 PVS 派生状态。
6. PVS 派生状态必须有非零运动响应，不能只是空包或静态记录。

## 3. 配置与运行条件

本次运行使用专用配置，避免污染既有 proxy/terrain 配置：

| 项目 | 取值 |
|---|---|
| bridge config | `config/bridge_params.protocol_udp.pvs.native_autopilot.yaml` |
| feature flags | `brain_linux/config/feature_flags.native_pvs_constant.yaml` |
| PVS control mode | `depthHeadingAutopilot` |
| PVS autonomy motion model | `native` |
| simulation backend | `pvs` |
| bridge backend | `protocol_udp` |
| 场景类型 | constant-depth / constant-heading smoke |
| 当前扰动 | `pvs.current_speed_mps=0.0` |
| MCAP | `rosbag/rosbag_0.mcap` |

`feature_flags.native_pvs_constant.yaml` 单独设为 constant-depth/constant-heading，是为了避免 terrain benchmark 自动生成的 `feature_flags.yaml` 把控制链污染为 `Depth:TERRAIN_FOLLOWING`。成功运行日志中已观测到：

```text
[Controller] Current Chain: Heading:CONSTANT + Depth:CONSTANT
[pvs] backend open: mode=depthHeadingAutopilot depth=12.00m heading=0.0deg rpm=520.0
```

## 4. 审计方法

审计脚本为：

```bash
python3 tools/audit_native_pvs_execution_chain.py \
  --run-dir results/control/native_pvs_execution_chain_constant_feature_smoke_20260810/20260810_225652 \
  --bridge-config config/bridge_params.protocol_udp.pvs.native_autopilot.yaml \
  --output-dir results/control/native_pvs_execution_chain_constant_feature_smoke_20260810/20260810_225652/native_pvs_execution_chain_audit
```

输出文件：

| 文件 | 作用 |
|---|---|
| `native_pvs_execution_chain_summary.json` | 机器可读总摘要 |
| `topic_rates.csv` | ROS2 topic 频率审计 |
| `setpoint_to_state_tracking.csv` | setpoint 到状态响应的抽样追踪 |
| `report.md` | 简短审计报告 |

审计逻辑由三部分组成：

1. **配置审计**：检查 `protocol_udp`、`depthHeadingAutopilot`、`native` 三个关键开关，并拒绝 `kinematic_setpoint`。
2. **日志审计**：统计 AUTO 模式、native autopilot backend open、kinematic proxy 相关日志，以及 protocol control mode byte。
3. **MCAP 审计**：统计 setpoint、MPC command、arbiter status、controller debug、filtered state 等话题，并提取状态跨度与求解器耗时。

## 5. 核心结果

### 5.1 配置结论

| 检查项 | 结果 |
|---|---|
| `bridge_backend_is_protocol_udp` | `true` |
| `pvs_control_mode` | `depthHeadingAutopilot` |
| `pvs_control_mode_is_native_autopilot` | `true` |
| `pvs_autonomy_motion_model` | `native` |
| `pvs_uses_kinematic_proxy` | `false` |

配置层结论：本次运行没有使用 `kinematic_setpoint` 运动学代理，满足 native PVS 执行链验证的前置条件。

### 5.2 日志证据

| 指标 | 数值 |
|---|---:|
| `auto_mode_log_count` | 149 |
| `manual_mode_log_count` | 4 |
| `native_autopilot_open_log_count` | 1 |
| `kinematic_log_count` | 0 |
| `autonomy_guard_rejection_count` | 21 |
| protocol control mode `0xEE` | 268 |
| protocol control mode `0x01` | 9 |

日志层结论：PVS 后端以 `depthHeadingAutopilot` 打开，AUTO 模式持续出现，且未出现 kinematic proxy 日志。少量 `0x01` 和 `manual` 记录来自启动/切换阶段，不改变主链路的 AUTO 执行证据。

### 5.3 ROS2 与 MCAP 证据

| 指标 | 数值 |
|---|---:|
| MCAP 文件数 | 1 |
| `/auv/control/setpoint` 样本 | 245 |
| `/auv/control/mpc_cmd` 样本 | 720 |
| `/auv/arbiter/status` 样本 | 8561 |
| `/auv/controller/debug` 样本 | 72 |
| `/auv/state/filtered` 样本 | 998 |
| arbiter effective control mode `238` | 8561 |
| debug solver status | `Solve_Succeeded` 72/72 |

话题频率摘要：

| Topic | 频率 |
|---|---:|
| `/auv/control/mpc_cmd` | 20.04 Hz |
| `/auv/control/setpoint` | 9.89 Hz |
| `/auv/state/filtered` | 20.02 Hz |
| `/auv/sensors/depth` | 46.47 Hz |
| `/auv/sensors/dvl` | 46.48 Hz |
| `/auv/sensors/imu` | 46.48 Hz |

MCAP 层结论：ROS2 setpoint、MPC command、arbiter status 和 PVS 派生 filtered state 同时存在，形成可追溯的执行链闭环记录。

### 5.4 状态响应证据

`/auv/state/filtered` 在约 50 s 窗口内的状态跨度为：

| 状态量 | span |
|---|---:|
| x | 24.035 m |
| y | 7.892 m |
| z | 1.127 m |
| yaw | 30.7 deg |

controller debug 侧观测到：

| 指标 | 数值 |
|---|---:|
| current depth span | 1.117 m |
| current yaw span | 30.7 deg |
| current speed span | 1.308 m/s |
| setpoint target depth span | 0.0 m |
| setpoint target heading span | 0.0 deg |
| setpoint target speed span | 0.0 m/s |

状态响应结论：本次 smoke 的 setpoint 是恒定目标，但 PVS 状态发生了非零深度、航向、速度和平面位移响应，说明链路不是静态记录或空包回放。由于运行目标是执行链验证，不把该响应解释为控制性能最优性或精确速度跟踪。

### 5.5 求解器与周期预算

| 指标 | 数值 |
|---|---:|
| solver wall time p95 | 19.318 ms |
| solver wall time max | 20.404 ms |
| `/auv/control/mpc_cmd` median period | 49.973 ms |
| `/auv/control/mpc_cmd` p95 period | 53.586 ms |
| `/auv/state/filtered` median period | 49.998 ms |
| `/auv/state/filtered` p95 period | 52.755 ms |
| `/auv/control/setpoint` median period | 101.173 ms |
| `/auv/control/setpoint` p95 period | 103.445 ms |

时序结论：solver p95/max 低于 20 Hz 控制周期的 50 ms 预算，也低于 bridge/VxWorks 约 10 Hz 的 100 ms 周期预算。但这只是仿真执行链内的 solver 与 topic 周期证据，不能写成真实 Jetson--AMD/PC104 物理链路时延。

## 6. 验证结论

本次审计可以支撑以下结论：

1. native PVS/protocol_udp 仿真执行链已经闭合。
2. 本次运行使用 `depthHeadingAutopilot` 与 `native` 运动模型，不使用 `kinematic_setpoint` proxy。
3. ROS2 controller/MPC/arbiter 输出进入了 `protocol_udp` 与 Mock AMD AUTO dispatch 路径。
4. PVS 派生状态被记录回 ROS2 MCAP，且有非零运动响应。
5. solver wall time 在本 smoke 中处于 20 Hz/10 Hz 周期预算内。

建议论文中的主表述为：

> native PVS/protocol_udp smoke 验证了 ROS2 controller/MPC/arbiter 可经 `protocol_udp` 二进制下行与 Mock AMD AUTO dispatch 进入 PVS `depthHeadingAutopilot` 原生内层自动驾驶路径，且审计确认未使用 `kinematic_setpoint` 运动学代理。该结果关闭了执行链接口风险，但不替代 R22 全因子性能矩阵、PC104/VxWorks 物理时延或海试证据。

## 7. 不可外推边界

本次结果不得外推为以下结论：

1. **不能写成 PC104/VxWorks 物理时延**：本报告没有共享时钟、firmware echo 或真实 VxWorks 时间戳，只能讨论仿真执行链与 ROS2 topic 周期。
2. **不能写成 R22 native PVS 性能矩阵**：本次是 constant-depth/constant-heading smoke，不覆盖声磁、地形、横流、长航时和多 seed 因子组合。
3. **不能写成海试或硬件 handoff**：Mock AMD 复现的是协议与 AUTO dispatch 语义，不等于真实 PC104 接收、解包、调度、本地安全逻辑和执行器响应。
4. **不能写成精确速度跟踪验收**：速度参考经主推 RPM 映射进入 PVS，当前证据只说明速度参考进入链路并引发状态响应，不说明推进器实物或精确速度闭环已验收。
5. **不能写成 CBF 或 R13/R22 既有矩阵自动升级**：既有 CBF/R22 proxy 结果的数据层不因本 smoke 改变；本 smoke 只单独补上 native PVS 执行链证据。

## 8. 后续工作

若要把 native PVS 从“执行链闭合”推进到“性能矩阵证据”，建议按以下顺序补强：

1. **native PVS 多 seed smoke**：保持 constant-depth/heading，扩展 3 到 5 个 seed，确认执行链稳定性。
2. **native PVS 扰动小矩阵**：加入横流、初始深度偏差、初始航向偏差和速度目标档位，形成低成本边界搜索。
3. **native PVS 与 R22 因子桥接**：选取 R22 中最难的曲线加横流组合，构造少量 native PVS 对照样本，避免直接重跑全矩阵造成成本失控。
4. **真实 PC104 echo 或共享时钟**：若论文需要单向或闭环物理时延，必须增加固件 echo 时间戳或共享时钟同步；否则继续只报告到达间隔和抖动。
5. **applied-speed 追踪**：若要讨论速度执行质量，需要从 setpoint、downlink RPM、PVS `reference_rpm/reference_speed_mps` 到状态速度建立逐步 trace。

## 9. 证据索引

| 类别 | 路径 |
|---|---|
| 审计摘要 | `results/control/native_pvs_execution_chain_constant_feature_smoke_20260810/20260810_225652/native_pvs_execution_chain_audit/native_pvs_execution_chain_summary.json` |
| topic 频率 | `results/control/native_pvs_execution_chain_constant_feature_smoke_20260810/20260810_225652/native_pvs_execution_chain_audit/topic_rates.csv` |
| setpoint-state 追踪 | `results/control/native_pvs_execution_chain_constant_feature_smoke_20260810/20260810_225652/native_pvs_execution_chain_audit/setpoint_to_state_tracking.csv` |
| 审计短报告 | `results/control/native_pvs_execution_chain_constant_feature_smoke_20260810/20260810_225652/native_pvs_execution_chain_audit/report.md` |
| 原始 MCAP | `results/control/native_pvs_execution_chain_constant_feature_smoke_20260810/20260810_225652/rosbag/rosbag_0.mcap` |
| PVS/protocol_udp 配置 | `config/bridge_params.protocol_udp.pvs.native_autopilot.yaml` |
| constant feature flags | `brain_linux/config/feature_flags.native_pvs_constant.yaml` |
| 审计脚本 | `tools/audit_native_pvs_execution_chain.py` |
| Manifest 条目 | `CONTROL-NATIVE-PVS-EXECUTION-CHAIN-SMOKE` |

