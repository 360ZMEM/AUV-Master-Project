# 深度安全修复 — 空板硬件在环 (HIL) 验证 SOP

> 适用条件: VxWorks PC104 通电运行, 无传感器接入 (IMU/DVL/FMCU 均不在线)
> 编写日期: 2026-06-01
> 对应修复: BUG-1/3/4/5/6/7/8 (深度安全多层围栏)

---

## 一、验证能力矩阵

### 1.1 【可以验证】的内容

| # | 验证项 | 方法 | 依赖 |
|---|--------|------|------|
| V1 | EmergencyTask 周期 & 触发 | Shell 读取 `Emergency_Task_Interval_Num`, 观察 printf 输出 | 仅需以太网 |
| V2 | BUG-3: 深度计数器递增/递减逻辑 | Shell 写入 `Current_State.Current_Dep` + `UI_WIFI_Instruction.FromUI12_Depth_Para1`, 观察 `Depth_Exceed_FromUI12_Depth_Para1` 变化 | Shell 直写全局变量 |
| V3 | BUG-4: 超深自救输出 (300RPM + 上浮舵 + Remote_Assignment) | Shell 注入深度使计数器>10, 读取 `Instruction_To_FMCU` 各字段 | Shell 直写 |
| V4 | BUG-5: 软限 — `Sys_Abnorm_Inf_Judgement` Bit11 置位 + 深度目标截断 | Shell 注入 `DVL_Prase_Data.BD_Height`<3.0 + `BD_Check`=2.0 | Shell 直写 |
| V5 | BUG-5: 硬限 — Bit12 置位 + 350RPM + HightCtrlAlgorithm 舵角输出 | Shell 注入 `DVL_Prase_Data.BD_Height`<1.8 | Shell 直写 |
| V6 | BUG-6: DVL 丢底自救 — 模式降级 + Bit13 + DepthCtrlAlgorithm(2.0) | Shell 写入 `DVL_Prase_Data.BD_Check=0.0` + `Current_State.Current_Mode=0xEE` | Shell 直写 |
| V7 | BUG-7: 水池模式保护 (需重编译 POOL_TEST_MODE=1) | 编译后 Shell 注入深度>0.9/Pitch>10/Roll>20, 观察输出 | 重编译 |
| V8 | Jetson 失联看门狗 | Shell 写入 `Not_Recv_From_Jetson_No=15`, 观察模式降级 | Shell 直写 |
| V9 | `Sys_Abnorm_Inf_Judgement` 回传到上位机 | PC 端 sniffer.py 监听 UDP $AUV 帧中的 Sys_Abnorm_Inf 字段 | 以太网连接 |
| V10 | NaN 防御路径 (BUG-1 部分) | Shell 写入 `CourseCtrl_para1=NaN` 等 PID 参数后观察舵角输出是否 clamp 到 0 | Shell 直写 (注1) |
| V11 | UdpLogger 日志通路 | PC 端 log_receiver.py 是否收到 EmergencyTask printf | 以太网连接 |
| V12 | 自动化注入脚本通路 | 运行 `vxworks_safety_hil.py` 从 PC 端自动驱动全部测试 | 以太网 + Shell |

> **注1**: VxWorks shell C 解释器不能直接写入 `NaN`。验证 NaN 路径需要通过特殊技巧:
> ```
> -> *((unsigned int *)&CourseCtrl_para1) = 0x7fc00000
> ```
> 这将 `CourseCtrl_para1` 设为 quiet NaN (IEEE754)。

### 1.2 【不能验证】的内容

| # | 不可验证项 | 原因 | 后续验证时机 |
|---|-----------|------|-------------|
| X1 | 真实深度传感器读数通路 | `Current_State.Current_Dep` 来自 FMCU 压力传感器, 空板无 FMCU | 水池联调 |
| X2 | 真实 DVL 底跟踪数据流 | COM17 串口无 DVL 设备 | DVL 接入后 |
| X3 | 真实 IMU 姿态角 | COM0 无 IMU 设备 | IMU 接入后 |
| X4 | 实际舵机/电机物理响应 | Remote_Assignment 发到 FMCU, 无 FMCU 无反馈 | 全系统联调 |
| X5 | 真实 Bumpless Transfer 过渡平滑性 | 需要实际运动中的模式切换 | 水池实测 |
| X6 | 超深上浮的实际水动力效果 | 300RPM 能否真正产生上浮力 | 水池/海试 |
| X7 | HightCtrlAlgorithm PID 在真实噪声下的稳定性 | 需连续传感器输入 | 水池实测 |
| X8 | 多传感器并发超时的竞态 | 空板上所有传感器同时超时, 无法分离验证 | 逐设备接入 |
| X9 | Jetson<->VxWorks 端到端延迟 | 需 Jetson 实际在线 | Jetson 联调 |
| X10 | 安全围栏触发到实际恢复的时间常数 | 需闭环系统 | 水池实测 |

