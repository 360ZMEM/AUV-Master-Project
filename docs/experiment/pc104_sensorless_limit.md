# PC104 空板实机极限验证

> 日期: 2026-07-16
> 目标: 在当前 PC104 无外接传感器条件下，确认实机还能可靠验证到哪一层，并判断是否应转入 `Zenoh + protocol_udp` 仿真做高层任务全覆盖。

---

## 1. 结论

当前 PC104 实机已经验证到空板条件下的可达上限。

可以继续信任的实机能力:

- PC104 基础网络在线，`192.168.0.101` 可达。
- UDP 上行 `$AUV` 可进入容器，状态回传稳定。
- UdpLogger 可收到 `EmergencyTask` 打印。
- 5 秒心跳保活通过，遥控模式下 Bit14 不误触发。
- `Sys_Abnorm=0x00002000` 稳定回传，符合空板无 DVL 锁底的 Bit13 预期。
- Telnet 可读 VxWorks 符号和关键内存。
- fan-out 可在 Docker Desktop/macOS 转发拓扑下接受 `172.18.0.1` 上行源，同时下行仍发往真实 PC104。
- 零执行器 `$CKTH` 可经 fan-out 进入 PC104，且 PC104 内部 `UI_WIFI_Instruction` 可观测到。

当前不能在这块 PC104 空板上继续实证的能力:

- 真实 DVL 锁底、离底高度、速度质量。
- 真实深度、姿态、IMU、导航闭环。
- 依赖传感器反馈的高层任务闭环。
- 非零执行器实物动作。
- 未烧录 Bit14 补丁后的 Jetson 失联告警保持。

因此，PC104 实机支线目前应收口为 **低层通信、安全状态和零执行器链路已验证**。下一步高层任务全方位验证应转入 `Zenoh + protocol_udp` 仿真环境。

---

## 2. 实测摘要

### 2.1 UDP 自动验证

命令:

```bash
python3 scripts/vxworks_safety_hil.py \
  --mode auto-udp \
  --host 192.168.0.101 \
  --bind 0.0.0.0 \
  --uplink-port 21 \
  --log-port 52367
```

结果:

```text
结果: 4/5 通过
✓ 上行帧接收: CtrlMode=0x01, Depth=0.0m
✓ UdpLogger 日志: 收到 4 条 EmergencyTask 打印
✓ 心跳保活: Bit14=0, CtrlMode=0x01
✗ Jetson 失联 Bit14: Bit14 未置位! Sys=0x00002000
✓ Sys_Abnorm 回传: Sys=0x00002000, Bit13 DVL丢底降级
```

判定:

- UDP 链路、日志链路和状态回传通过。
- Bit14 失败不是 UDP 问题，而是当前 PC104 尚未烧录 `SecurityEmergencyManage.c` 中的 Bit14 latch 补丁。

证据:

```text
docs/experiment/assets/pc104_sensorless_limit/auto_udp_4of5_bit14_expected_fail.log
```

### 2.2 Telnet DVL 空板 baseline

命令:

```bash
python3 scripts/vxworks_dvl_runtime_probe.py \
  --host 192.168.0.101 \
  --user target \
  --password password
```

结果:

```text
Sys_Abnorm=0x00002000
DVL: BD_Check=0.000 BD_Height=0.000
Current_State: mode=1 work=0x00 dep=0.000 pitch=0.000 dvl_kn=0.000
UI_WIFI: ctrl=1 para1=500 work=0x00
Instruction_To_FMCU: motor1=0 lh=2048 rh=2048
```

判定:

- 当前 Bit13 是空板无 DVL 锁底的预期状态。
- DVL 真实软限、硬限、丢底仲裁无法靠当前硬件自然触发；只能通过 Telnet 注入验证状态机逻辑。

证据:

```text
docs/experiment/assets/pc104_sensorless_limit/telnet_dvl_baseline_dryrun.log
```

### 2.3 fan-out 零执行器实机短测

