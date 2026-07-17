# Zenoh + protocol_udp 仿真验证记录

## 1. 验证目标

PC104 空板实机验证已收口到低层链路边界后，转入 `Zenoh + protocol_udp`
仿真验证高层链路：

- `auto_activate_emu.py` 是否能通过 `rt/pc/cmd_raw` 持续授权自主模式。
- `protocol_udp` 二进制下行是否进入仿真端。
- 行为树是否从 `StandbyCheck` 进入任务态。
- 区分运行期 PC link 异常与外层脚本停机阶段的预期掉线日志。

## 2. 运行命令

```bash
bash scripts/preflight_clean.sh
bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --auto-activate \
  --duration 70 \
  --no-record-bag \
  --launcher-output stream \
  --preflight-clean
```

## 3. 运行证据

### 3.1 70s smoke

运行目录：

```text
/auv_data/bags/20260716_235621
```

`auto_activate_emu.py` 正常发布：

```text
2026-07-16 23:56:22,093 INFO auto_activate_emu peer session up; publishing on rt/pc/cmd_raw at 10.0 Hz
2026-07-16 23:57:31,771 INFO auto_activate_emu received signal 2, shutting down
```

行为树进入并保持任务态：

```text
[行为树切换] behavior=ZigZagSearch | mode=ZIGZAG_SEARCH
[状态摘要] mode=ZIGZAG_SEARCH | behavior=ZigZagSearch | goal_speed=0.40m/s | goal_depth=4.00m
```

`protocol_udp` 下行字段统计：

```text
Work Instruction: 0x00  -> 30 frames
Work Instruction: 0x02  -> 9 frames
Work Instruction: 0xEE  -> 199 frames
```

首个自主下行包字段：

```text
Control Mode Byte: 0xEE
  -> AUTONOMOUS
Work Instruction: 0xEE
  -> AUTONOMOUS_CONTROL
```

### 3.2 ESTOP/manual override 注入

运行目录：

```text
/auv_data/bags/20260717_000253
```

本轮在 `auto_activate_emu.py` 持续运行时注入 3s ESTOP/manual override burst，
避免与外层停机阶段混淆：

```text
2026-07-17 00:02:53,606 INFO auto_activate_emu peer session up; publishing on rt/pc/cmd_raw at 10.0 Hz
[estop-test] injected_frames=59
2026-07-17 00:04:23,283 INFO auto_activate_emu received signal 2, shutting down
```

注入载荷字段：

```text
control_mode_byte = 0x01
work_instruction = 0x02
motor/fins/thrust = 0
```

brain 侧确认收到 ESTOP/manual override，并立即强制回 REMOTE：

```text
[行为树切换] behavior=ZigZagSearch | mode=ZIGZAG_SEARCH
[bridge] ESTOP/MANUAL_OVERRIDE received, forcing REMOTE
[行为树切换] behavior=StandbyCheck | mode=IDLE
```

`protocol_udp` 下行字段统计：

```text
Work Instruction: 0x00  -> 29 frames
Work Instruction: 0x02  -> 18 frames
Work Instruction: 0xEE  -> 267 frames
```

首个 `0x02` 下行包字段：

```text
Control Mode Byte: 0x01
  -> REMOTE_CONTROL
Work Instruction: 0x02
  -> TASK_CANCEL
CONTROL SURFACES:
  Right Fin: +0.0 deg
  Top Fin: +0.0 deg
  Left Fin: +0.0 deg
  Bottom Fin: +0.0 deg
  Thrust: +0.0 %
```

本轮同时暴露一个修复前语义边界：3s ESTOP burst 结束后，`auto_activate_emu.py`
仍以 10Hz 继续发布 `0xEE` 自主授权心跳，因此系统随后又从 `StandbyCheck`
重新进入 `ZigZagSearch`：

```text
[行为树切换] behavior=StandbyCheck | mode=IDLE
[行为树切换] behavior=ZigZagSearch | mode=ZIGZAG_SEARCH
```

这说明修复前实现验证通过的是“连续 ESTOP/manual override 生效”，不是“单次
ESTOP 锁存直到显式清除”。

### 3.3 ESTOP 锁存修复复验