### 1.3 【部分验证 / 需关注】

| # | 项目 | 可验证部分 | 需实测确认部分 |
|---|------|-----------|--------------|
| P1 | EmergencyTask 实际频率 | 可验证 semGive 间隔 | 函数注释说"10Hz"但实际 `Emergency_Task_Period=5` → 2Hz (见§3.1) |
| P2 | 安全围栏时序门限 | 可验证计数器增长 | 实际延迟与设计意图不符 (见§3.1 关键发现) |
| P3 | UDP Jetson 模拟通路 | 可通过 PC 发 $CKTH 帧模拟 | 真实 Jetson 处理延迟不同 |

---

## 二、关键发现: 计时参数偏差

### 2.1 EmergencyTask 实际运行频率

```
系统时钟:       sysClkRateSet(1000) → 1000 Hz (1ms/tick)
看门狗周期:     wdStart(wd, sysClkRateGet()*0.1, ...) → 100 ticks = 0.1s
计数器阈值:     Emergency_Task_Period = 5
实际周期:       5 × 0.1s = 0.5s → 2 Hz
```

### 2.2 各防抖门限的实际时间

| 计数器 | 代码阈值 | @2Hz 实际时间 | 函数注释声称 | 偏差 |
|--------|---------|---------------|-------------|------|
| `dvl_lost_lock_count` | >= 20 | **10.0s** | 2.0s | 5x 慢 |
| `altitude_critical_count` | >= 3 | **1.5s** | 0.3s | 5x 慢 |
| `altitude_warning_count` | >= 5 | **2.5s** | 0.5s | 5x 慢 |
| `Depth_Exceed_*` | >= 10 | **5.0s** | (未标注) | — |
| `Not_Recv_From_Jetson_No` | >= 10 | **1.0s** | 1.0s | ✓ 正确 (看门狗直接递增) |

> **根因**: `Seafloor_Grounding_Arbitration()` 的注释假设 10Hz, 但 EmergencyTask 实际 2Hz。
> `Not_Recv_From_Jetson_No` 正确是因为它由看门狗 (0.1s) 而非 EmergencyTask 递增。

### 2.3 修正建议 (HIL 验证后执行)

**方案 A**: 修改 `Emergency_Task_Period = 1` (使 EmergencyTask 变为 10Hz)
- 优点: 函数注释无需修改, 所有门限符合设计
- 缺点: EmergencyTask CPU 占用增加 5x
- 风险: 低 (EmergencyTask 逻辑轻量, PC104 有足够余量)

**方案 B**: 修改门限常数 (保持 2Hz 不变)
- `dvl_lost_lock_count >= 4` (2.0s @2Hz)
- `altitude_critical_count >= 1` (0.5s @2Hz, 无防抖能力)
- `altitude_warning_count >= 1` (0.5s @2Hz, 无防抖能力)
- 缺点: 计数器为 1 等于无防抖, 不如方案 A

**推荐: 方案 A** — 在 HIL 验证通过后将 `Emergency_Task_Period` 改为 1。

---

## 三、VxWorks Shell 验证 SOP (逐项操作)

### 3.0 准备工作

**PC 端环境搭建**:
```bash
# 终端1: 启动 UDP 日志接收
python scripts/log_receiver.py --timestamps --save hil_test.log

# 终端2: 启动协议嗅探器 (监控上行状态帧)
python scripts/sniffer.py --bind-port 52365 --ascii-format

# 终端3: VxWorks telnet/串口 Shell 连接
# 方法1: telnet 192.168.0.101 (如VxWorks开启了telnetd)
# 方法2: 串口console (通常COM0, 115200 8N1)
```