fan-out 启动参数关键点:

```text
--listen-host 0.0.0.0
--pc104-remote-host 192.168.0.101
--accept-uplink-source 172.18.0.1
--cmd-host 127.0.0.1
--cmd-port 52364
--subscriber pyside6=127.0.0.1:52366
```

controller 摘要:

```text
[real-fanout] zero CKTH len=72 head=b'$CKTH\x02\x01\x01'
[real-fanout] recv $AUV #1 from=127.0.0.1:21 len=145 sys=0x00002000
[real-fanout] sent zero CKTH #1
[real-fanout] sent zero CKTH #2
[real-fanout] sent zero CKTH #3
[real-fanout] summary sent_zero_ckth=3 recv_uplink=91
```

fan-out 摘要:

```text
[fanout] accepted uplink sources: 172.18.0.1, 192.168.0.101
[fanout] forward pyside6 -> PC104: obj=1 ctrl=1 work=0 depth=(500, 29) bottom=(300, 200) preset=0 motor=0/0 fins=(0.0,0.0,0.0,0.0)
[fanout] status uplink=93 downlink=3 blocked=0
```

判定:

- Docker Desktop/macOS publish 场景下，容器内上行源地址为 Docker 网关的问题已由 `--accept-uplink-source 172.18.0.1` 覆盖。
- 下行仍发往真实 PC104 `192.168.0.101:21`。
- 3 个零执行器 `$CKTH` 均被转发，未触发阻断。

证据:

```text
docs/experiment/assets/pc104_sensorless_limit/fanout_zero_real_pc104_controller.log
docs/experiment/assets/pc104_sensorless_limit/fanout_zero_real_pc104.log
```

### 2.4 Telnet 确认零执行器下行进入 PC104

命令:

```bash
python3 scripts/vxworks_bug4_runtime_probe.py \
  --host 192.168.0.101 \
  --user target \
  --password password
```

结果:

```text
Sys_Abnorm=0x00002000  DepthExceed=0
UI_WIFI shadow: ctrl=1 depth_para1=500 work_cmd=0x00 motor1=0 lh_angle=0 rh_angle=0
TOBUF=$MCUFD,035,020101,012716,00,00,00,DZ,00000,00000,2048,2048,2048,2048,00,*RN*RN
判定: final frame still contains Motor1=00000
```

判定:

- PC104 内部已接收零执行器下行字段。
- 最终 MCU 下行缓存仍为零主推、零侧推、舵角中位，符合安全边界。

证据:

```text
docs/experiment/assets/pc104_sensorless_limit/telnet_bug4_baseline_after_zero_fanout.log
```

### 2.5 GUI 执行器/ESTOP 按钮字段验证

本轮在 Xvfb 中启动 PySide6 GUI，使用真实按钮信号路径触发:

- `扩展控制... -> 主推上电 (0x11)`
- `紧急切断 ESTOP`

fan-out 继续保持零执行器门控:

```text
allow_nonzero_actuator=False
```

fan-out 摘要:

```text
[fanout] forward pyside6 -> PC104: obj=1 ctrl=1 work=17 depth=(500, 29) bottom=(300, 200) preset=10 motor=0/0 fins=(0.0,0.0,0.0,0.0)
[fanout] forward pyside6 -> PC104: obj=1 ctrl=1 work=2 depth=(500, 29) bottom=(300, 200) preset=10 motor=0/0 fins=(0.0,0.0,0.0,0.0)
[fanout] status uplink=188 downlink=9 blocked=0
```

`主推上电 (0x11)` 后 Telnet 读数:

```text
Sys_Abnorm=0x00002000  DepthExceed=0
UI_WIFI shadow: ctrl=1 depth_para1=500 work_cmd=0x11 motor1=0 lh_angle=0 rh_angle=0
```

`ESTOP` 后 Telnet 读数:

```text
Sys_Abnorm=0x00002000  DepthExceed=0
UI_WIFI shadow: ctrl=1 depth_para1=500 work_cmd=0x02 motor1=0 lh_angle=0 rh_angle=0
TOBUF=$MCUFD,002,020101,012716,00,00,00,DZ,00000,00000,2048,2048,2048,2048,01,*RN*RN
判定: final frame still contains Motor1=00000
```

判定:

- GUI 执行器按钮能正确改变 PC104 的 `UI_WIFI_Instruction.work_cmd=0x11`。
- GUI `ESTOP` 能正确改变 PC104 的 `UI_WIFI_Instruction.work_cmd=0x02`。
- 两类按钮路径均保持 `ctrl=1`、`motor1=0`、舵角为 0 或中位，符合空板安全边界。
- fan-out 没有转发任何非零执行器包。

证据:

```text
docs/experiment/assets/pc104_button_field_check/fanout_button_field_check.log
docs/experiment/assets/pc104_button_field_check/gui_main_thruster_on.log
docs/experiment/assets/pc104_button_field_check/gui_estop.log
docs/experiment/assets/pc104_button_field_check/telnet_after_main_thruster_on.log
docs/experiment/assets/pc104_button_field_check/telnet_after_estop.log
docs/experiment/assets/pc104_button_field_check/console_pc104_button_check.yaml
```

---

## 3. 未收口项

### 3.1 Bit14 补丁未烧录

源码侧已修改 `csd_vx6.8_lastest/SecurityEmergencyManage.c`，但当前 PC104 运行镜像尚未重编译/烧录，因此 `auto-udp` 中 Jetson 失联 Bit14 仍失败。

状态:

```text
未收口，但不阻塞高层仿真验证。
```

后续收口条件:

- 用户在 VxWorks 构建环境中应用当前 `git diff`。
- 重编译并烧录 PC104。
- 重新运行 `vxworks_safety_hil.py --mode auto-udp`。
- 期望 `Jetson 失联 Bit14` 从 FAIL 变为 PASS。

### 3.2 真实传感器闭环不可验证

当前 PC104 没有 DVL、深度、IMU 等真实传感器输入，因此无法在实机上自然复现:

- DVL 有效锁底。
- DVL 离底 soft/hard 阈值。
- 深度超限真实触发。
- 导航、控制和任务闭环。

状态:

```text
硬件条件阻塞。
```

替代方案:

- 低层状态机可继续通过 Telnet 注入验证。
- 高层任务闭环应转入 `Zenoh + protocol_udp` 仿真。

### 3.3 非零执行器链路未验证

本轮只允许零执行器 `$CKTH`。未验证:

- 非零主推。
- 非零侧推。
- 非零舵角。
- GUI 按钮导致的任务下发、ESTOP、自主授权。

状态:

```text
安全边界内主动不测。
```

---

## 4. 下一步建议

建议转入 `Zenoh + protocol_udp` 仿真做高层任务全方位验证。

理由:

- PC104 空板实机已经证明底层 UDP、Telnet、fan-out、零执行器链路和状态回传可用。
- 当前剩余高层问题需要稳定传感器输入，而实机硬件不具备。
- `protocol_udp` 可以继续使用真实 `$CKTH/$AUV` 二进制协议边界。
- Zenoh 可以覆盖 side channel、任务语义、arbiter 状态、可视化和遥测融合。

推荐下一阶段验证范围:

- `protocol_udp` backend 的 `$CKTH/$AUV` 编解码一致性。
- Zenoh `rt/pc/cmd_raw`、`rt/auv/telemetry`、`rt/auv/viz/internal` 通道。
- 自主授权、手动接管、ESTOP、任务下发状态机。
- PVS/HoloOcean 传感器闭环下的电缆巡检任务。
- Foxglove/GUI 对高层状态的实时显示。

PC104 实机支线后续只保留为:

- VxWorks Bit14 补丁烧录后的回归测试。
- 传感器/执行器接回后的实物闭环测试。
- 必要时的 Telnet 运行期状态机复核。
