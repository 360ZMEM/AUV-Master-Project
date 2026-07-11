# PC104 空板实物 Telnet 优先全链路调试计划

> 目标对象: 真实 PC104 / VxWorks 空板 HIL  
> 当前阶段: 先把 Telnet 注入和观测闭环调通，再进入 UDP、ROS2、上位机和字段契约全链路  
> 安全边界: 无传感器、无执行机构或执行机构物理断开时执行；任何会写内存、触发任务、下发推力的步骤都按空板 HIL 处理  

## 1. 本文定位

本文接续以下交接材料，形成新的执行计划:

- `.trae/documents/实物调试接手文档_UDP与BUG验证.md`
- `.trae/documents/实物部署_Telnet调试坑记录.md`
- `.trae/documents/深度安全BUG实物HIL状态机验证记录.md`
- `.trae/documents/深度安全_空板HIL验证SOP.md`
- `.trae/documents/VxWorks_重构修改日志.md`
- `.trae/documents/VxWorks_Diff_Report.md`

本计划不宣称实物链路已经最终调通。它的作用是把后续调试拆成可复现步骤，明确每一步的输入、命令、通过标准、失败分支和记录格式。

## 2. 当前接手上下文

### 2.1 已知硬件与网络状态

| 项目 | 当前信息 | 调试含义 |
|---|---|---|
| PC104 IP | `192.168.0.101` | Telnet、UDP 目标地址 |
| Telnet | `23/tcp`, `target/password`, prompt `->` | 当前优先调通路径 |
| 当前实物状态 | 空板 HIL，多数传感器未接入 | 必须用 Telnet 注入虚拟深度、DVL、状态量 |
| 宿主机 UDP | 宿主机直跑曾收到 `$AUV` 与 UdpLogger | PC104 回流能力不能被容器 UDP 失败否定 |
| 容器 UDP | 容器内回流不稳定或不可达 | 容器只做静态分析/Telnet 辅助，不作为最终 UDP 结论 |
| UdpLogger | 监听 `52367/udp` | 观察 VxWorks printf/任务日志 |
| 实测 HIL UDP | 当前脚本按 `21/udp` 收发 | 与 mock/ROS 默认 `52364/52365` 不同，必须分清 |

### 2.2 VxWorks 当前功能状态

| 项 | 当前结论 | 下一步 |
|---|---|---|
| BUG-3 深度计数器 | 已有 HIL 证据: 递增后可递减归零 | Telnet 基线中重跑一次作为接手复核 |
| BUG-4 超深自救 | 板上当前运行时失败: Bit9 能置位，但最终 Motor1 仍可能为 0 | 先 Telnet probe 复现；重编译/重烧录后再验证源码补丁 |
| BUG-5 DVL 软/硬离底 | 状态位层面已有证据；软硬分离需干净启动复测 | 重启后单测软限，再测硬限 |
| BUG-6 DVL 丢底 | 已有 HIL 证据: Bit13 与 CtrlMode 降级有效 | 复核时保持 Jetson 心跳，避免 Bit14 干扰 |
| Jetson lost | 模式降级、Motor1/Motor2 归零有效；Bit14 不保持 | 单独做“动作通过”和“状态位可观测性”两级判据 |
| 0xEE/0xEF | VxWorks diff 已引入 Jetson shadow / hybrid | 验证太少，需要 UDP + Telnet + ROS 三侧证据 |
| `POOL_TEST_MODE` | 当前镜像符号表无 `Pool_Safety_Check` | 水池模式 BUG-7 不能用当前镜像验证 |

### 2.3 已知 Telnet 坑

后续所有 Telnet 自动化必须遵守:

1. 使用 `lkup "Symbol"` 找基址，再由 PC 端计算绝对地址。
2. VxWorks shell 只执行短命令，例如 `*(unsigned int*)0x536a74=0x41200000`。
3. 不使用 `Symbol + offset` 写法，已观察到可能触发 shell task Page Fault。
4. 不使用结构体字段表达式，例如 `Current_State.Current_Dep`，当前 shell 不稳定支持。
5. 不直接写 float 字面量，统一写 IEEE754 位模式。
6. 避免长 `printf`，一次只读 1 到 3 个字段。
7. `MainCtrlTask` 会覆盖注入快照；需要短暂停任务或使用周期性注入。
8. 每次侵入式测试前做 snapshot，结束后 best-effort restore 并 resume 任务。