**Shell 基础命令**:
```c
// 查看任务列表
-> i
// 查看信号量状态
-> semShow semEmergencyTask
// 读取浮点变量
-> printf("%.3f\n", Current_State.Current_Dep)
// 读取整型变量
-> printf("0x%08x\n", Sys_Abnorm_Inf_Judgement)
// 写入浮点变量
-> Current_State.Current_Dep = 5.5
// 写入整型变量
-> UI_WIFI_Instruction.FromUI12_Depth_Para1 = 3000
```

---

### 3.1 TEST-V1: EmergencyTask 存活确认

**目的**: 确认 EmergencyTask 正常运行, 日志通路正常

**操作**:
```c
// 1. 确认任务存在
-> i
// 预期: 任务列表中有 "EmergencyTask", 状态 PEND (等待信号量)

// 2. 观察 UdpLogger 输出 (PC端 log_receiver.py)
// 预期: 每 0.5s 看到一条 "EmergencyTask start::::"
```

**预期输出 (PC 端 log_receiver.py)**:
```
[14:30:00.100] EmergencyTask start::::
[14:30:00.600] EmergencyTask start::::
[14:30:01.100] EmergencyTask start::::
```

**异常判断**:
| 现象 | 含义 | 处置 |
|------|------|------|
| 无输出 | EmergencyTask 未运行或 UdpLogger 故障 | `semShow semEmergencyTask` 检查; 检查网线连接 |
| 间隔不是 ~0.5s | 看门狗周期异常 | 检查 `sysClkRateGet()` 返回值 |
| 输出后系统卡死 | EmergencyTask 中死循环或信号量死锁 | 检查串口console是否有异常打印 |

---

### 3.2 TEST-V2: BUG-3 深度计数器滑动窗口

**目的**: 验证计数器能递增也能递减 (修复前只增不减)

**操作**:
```c
// 1. 设置深度报警阈值 (Para1=3m, 即 3000mm 编码)
-> UI_WIFI_Instruction.FromUI12_Depth_Para1 = 3

// 2. 注入当前深度为 5.0m (超过阈值)
-> Current_State.Current_Dep = 5.0

// 3. 等待 5s (10个EmergencyTask周期@2Hz), 观察计数器
-> printf("%d\n", Depth_Exceed_FromUI12_Depth_Para1)
// 预期: ≈10 (每周期+1)

// 4. 将深度改回 1.0m (低于阈值)
-> Current_State.Current_Dep = 1.0

// 5. 再等 5s, 观察计数器是否递减
-> printf("%d\n", Depth_Exceed_FromUI12_Depth_Para1)
// 预期: ≈0 (每周期-1, 递减到0停止)
```

**预期输出**:
```
步骤3: Depth_Exceed_FromUI12_Depth_Para1 ≈ 10
步骤5: Depth_Exceed_FromUI12_Depth_Para1 = 0
```

**异常判断**:
| 现象 | 含义 |
|------|------|
| 步骤3值持续为0 | 条件判断逻辑错误, 检查 `FromUI12_Depth_Para1` 单位 (注意: 代码中比较的是 `float Current_Dep > u16 Para1`) |
| 步骤5值不递减 | BUG-3 修复未生效, 检查 else 分支是否被编译 |
| 步骤5值负溢出 | u16 下溢 (不应发生, 有 `> 0` 守卫) |

> **注意**: `Current_State.Current_Dep` 是 float (单位:m), 而 `FromUI12_Depth_Para1` 是 u16。
> 代码中直接比较: `Current_Dep > FromUI12_Depth_Para1`。
> 如果 Para1=3000 表示 3000mm=3.0m, 那么需要确认代码是否做了单位换算。
> 从代码看: **直接比较, 无换算** → Para1=3 表示阈值为 3.0m? 还是 3000?
> 需要 HIL 时确认此处的单位语义。设置 `Para1=5` 然后注入 `Current_Dep=6.0` 来安全测试。

---

### 3.3 TEST-V3: BUG-4 超深自救输出验证

**目的**: 确认超深触发时不再归零推力, 而是输出 300RPM + 上浮舵

