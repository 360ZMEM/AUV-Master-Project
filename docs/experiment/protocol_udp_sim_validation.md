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
- 30s smoke 太短，brain 启动、Mock AMD time fallback、任务进入后很快触发外层停止，容易把 shutdown 日志误判为运行期 PC link 异常。

## 5. 下一步

- 后续仿真 smoke 建议使用 `--duration >= 70`。
- 若要记录 rosbag 或 Foxglove 验证，应在任务进入 `ZIGZAG_SEARCH` 后至少保留 30s 运行窗口。
- ESTOP/manual override 语义已收口；后续可转入 rosbag/Foxglove 可视化记录或更完整任务状态机验证。