## 3. 总体调试策略

### 3.1 分阶段路线

| 阶段 | 名称 | 目标 | 是否需要写板上内存 |
|---|---|---|---|
| S0 | 环境与端口审计 | 确认 PC104、宿主机、Jetson/PC IP、UDP 端口、占用情况 | 否 |
| S1 | Telnet 只读基线 | 登录、符号表、关键变量读回、任务状态 | 否 |
| S2 | Telnet 安全写入原语 | 验证绝对地址读写、float bit 写入、snapshot/restore | 是 |
| S3 | Telnet 注入状态机 | 复测 BUG-3/4/5/6/Jetson lost | 是 |
| S4 | Telnet + UDP 双证据 | 注入虚拟传感器，同时收 `$AUV` 与 UdpLogger | 是 |
| S5 | ROS2 protocol_udp 接入 | PC104 上行映射成 ROS topic，下行 `$CKTH` 保活 | 可能需要注入 |
| S6 | 上位机/Jetson/PC104 链路 | 上位机 MANUAL/AUTONOMY/ESTOP 与 Jetson 仲裁 | 可能需要注入 |
| S7 | 字段与传感器定界 | 明确空板能验证什么、不能验证什么、需补哪些传感器 | 否 |

### 3.2 核心原则

- 先 Telnet，再 UDP，再 ROS，再上位机。
- 同一结论至少需要两类证据: 内部变量证据和外部链路证据。
- 安全项不能只看异常位，必须同时看最终执行命令。
- 空板上的“传感器读数”默认不可信，需要通过 Telnet 注入或明确记录为缺失。
- 容器内 UDP 失败只记录为部署现象，不作为实物板 UDP 根因结论。
- 每次测试都记录固件版本或烧录时间，否则 BUG-4 等结论无法复用。

## 4. S0: 环境与端口审计

### 4.1 前置安全检查

执行前确认:

- 主推电源未接通。
- 舵机/电机执行机构物理断开，或处于安全架台。
- 具备物理急停手段。
- PC104 当前固件版本、烧录时间、是否包含后版 BUG-4 patch 已记录。
- 当前网络不是 Docker bridge 结论路径；最终 UDP/ROS/上位机用宿主机或真实 Jetson 验证。

### 4.2 网络检查

```bash
ping 192.168.0.101
nc -vz 192.168.0.101 23
ip addr
ip route
ss -ulpn | grep -E ':(21|52364|52365|52366|52367)\b' || true
```

通过标准:

- `ping` 稳定。
- `23/tcp` 可连接。
- `21/udp`、`52367/udp` 未被无关进程占用。
- 若需要监听 `21/udp`，确认当前用户具备绑定低端口权限，或用 root / capabilities 执行。

### 4.3 端口基线

当前必须区分两套端口:

| 场景 | 下行目标 | 上行监听 | 备注 |
|---|---|---|---|
| Mock AMD / 仿真默认 | bridge -> `127.0.0.1:52364` | bridge bind `52365` | `config/bridge_params.protocol_udp.yaml` 默认 |
| 当前 PC104 HIL 实测 | PC/Jetson -> `192.168.0.101:21` | PC/Jetson bind `21` | 以接手文档和 HIL 脚本为准 |
| UdpLogger | PC104 -> PC/Jetson `52367` | PC/Jetson bind `52367` | `scripts/log_receiver.py` |

风险项:

- `console_soft/auv_console_pyside6/console_config.yaml` 当前仍写 `amd_port: 52364`, `local_port: 52365`。
- ROS2 `brain_linux/config/params.protocol_udp_arbiter.yaml` 默认仍是 `remote_host: 127.0.0.1`, `remote_port: 52364`, `local_port: 52365`。
- 在进入实物全链路前，需要建立单独 real PC104 参数文件，不能直接复用 mock 配置。

## 5. S1: Telnet 只读基线

### 5.1 登录验证

```bash
telnet 192.168.0.101 23
```

账号:

```text
user: target
password: password
prompt: ->
```