**操作**:
```c
// 1. 注入使计数器快速超限 (直接写计数器值)
-> Depth_Exceed_FromUI12_Depth_Para1 = 12
-> UI_WIFI_Instruction.FromUI12_Depth_Para1 = 5
-> Current_State.Current_Dep = 10.0

// 2. 等待 1 个 EmergencyTask 周期 (0.5s)
-> taskDelay(sysClkRateGet()/2)

// 3. 检查输出到 FMCU 的指令
-> printf("Motor1=%d\n", Instruction_To_FMCU.McuFD_Motor1_Set_Speed)
-> printf("LH_Rud=%d\n", Instruction_To_FMCU.McuFD_LH_Set_Rud_Location)
-> printf("RH_Rud=%d\n", Instruction_To_FMCU.McuFD_RH_Set_Rud_Location)

// 4. 检查 Sys_Abnorm 位
-> printf("Sys=0x%08x\n", Sys_Abnorm_Inf_Judgement)
```

**预期输出**:
```
Motor1=300                    (最低舵效航速)
LH_Rud=2276                   (2048 + 20*4096/360 ≈ 2048 + 227 = 2275)
RH_Rud=1820                   (2048 - 20*4096/360 ≈ 2048 - 227 = 1821)
Sys=0x00000200                (Bit9 置位)
```

> 舵角计算: `20.0 * 4096/360 ≈ 227.6 → 228`
> LH: `2048 + 228 = 2276` (满上浮)
> RH: `2048 - 228 = 1820` (满上浮)

**异常判断**:
| 现象 | 含义 |
|------|------|
| Motor1=0 | BUG-4 修复未生效, 仍为旧代码 |
| 舵角=2048 (中位) | 上浮舵角计算未执行 |
| Sys 无 Bit9 | 计数器未达到阈值, 检查注入值 |

---

### 3.4 TEST-V4: BUG-5 软限 (离底高度 < 3.0m)

**目的**: 验证软限预警 + 目标深度截断

**前提**: 需要系统处于 Jetson 模式

**操作**:
```c
// 1. 设置为 Jetson Shadow 模式
-> Current_State.Current_Mode = 0xEE
-> UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0xEE

// 2. 设置 Jetson 目标深度 = 20m (Para1=20000)
-> UI_WIFI_Instruction.FromUI12_Para1 = 20000

// 3. 设置当前深度 = 15.0m
-> Current_State.Current_Dep = 15.0

// 4. 注入 DVL 有效锁底 + 离底高度 2.5m (低于 soft_limit=3.0m)
-> DVL_Prase_Data.BD_Check = 2.0
-> DVL_Prase_Data.BD_Height = 2.5

// 5. 等待 3s (6个周期, 使 altitude_warning_count >= 5)
-> taskDelay(sysClkRateGet()*3)

// 6. 检查结果
-> printf("Sys=0x%08x\n", Sys_Abnorm_Inf_Judgement)
-> printf("Para1=%d\n", UI_WIFI_Instruction.FromUI12_Para1)
```

**预期输出**:
```
Sys=0x00000800    (Bit11 置位: 离底超限预警)
Para1=15000       (目标深度被截断为当前深度 15.0m*1000=15000)
```

**异常判断**:
| 现象 | 含义 |
|------|------|
| Bit11 未置位 | `altitude_warning_count` 未达阈值 (可能因2Hz需等更久) 或 BD_Check 判断异常 |
| Para1 未改变 (仍=20000) | 软限截断逻辑未执行, 检查模式判断 |
| Para1 变为负数 | int32 溢出, 检查 `(int)(Current_Dep*1000)` |

---

### 3.5 TEST-V5: BUG-5 硬限 (离底高度 < 1.8m)

**目的**: 验证硬限强制夺权 + HightCtrlAlgorithm 输出

**操作**:
```c
// 1. 保持 Jetson 模式 + DVL 锁底
-> Current_State.Current_Mode = 0xEE
-> DVL_Prase_Data.BD_Check = 2.0

// 2. 注入极低离底高度
-> DVL_Prase_Data.BD_Height = 1.2

// 3. 注入当前姿态 (HightCtrlAlgorithm 需要)
-> Current_State.Current_IMU_Pitch = 2.0
-> Current_State.Current_DVL_Velocity_Kn = 3.0
-> IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1] = 0.0

// 4. 等待 2s (使 altitude_critical_count >= 3 @2Hz)
-> taskDelay(sysClkRateGet()*2)

// 5. 检查输出
-> printf("Sys=0x%08x\n", Sys_Abnorm_Inf_Judgement)
-> printf("Motor1=%d\n", Instruction_To_FMCU.McuFD_Motor1_Set_Speed)
-> printf("LH=%d RH=%d\n", Instruction_To_FMCU.McuFD_LH_Set_Rud_Location, Instruction_To_FMCU.McuFD_RH_Set_Rud_Location)
```