修复点：

- `AutonomyGuard.request_activation()` 在 `LOCKED/MANUAL_OVERRIDE` 下拒绝普通 `0xEE` 自主申请。
- `bridge_node.handle_pc_raw_command()` 将 `TASK_CANCEL(0x02)` 与 `CLEAR_FAULT(0x91)` 分开：
  `0x02` 只锁定，`0x91` 清除手动覆盖锁并下发零执行器 REMOTE 包。
- 普通手动包不能隐式清除 `MANUAL_OVERRIDE` 锁；锁定态下手动包执行器字段强制归零。

运行目录：

```text
/auv_data/bags/20260717_000852
```

运行命令：

```bash
bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --auto-activate \
  --duration 90 \
  --no-record-bag \
  --launcher-output stream \
  --preflight-clean
```

注入结果：

```text
[estop-test] injected_frames=59
```

注入前系统已进入任务态：

```text
[行为树切换] behavior=ZigZagSearch | mode=ZIGZAG_SEARCH
```

注入后 bridge 立即强制 REMOTE，行为树退回 Standby：

```text
[bridge] ESTOP/MANUAL_OVERRIDE received, forcing REMOTE
[行为树切换] behavior=StandbyCheck | mode=IDLE
```

随后 `auto_activate_emu.py` 仍持续发布 `0xEE`，但 guard 持续拒绝重新激活：

```text
[bridge] Autonomy guard rejected, forcing zero-thrust REMOTE
```

注入点之后统计：

```text
ZigZagSearch switches after ESTOP: 0
Autonomy guard rejections after ESTOP: 275
Post-ESTOP protocol_udp Work Instruction:
  0x02 -> 107 frames
```

本轮完整下行字段统计：

```text
Work Instruction: 0x00  -> 30 frames
Work Instruction: 0x02  -> 124 frames
Work Instruction: 0xEE  -> 157 frames
```

本轮说明：修复后 `ESTOP/manual override` 已具备锁存行为；单次 3s burst
结束后，持续运行的 `auto_activate` 不能再把系统重新授权回 `ZigZagSearch`。

验证命令：

```bash
python3 -m py_compile \
  brain_linux/src/auv_bridge/auv_bridge/autonomy_guard.py \
  brain_linux/src/auv_bridge/auv_bridge/bridge_node.py \
  brain_linux/src/auv_bridge/auv_bridge/arbiter.py \
  brain_linux/src/auv_bridge/test/test_autonomy_guard.py

PYTHONPATH=brain_linux/src/auv_bridge:. python3 -m pytest -q \
  brain_linux/src/auv_bridge/test/test_autonomy_guard.py \
  brain_linux/src/auv_bridge/test/test_arbiter.py \
  brain_linux/src/auv_bridge/test/test_estop_safety_lock.py
```

结果：

```text
py_compile passed
15 passed in 0.02s
```

运行结束后执行 `bash scripts/preflight_clean.sh`，确认端口 `52364/52365/52366/8765/7447`
无残留占用。

### 3.4 CLEAR_FAULT 解锁复验

运行目录：

```text
/auv_data/bags/20260717_001327
```

运行命令：

```bash
bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --auto-activate \
  --duration 100 \
  --no-record-bag \
  --launcher-output stream \
  --preflight-clean
```

`auto_activate_emu.py` 在本轮持续运行到外层 duration 结束：

```text
2026-07-17 00:13:27,610 INFO auto_activate_emu peer session up; publishing on rt/pc/cmd_raw at 10.0 Hz
2026-07-17 00:15:07,277 INFO auto_activate_emu received signal 2, shutting down
```

注入序列：

```text
[estop-test] injected_frames=59
[clear-fault-test] injected_frames=10
```

ESTOP 后，持续 `0xEE` 被锁存拒绝：

```text
[bridge] Autonomy guard rejected, forcing zero-thrust REMOTE
```

随后注入 `CLEAR_FAULT(0x91)`，bridge 清除手动覆盖锁：

```text
[bridge] CLEAR_FAULT received, manual override lock cleared
```

清锁后，下一轮 `auto_activate` 心跳可重新授权自主，行为树回到任务态：

