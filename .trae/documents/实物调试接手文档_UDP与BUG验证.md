# 实物调试接手文档: UDP 直连与深度安全 BUG 验证

日期: 2026-07-11
适用场景: 在非容器 Linux 环境重新克隆仓库后，继续接手 PC104/VxWorks 空板 HIL 与 Jetson 实物部署验证。

## 1. 本文定位

本文是接手用的自包含说明，承接 `.trae/documents/AUV_调试SOP_全阶段指南.md` 的阶段 2/阶段 3 调试流程，但不替代该 SOP。

当前调试已经发现两个事实:

1. 宿主机直接运行 UDP 验证脚本时，`$AUV` 上行帧和 `UdpLogger` 均可收到，说明 PC104 的 UDP 回流在宿主机层面可达。
2. 容器内 UDP 回流不稳定或不可达，导致容器环境不能完整代表真实 Jetson/宿主机直连网络。

因此后续应在非容器 Linux 环境完成 UDP/ROS2/Console 端到端验证，容器内结果只作为代码分析和 Telnet 辅助，不作为最终部署结论。

## 2. 当前已知状态

### 2.1 PC104/VxWorks 侧

```text
PC104 IP:        192.168.0.101
Telnet:          23/tcp, target/password
当前烧录镜像:    已包含 BUG-3/5/6 修复和 Jetson lost 降级逻辑
当前 BUG-4 状态: 板上镜像仍是第一版 BUG-4 修复，运行时未闭环
```

符号表已确认存在:

```text
Not_Recv_From_Jetson_No
Seafloor_Grounding_Arbitration
```

符号表未出现:

```text
Pool_Safety_Check
```

解释: 当前镜像为 `POOL_TEST_MODE=0` 海试模式，水池模式未编译进镜像。

### 2.2 宿主机 UDP 验证结果

用户在宿主机运行自动 UDP 验证，结果为:

```text
上行帧接收: PASS, CtrlMode=0x00, Depth=0.0m
UdpLogger 日志: PASS, 收到 EmergencyTask 打印
心跳保活: PASS, Bit14=0, CtrlMode=0x01
Jetson 失联 Bit14: FAIL, Sys=0x00000000
Sys_Abnorm 回传: PASS, Sys=0x00000000
```

结论:

1. UDP 回流在宿主机层面已经闭环。
2. Jetson lost 的模式降级/停机需要 Telnet 再核查；Bit14 当前不能作为已通过项。
3. 容器内收不到 UDP 更像是 Docker 端口映射、监听端口、目标 IP 或宿主机已有监听进程造成的部署拓扑问题。

## 3. 当前因为容器 UDP 直连缺失，不能在容器里验证什么

以下项目不能仅凭容器内结果钉结论:

| 项目 | 为什么容器内不能定论 | 接手后验证环境 |
|---|---|---|
| `$AUV` 上行稳定性 | VxWorks 回包目标通常是宿主机 LAN IP，Docker UDP publish 可能未覆盖实际端口 | 非容器 Linux 直接绑定监听端口 |
| UdpLogger 回流 | 容器端口映射与 VxWorks 日志目标端口可能不一致 | 非容器 Linux 监听 `52367/udp` |
| Jetson Bridge 收到遥测 | 容器未稳定收到 `$AUV`，无法判断 Bridge freshness | 非容器 ROS2/Jetson 环境 |
| Console 顶部报文编号递增 | 容器不代表 GUI/Jetson 所在网络命名空间 | 非容器 Console 或 Jetson |
| 0xEE/0xEF 实物链路 | 需要真实 UDP 双向和 Jetson/Console 仲裁状态 | 非容器阶段 2 台架 |
| AMD_UPLINK_STALE 消除 | 容器内 UDP 回流缺失会制造假 stale | 非容器直连环境 |
| Jetson lost 状态位 Bit14 | UDP 可见 Sys=0，但需 Telnet 同步读内部变量排除清位/瞬时置位 | 非容器 UDP + Telnet 双证据 |

## 4. 接手后第一轮验证顺序

### 4.1 网络与 UDP 基线

在非容器 Linux 中:

```bash
ping 192.168.0.101
python3 scripts/vxworks_safety_hil.py \
  --mode auto-udp \
  --host 192.168.0.101 \
  --uplink-port 21 \
  --log-port 52367
```

成功标准:

```text
上行帧接收: PASS
UdpLogger 日志: PASS
心跳保活: PASS
Sys_Abnorm 回传: PASS
```

注意:

`.trae/documents/AUV_调试SOP_全阶段指南.md` 中阶段 2 使用的是标准 `52364/52365` 叙述；本轮 PC104 HIL 已实测需要按当前固件/端口映射使用 VxWorks UDP `21`。接手时应以实测端口为准，并记录最终端口配置。

### 4.2 Telnet 基线

```bash
python3 scripts/vxworks_bug4_runtime_probe.py \
  --host 192.168.0.101
```

不带 `--execute` 时只读符号和当前状态，不会写内存。

成功标准:

```text
能登录 target/password
能 lkup 到 Current_State, UI_WIFI_Instruction, Instruction_To_FMCU, Sys_Abnorm_Inf_Judgement, to_MCU_buf
能打印 BASELINE 状态
```

### 4.3 BUG-4 未重烧录状态下继续 Probe

当前暂不烧录时，执行:

```bash
python3 scripts/vxworks_bug4_runtime_probe.py \
  --host 192.168.0.101 \
  --execute \
  --probe both
```

这个 Probe 分两段:

1. `trigger-bug4`: 注入深度超限并触发 `EmergencyTask`，观察当前未修复镜像是否仍出现 Bit9 置位但最终 Motor1 为 0。
2. `shadow-override`: 运行时手动写 `UI_WIFI_Instruction` shadow 为 `Motor1=300, LH/RH=-20`，再调用 `Remote_Assignment(&Instruction_To_FMCU)`，验证最终 `$MCUFD` 是否能变为 `00300`。

成功/失败判定:

```text
trigger-bug4 后:
  Sys & 0x00000200 != 0 且 TOBUF 含 00000 => 复现当前 BUG-4 未闭环。

shadow-override 后:
  TOBUF 含 00300 且 LH/RH 约 2275/1821 => 证明后版源码补写 UI shadow 的方向正确。

shadow-override 后仍无 00300:
  说明 UI shadow 偏移、UI_Channel_Selection_Down 或 Remote_Assignment 覆盖链路仍有未解释因素。
```

安全要求:

```text
仅在空板 HIL、执行机构断开、主推电源未接通时使用 --execute。
```

### 4.4 Jetson lost 复核

当前 UDP 输出显示:

```text
Jetson 失联 Bit14: FAIL, Sys=0x00000000
```

接手后应补充 Telnet 同步观测:

```text
Not_Recv_From_Jetson_No
UI_WIFI_Instruction.FromUI12_Ctrl_Mode
UI_WIFI_Instruction.FromUI12_Motor_Speed1
UI_WIFI_Instruction.FromUI12_Motor_Speed2
Sys_Abnorm_Inf_Judgement
```

成功标准分层:

```text
最低安全通过:
  Jetson 停发后 Ctrl_Mode -> 0x01, Motor1/Motor2 -> 0。

可观测性通过:
  Sys_Abnorm_Inf_Judgement Bit14 能稳定保持，直到收到有效 Jetson 包后清除。
```

当前状态应记为:

```text
Jetson lost: partial pass
原因: UDP 已见 Bit14 不保持；降级/停机动作需 Telnet 再证实。
```

## 5. 重烧录后必须复测的项目

当包含后版 BUG-4 runtime fix 的 VxWorks 镜像重新编译并烧录后，必须复测:

```text
BUG-4: Depth 超限后最终 $MCUFD 包含 Motor1=00300, LH/RH≈2275/1821, Sys Bit9 置位。
BUG-3: 深度计数器递增后可递减归零。
BUG-5: DVL 软/硬离底状态位，干净启动后分别确认 Bit11/Bit12。
BUG-6: DVL 丢底后 Bit13 置位且 Ctrl_Mode 降级到 0x01。
Jetson lost: 降级/停机动作 + Bit14 可观测性。
```

BUG-4 重烧录后成功标准:

```text
Sys_Abnorm_Inf_Judgement & 0x00000200 != 0
to_MCU_buf 包含 ",00300,"
LH/RH 字段约为 2275/1821
```

如果重烧录后仍然失败，应转入源码级 emergency override 设计，不再只补 `Instruction_To_FMCU`。

## 6. Jetson/Console 实物部署接手标准

参考 `.trae/documents/AUV_调试SOP_全阶段指南.md` 阶段 2，接手后 Jetson/Console 侧需要确认:

| 验证项 | 成功标准 |
|---|---|
| Console/Bridge 上行 | 报文编号持续递增，Bridge 日志出现有效 `$AUV` frame |
| 下行 `$CKTH` | PC104 侧 `Not_Recv_From_Jetson_No` 被持续清零 |
| 0xEE 模式 | PC104 进入 Jetson shadow 路径，舵面/推力命令有可解释输出 |
| 0xEF 模式 | PC104 进入透传路径，`Remote_Assignment()` 最终帧与下行命令一致 |
| 遥测新鲜度 | Jetson 不再报 `AMD_UPLINK_STALE` |
| 失联降级 | 停止 Jetson 下行后，PC104 降级到 0x01 并停机 |

阶段 2 仍应保持:

```text
禁止接通主推电源
准备物理急停
只验证通信、状态机和舵面/推力命令链路
```

## 7. 建议接手记录格式

每次 Probe 建议记录:

```text
日期/操作者:
运行环境: 宿主机 Linux / Jetson / 容器
PC104 固件版本或烧录时间:
执行命令:
关键输出:
判定:
下一步:
```

不要只记录 PASS/FAIL。对安全项必须同时记录:

```text
状态位是否置位
模式是否降级
最终执行命令是否改变
是否需要源码修改
是否影响接执行机构/下水风险
```