**预期输出**:
```
Sys=0x00001800    (Bit11 + Bit12 同时置位)
Motor1=350        (硬限航速)
LH=xxxx RH=xxxx  (由 HightCtrlAlgorithm(4.0, 1.2, ...) 计算)
```

> HightCtrlAlgorithm(4.0, 1.2, 2.0, 0.0, 3.0) 预期:
> = -(3.0*(4.0-1.2)) + 1.5*(2.0+3.0) + 1.5*0.0
> = -8.4 + 7.5 + 0 = -0.9 (轻微上浮舵角)
> LH: 2048 - (-0.9)*4096/360 = 2048 + 10 ≈ 2058
> RH: 2048 + (-0.9)*4096/360 = 2048 - 10 ≈ 2038

**异常判断**:
| 现象 | 含义 |
|------|------|
| Motor1≠350 | 硬限逻辑未触发, 增加等待时间 |
| LH=RH=2048 | HightCtrlAlgorithm 返回 0 或未调用 |
| 舵角超出合理范围 | NaN 防御未生效, 检查 PID 参数 |

---

### 3.6 TEST-V6: BUG-6 DVL 丢底自救

**目的**: 验证 DVL 丢底超时后的模式降级 + 定深上浮

**操作**:
```c
// 1. 设置为 Jetson 模式, 当前深度 10m
-> Current_State.Current_Mode = 0xEE
-> UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0xEE
-> Current_State.Current_Dep = 10.0
-> Current_State.Current_IMU_Pitch = 0.0
-> Current_State.Current_DVL_Velocity_Kn = 3.0
-> IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1] = 0.0

// 2. 设置 DVL 丢底 (BD_Check 非 2.0/3.0)
-> DVL_Prase_Data.BD_Check = 0.0
-> DVL_Prase_Data.BD_Height = 0.0

// 3. 等待 11s @2Hz (使 dvl_lost_lock_count >= 20)
//    注意: 实际需要 10s, 多等 1s 确保
-> taskDelay(sysClkRateGet()*11)

// 4. 检查结果
-> printf("Sys=0x%08x\n", Sys_Abnorm_Inf_Judgement)
-> printf("CtrlMode=0x%02x\n", UI_WIFI_Instruction.FromUI12_Ctrl_Mode)
-> printf("Motor1=%d\n", Instruction_To_FMCU.McuFD_Motor1_Set_Speed)
```

**预期输出**:
```
Sys=0x00002000    (Bit13: DVL丢底降级)
CtrlMode=0x01     (降级到 Remote 模式)
Motor1=300        (维持舵效)
```

> DepthCtrlAlgorithm(2.0, 10.0, 0.0, 0.0, 3.0) 预期:
> = 4.0*(2.0-10.0) + 2.0*(0.0+3.0) + 2.0*0.0
> = -32.0 + 6.0 = -26.0 → clamp to -20.0 (满上浮)
> 触发上浮舵角 = -20° (满打)

**异常判断**:
| 现象 | 含义 |
|------|------|
| 等 11s 后 Bit13 未置位 | 频率确认: 可能 EmergencyTask 更慢, 增大等待 |
| CtrlMode 仍为 0xEE | 模式降级逻辑未执行, 检查 `Current_State.Current_Mode` 判断 |
| Motor1=0 | 旧 Jetson 失联逻辑可能先触发 (检查 `Not_Recv_From_Jetson_No`) |

> **重要**: 此测试中 `Not_Recv_From_Jetson_No` 也在递增 (无真实 Jetson)。
> 需要在测试前定期清零: `Not_Recv_From_Jetson_No = 0`
> 或使用自动化脚本持续发送 Jetson 心跳包 (推荐)。

---

### 3.7 TEST-V8: Jetson 失联看门狗