```text
[行为树切换] behavior=ZigZagSearch | mode=ZIGZAG_SEARCH
[状态摘要] mode=ZIGZAG_SEARCH | behavior=ZigZagSearch | goal_speed=0.40m/s | goal_depth=4.00m
```

本轮完整下行字段统计：

```text
Work Instruction: 0x00  -> 30 frames
Work Instruction: 0x02  -> 122 frames
Work Instruction: 0x91  -> 2 frames
Work Instruction: 0xEE  -> 200 frames
```

本轮最后在 `00:15:07` 附近出现 `StandbyCheck` 和 `PC LOST/reconnected`，与
`auto_activate_emu.py received signal 2` 同阶段，判定为外层 duration 到时后的停机现象。

运行结束后执行 `bash scripts/preflight_clean.sh`，清理残留 `zenoh_json_bridge`、
`zenoh_viz_bridge`、`foxglove_bridge` 和共享内存。

### 3.5 关键判定

`PC LOST` 首次出现在 `auto_activate_emu.py` 收到停止信号之后：

```text
23:57:31.771 auto_activate_emu received signal 2, shutting down
[行为树切换] behavior=StandbyCheck | mode=IDLE
[bridge] PC LOST! No heartbeat ...
```

因此本次看到的 `PC link WEAK/LOST/reconnected` 属于外层 `--duration`
到时后的停机阶段现象，不是运行期 `Zenoh + protocol_udp` 链路失败。

### 3.6 mock wrapper 顶层整合 quick smoke

本轮目标是确认顶层实验命令已经可以直接拉起：

- `sensor_supervisor_node`
- `magnetic_sensor_wrapper_node`
- `forward_sonar_wrapper_node`

先重新安装新增 console script：

```bash
source /opt/ros/humble/setup.bash
cd brain_linux
colcon build --packages-select auv_decision_ros auv_controller
```

随后运行 20s quick smoke：

```bash
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration 20 \
  --no-record-bag \
  --skip-layout \
  --launcher-output log \
  --enable-mock-magnetic-wrapper \
  --enable-mock-forward-sonar-wrapper
```

运行目录：

```text
/auv_data/bags/20260717_173804
```

brain launcher 已确认顶层参数透传成功：

```text
stack launch args: ... enable_mock_magnetic_wrapper:=true enable_mock_forward_sonar_wrapper:=true
```

新增节点已实际启动：

```text
sensor supervisor ready enabled=True watches=['forward_sonar', 'magnetic', 'navigation']
magnetic wrapper skeleton ready topic=/auv/sensors/magnetic
forward sonar wrapper skeleton ready slope_topic=/auv/sensors/forward_sonar_slope
capability terrain_following changed -> True missing=[]
```

补充做了一轮 12s CLI 冒烟，确认新的专用入口参数可直接使用：

```bash
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration 12 \
  --no-record-bag \
  --skip-layout \
  --launcher-output log \
  --enable-mock-magnetic-wrapper \
  --enable-mock-forward-sonar-wrapper
```

运行目录：

```text
/auv_data/bags/20260717_173934
```

本轮判定：

- 之前阻断 quick smoke 的问题已确认修复，根因就是 install 空间未更新；
- 现在顶层实验命令已经可以直接拉起 mock magnetic / mock forward sonar；
- `sensor_supervisor` 能收到 mock sonar 输入，并把 `terrain_following` capability 置为可用；
- 停机阶段仍可见部分 ROS2 `ExternalShutdownException` / `context is invalid` 日志，这属于当前栈清理路径噪声，不是本轮 mock wrapper 接入失败。

### 3.7 auto_activate + mock wrapper 75s smoke

为避免 20s/30s 启动窗过短，本轮补做一轮更完整的 75s 烟雾实验：

```bash
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --auto-activate \
  --duration 75 \
  --no-record-bag \
  --skip-layout \
  --launcher-output log \
  --enable-mock-magnetic-wrapper \
  --enable-mock-forward-sonar-wrapper
```

运行目录：

```text
/auv_data/bags/20260717_174237
```

`auto_activate_emu.py` 在本轮持续在线直到外层 duration 结束：

