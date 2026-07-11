# 深度安全 BUG 实物 HIL 状态机验证记录

日期: 2026-07-11
对象: VxWorks PC104 空板 HIL
说明: 本文记录运行时 Probe 结果、状态机解释、源码是否需要再动、以及对后续实物部署的启示。它是运行时记录，不替代 `.trae/documents/深度安全_空板HIL验证SOP.md`。

## 1. 总体状态

### 已确认固件特征

最新固件符号表中已出现:

```text
Not_Recv_From_Jetson_No
Seafloor_Grounding_Arbitration
```

未出现:

```text
Pool_Safety_Check
```

解释:

当前烧录镜像为 `POOL_TEST_MODE=0` 海试模式，水池模式函数未编译进镜像，符合预期。

### UDP 自动化状态

容器内 `auto-udp` 曾未闭环:

```text
上行 $AUV: 未收到
UdpLogger: 未收到
```

解释:

Telnet 能通，说明容器到 PC104 路径可用；当时 UDP 回流未进入容器，需检查 VxWorks 目标 IP/端口与 Docker 映射。

后续用户在宿主机直接运行 `auto-udp` 已得到:

```text
上行 $AUV: PASS
UdpLogger: PASS
心跳保活: PASS
Jetson lost Bit14: FAIL
```

因此当前结论更新为:

```text
PC104 -> 宿主机 UDP 回流可达。
容器内 UDP 不闭环属于 Docker 端口映射/网络命名空间/监听端口问题，不能视为 PC104 UDP 根因。
```

影响:

当前容器内 BUG 验证仍主要依赖 Telnet 注入 + VxWorks 内存读回；换到非容器 Linux 后，应补齐 UDP/Bridge/Console 的端到端验证。

## 2. BUG-3: 深度计数器只增不减

### 运行时结果

```text
BUG3_RESULT up=7 down=0
```

### 状态机解释

测试方法:

1. 暂停 `MainCtrlTask`，防止 `Current_State` 被刷新覆盖。
2. 注入 `Current_Dep = 10.0f`，`Depth_Para1 = 5`。
3. 触发多次 `EmergencyTask`，计数器递增。
4. 注入 `Current_Dep = 1.0f`。
5. 触发多次 `EmergencyTask`，计数器递减归零。

结论:

BUG-3 修复有效。计数器不是闩锁式只增不减，而是滑动窗口式递增/递减。

### 是否需要再改 VxWorks

不需要。

### 对实物启示

1. 实水环境中短时深度尖峰不会永久锁死。
2. 计数器阈值仍受 `EmergencyTask` 实际频率影响，实际延迟需按运行频率重新核算。

## 3. BUG-4: 超深推力归零导致欠驱动沉底

### 运行时结果

第一次按原修复逻辑触发:

```text
SYS=0x00000200
EX=13
M1=0
LH=2048
RH=2048
```

宽范围扫描:

```text
WIDE_HITS []
```

含义:

Bit9 已置位，深度超限分支进入；但 `Instruction_To_FMCU` 附近没有出现 `300RPM`、`2276`、`1820` 等应急输出特征值。

进一步验证 `Remote_Assignment()`:

```text
TOBUF=$MCUFD,...,00000,00000,2275,1821,2059,2048,00,*RN
```

含义:

最终下发帧里电机仍是 `00000`。舵角在某些预置 UI 影子指令场景下能变为上浮舵，但 Motor1 没有保持 300。

### 状态机解释

关键源码链路:

```c
Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 300;
Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = ...
Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = ...
Remote_Assignment(&Instruction_To_FMCU);
```

但 `Remote_Assignment()` 内部会重建字段:

```c
if(UI_Channel_Selection_Down == 0x01)
    temp->McuFD_Motor1_Set_Speed = UI_LORA_Instruction.FromUI12_Motor_Speed1;
if(UI_Channel_Selection_Down == 0x02)
    temp->McuFD_Motor1_Set_Speed = UI_WIFI_Instruction.FromUI12_Motor_Speed1;
```

因此 BUG-4 的第一版修复属于“写了应急输出，但随后打包函数可能从 UI/LORA 影子指令覆盖回普通值”的状态机不闭环。

### 已做源码修正

已对 `csd_vx6.8_lastest/SecurityEmergencyManage.c` 做最小修正:

```c
UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 300;
UI_WIFI_Instruction.FromUI12_RCD_LH_Set_Rud_Angle = -20;
UI_WIFI_Instruction.FromUI12_RCD_RH_Set_Rud_Angle = -20;
UI_LORA_Instruction.FromUI12_Motor_Speed1 = 300;
UI_LORA_Instruction.FromUI12_RCD_LH_Set_Rud_Angle = -20;
UI_LORA_Instruction.FromUI12_RCD_RH_Set_Rud_Angle = -20;
```

Para1/Para2 两个超深分支均已补上。

### 当前版本边界

当前 PC104 上已经烧录并实测的镜像，仍然对应“第一版 BUG-4 修复运行时失败”的状态:

```text
Bit9 能置位
最终 $MCUFD Motor1 仍可能为 00000
```

源码侧已经补上 UI/WIFI 与 LORA shadow command，但该补丁只有在重新编译并重新烧录后才会进入板上运行时。当前 Linux 容器只能看到 Workbench 工程文件，`Makefile` 仍指向:

```text
C:/WindRiver/workspace/csd_vx6.8_lastest
C:/WindRiver_6.8.3_x86/vxworks-6.8/target/config/BSP
```

因此最终可烧录镜像需要在原 Wind River Workbench/烧录环境中生成，容器内不能替代这一步。

### 是否需要再改 VxWorks

需要。

当前修改还需要:

1. 重新编译 VxWorks 镜像。
2. 重新烧录 PC104。
3. 重跑 BUG-4 Probe。

如果重烧录后仍然失败，下一轮不建议继续只改 `Instruction_To_FMCU`。应直接检查 `Remote_Assignment()` 后的最终覆盖关系，必要时引入明确的 emergency override 优先级，例如:

```text
Emergency override active -> 跳过 UI/LORA 普通指令重建 -> 直接写最终执行帧
```

### 复测通过标准

期望最终帧类似:

```text
$MCUFD,...,00300,xxxxx,2275,1821,...
```

或结构体/打包缓冲区至少出现:

```text
Motor1 = 300
LH ~= 2275/2276
RH ~= 1820/1821
Sys & 0x00000200 != 0
```

推荐复测步骤:

```text
1. 确认符号存在: lkup "Depth_Exceed", lkup "Sys_Abnorm", lkup "UI_WIFI", lkup "Instruction_To_FMCU"
2. 如需空板注入，短暂停 MainCtrlTask，避免 Current_State 被刷新覆盖
3. 注入 Current_Dep > Depth_Para1，并连续触发 EmergencyTask 到计数器 >= 10
4. 读取 Sys_Abnorm_Inf_Judgement，确认 Bit9
5. 读取最终 $MCUFD/to_MCU_buf 或 Instruction_To_FMCU，确认 Motor1 与 LH/RH
6. 恢复 MainCtrlTask，并清理注入状态
```

失败分支判定:

```text
Bit9 = 0:
  深度注入、计数器或阈值链路未触发。

Bit9 = 1, Motor1 = 0:
  安全状态机触发，但执行命令链路被覆盖，BUG-4 不通过。

Bit9 = 1, Motor1 = 300, LH/RH 正确:
  BUG-4 空板 HIL 通过；接执行机构前仍需确认物理方向和舵面极性。
```

### 对实物启示

1. 不能只检查异常位，必须检查最终执行命令帧。
2. 对欠驱动 AUV，超深保护必须保持最低舵效航速，否则“安全停机”反而可能变成沉底。
3. 实物需求若变为“任何超深立即停推进”，必须同时评估是否有独立浮力/压载上浮能力；没有独立上浮能力时，不建议简单停推进。
4. 应急逻辑最好绕过普通 UI 透传打包路径，或引入明确的 emergency override 优先级。

## 4. BUG-5: DVL 离底高度软/硬限

### 运行时结果

硬限 Probe:

```text
BUG5_HARD sys=0x00001800
```

软限 Probe:

```text
BUG5_SOFT sys=0x00001800 para1=0
```

### 状态机解释

`0x00001800` 表示:

```text
Bit11 = 0x00000800  离底软限
Bit12 = 0x00001000  离底硬限
```