**目的**: 确认 1.0s 无 Jetson 数据时正确降级

**操作**:
```c
// 1. 设置为 Jetson Shadow 模式
-> Current_State.Current_Mode = 0xEE
-> UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0xEE
-> UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 400
-> UI_WIFI_Instruction.FromUI12_Motor_Speed2 = 400

// 2. 模拟 Jetson 失联 (计数器超阈值)
-> Not_Recv_From_Jetson_No = 15

// 3. 等待 1 个 EmergencyTask 周期
-> taskDelay(sysClkRateGet()/2)

// 4. 检查降级
-> printf("CtrlMode=0x%02x\n", UI_WIFI_Instruction.FromUI12_Ctrl_Mode)
-> printf("Motor1=%d Motor2=%d\n", UI_WIFI_Instruction.FromUI12_Motor_Speed1, UI_WIFI_Instruction.FromUI12_Motor_Speed2)
-> printf("Sys=0x%08x\n", Sys_Abnorm_Inf_Judgement)
```

**预期输出**:
```
CtrlMode=0x01     (降级到 Remote)
Motor1=0 Motor2=0 (双电机停)
Sys=0x00004000    (Bit14: Jetson通信超时)
```

---

### 3.8 TEST-V10: NaN 防御 (BUG-1)

**目的**: 验证 PID 输出为 NaN 时舵角不溢出

**操作**:
```c
// 1. 确保在 Jetson Shadow 模式, 系统在运行 Jetson_Shadow_Proces
-> Current_State.Current_Mode = 0xEE
-> UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0xEE
-> Not_Recv_From_Jetson_No = 0

// 2. 注入 NaN 到航向 PID 参数 (使 Course_Keep_Algorithm 输出 NaN)
//    IEEE754 quiet NaN: 0x7FC00000
-> *((unsigned int *)&CourseCtrl_para1) = 0x7fc00000

// 3. 等待主控制循环执行 (0.1s)
-> taskDelay(sysClkRateGet()/10)

// 4. 检查垂直舵角是否为中位 (NaN被clamp为0, 中位2048不变)
-> printf("UV=%d LV=%d\n", Instruction_To_FMCU.McuFD_UV_Set_Rud_Location, Instruction_To_FMCU.McuFD_LV_Set_Rud_Location)

// 5. 恢复正常 PID 参数
-> CourseCtrl_para1 = 2.0
```

**预期输出**:
```
UV=2048 LV=2048   (NaN被检测, course_pid_output=0, 舵角=中位)
```

**异常判断**:
| 现象 | 含义 |
|------|------|
| UV/LV = 0 或 65535 | NaN 检测未生效, u16 溢出! 严重 bug |
| UV/LV = 中位±小偏差 | 可能 MainCtrlTask 未进入 Jetson_Shadow_Proces, 检查模式 |

---

### 3.9 TEST-V9: 状态回传验证

**目的**: 确认 `Sys_Abnorm_Inf_Judgement` 能通过 UDP 上行帧回传到 PC

**操作**:
```c
// 1. 在 PC 端启动 sniffer
//    python scripts/sniffer.py --bind-port 52365 --ascii-format

// 2. 在 VxWorks shell 中手动置位
-> Sys_Abnorm_Inf_Judgement = 0xDEADBEEF

// 3. 观察 PC 端 sniffer 输出中 Sys_Abnorm_Inf 字段
//    (位于上行帧 byte[126-129], 大端)
```

**预期**: sniffer 中能看到对应字段变为 `DE AD BE EF`

---

## 四、自动化验证工具

### 4.1 工具架构

```
PC (192.168.0.11)                         VxWorks PC104 (192.168.0.101)
┌────────────────────────┐                ┌──────────────────────────────┐
│ vxworks_safety_hil.py  │                │                              │
│                        │───UDP:21──────>│ NetRecvTask (模拟上位机指令)  │
│                        │<──UDP:52365────│ NetSendTask (接收状态反馈)   │
│                        │<──UDP:52367────│ UdpLogger   (接收printf日志) │
│                        │                │                              │
│  ┌─ Test Runner ─────┐ │                │  EmergencyTask               │
│  │ inject_depth()    │ │                │  MainCtrlTask                │
│  │ inject_dvl()      │ │                │  Seafloor_Grounding_Arb()    │
│  │ check_sys_abnorm()│ │                │  Pool_Safety_Check()         │
│  │ check_motor()     │ │                │  Jetson_Shadow_Proces()      │
│  └───────────────────┘ │                │                              │
└────────────────────────┘                └──────────────────────────────┘
```