```text
2026-07-17 17:42:37,838 INFO auto_activate_emu peer session up; publishing on rt/pc/cmd_raw at 10.0 Hz
2026-07-17 17:44:00,501 INFO auto_activate_emu received signal 2, shutting down
```

brain 侧确认：

```text
sensor supervisor ready enabled=True watches=['forward_sonar', 'magnetic', 'navigation']
magnetic wrapper skeleton ready topic=/auv/sensors/magnetic
forward sonar wrapper skeleton ready slope_topic=/auv/sensors/forward_sonar_slope
[行为树切换] behavior=ZigZagSearch | mode=ZIGZAG_SEARCH
[Controller] Current Chain: Heading:CONSTANT + Depth:TERRAIN_FOLLOWING
```

本轮判定：

- mock magnetic / mock forward sonar 与 `auto_activate` 可以同时从顶层实验命令拉起；
- 行为树成功进入 `ZIGZAG_SEARCH`，控制链进入 `TERRAIN_FOLLOWING`；
- 启动最初约 2s 出现若干 `Autonomy guard rejected`，随后系统正常进入任务态，判定为启动阶段暂态，不构成 mock wrapper 接入失败。

### 3.8 新增节点停机清理修补

在 75s smoke 后，确认 `sensor_supervisor_node`、`magnetic_sensor_wrapper_node`、
`forward_sonar_wrapper_node` 在停机阶段会收到 `ExternalShutdownException`。
虽然不影响功能链路，但会把新节点记成 `exit code 1`，给实验收尾带来噪声。

修补方式：

- 在 3 个新节点的 `main()` 中显式捕获 `ExternalShutdownException`；
- 仅当 `rclpy.ok()` 时才执行 `rclpy.shutdown()`。

验证命令：

```bash
source /opt/ros/humble/setup.bash
cd brain_linux
colcon build --packages-select auv_decision_ros

AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration 20 \
  --no-record-bag \
  --skip-layout \
  --launcher-output log \
  --enable-mock-magnetic-wrapper \
  --enable-mock-forward-sonar-wrapper
```

运行目录：

```text
/auv_data/bags/20260717_174744
```

修补后新节点已经变为干净退出：

```text
[INFO] [forward_sonar_wrapper_node-6]: process has finished cleanly
[INFO] [magnetic_sensor_wrapper_node-5]: process has finished cleanly
[INFO] [sensor_supervisor_node-4]: process has finished cleanly
```

说明：

- 本轮仅收口了新增 mock wrapper / supervisor 的退出噪声；
- `decision_node`、`zenoh_viz_bridge_node`、`auv_localization_node`、`zenoh_json_bridge_node`
  等现有节点仍沿用原有退出路径，停机时还会打印 `ExternalShutdownException`。

### 3.9 主栈节点停机清理收口

在上一轮基础上，继续对主栈入口函数补齐停机收尾逻辑：

- `decision_node.py`
- `auv_controller_node.py`
- `auv_localization_node.py`
- `bridge_node.py`
- `zenoh_viz_bridge_node.py`

处理原则：

- `main()` 中显式捕获 `ExternalShutdownException`，避免 ROS context 停止时被记成异常退出；
- `zenoh_viz_bridge_node.py` 的 `_on_timer()` 增加 `rclpy.ok()` 守卫，并在停机竞态下吞掉
  `publisher context is invalid` 的发布异常，但保留运行期真实异常上抛。

修改前已分别保留备份：

```text
decision_node.py.bak_20260717_2
auv_controller_node.py.bak_20260717_2
auv_localization_node.py.bak_20260717_2
bridge_node.py.bak_20260717_2
zenoh_viz_bridge_node.py.bak_20260717_2
```

验证命令：

```bash
source /opt/ros/humble/setup.bash
cd brain_linux
colcon build --packages-select auv_decision_ros auv_controller auv_localization auv_bridge auv_viz_bridge

AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --duration 20 \
  --no-record-bag \
  --skip-layout \
  --launcher-output log \
  --enable-mock-magnetic-wrapper \
  --enable-mock-forward-sonar-wrapper
```

最终运行目录：

```text
/auv_data/bags/20260717_175342
```