硬限 Probe 通过 4 次调用 `Seafloor_Grounding_Arbitration()` 后置位，说明 DVL 有效锁底 + 离底高度低于硬限时，状态仲裁有效。

软限 Probe 中也出现 Bit12，原因是上一轮硬限 Probe 的静态计数器未完全衰减。该函数内部计数器是 static，空板连续 Probe 时需要让状态自然恢复，或重启固件获得干净初始状态。

### 是否需要再改 VxWorks

状态位层面不需要。

仍建议后续复核:

1. 干净启动后单独测软限，只期望 Bit11。
2. 接入真实 DVL 后，验证 BD_Check 有效锁底状态和 BD_Height 单位。

### 对实物启示

1. static 防抖计数器会跨 Probe 保持状态，实测脚本必须设计“恢复段”。
2. 实物靠近海底时，硬限必须能夺权，不应只靠 Jetson 端规避。
3. 如果任务需求允许贴底作业，需要可配置软/硬限参数，而不是永久固定 3.0m/1.8m。

## 5. BUG-6: DVL 丢底后空函数

### 运行时结果

```text
BUG6 sys=0x00002000 ui_ctrl=1
```

### 状态机解释

注入:

```text
BD_Check = 0
Current_Mode = 0xEE
UI Ctrl = 0xEE
```

连续调用 `Seafloor_Grounding_Arbitration()` 超过 DVL lost threshold 后:

```text
Bit13 = 0x00002000
UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0x01
```

结论:

DVL 丢底降级逻辑有效。

### 是否需要再改 VxWorks

当前不需要。

但仍建议在真实 DVL 接入后验证:

1. `BD_Check == 2.0/3.0` 是否确实代表锁底有效。
2. 丢底/重锁底时 Bit13 是否能清除。
3. Jetson 模式切回 Remote 后，执行机构是否进入预期安全状态。

### 对实物启示

1. DVL 丢底不是普通传感器告警，低高度场景下可能意味着已经接近底部或回波失败，必须触发模式降级。
2. 若未来任务需要穿越 DVL 易丢底区域，应配套声呐/高度计冗余，不能简单放宽丢底保护。

## 6. Jetson 失联保护

### 运行时结果

```text
JETSON_LOST sys=0x00000000 ui_ctrl=1 m1=0 m2=0
```

### 状态机解释

模式降级与双电机停机生效:

```text
UI Ctrl -> 0x01
Motor1 -> 0
Motor2 -> 0
```

但 `Sys_Abnorm_Inf_Judgement` 中 Bit14 没保持住。可能原因:

1. 后续逻辑清除了 Bit14。
2. 本次 Probe 暂停 MainCtrlTask 后，某些模式/计数器状态与真实循环不同。
3. `Sys_Abnorm_Inf_Judgement` 在其他分支被重新赋值或清位。

### 是否需要再改 VxWorks

暂不直接改源码，建议先做单独复测:

1. 不暂停 MainCtrlTask，仅通过实际 Jetson 心跳停止来触发。
2. 连续读 `Sys_Abnorm_Inf_Judgement`，看 Bit14 是瞬时置位还是从未置位。
3. 若确认为瞬时置位后被清，考虑将 Jetson lost 状态独立锁存，直到收到有效 Jetson 包后清除。

### 对实物启示

Jetson 失联保护的首要目标是“夺权和停机/安全态”，状态位是上位机可观测性。如果实物测试中上位机需要明确显示 Jetson lost，则 Bit14 必须稳定保持。

## 7. 仍需覆盖的项目

可参考 `.trae/documents/深度安全_空板HIL验证SOP.md` 继续验证:

1. BUG-1 NaN 防御。
2. BUG-2 Bumpless Transfer 端到端确认。
3. BUG-7 水池模式，需 `POOL_TEST_MODE=1` 重新编译。
4. `$AUV` 上行状态回传。
5. UdpLogger 回流。
6. 接入真实 DVL/IMU/FMCU 后的闭环动作验证。

## 8. 当前结论

```text
BUG-3: PASS
BUG-4: FAIL in current burned runtime; source has been patched and needs rebuild/reburn
BUG-5: PASS for status bits; soft/hard clean separation needs rebooted clean run
BUG-6: PASS
Jetson lost: partial pass; mode/motor OK, Bit14 needs separate复测
UDP回流: not closed
```