### 4.2 限制说明

自动化脚本可以:
- 通过 UDP 发送 $CKTH 控制帧 → 填充 `UI_WIFI_Instruction` (模拟上位机/Jetson)
- 接收 $AUV 上行帧 → 读取 `Sys_Abnorm_Inf` 等状态位
- 接收 UdpLogger 日志 → 确认代码路径执行

自动化脚本**不能**:
- 直接写入 `DVL_Prase_Data`, `Current_State.Current_Dep` (这些来自串口硬件)
- 直接读取 `Instruction_To_FMCU` 内部值 (需通过上行帧间接获取)
- 注入 NaN (需 shell 操作)

→ **结论**: 完全自动化需要 **Shell 脚本** + **UDP 脚本** 配合。
→ 对于不依赖传感器注入的场景 (如 Jetson 心跳/失联, 深度指令下发), UDP 脚本可独立完成。
→ 对于需要传感器注入的场景 (DVL/深度), 需要人工在 Shell 中操作, 或通过 telnet 自动化。

### 4.3 使用方式

```bash
# 方式1: 纯 UDP 自动化 (验证通信通路 + 心跳 + 状态回传)
python scripts/vxworks_safety_hil.py --mode auto-udp

# 方式2: 交互式引导 (脚本提示你在 Shell 中输入什么, 然后自动验证结果)
python scripts/vxworks_safety_hil.py --mode guided

# 方式3: Telnet 全自动 (如果 VxWorks 开启了 telnetd)
python scripts/vxworks_safety_hil.py --mode telnet --host 192.168.0.101
```

---

## 五、测试执行检查单

| # | 测试 | 方法 | 通过标准 | 结果 |
|---|------|------|---------|------|
| 1 | EmergencyTask 存活 | V1 | log_receiver 收到周期性打印 | □ |
| 2 | 深度计数器递增 | V2-step3 | 计数器 > 0 | □ |
| 3 | 深度计数器递减 | V2-step5 | 计数器回到 0 | □ |
| 4 | 超深输出 Motor=300 | V3 | Motor1=300, 非0 | □ |
| 5 | 超深输出上浮舵 | V3 | LH≈2276, RH≈1820 | □ |
| 6 | DVL 软限 Bit11 | V4 | Sys & 0x800 != 0 | □ |
| 7 | DVL 软限截断 Para1 | V4 | Para1 = Current_Dep*1000 | □ |
| 8 | DVL 硬限 Bit12 | V5 | Sys & 0x1000 != 0 | □ |
| 9 | DVL 硬限 Motor=350 | V5 | Motor1=350 | □ |
| 10 | DVL 丢底 Bit13 | V6 | Sys & 0x2000 != 0 | □ |
| 11 | DVL 丢底模式降级 | V6 | CtrlMode=0x01 | □ |
| 12 | Jetson 失联 Bit14 | V8 | Sys & 0x4000 != 0 | □ |
| 13 | Jetson 失联停机 | V8 | Motor1=0, Motor2=0 | □ |
| 14 | NaN 防御 - 舵角中位 | V10 | UV=2048, LV=2048 | □ |
| 15 | 状态回传到 PC | V9 | sniffer 能读到 Sys 值 | □ |
| 16 | EmergencyTask 频率 | 手动计时 | 确认 0.5s 或调整为 0.1s | □ |

---

## 六、后续行动项

1. **[立即]** HIL 时首先执行 TEST-V1 确认基本通路
2. **[立即]** 确认 `FromUI12_Depth_Para1` 的单位语义 (mm? m? 原始u16?)
3. **[高优先级]** 验证 EmergencyTask 实际频率, 决定是否将 `Emergency_Task_Period` 改为 1
4. **[中优先级]** 在 HIL 通过后, 进行 `Emergency_Task_Period=1` 的重编译验证
5. **[低优先级]** 如果 VxWorks 开启 telnetd, 实现全自动 telnet 注入脚本