本轮 brain launcher 收尾结果：

```text
[INFO] [forward_sonar_wrapper_node-6]: process has finished cleanly
[INFO] [magnetic_sensor_wrapper_node-5]: process has finished cleanly
[INFO] [sensor_supervisor_node-4]: process has finished cleanly
[INFO] [auv_localization_node-2]: process has finished cleanly
[INFO] [decision_node-8]: process has finished cleanly
[INFO] [zenoh_viz_bridge_node-3]: process has finished cleanly
[INFO] [auv_controller_node-7]: process has finished cleanly
[INFO] [zenoh_json_bridge_node-1]: process has finished cleanly
```

判定：

- 当前 mock wrapper quick smoke 已实现“启动可验证、停机可干净收尾”；
- 本轮未再观察到此前的批量 `process has died [exit code 1]` 停机噪声；
- 后续再看 quick smoke 日志时，可以更专注于运行期行为，而不是停机阶段误报。

### 3.10 auto_activate + 全 mock wrapper 长时 smoke（clean-exit 版本）

在主栈 clean-exit 收口后，再补一轮 75s 长时 smoke，确认：

- `auto_activate_emu.py` 持续在线；
- mock magnetic / mock forward sonar 与主栈可长期共存；
- 行为树可稳定进入并保持任务态；
- 新的 clean-exit 路径不会破坏运行期链路。

运行命令：

```bash
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --auto-activate \
  --duration 75 \
  --no-record-bag \
  --skip-layout \
  --launcher-output log \
  --enable-mock-magnetic-wrapper \
  --enable-mock-forward-sonar-wrapper
```

运行目录：

```text
/auv_data/bags/20260717_175632
```

`auto_activate_emu.py` 持续运行到外层 duration 结束：

```text
2026-07-17 17:56:32,555 INFO auto_activate_emu peer session up; publishing on rt/pc/cmd_raw at 10.0 Hz
2026-07-17 17:57:55,302 INFO auto_activate_emu received signal 2, shutting down
```

brain 侧确认：

```text
sensor supervisor ready enabled=True watches=['forward_sonar', 'magnetic', 'navigation']
magnetic wrapper skeleton ready topic=/auv/sensors/magnetic
forward sonar wrapper skeleton ready slope_topic=/auv/sensors/forward_sonar_slope
[行为树切换] behavior=ZigZagSearch | mode=ZIGZAG_SEARCH
[Controller] Current Chain: Heading:CONSTANT + Depth:TERRAIN_FOLLOWING
```

本轮结论：

- `auto_activate + full mock wrappers + capability gate` 在 75s 窗口内可稳定运行；
- 行为树成功进入 `ZIGZAG_SEARCH`，控制链进入 `TERRAIN_FOLLOWING`；
- 启动初期仍可见短暂 `Autonomy guard rejected`，但随后系统恢复正常任务态，判定为启动暂态。

### 3.11 缺失 forward_sonar 的 capability gate 运行态复验

为验证 `terrain_following` 缺失时的降级语义，本轮关闭 mock forward sonar，仅保留：

- `auto_activate`
- `sensor_supervisor`
- `mock magnetic`

运行命令：

```bash
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --auto-activate \
  --duration 45 \
  --no-record-bag \
  --skip-layout \
  --launcher-output log \
  --enable-mock-magnetic-wrapper
```

运行目录：

```text
/auv_data/bags/20260717_175841
```

运行期关键证据：

```text
sensor supervisor ready enabled=True watches=['forward_sonar', 'magnetic', 'navigation']
magnetic wrapper skeleton ready topic=/auv/sensors/magnetic
[行为树切换] behavior=ZigZagSearch | mode=ZIGZAG_SEARCH
[capability_gate] terrain following disabled, missing=['forward_sonar']; publishing zero-effort hold
```

这说明：

- `decision_node` 仍然可以维持上层任务选择并进入 `ZIGZAG_SEARCH`；
- 但 `auv_controller_node.py` 在进入 `TERRAIN_FOLLOWING` 控制链时，已经识别到
  `forward_sonar` 缺失，并触发 `zero-effort hold` 路径；