或使用脚本 dry-run:

```bash
python3 scripts/vxworks_bug4_runtime_probe.py \
  --host 192.168.0.101
```

通过标准:

- 能看到 `->` prompt。
- dry-run 不写内存，只打印符号表和 baseline。
- 至少能 `lkup` 到:
  - `Current_State`
  - `UI_WIFI_Instruction`
  - `UI_Channel_Selection_Down`
  - `Instruction_To_FMCU`
  - `Sys_Abnorm_Inf_Judgement`
  - `Depth_Exceed_FromUI12_Depth_Para1`
  - `to_MCU_buf`
  - `Not_Recv_From_Jetson_No`
  - `Seafloor_Grounding_Arbitration`

记录项:

```text
PC104 固件/烧录时间:
Telnet 登录结果:
符号表结果:
Current_State base:
UI_WIFI_Instruction base:
Instruction_To_FMCU base:
Sys_Abnorm_Inf_Judgement:
to_MCU_buf:
是否存在 Pool_Safety_Check:
```

### 5.2 只读任务与日志确认

在 Telnet shell:

```c
i
semShow semEmergencyTask
lkup "EmergencyTask"
lkup "MainCtrlTask"
```

同时在 PC 端启动日志:

```bash
python3 scripts/log_receiver.py --port 52367 --timestamps
```

通过标准:

- 任务列表中能看到关键任务。
- `semEmergencyTask` 状态可读。
- `log_receiver.py` 能收到 UdpLogger，至少能看到任务打印或普通日志。

## 6. S2: Telnet 安全写入原语

S2 的目标不是验证业务逻辑，而是验证“我们可以安全、可恢复地注入虚拟传感器读数”。

### 6.1 地址与偏移策略

当前实测偏移只作为本固件的 runtime 经验，换镜像必须重验:

| 结构 | 字段 | 偏移 |
|---|---|---|
| `Current_State` | `Current_Dep` | `+0x34` |
| `UI_WIFI_Instruction` | `Ctrl_Mode` | `+0x07` |
| `UI_WIFI_Instruction` | `Depth_Para1` | `+0x08` |
| `UI_WIFI_Instruction` | `Motor_Speed1` | `+0x18` |
| `UI_WIFI_Instruction` | `RCD_LH_Set_Rud_Angle` | `+0x1c` |
| `UI_WIFI_Instruction` | `RCD_RH_Set_Rud_Angle` | `+0x1e` |
| `UI_WIFI_Instruction` | `Para1` | `+0x28` |
| `DVL_Prase_Data` | `BD_Height` | `+0x18` |
| `DVL_Prase_Data` | `BD_Check` | `+0x20` |

### 6.2 最小写入验证

只在空板 HIL 安全条件下执行:

```bash
python3 scripts/vxworks_bug4_runtime_probe.py \
  --host 192.168.0.101 \
  --execute \
  --probe shadow-override
```

通过标准:

- 脚本先 snapshot 关键字段。
- 写入 `UI_WIFI_Instruction` shadow 后调用 `Remote_Assignment(&Instruction_To_FMCU)`。
- `to_MCU_buf` 或 word scan 中能看到 `Motor1=00300`、LH/RH 接近 `2275/1821`。
- 结束后执行 restore，不遗留测试值。

失败处理:

- 若 Telnet 断开但 PC104 主任务还在运行，先重新登录，确认 shell task 是否重启。
- 若出现 Page Fault，检查是否误用了 `Symbol + offset`。
- 若 shadow-override 无 `00300`，说明 `UI_Channel_Selection_Down`、偏移或 `Remote_Assignment()` 覆盖链路仍需源码级追踪。

## 7. S3: Telnet 注入状态机复测

### 7.1 BUG-3 深度计数器滑动窗口

目标:

- 复核 `Depth_Exceed_FromUI12_Depth_Para1` 能递增，也能在深度恢复后递减到 0。

建议方式:

- 用 `lkup + 绝对地址` 写入 `Current_Dep=10.0f` 和 `Depth_Para1=5`。
- 连续 `semGive(semEmergencyTask)` 或等待 EmergencyTask 周期。
- 再写入 `Current_Dep=1.0f`，观察计数器回落。

通过标准:

```text
count_up > 0
count_down == 0
Sys 不应遗留非预期位
```

### 7.2 BUG-4 超深自救

当前必须分两轮:

#### 旧固件运行时复现

```bash
python3 scripts/vxworks_bug4_runtime_probe.py \
  --host 192.168.0.101 \
  --execute \
  --probe both
```

旧固件失败预期:

```text
Sys & 0x00000200 != 0
to_MCU_buf 中 Motor1 仍可能是 00000
```

这个结果表示“安全状态机进入，但最终执行命令被覆盖”，不能算通过。

#### 重编译/重烧录后复测

通过标准:

```text
Sys_Abnorm_Inf_Judgement & 0x00000200 != 0
to_MCU_buf 包含 ",00300,"
LH/RH 约为 2275/1821
```

若重烧录后仍失败:

- 不再继续只补 `Instruction_To_FMCU`。
- 转入 emergency override 设计: 应急激活时绕过 UI/LORA 普通重建路径，直接优先写最终执行帧。

### 7.3 BUG-5 DVL 软/硬离底

要求干净启动后分开测，避免 static 计数器污染。

软限通过标准:

```text
仅 Bit11 置位，Sys & 0x00000800 != 0
不应同时出现 Bit12，除非确实低于硬限或上一轮计数器未恢复
目标深度截断逻辑按当前深度生效
```

硬限通过标准:

```text
Bit12 置位，Sys & 0x00001000 != 0
必要时 Bit11 + Bit12 同时置位可以接受
Motor1 约 350
水平舵由 HightCtrlAlgorithm 给出合理值
```

### 7.4 BUG-6 DVL 丢底

测试时必须保持 Jetson 心跳，避免 Bit14 抢先干扰。

通过标准:

```text
Sys & 0x00002000 != 0
UI_WIFI_Instruction.FromUI12_Ctrl_Mode == 0x01
执行命令进入安全态
```

后续接真实 DVL 时还要验证:

- `BD_Check == 2.0/3.0` 是否确为锁底有效。
- 丢底恢复后 Bit13 是否清除。
- 重新夺回 Jetson 模式是否有明确授权流程。

### 7.5 Jetson lost

分两级判据，不混在一起:

最低安全通过:

```text
停止 Jetson 下行后 Ctrl_Mode -> 0x01
Motor1/Motor2 -> 0
```

可观测性通过:

```text
Sys_Abnorm_Inf_Judgement Bit14 稳定保持
收到有效 Jetson 包后 Bit14 清除
```

当前接手状态应继续标记为:

```text
Jetson lost: partial pass
原因: 降级/停机动作已有证据，Bit14 保持性未闭环
```

## 8. S4: Telnet + UDP 双证据

### 8.1 同步运行约束

`21/udp` 同一时间只能有一个主要接收者。调试时不要让 `vxworks_safety_hil.py`、ROS bridge、上位机、sniffer 同时绑定同一个端口。

推荐组合:

| 组合 | 用途 |
|---|---|
| `vxworks_safety_hil.py` + `log_receiver.py` | 自动 HIL 验证 |
| ROS bridge + `log_receiver.py` + `tcpdump` | ROS 接入验证 |
| 上位机 + `log_receiver.py` + `tcpdump` | GUI 接入验证 |

如果需要旁路观察 `21/udp`，优先用:

```bash
sudo tcpdump -ni <iface> host 192.168.0.101 and udp -XX
```

不要再另起一个绑定 `21/udp` 的 Python sniffer 抢端口。

### 8.2 UDP 基线

在非容器 Linux 或真实 Jetson 上运行:

```bash
python3 scripts/vxworks_safety_hil.py \
  --mode auto-udp \
  --host 192.168.0.101 \
  --uplink-port 21 \
  --log-port 52367
```

通过标准:

```text
上行帧接收: PASS
UdpLogger 日志: PASS
心跳保活: PASS
Sys_Abnorm 回传: PASS
```

Jetson lost Bit14 单独记录，不作为 UDP 基线总失败:

```text
Jetson lost Bit14: PASS / FAIL / transient
CtrlMode 降级: PASS / FAIL
Motor 停机: PASS / FAIL
```

### 8.3 虚拟传感器注入策略

