# 实物部署 Telnet 调试坑记录

日期: 2026-07-11
场景: 真实 PC104 + VxWorks, 多数传感器未接入的空板 HIL

## 1. 当前网络拓扑结论

容器内网络为 Docker bridge:

```text
container ip: 172.18.0.2
docker gateway: 172.18.0.1
PC104/VxWorks: 192.168.0.101
```

容器访问 PC104 的方向是:

```text
container -> docker gateway/host -> 192.168.0.101
```

这意味着容器主动连 Telnet、主动向 VxWorks 发 UDP 通常可行；但 VxWorks 主动回包到宿主机后，是否能进容器，取决于宿主机路由、Docker UDP 端口映射、VxWorks 目标 IP/端口三者是否一致。

## 2. Telnet 登录方式

当前 Telnet 可用:

```text
host: 192.168.0.101
port: 23
user: target
password: password
prompt: ->
```

脚本已支持:

```bash
python3 scripts/vxworks_safety_hil.py \
  --mode telnet \
  --host 192.168.0.101 \
  --telnet-user target \
  --telnet-password password \
  --uplink-port 21 \
  --log-port 52367
```

## 3. 已踩坑

### 3.1 宿主机路由 Loop

现象:

```text
容器可 connect UDP/21, Telnet 有时可连, 但 $AUV/UdpLogger 回流收不到。
```

处理:

用户修复宿主机路由 Loop 后，Telnet 恢复可用。但 UDP 回流仍未在容器内收到，后续还需单独检查 VxWorks 的回传目标 IP/端口与 compose 映射。

### 3.2 容器内 UDP 回流未闭环，宿主机直跑已闭环

当前 compose 映射:

```yaml
- "21:21/udp"
- "52367:52367/udp"
- "52366:52366/udp"
```

脚本已将默认 `$AUV` 上行监听端口改为 `21/udp`，但实测:

```text
auto-udp: 0/5 pass
上行帧: 未收到
UdpLogger: 未收到
```

这不影响 Telnet 注入验证核心逻辑，但会影响自动化脚本对 `$AUV` 状态帧的判定。

后续用户在宿主机直接运行 UDP 自动验证，已确认:

```text
上行 $AUV: PASS
UdpLogger: PASS
心跳保活: PASS
```

因此该问题当前应理解为:

```text
PC104 -> 宿主机 UDP 回流可达。
PC104 -> Docker 容器 UDP 回流未稳定打通。
```

接手时建议优先在非容器 Linux 或真实 Jetson 上验证 UDP/ROS2/Console 链路，不要用容器内 UDP 结果否定 PC104 回包能力。

### 3.3 VxWorks shell 不可靠支持结构体字段

以下形式在当前 shell 中会失败:

```c
Current_State.Current_Mode
UI_WIFI_Instruction.FromUI12_Ctrl_Mode
Instruction_To_FMCU.McuFD_Motor1_Set_Speed
```

表现:

```text
C interp: syntax error
unknown symbol name
```

稳定做法:

```c
lkup "Current_State"
lkup "UI_WIFI"
lkup "Instruction_To_FMCU"
```

然后用绝对地址 + 偏移读写。

### 3.4 VxWorks shell 对 float 赋值/printf 有坑

这些形式不可靠:

```c
*(float*)addr = 10.0
printf("%.3f\n", *(float*)addr)
```

实测出现:

```text
value = 10
但内存位模式仍为 0x00000000
C interp: cannot use a floating point values as a function argument
```

稳定做法是写 IEEE754 位模式:

```c
*(unsigned int*)addr = 0x41200000  /* 10.0f */
*(unsigned int*)addr = 0x3f800000  /* 1.0f */
*(unsigned int*)addr = 0x40000000  /* 2.0f */
```

### 3.5 Shell 命令行长度限制

长 `printf(...)` 会被截断，导致:

```text
C interp: syntax error
unknown symbol name 'un'
```

稳定做法:

- 一次只读 1-3 个字段
- 避免超长格式串
- 不要在一条命令里展开大量地址表达式