- 也就是说，当前实现已经实现“任务层不必整栈崩掉，但控制层拒绝在缺少前视声呐时继续 terrain-following”。

补充说明：

- 该场景停机时仍可见 bridge 接收线程里一次 `publisher context is invalid` 噪声；
- 相关进程本身最终已 clean exit，因此该日志属于停机阶段线程竞态，不影响本轮
  `terrain_following` capability gate 的运行态判定。

### 3.12 缺失 magnetic 的 cable_inspection 对称验证

由于 `protocol_udp` 仿真链路本身会通过 side-channel 发布磁场样本，单纯关闭
 `mock magnetic wrapper` 并不能构成真正的“缺磁”场景。因此需要把 brain 侧
 `bridge.magnetic_key` 临时改到一个不存在的 key：

```text
rt/auv/sensors/magnetic_disabled
```

该能力最初是通过手工准备临时 `params_file` 完成的，后续已被收敛为
 `start_experiment.sh` 的正式 CLI 开关：

```text
--disable-bridge-magnetic-side-channel
```

运行命令：

```bash
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --auto-activate \
  --duration 30 \
  --no-record-bag \
  --skip-layout \
  --launcher-output log \
  --enable-mock-forward-sonar-wrapper \
  --disable-bridge-magnetic-side-channel \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_mission_type:=CABLE_INSPECTION
```

运行目录：

```text
/auv_data/bags/20260717_184140
```

运行期关键证据：

```text
[bridge] protocol_udp side-channel subscribed magnetic_key=rt/auv/sensors/magnetic_disabled
[mission_command] reject mission_type=CABLE_INSPECTION capability=cable_inspection missing=['magnetic']
cable mission accepted: CABLE_INSPECTION
cable tracking degraded by sensor gate reason=magnetic_unavailable_inspection_blocked blocked_sensors=['magnetic'] blocked_capabilities=['cable_inspection']
[capability_gate] hold mode because capability=cable_inspection missing=['magnetic']
```

本轮结论：

- `decision_node.py` 已在任务注入层拒绝缺磁的 `CABLE_INSPECTION` 指令；
- `cable_tracking_node.py` 仍可感知到 cable mission，但会立刻进入
  `magnetic_unavailable_inspection_blocked` 降级态；
- 说明 `cable_inspection` 的 capability gate 与任务级 degraded-hold 语义已经形成闭环。

### 3.13 缺失 magnetic 场景 clean-exit 回归

在 3.12 的对称验证中，又暴露出若干停机尾噪：

- `cable_tracking_node.py`
- `cable_mission_autostart_node.py`
- `zenoh_viz_bridge_node.py` 的 ground-truth 回调
- `auv_controller_node.py` 的 `_mpc_cmd_pub.publish(...)`
- `zenoh_json_bridge_node.py` 在 shutdown window 的 `wait set context invalid`

针对上述节点补充 shutdown 护栏后，复跑同一缺磁场景：

```bash
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --auto-activate \
  --duration 20 \
  --no-record-bag \
  --skip-layout \
  --launcher-output log \
  --enable-mock-forward-sonar-wrapper \
  --disable-bridge-magnetic-side-channel \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_mission_type:=CABLE_INSPECTION
```

运行目录：

```text
/auv_data/bags/20260717_184633
```

关键结果：

```text
[INFO] [cable_mission_autostart_node-9]: process has finished cleanly
[INFO] [forward_sonar_wrapper_node-5]: process has finished cleanly
[INFO] [sensor_supervisor_node-4]: process has finished cleanly
[INFO] [auv_localization_node-2]: process has finished cleanly
[INFO] [decision_node-7]: process has finished cleanly
[INFO] [cable_tracking_node-8]: process has finished cleanly
[INFO] [zenoh_viz_bridge_node-3]: process has finished cleanly
[INFO] [zenoh_json_bridge_node-1]: process has finished cleanly
[INFO] [auv_controller_node-6]: process has finished cleanly
```

本轮结论：

- “真缺磁”的 `cable_inspection` capability gate 已有运行期证据；
- 同一场景下，bridge / controller / cable tracking / viz / autostart 现已全部 clean exit；
- 当前 capability gate 的两条关键降级分支
  （`terrain_following <- forward_sonar`、`cable_inspection <- magnetic`）
  都已经具备可复验的运行记录。