因为当前是纯 PC104 空板，无真实传感器，必须明确每个读数来源:

| 读数 | 默认空板状态 | 注入方式 | 可验证链路 |
|---|---|---|---|
| 深度 `Current_Dep` | 可能为 0 或被刷新 | Telnet 写 IEEE754 float bit | 深度安全、`$AUV` 深度、ROS `/auv/sensors/depth` |
| DVL `BD_Check/BD_Height` | 无 DVL，不可信 | Telnet 写 float bit | BUG-5/6、ROS DVL/altitude |
| IMU 姿态 | 无 IMU，不可信 | Telnet 写姿态字段或保持 0 | ROS IMU 映射、PID 输入 |
| Jetson 心跳 | 无真实 Jetson 时会超时 | UDP 周期性 `$CKTH` | Not_Recv_From_Jetson_No、0xEE/0xEF |

建议先做短时注入:

1. Telnet 写一次虚拟读数。
2. 立即读内部变量。
3. 同时观察 `$AUV` 上行是否反映。
4. 若被 MainCtrlTask 覆盖，再改为 2 到 5Hz 周期注入，而不是长时间 suspend 主任务。

## 9. S5: ROS2 protocol_udp 接入

### 9.1 实物参数文件要求

进入 ROS2 前，应新增或临时生成实物参数，不直接使用 mock 默认值。

建议实物 bridge 参数:

```yaml
bridge:
  backend: protocol_udp
  passive_mode: true   # 首轮只翻译遥测，不主动下发控制
  command_publish_hz: 5.0
  protocol_control_mode_byte: 238
  protocol_send_zero_on_idle: true
  protocol_udp:
    local_host: 0.0.0.0
    local_port: 21
    remote_host: 192.168.0.101
    remote_port: 21
    socket_timeout_s: 0.1
    recv_buffer_size: 2048
    obj_address: 1
    main_motor_rpm_scale: 15.0
    side_motor_rpm: 0
    zenoh_side_channel_enabled: true
```

注意:

- `local_port: 21` 可能需要 root 或 `CAP_NET_BIND_SERVICE`。
- 如果实测 VxWorks 回包目标不是 PC/Jetson `21/udp`，以 tcpdump 和实际上行帧为准更新。
- 首轮 `passive_mode: true`，确认遥测和状态话题后再允许主动下发。

### 9.2 ROS2 启动与观测

```bash
cd scripts
bash start_lin_brain.sh stack --backend protocol_udp --arbiter-profile
```

观测话题:

```bash
ros2 topic echo /auv/bridge/shadow_telemetry
ros2 topic echo /auv/sensors/imu --once
ros2 topic echo /auv/sensors/dvl --once
ros2 topic echo /auv/sensors/depth --once
ros2 topic echo /auv/sensors/altitude --once
ros2 topic echo /auv/arbiter/status --once
ros2 topic echo /auv/sensors/status --once
```

通过标准:

- `bridge_node` 能持续解析 145 字节 `$AUV`。
- `/auv/bridge/shadow_telemetry` 中 `frame_number` 递增。
- `telemetry_freshness_ms` 不持续超出 guard 阈值。
- Telnet 注入的深度能在 `/auv/sensors/depth` 上出现。
- Telnet 注入的 DVL/altitude 能在对应 topic 上出现，或明确记录由于空板无传感器而为 0。

### 9.3 下行 `$CKTH` 与 PC104 内部证据

进入主动下发前，先确认:

```text
Not_Recv_From_Jetson_No 被持续清零
UI_WIFI_Instruction.FromUI12_Ctrl_Mode 能接收到 0xEE 或 0xEF
UI_WIFI_Instruction.FromUI12_Motor_Speed1 与 ROS/bridge 下发一致
to_MCU_buf 最终帧可解释
```

不要只看 ROS `/cmd_vel`，必须同步读 PC104 内部变量。

## 10. S6: 上位机、Jetson、PC104 全链路

### 10.1 上位机配置审计

当前 PySide6 上位机配置仍含 mock/旧端口:

```yaml
udp:
  amd_ip: "192.168.0.101"
  amd_port: 52364
  local_port: 52365
```

进入实物前必须确认:

- 当前固件实际收包端口是否为 `21/udp`。
- 上位机是直连 PC104，还是通过 Jetson/Zenoh 侧通道。
- MANUAL 模式是否允许 UDP 直发 PC104。
- AUTONOMY 模式是否只发 Zenoh 语义命令，由 Jetson 仲裁。
- ESTOP 是否 UDP + Zenoh 双通道推力归零。

### 10.2 MANUAL 模式

通过标准:

```text
上位机按钮/摇杆产生 CKTH
PC104 Telnet 侧 Not_Recv_From_Jetson_No 或 WIFI 接收计数被刷新
UI_WIFI_Instruction 控制字段变化可读
to_MCU_buf 最终帧与手动命令一致
上行 $AUV 报文编号递增
```

### 10.3 AUTONOMY / 0xEE 模式

通过标准:

```text
上位机发语义任务到 Zenoh
ROS bridge 收到 rt/pc/cmd_raw 或 mission command
arbiter 状态从 LOCKED/REQUESTING 进入允许态，或给出明确 deny_reason
bridge 下发 control_mode_byte=0xEE
PC104 进入 Jetson_Shadow_Proces 路径
Not_Recv_From_Jetson_No 持续清零
Telnet 可读 target heading/depth 与下发字段一致
```

### 10.4 HYBRID / 0xEF 模式

通过标准:

```text
bridge 下发 control_mode_byte=0xEF
PC104 进入 Remote_Proces / Remote_Assignment 透传路径
推力和舵角最终 to_MCU_buf 与下行命令一致
停止下行后能触发 Jetson lost 安全动作
```

### 10.5 ESTOP

通过标准:

```text
上位机 ESTOP 后 UDP 下行推力归零
Zenoh 侧 autonomous command 被锁止或置安全态
PC104 最终 to_MCU_buf 推力归零
ROS arbiter/status 显示 ESTOP 或等价锁止状态
解除 ESTOP 前不允许非零推力恢复
```

## 11. 字段定义和协议高风险审计

### 11.1 必查字段

| 字段 | VxWorks 文档语义 | 当前 Python/ROS 风险 |
|---|---|---|
| `$CKTH` offset 7 | `Ctrl_Mode`, 0xEE/0xEF | 需确认上位机、bridge 一致使用 |
| `$CKTH` offset 23 | Motor1 RPM | `main_motor_rpm_scale=15.0` 是否符合实物 |
| `$CKTH` offset 35 | target heading ×10 | 与 VxWorks shadow 一致 |
| `$CKTH` offset 37 Para1 | VxWorks diff 写 target_depth_m ×1000 | `common/protocol.py` 当前对 `KEY_TARGET_DEPTH_M` 使用 ×10，高风险 |
| `$AUV` offset 56/58/60 | DVL BI_X/Y/Z, mm/s | ROS parse 转 m/s，方向需实测标定 |
| `$AUV` offset 82 | DVL speed m/s×10 | VxWorks diff 已从 knots×10 改为 BI_V/100 |
| `$AUV` offset 126 | Sys_Abnorm | Python parse 读取 126:130，需实测确认 |

### 11.2 目标深度单位专项

必须做一个专项测试，不能跳过:

1. ROS/bridge 下发 `target_depth_m=3.0`。
2. Telnet 读 `UI_WIFI_Instruction.FromUI12_Para1` 或对应绝对地址。
3. 期望值按 VxWorks diff 应为 `3000`。
4. 若读到 `30`，说明 Python common 侧仍按 `×10`，0xEE 深度控制不可进入正式实物闭环。

该项失败时，修复顺序:

1. 先改 `common/protocol.py` 契约和测试。
2. 再改 ROS bridge / 上位机使用。
3. 再改文档字段真值表。
4. 最后复测 PC104 Telnet 读数。

### 11.3 上行异常位专项

至少验证这些位:

| 位 | 语义 | 空板可验证方式 |
|---|---|---|
| Bit9 | 深度超限 Para1 | Telnet 注入深度 |
| Bit11 | 离底软限 | Telnet 注入 DVL |
| Bit12 | 离底硬限 | Telnet 注入 DVL |
| Bit13 | DVL 丢底 | Telnet 注入 DVL 丢底 |
| Bit14 | Jetson 通信超时 | 停止 UDP 心跳 |