### 3.6 `Symbol + offset` 形式可能触发 Page Fault

危险形式:

```c
*(unsigned short*)(UI_WIFI_Instruction+8)=5
*(unsigned short*)(Data_From_FMCU+32)=10000
```

实测触发 shell task Page Fault，但系统主任务可继续运行，shell task 会自动重启。

稳定做法:

```c
*(unsigned short*)0x5369e8 = 5
```

也就是先 `lkup` 得到基址，再在脚本侧算好绝对地址。

### 3.7 主控任务会覆盖注入快照

`MainCtrlTask` 会持续刷新 `Current_State`，所以直接写 `Current_State` 后，值可能在下一条 shell 命令前被覆盖。

稳定做法:

```c
taskSuspend(taskNameToId("MainCtrlTask"))
/* 注入快照并 semGive */
taskResume(taskNameToId("MainCtrlTask"))
```

注意: 只在空板 HIL 或执行机构断开的安全条件下使用。

## 4. 当前实物内存偏移经验

本轮实测偏移，不保证换编译器/结构体后仍然一致:

```text
Current_State base:       0x00536a40
Current_Dep:              Current_State + 0x34

UI_WIFI_Instruction base: 0x005369e0
Ctrl_Mode:                +0x07
Depth_Para1:              +0x08
Motor_Speed1:             +0x18 (运行时写入验证点)
RCD_LH_Set_Rud_Angle:     +0x1c
RCD_RH_Set_Rud_Angle:     +0x1e
Para1:                    +0x28

DVL_Prase_Data base:      0x00536cc0
BD_Height:                +0x18
BD_Check:                 +0x20

Instruction_To_FMCU base: 0x00536c40
observed rudder mids:     +0x20/+0x22/+0x24/+0x26
```

## 5. 后续建议

1. 如果继续做 Telnet 自动化，脚本必须使用 `lkup + 绝对地址`，不要依赖结构体字段名。
2. 如果要恢复容器内 UDP 自动化闭环，需要确认 VxWorks 上位机目标 IP 是否是宿主机 `192.168.0.11`，目标端口是否与 compose 映射一致；若在非容器 Linux 上接手，则优先直接绑定端口验证。
3. 实物接执行机构前，任何 `taskSuspend(MainCtrlTask)`、`semGive(semEmergencyTask)` 类测试都必须确认电机/舵机物理断开或处于安全架台。

## 6. 推荐 Telnet 操作模板

后续 Probe 建议固定为三段式，不再临场手写复杂表达式:

```text
1. lkup "TargetSymbol"
2. 在容器/脚本侧计算绝对地址
3. VxWorks shell 只执行短的绝对地址读写命令
```

示例:

```c
lkup "Current_State"
*(unsigned int*)0x00536a74 = 0x41200000
semGive(semEmergencyTask)
*(unsigned int*)0x00536a74
```

其中 `0x41200000` 是 `10.0f` 的 IEEE754 位模式。不要在 shell 中写:

```c
*(float*)0x00536a74 = 10.0
```

也不要写:

```c
*(unsigned int*)(Current_State+0x34) = 0x41200000
```

原因是当前实测 shell 对 float 表达式和 `Symbol + offset` 都不稳定。

## 7. BUG-4 复测时的 Telnet 注意事项

BUG-4 的目标不是单纯让 `Sys_Abnorm_Inf_Judgement` Bit9 置位，而是验证最终执行命令链路闭环:

```text
Depth 超限 -> EmergencyTask -> Remote_Assignment -> Instruction_To_FMCU/to_MCU_buf
```

因此复测时至少要同时观察:

```text
Sys_Abnorm_Inf_Judgement & 0x00000200 != 0
to_MCU_buf 或 Instruction_To_FMCU 中 Motor1 == 300
LH/RH 舵角约为 2275/1821
```

如果只看到 Bit9 置位，但 `$MCUFD` 最终帧仍是:

```text
...,00000,00000,2275,1821,...
```

则说明安全状态位有效，但应急执行命令没有真正闭环，不能判定 BUG-4 通过。