### 3.14 bridge magnetic side-channel 覆盖入口

为避免每次手工准备 `/tmp/params.protocol_udp_arbiter.nomag.yaml`，现已把该做法整理成
 `start_experiment.sh` 的底层参数覆盖 CLI：

- `--disable-bridge-magnetic-side-channel`
  - 自动把 `bridge.magnetic_key` 改为 `rt/auv/sensors/magnetic_disabled`
  - 自动在当前 run 目录下生成 per-run brain 参数文件
- `--brain-magnetic-key KEY`
  - 允许高级用户手工指定任意 `bridge.magnetic_key`
  - 仍然走同一套 per-run brain params 生成逻辑

使用该覆盖入口的回归命令：

```bash
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --auto-activate \
  --duration 20 \
  --no-record-bag \
  --skip-layout \
  --launcher-output log \
  --enable-mock-forward-sonar-wrapper \
  --inject-missing-magnetic \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_mission_type:=CABLE_INSPECTION
```

运行目录：

```text
/auv_data/bags/20260717_185431
```

入口层关键证据：

```text
[AUV] brain magnetic_key override: rt/auv/sensors/magnetic_disabled
[AUV] generated per-run brain params: /auv_data/bags/20260717_185431/brain_params.magnetic_key_override.yaml
[bridge] protocol_udp side-channel subscribed magnetic_key=rt/auv/sensors/magnetic_disabled
```

该 run 自动生成的参数文件内容可验证为：

```yaml
bridge:
  magnetic_key: rt/auv/sensors/magnetic_disabled
```

同时该 run 已 clean exit：

```text
[INFO] [cable_mission_autostart_node-9]: process has finished cleanly
[INFO] [forward_sonar_wrapper_node-5]: process has finished cleanly
[INFO] [sensor_supervisor_node-4]: process has finished cleanly
[INFO] [auv_localization_node-2]: process has finished cleanly
[INFO] [cable_tracking_node-8]: process has finished cleanly
[INFO] [decision_node-7]: process has finished cleanly
[INFO] [zenoh_viz_bridge_node-3]: process has finished cleanly
[INFO] [auv_controller_node-6]: process has finished cleanly
[INFO] [zenoh_json_bridge_node-1]: process has finished cleanly
```

### 3.15 成对 capability fault 注入入口

为让两条 capability gate 都不再依赖“是否恰好没启动 mock wrapper”，新增成对的正式
实验开关：

- `--inject-missing-magnetic`
  - bridge side-channel 改订阅 `rt/auv/sensors/magnetic_disabled`
  - per-run `sensor_supervisor` 配置把 `magnetic` watch 改为
    `/auv/sensors/magnetic_fault_disabled`
  - 拒绝与 mock 或 real magnetic wrapper 同时使用
- `--inject-missing-forward-sonar`
  - per-run `sensor_supervisor` 配置把 `forward_sonar` watch 改为
    `/auv/sensors/forward_sonar_fault_disabled`
  - 拒绝与 mock forward sonar wrapper 同时使用

两个 fault 也可以同时指定。每次执行均在 run 目录保留生成后的 YAML，并在
`metadata.txt` 记录 `inject_missing_magnetic`、`inject_missing_forward_sonar` 和生成文件路径。

缺 forward sonar 正式回归命令：

```bash
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --auto-activate \
  --duration 25 \
  --no-record-bag \
  --skip-layout \
  --launcher-output log \
  --inject-missing-forward-sonar
```

运行目录：

```text
/auv_data/bags/20260717_185925
```

关键证据：

```text
[AUV] capability fault injection: missing_magnetic=false missing_forward_sonar=true
[capability_gate] terrain following disabled, missing=['forward_sonar']; publishing zero-effort hold
[INFO] [auv_controller_node-5]: process has finished cleanly
```

缺 magnetic 正式回归命令：