每个位都要求:

```text
内部变量 Sys_Abnorm_Inf_Judgement 置位
$AUV 上行帧中对应 offset 可见
ROS shadow_telemetry 中 sys_abnorm_info 可见
上位机若已接入，GUI 可见或日志可见
```

## 12. 空板 HIL 能力定界

### 12.1 空板可以充分验证

- Telnet 登录、符号表和 runtime 变量读写。
- VxWorks 安全状态机的条件触发。
- UDP `$CKTH` 下行解析和 `$AUV` 上行回传。
- UdpLogger 回流。
- 0xEE/0xEF 控制模式的状态机入口。
- Jetson lost 的模式降级和推力归零动作。
- ROS bridge 对 `$AUV` 的解析和 topic 发布。
- ROS/bridge 下发 `$CKTH` 后 PC104 内部字段变化。
- 上位机 MANUAL/AUTONOMY/ESTOP 的通信链路。

### 12.2 空板只能部分验证

- BUG-4 的“最终命令帧”能验证，但真实上浮效果不能验证。
- DVL 软/硬限状态机能验证，但真实 `BD_Check/BD_Height` 单位和可靠性不能验证。
- IMU 姿态可通过注入验证映射，但真实姿态传感器链路不能验证。
- ROS EKF 能收到话题，但无真实 IMU/DVL/深度时不能验证估计质量。
- 控制器输出能被编码下发，但无执行机构时不能验证物理响应。

### 12.3 空板不能验证，必须补传感器或执行机构

- 真实深度计/压力传感器到 `Current_State.Current_Dep` 的链路。
- 真实 DVL 串口解析、锁底状态、体轴速度极性。
- 真实 IMU 姿态、角速度和坐标系。
- FMCU 舵机/电机实际响应、方向和死区。
- 超深自救的水动力效果。
- Bumpless Transfer 在真实运动过程中的平滑性。
- 多传感器并发异常时的真实竞态。
- 下水后的延迟、丢包、噪声、供电和漏水联动。

## 13. 每次调试记录模板

每次执行都按下面格式写入新的运行记录，避免只留下 PASS/FAIL:

```text
日期:
操作者:
运行地点:
运行环境: 宿主机 Linux / Jetson / 容器 / 其他
PC104 固件版本或烧录时间:
执行机构状态: 断开 / 安全架台 / 其他
网络拓扑:
本机 IP:
PC104 IP:
UDP 端口:

执行命令:
Telnet 注入内容:
UDP/ROS/上位机并行观测:

内部变量证据:
外部链路证据:
最终执行帧证据:

判定:
影响:
下一步:
是否允许进入下一阶段:
```

安全项必须额外记录:

```text
状态位是否置位:
模式是否降级:
最终执行命令是否改变:
推力是否归零或进入应急最小航速:
是否需要源码修改:
是否影响接执行机构/下水风险:
```

## 14. 最终定界报告预留结构

完成实物调试后，另写一份“最终调通与定界报告”，建议结构如下:

```text
# PC104 空板实物全链路调试定界报告

## 1. 结论摘要
- 已最终调通:
- 未调通:
- 部分调通:
- 禁止外推的结论:

## 2. 硬件与固件版本

## 3. Telnet 调试结果

## 4. UDP 协议调试结果

## 5. ROS2 话题与桥接结果

## 6. 上位机链路结果

## 7. 字段定义与单位修正结果

## 8. 深度安全 BUG 复测结果

## 9. 空板 HIL 能力边界

## 10. 需要补充的传感器/执行机构
- 深度计:
- DVL:
- IMU:
- FMCU/舵机/电机:
- BMS/漏水/电源:

## 11. 下一阶段准入条件
```

## 15. 下一次实际执行入口

建议下一步只做 S1，不进入写内存:

```bash
python3 scripts/vxworks_bug4_runtime_probe.py \
  --host 192.168.0.101
```

同时开日志:

```bash
python3 scripts/log_receiver.py \
  --port 52367 \
  --timestamps
```

完成后把输出按第 13 节模板记录。只有 S1 通过，才进入 S2 的 `--execute` 写内存测试。