```bash
AUV_SKIP_BRAIN_BUILD=1 bash scripts/start_experiment.sh \
  --sim-backend pvs \
  --bridge-backend protocol_udp \
  --arbiter-profile \
  --auto-activate \
  --duration 30 \
  --no-record-bag \
  --skip-layout \
  --launcher-output log \
  --enable-mock-forward-sonar-wrapper \
  --inject-missing-magnetic \
  --brain-arg enable_cable_tracking:=true \
  --brain-arg enable_cable_mission_autostart:=true \
  --brain-arg cable_mission_type:=CABLE_INSPECTION
```

运行目录：

```text
/auv_data/bags/20260717_190116
```

关键证据：

```text
[AUV] capability fault injection: missing_magnetic=true missing_forward_sonar=false
[mission_command] reject mission_type=CABLE_INSPECTION capability=cable_inspection missing=['magnetic']
cable tracking degraded by sensor gate reason=magnetic_unavailable_inspection_blocked
[INFO] [cable_tracking_node-8]: process has finished cleanly
```

这里保留的 `--brain-arg` 只用于开启 cable mission 流程；能力缺失本身已经完全由正式
fault CLI 注入，不再需要手工指定 `params_file` 或 `sensor_supervisor_config`。

## 4. 当前结论

- PC104 物理连接不影响本仿真链路，前提是 PC104 fanout/GUI relay 等旧进程已停止。
- `rt/pc/cmd_raw` side-channel 可稳定驱动 `AutonomyGuard`。
- `protocol_udp` 二进制下行已进入 PVS/mock AMD，`0xEE/0xEE` 为自主控制态的预期字段。
- ESTOP/manual override 注入可立即使 bridge 强制 REMOTE，行为树退回 `StandbyCheck`，
  下行包字段为 `0x01/0x02` 且执行器全零。
- ESTOP 锁存语义已修复并完成 runtime 复验；若 `auto_activate` 继续发布 `0xEE`，
  bridge 会持续拒绝重新激活，行为树保持 `StandbyCheck`。
- `CLEAR_FAULT(0x91)` 解锁路径已完成 runtime 复验；清锁后下一轮 `0xEE`
  可重新授权自主模式，行为树回到 `ZigZagSearch`。
- mock magnetic / mock forward sonar 已接入 `auv_stack.launch.py`，并可由
  `start_experiment.sh --enable-mock-magnetic-wrapper --enable-mock-forward-sonar-wrapper`
  直接从顶层实验命令拉起。
- `auto_activate + mock wrapper + capability gate` 已完成 75s 运行态复验，行为树可稳定进入
  `ZIGZAG_SEARCH`，控制链可进入 `TERRAIN_FOLLOWING`。
- 当 `forward_sonar` 缺失时，`auv_controller_node.py` 会明确打印
  `[capability_gate] terrain following disabled, missing=['forward_sonar']`，
  并转入 `zero-effort hold`，说明 `terrain_following` capability gate 已在运行态生效。
- 当 `magnetic` 缺失时，`decision_node.py` 会拒绝 `CABLE_INSPECTION` 任务注入，
  同时 `cable_tracking_node.py` 会进入
  `magnetic_unavailable_inspection_blocked` 的降级态，说明
  `cable_inspection` capability gate 也已在运行态生效。
- 缺 `magnetic` 与缺 `forward_sonar` 均已有成对的正式 fault CLI，可在 run metadata 和
  per-run 参数文件中审计注入语义，不再依赖手工 `/tmp` 配置。
- 新增 `sensor_supervisor` / mock wrapper 节点的停机退出噪声已收口，现已能 clean exit。
- 主栈 `decision/controller/localization/bridge/viz` 节点的停机退出噪声也已收口；
  当前 quick smoke 已可做到整栈 clean exit。
- 30s smoke 太短，brain 启动、Mock AMD time fallback、任务进入后很快触发外层停止，容易把 shutdown 日志误判为运行期 PC link 异常。

## 5. 下一步

- 后续仿真 smoke 建议使用 `--duration >= 70`。
- 若要记录 rosbag 或 Foxglove 验证，应在任务进入 `ZIGZAG_SEARCH` 后至少保留 30s 运行窗口。
- ESTOP/manual override 语义已收口；后续可转入 rosbag/Foxglove 可视化记录或更完整任务状态机验证。
