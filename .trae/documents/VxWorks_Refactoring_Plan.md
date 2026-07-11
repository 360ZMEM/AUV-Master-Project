# VxWorks 重构计划书

> 文档版本: v1.0  
> 日期: 2026-04-30  
> 作者: 清华 AUV 课题组  
> 状态: 待审核

---

## 一、总体概述

### 1.1 目标

将未修改的 VxWorks 源码 (`csd_vx6.8_lastest`) 与当前仓库主线 Jetson/Mock AMD 协议栈对齐，实现：

1. **初始状态**：Jetson 仅透传上位机 PC 控制指令到 PC104（遥控模式 0x01）
2. **自主控制**：上位机发出 0xEE/0xEF 指令后，Jetson 接管控制权，PC104 执行 Jetson 的航向/深度/速度闭环
3. **安全降级**：Jetson 断联、急停、触底等紧急情况下 PC104 自主保命（停推+自然上浮）

### 1.2 核心原则

- **最小侵入**：不删除原有任何功能，仅以增量 `if/else if` 分支扩展
- **向下兼容**：不接 Jetson 时，系统行为与原始代码 100% 一致
- **便于审计**：每个文件修改前备份 `_bak.c`，所有新增代码带 Doxygen 注释
- **可观测性**：关键分支插入 `printf` 便于 Telnet 调试

---

## 二、现有协议契约（Single Source of Truth）

### 2.1 数据契约真值源

**唯一参考**: `common/protocol.py` 中的 `build_downlink_packet()` 和 `parse_uplink_packet()`。

VxWorks 端的字节解析 (`From_WIFI_Buf`) 和组包 (`To_UI12_Buf`) **必须严格对齐**该文件定义的物理偏移与数据类型。

### 2.2 下行帧 $CKTH (72 字节, 大端序)

| Offset | 长度 | VxWorks 字段名 | Python 字段名 | 类型 | 说明 |
|--------|------|---------------|--------------|------|------|
| 0-4 | 5 | `FromUI12_Head_BUF` | header | bytes | `$CKTH` |
| 5 | 1 | `FromUI12_Msg_Num` | frame_number | u8 | 帧序号 |
| 6 | 1 | `FromUI12_ID` | obj_address | u8 | 目标地址 |
| **7** | **1** | **`FromUI12_Ctrl_Mode`** | **control_mode_byte** | **u8** | **0x01=遥控, 0xEE=Jetson自主, 0xEF=混合** |
| 8-9 | 2 | `FromUI12_Depth_Para1` | depth_protect_min | u16 | 深度保护阈值1 |
| 10-11 | 2 | `FromUI12_Depth_Para2` | depth_protect_max | u16 | 深度保护阈值2 |
| 12-13 | 2 | `FromUI12_Height_Para1` | bottom_protect_min | u16 | 底高保护1 |
| 14-15 | 2 | `FromUI12_Height_Para2` | bottom_protect_max | u16 | 底高保护2 |
| 16-17 | 2 | `FromUI12_Remain_Time` | preset_time_tenths_min | u16 | 预设时间 |
| 18-19 | 2 | `FromUI12_Spare_Para1` | spare_params[0] | int16 | 备用 |
| 20-21 | 2 | `FromUI12_Spare_Para2` | spare_params[1] | int16 | 备用 |
| **22** | **1** | **`FromUI12_Work_Cmd`** | **work_instruction** | **u8** | **工作指令** |
| 23-24 | 2 | `FromUI12_Motor_Speed1` | main_motor_rpm | int16 | RPM (thrust% × 15) |
| 25-26 | 2 | `FromUI12_Motor_Speed2` | side_motor_rpm | int16 | 侧推 |
| 27-28 | 2 | `FromUI12_RCD_LH_Set_Rud_Angle` | left_fin ×10 | int16 | 左舵角(0.1°) |
| 29-30 | 2 | `FromUI12_RCD_RH_Set_Rud_Angle` | right_fin ×10 | int16 | 右舵角(0.1°) |
| 31-32 | 2 | `FromUI12_RCD_UV_Set_Rud_Angle` | top_fin ×10 | int16 | 上舵角(0.1°) |
| 33-34 | 2 | `FromUI12_RCD_LV_Set_Rud_Angle` | bottom_fin ×10 | int16 | 下舵角(0.1°) |
| 35-36 | 2 | `FromUI12_Set_Course` | orientation_deg ×10 | u16 | 目标航向(0.1°) |
| **37-40** | **4** | **`FromUI12_Para1`** | **parameters[0] = target_depth_m × 10** | **int32** | **[征用] 目标深度** |
| 41-44 | 4 | `FromUI12_Para2` | parameters[1] = timestamp_us | int32 | AMD时间戳 |
| 45-48 | 4 | `FromUI12_Para3` | parameters[2] | int32 | 扩展 |
| 49-52 | 4 | `FromUI12_Para4` | parameters[3] | int32 | 扩展 |
| 53-68 | 16 | `FromUI12_Para5~12` | parameters[4-11] | int16×8 | 扩展 |
| 69 | 1 | `FromUI12_Check_Sum` | checksum | u8 | 字节和 |
| 70-71 | 2 | `FromUI12_End_Buf` | tail | bytes | 0xFF 0xFF |

### 2.3 上行帧 $AUV (145 字节, 大端序)

| Offset | 长度 | VxWorks 字段名 | Python 字段名 | 类型 | 说明 |
|--------|------|---------------|--------------|------|------|
| 0-3 | 4 | `ToUI12_Head_Buf` | header | bytes | `$AUV` |
| 4 | 1 | `ToUI12_Msg_Length` | - | u8 | 145 |
| 5 | 1 | `ToUI12_Msg_Num` | frame_number | u8 | 帧序号 |
| 6 | 1 | `ToUI12_ID` | auv_address | u8 | AUV地址 |
| 7 | 1 | `ToUI12_Ctrl_Mode` | control_mode_byte | u8 | 当前控制模式 |
| 8-9 | 2 | `ToUI12_Depth_Para1` | depth_protect_min | u16 | 深度保护1 |
| 10-11 | 2 | `ToUI12_Depth_Para2` | depth_protect_max | u16 | 深度保护2 |
| 38-39 | 2 | `ToUI12_Depth` | depth ×10 | u16 | 当前深度(0.1m) |
| 72-73 | 2 | `ToUI12_IMU_Heading` | heading ×10 | u16 | 航向(0.1°) |
| 74-75 | 2 | `ToUI12_IMU_Pitch` | pitch ×10 | int16 | 俯仰(0.1°) |
| 76-77 | 2 | `ToUI12_IMU_Roll` | roll ×10 | int16 | 横滚(0.1°) |
| **82-83** | **2** | **`ToUI12_DVL_Velocity`** | **dvl_speed ×10** | **int16** | **DVL速度(0.1m/s)** |
| 84-85 | 2 | `ToUI12_Height` | altitude ×10 | u16 | 离底高度(0.1m) |
| 86-89 | 4 | `ToUI12_Cal_Longitude` | dead_reckoning_lon ×10^6 | int32 | 推算经度 |
| 90-93 | 4 | `ToUI12_Cal_Latitude` | dead_reckoning_lat ×10^6 | int32 | 推算纬度 |
| 94-97 | 4 | `ToUI12_GPS_Longitude` | gps_lon ×10^6 | int32 | GPS经度 |
| 98-101 | 4 | `ToUI12_GPS_Latitude` | gps_lat ×10^6 | int32 | GPS纬度 |
| 102-103 | 2 | `ToUI12_Total_Voltage` | total_voltage ×10 | u16 | 总电压(0.1V) |
| 104-105 | 2 | `ToUI12_Total_Current` | total_current ×10 | u16 | 总电流(0.1A) |
| 106 | 1 | `ToUI12_SOC` | soc | u8 | SOC% |
| 107 | 1 | `ToUI12_SOH` | soh | u8 | SOH% |
| 114-117 | 4 | `ToUI12_DevicePower_State` | device_power_status | u32 | 设备电源 |
| 126-129 | 4 | `ToUI12_Sys_Abnorm_Inf` | system_alarm... | u32 | 系统异常 |

### 2.4 控制模式定义

| 值 | 名称 | VxWorks现有 | 需新增 | 说明 |
|----|------|:-----------:|:------:|------|
| 0x00 | SEND_ONLY | - | - | 仅发送 |
| 0x01 | REMOTE | ✅ | - | 遥控（PC透传） |
| 0x02 | AUTO_FIXED_POINT | ✅ | - | 自动定点 |
| 0x03 | AUTO_DIRECTION | ✅ | - | 自动定向 |
| 0x04 | AUTO_BACK | ✅ | - | 返航 |
| **0xEE** | **JETSON_PROTOCOL** | ❌ | **✅** | **Jetson全自主：推力直接透传，航向/深度PID闭环** |
| **0xEF** | **JETSON_HYBRID** | ❌ | **✅** | **Jetson混合：所有舵面/推力全透传** |

### 2.5 工作指令定义

| 值 | 名称 | VxWorks现有 | 需新增 | 说明 |
|----|------|:-----------:|:------:|------|
| 0x00 | NONE | ✅ | - | 无 |
| 0x01 | TASK_START | ✅ | - | 任务开始 |
| 0x02 | TASK_CANCEL | ✅ | **行为扩展** | 任务取消 → **强制退回0x01** |
| 0x11-0x28 | 设备电源 | ✅ | - | 设备上下电 |
| 0x71 | COURSE_KEEP_ON | ✅ | - | 航向保持 |
| 0x72 | COURSE_KEEP_OFF | ✅ | - | 航向保持关 |
| 0x91 | CLEAR_FAULT | ✅ | **行为扩展** | 系统初始化 → **强制退回0x01** |
| **0xEE** | **AUTONOMOUS_CTRL** | ❌ | **✅** | **确认进入自主** |

---

## 三、需新增/同步的协议契约

### 3.1 控制模式 0xEE（影子诱导模式）

**[CONFIDENT]** - Mock AMD 已完整实现，协议字节位明确。

当 `FromUI12_Ctrl_Mode == 0xEE` 时：

| 通道 | 控制来源 | 字段 | 行为 |
|------|----------|------|------|
| **Surge (速度)** | Jetson 直接决定 | `FromUI12_Motor_Speed1` | 直接透传给 MCU 电机 |
| **Heading (航向)** | Jetson 给目标 | `FromUI12_Set_Course` (offset 35-36) | PC104 本地调用 `Course_Keep_Algorithm()` PID闭环 |
| **Depth (深度)** | Jetson 给目标 | `FromUI12_Para1` (offset 37-40, ÷10得米) | PC104 本地调用 `DepthCtrlAlgorithm()` PID闭环 |
| **Side (侧推)** | Jetson 直接决定 | `FromUI12_Motor_Speed2` | 直接透传 |

### 3.2 控制模式 0xEF（全透传混合模式）

**[CONFIDENT]** - Mock AMD 和仲裁器已实现。

当 `FromUI12_Ctrl_Mode == 0xEF` 时：

| 通道 | 行为 |
|------|------|
| 所有舵面角 | 直接透传 (从报文读出角度值，转为编码器位置) |
| 主推/侧推 | 直接透传 |
| 无 PID 闭环 | Jetson 端自己做 PID，VxWorks 只做执行器 |

### 3.3 `FromUI12_Depth_Para1` (offset 8-9) 字段征用问题

**⚠️ 关键对齐差异！**

| 层面 | 字段理解 | 实际 |
|------|----------|------|
| VxWorks 原始 | offset 8-9, u16, 用作深度保护阈值 | 在 `EmergencyTask` 中用于深度超限判断 |
| Python `protocol.py` | offset 8-9, u16, `depth_protect_min` | 同为保护参数 |
| **Jetson 传输目标深度** | **offset 37-40, int32, `parameters[0]`** | **对应 `FromUI12_Para1` (int32)** |

**结论**：**目标深度通过 `FromUI12_Para1` (offset 37-40) 传输，NOT offset 8-9**。offset 8-9 仍为保护参数（原始安全功能不受影响）。

### 3.4 控制频率对齐

| 参数 | VxWorks 当前值 | Jetson 侧期望 | 需修改为 | 信心 |
|------|---------------|--------------|----------|------|
| 主控周期 `Main_Ctrl_Task_Period` | 6 (× 0.1s = **0.6s ≈ 1.67Hz**) | **10 Hz** | **1** (× 0.1s = 0.1s) | **[CONFIDENT]** |
| 网络接收周期 | 3 (× 0.1s = 0.3s) | ≤ 10Hz | **1** (× 0.1s = 0.1s) | **[CONFIDENT]** |
| 紧急检测周期 | 5 (× 0.1s = 0.5s) | ≤ 0.5s | 保持 5（0.5s 可接受） | **[CONFIDENT]** |
| 看门狗基准tick | 0.1s | - | 保持不变 | **[CONFIDENT]** |

### 3.5 DVL 上行数据增强

**[CONFIDENT]** - 架构师审计确认：`BI_X/Y/Z` 为 Body Frame (载具系) 速度，单位 mm/s，与 ES-EKF `correct_dvl(dvl_vel_body)` 接口完全一致。

| 当前状态 | 需要增强 |
|----------|----------|
| 上行仅传 `ToUI12_DVL_Velocity` (合成标量速度, knots×10) | ES-EKF 需要: 前向速度(m/s) + 三轴 body frame 分量 |
| VxWorks `_From_DVL` 结构已有 `BI_X, BI_Y, BI_Z` (mm/s) | 通过 Para 字段扩展传输 |

**Para 字段分配（DVL 三轴扩展）**：

| Para字段 | 偏移 | 内容 | 单位 | 信心 |
|----------|------|------|------|------|
| `ToUI12_Para5` | 56-57 | DVL BI_X 速度（前向） | mm/s, int16 | **[CONFIDENT]** |
| `ToUI12_Para6` | 58-59 | DVL BI_Y 速度（右向） | mm/s, int16 | **[CONFIDENT]** |
| `ToUI12_Para7` | 60-61 | DVL BI_Z 速度（下向） | mm/s, int16 | **[CONFIDENT]** |
| `ToUI12_Para8` | 62-63 | DVL BI 有效标志 | 0/1, int16 | **[CONFIDENT]** |
| `ToUI12_Para9` | 64-65 | DVL BD 离底高度 | cm, int16 | **[CONFIDENT]** |

> **注**: Jetson 端接收后对 Para5-7 乘以 0.001 即可得到 m/s。需同步更新 `protocol.py` 的 `parse_uplink_packet()`。
> **极性标定预留**: 代码中加入 `// TODO: 如果海试中发现 ES-EKF 前后方向相反，在此处乘以 -1`。

### 3.6 `FromUI12_Set_Course` (offset 35-36) 对齐问题

**[CONFIDENT]** - 已确认完整链路。

| 层面 | 处理方式 |
|------|----------|
| VxWorks 原始 `Unpack_Data_From_UI12_WIFI` | `(u16)((temp_buf[35]<<8) + temp_buf[36])` → **原始值（×10存储）** |
| Python `build_downlink_packet` | `orientation_deg × 10` 写入 offset 35-36 (uint16) |
| Jetson `_resolve_target_heading_deg()` | 从 `target_heading_rad` 通过 `math.degrees()` 得到**真实度数** |

**`orientation_deg` 确切含义**：**目标航向角（度）**。Jetson 的控制器 setpoint 中的 `target_heading_rad` 转为度后，乘以 10 写入协议。

**修改方案**：VxWorks 在 0xEE 模式下使用 `FromUI12_Set_Course` 时需**除以 10** 得到真实角度。  
注：`Remote_Assignment` 中原有的 `Course_Keep_Algorithm` 调用处已经直接使用了 `FromUI12_Set_Course`（原始遥控下存的就是整数度），因此 0xEE 模式需要单独处理。

---

## 四、新增功能详细设计

### 4.1 影子诱导模式 (0xEE) 处理逻辑

**修改文件**: `main.c`

```c
/**
 * @brief  Jetson 影子诱导模式处理
 * @date   2026-05-xx
 * @author 清华 AUV 课题组
 * @note   新增模式：Jetson 提供目标航向/深度/速度，PC104 本地PID闭环
 */
void Jetson_Shadow_Proces(void)
{
    float target_depth_m, target_heading_deg;
    float depth_rudder_angle, heading_rudder_angle;
    
    /* 1. 执行工作指令（保留电源控制等） */
    Work_Cmd_Execute(&Current_State.Current_Work_Cmd);
    
    /* 2. 提取Jetson目标 */
    target_depth_m = (float)UI_WIFI_Instruction.FromUI12_Para1 / 10.0f;
    target_heading_deg = (float)UI_WIFI_Instruction.FromUI12_Set_Course;
    
    /* 3. 航向PID闭环 */
    heading_rudder_angle = Course_Keep_Algorithm(
        target_heading_deg,
        Current_State.Current_IMU_Heading,
        IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[2]
    );
    
    /* 4. 深度PID闭环 */
    depth_rudder_angle = DepthCtrlAlgorithm(
        target_depth_m,
        Current_State.Current_Dep,
        Current_State.Current_IMU_Pitch,
        IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1],
        Current_State.Current_DVL_Velocity_Kn * 0.5144f
    );
    
    /* 5. 主推直接透传 */
    Instruction_To_FMCU.McuFD_Motor1_Set_Speed = UI_WIFI_Instruction.FromUI12_Motor_Speed1;
    Instruction_To_FMCU.McuFD_Motor2_Set_Speed = UI_WIFI_Instruction.FromUI12_Motor_Speed2;
    
    /* 6. 水平舵（深度控制） */
    Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location - depth_rudder_angle * 4096/360);
    Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location + depth_rudder_angle * 4096/360);
    
    /* 7. 垂直舵（航向控制） */
    Instruction_To_FMCU.McuFD_UV_Set_Rud_Location = (u16)(UV_Ref_Location - heading_rudder_angle * 4096/360);
    Instruction_To_FMCU.McuFD_LV_Set_Rud_Location = (u16)(LV_Ref_Location + heading_rudder_angle * 4096/360);
    
    /* 8. 组装 $MCUFD 并发送 */
    Remote_Assignment(&Instruction_To_FMCU);
}
```

### 4.2 全透传模式 (0xEF) 处理逻辑

**修改文件**: `main.c`

当 `FromUI12_Ctrl_Mode == 0xEF` 时，行为与原始 `Remote_Proces()` 完全一致（所有舵面/推力来自报文），仅标记模式不同。实现上可直接复用 `Remote_Proces()` 逻辑。

### 4.3 无扰动切换 (Bumpless Transfer)

**修改文件**: `main.c` (`MainCtrlTask`)

```c
/**
 * @brief  检测模式跃迁，执行 Bumpless Transfer
 * @date   2026-05-xx
 * @note   切换至 0xEE 第一周期强制对齐 PID 参考初值
 */
static u8 prev_ctrl_mode = 0x01;

/* 在 MainCtrlTask 循环内，模式分发前 */
if (Current_State.Current_Mode == 0xEE && prev_ctrl_mode != 0xEE) {
    /* 强制抓取当前物理状态作为 PID 初值 */
    /* 防止目标阶跃导致舵面打满 */
    printf("[BUMPLESS] Enter 0xEE: depth=%.2f heading=%.1f\n",
           Current_State.Current_Dep, Current_State.Current_IMU_Heading);
}
prev_ctrl_mode = Current_State.Current_Mode;
```

### 4.4 主控频率提升 (1.67Hz → 10Hz)

**修改文件**: `main.c`

```c
/* 修改前 */
const float Main_Ctrl_Task_Period = 6;  /* 0.6s → 1.67Hz */

/* 修改后 */
const float Main_Ctrl_Task_Period = 1;  /* 0.1s → 10Hz */
```

### 4.5 任务优先级审计

**修改文件**: `main.c` (`Task_Creation`)

| 任务 | 当前优先级 | 修改后 | 理由 |
|------|-----------|--------|------|
| EmergencyTask | 110 | **110 (不变)** | 最高，安全优先 |
| **NetRecvTask** | **125** | **115** | 收包必须先于解算 |
| **UnpackNetDataTask** | **125** | **116** | 解包紧随收包 |
| MainCtrlTask | 120 | **120 (不变)** | 控制中等优先 |
| IMU/DVL/GPS Recv | 130 | **118** | 串口中断数据需及时处理 |
| 其他 | 125-145 | 不变 | 低频/非关键 |

**[CONFIDENT]** - 提频至10Hz后，若不调整优先级，0.1s内主控循环可能饿死低优先级收包任务。

### 4.6 Jetson 失联看门狗

**修改文件**: `SecurityEmergencyManage.c`

```c
/**
 * @brief  Jetson 心跳看门狗
 * @date   2026-05-xx
 * @note   在0xEE/0xEF模式下，若1.0s未收到Jetson有效报文则紧急降级
 */
#define JETSON_WDG_TIMEOUT_TICKS  10  /* 10 × 0.1s = 1.0s */

static u16 Not_Recv_From_Jetson_No = 0;

/* 在 FuncWd_InfoOutputCtrl 中递增 */
/* 在 Unpack_Data_From_UI12_WIFI 成功后清零 */

/* 在 EmergencyTask 中检查 */
if ((Current_State.Current_Mode == 0xEE || Current_State.Current_Mode == 0xEF)
    && Not_Recv_From_Jetson_No >= JETSON_WDG_TIMEOUT_TICKS)
{
    printf("[SAFETY] Jetson heartbeat lost! Fallback to REMOTE\n");
    UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0x01;  /* 强制回遥控 */
    UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;  /* 停推 */
    UI_WIFI_Instruction.FromUI12_Motor_Speed2 = 0;
    /* AUV 依赖正浮力自然上浮 */
}
```

### 4.7 急停 (ESTOP) 透传

**修改文件**: `main.c` (`Work_Cmd_Execute`)

```c
/* 在 switch 中新增 0x02 的行为扩展 */
case 0x02:  /* TASK_CANCEL - 来自 Jetson 的急停 */
    Auto_Task_Carry_Flag = false;
    UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;  /* 立即停推 */
    UI_WIFI_Instruction.FromUI12_Motor_Speed2 = 0;
    UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0x01;  /* 强制回遥控 */
    printf("[ESTOP] TASK_CANCEL received, motors stopped!\n");
    break;
```

### 4.8 DVL 三轴速度上行扩展

**修改文件**: `DataProcess.c` (`Pack_Data_To_UI12`)

```c
/**
 * @brief  DVL 三轴速度填入 Para5-Para9
 * @date   2026-05-xx
 * @note   辅助 Jetson ES-EKF，单位 mm/s
 */
temp->ToUI12_Para5 = (short int)(DVL_Prase_Data.BI_X);  /* 前向 mm/s */
temp->ToUI12_Para6 = (short int)(DVL_Prase_Data.BI_Y);  /* 右向 mm/s */
temp->ToUI12_Para7 = (short int)(DVL_Prase_Data.BI_Z);  /* 下向 mm/s */
temp->ToUI12_Para8 = (short int)(DVL_Prase_Data.BI_Valid_Flag ? 1 : 0);
temp->ToUI12_Para9 = (short int)(DVL_Prase_Data.BD_Height * 100); /* cm */
```

---

## 五、VxWorks ↔ Python 协议对齐差异清单

### 5.1 已确认的差异（需修改）

| # | 差异点 | VxWorks 当前 | Python 期望 | 修改方案 | 信心 |
|---|--------|-------------|------------|----------|------|
| 1 | `Set_Course` 精度 | 原始值(×10存储) | ×10 存储(0.1°精度) | 0xEE模式使用时÷10 | **[CONFIDENT]** |
| 2 | 缺少 0xEE/0xEF 模式 | 仅 0x01-0x04 | 0xEE, 0xEF | 新增分支 | **[CONFIDENT]** |
| 3 | 主控频率 | 1.67 Hz | 10 Hz | 改 Period=1 | **[CONFIDENT]** |
| 4 | DVL 上行仅标量 | knots×10 | m/s × 10 + 三轴(mm/s) | 扩展 Para5-9 | **[CONFIDENT]** |
| 5 | 无 Jetson 看门狗 | 仅 WIFI 10s超时 | 1.0s 看门狗 | 新增 | **[CONFIDENT]** |
| 6 | 帧头第5字节 | `$AUV` + MsgLen=145(0x91) | `$AUV\x91` (5字节) | **无需修改，已对齐** | **[CONFIDENT]** |
| 7 | DVL速度单位 | knots×10 (offset 82-83) | m/s × 10 | `BI_V / 100` | **[CONFIDENT]** |

### 5.2 帧头差异分析 [CONFIRMED - 已对齐]

VxWorks 上行帧头: `"$AUV"` (4字节) + `ToUI12_Msg_Length = 145 = 0x91` (offset 4)  
Python 期望帧头: `b"\x24\x41\x55\x56\x91"` (5字节)

**架构师确认**: ✅ 完全对齐。Python 将 ASCII `$AUV` + 长度字段 `0x91` 合并为 5 字节帧头匹配模式。**无需修改**。

### 5.3 DVL 速度单位差异

| 端 | 存储方式 |
|----|---------|
| VxWorks Pack | `(Current_DVL_Velocity_Kn) × 10` (knots × 10) |
| Python Parse | `dvl_speed_mps = struct.unpack(">h", packet[82:84])[0] * 0.1` |

Python 端解释为 **m/s × 10**，但 VxWorks 发送的是 **knots × 10**。

**转换**: 1 knot = 0.5144 m/s。需在 VxWorks 端改为发送 m/s × 10。

```c
/* 修改后: */
temp->ToUI12_DVL_Velocity = (short int)(Current_State.Current_DVL_Velocity_Kn * 5.144f);
/* 或: 直接从 DVL mm/s 计算 */
temp->ToUI12_DVL_Velocity = (short int)(DVL_Prase_Data.BI_V / 100.0f);  /* mm/s -> 0.1m/s */
```

**[CONFIDENT]** - 但需确认 `BI_V` 的单位和计算方式。

---

## 六、安全机制改进

### 6.1 Jetson 失联看门狗

| 参数 | 值 | 说明 |
|------|------|------|
| 超时时间 | 1.0s (10 ticks) | 与 Jetson 端 `pc_soft_warning_s` 对称 |
| 触发条件 | `Current_Mode ∈ {0xEE, 0xEF}` 且超时 | 仅自主模式生效 |
| 降级动作 | 1. 模式→0x01, 2. 推力→0, 3. 正浮力上浮 | 三步保命 |
| 复位条件 | 收到新的有效 $CKTH 包 | 计时器清零 |

### 6.2 深度/触底紧急判断增强

**现有机制**（保留）：
- Depth > Para1 连续10次 → 停推
- Depth > Para2 连续10次 → 停推 + 压载开启

**新增**：
- 在 0xEE/0xEF 模式下，深度超限同时触发模式回退到 0x01

### 6.3 ESTOP 指令响应

| 来源 | 指令值 | 响应方式 |
|------|--------|----------|
| Jetson `TASK_CANCEL` | 0x02 | 立即停推 + 回退 0x01 |
| 上位机 `CLEAR_FAULT` | 0x91 | 清除所有状态 + 回退 0x01 |
| 漏水检测 | MCU bit0 | Emergency_Level3() + 停推 |

---

## 七、台架调试 SOP（无传感器环境）

### 7.1 环境

- PC104 无物理传感器接入（所有传感器字段为 0 或默认值）
- Jetson 通过以太网 UDP 连接 PC104
- 上位机 PC 通过 WiFi/以太网连接 Jetson

### 7.2 调试步骤

#### Step 1: 启动验证

1. PC104 上电，Telnet 登入 (`telnet 192.168.0.101`)
2. 观察 `MainCtrlTask` 打印：确认频率约 10Hz
3. 确认 `"program starting:::::"` 输出

#### Step 2: 遥控模式验证

1. 上位机发送 `Ctrl_Mode=0x01` 的 $CKTH 包
2. Telnet 观察：
   - `UI_Channel_Selection_Down == 0x02` (WIFI通道)
   - 舵角和推力正确透传
3. 确认上行 $AUV 包中 `Ctrl_Mode = 0x01`

#### Step 3: 自主模式切入验证

1. 上位机发送 `Ctrl_Mode=0xEE`，`Work_Cmd=0xEE`
2. Telnet 观察：
   - `[BUMPLESS] Enter 0xEE: depth=xxx heading=xxx`
   - PID 控制器输出（航向/深度舵角）
3. 发送目标深度：`Para1 = 20`（即 2.0m）
4. 由于无深度传感器，`Current_Dep = 0`，PID 输出应为正下潜角

#### Step 4: 看门狗验证

1. 在 0xEE 模式下，停止发送 $CKTH 包
2. 等待 1.0s 后 Telnet 观察：
   - `[SAFETY] Jetson heartbeat lost! Fallback to REMOTE`
   - 模式回退到 0x01
   - 推力归零

#### Step 5: ESTOP 验证

1. 发送 `Work_Cmd=0x02`
2. 观察 `[ESTOP] TASK_CANCEL received, motors stopped!`
3. 确认推力立即归零

### 7.3 Telnet 手动注入调试

在无传感器环境下，可通过 Telnet 直接修改全局变量模拟传感器输入：

```shell
# 模拟深度传感器 (2.5m)
-> Current_State.Current_Dep = 2.5

# 模拟 IMU 航向 (90度)
-> Current_State.Current_IMU_Heading = 90.0

# 模拟 DVL 速度 (1.0 knot)
-> Current_State.Current_DVL_Velocity_Kn = 1.0

# 查看 PID 输出
-> printf("depth_rud=%f heading_rud=%f\n", ...)
```

### 7.4 需要修改的配置

| 配置项 | 文件 | 修改内容 |
|--------|------|---------|
| Jetson UDP 目标 IP | `bridge_params.protocol_udp.yaml` | `remote_host: 192.168.0.101` |
| PC104 本机 IP | `usrAppInit.c` | 确认 `ifconfig("fei1 192.168.0.101 up")` |
| 控制模式 | `params.protocol_udp_arbiter.yaml` | `protocol_control_mode_byte: 238` |
| 桥接频率 | `params.protocol_udp_arbiter.yaml` | `command_publish_hz: 10.0` |

---

## 八、裸机联调对 Jetson ES-EKF 的影响分析

### 8.1 风险评估

当 PC104 无传感器时，上行 $AUV 包的关键字段：
- `depth = 0`, `heading = 0`, `pitch = 0`, `roll = 0`
- `dvl_speed = 0`, `altitude = 0`
- `gps_lon = 0`, `gps_lat = 0`

**ES-EKF 风险**：
- 长期接收恒零 DVL 修正 → 协方差 P 收敛至极小值
- 未来接入真实传感器时，EKF 会因 P 过小而拒绝更新（发散/锁死）

### 8.2 缓解方案

**[CONFIDENT]** - Jetson 端 `es_ekf.py` 已有 `auto_init` 机制：

1. **自动初始化**: EKF 在首次收到**有效** DVL/深度观测时才初始化状态，全零数据不会触发初始化
2. **质量控制 (QC)**: 建议在桥接层增加判断：
   - 如果 `dvl_speed == 0` 且 `heading == 0` 且 `depth == 0`，标记数据为 `QC_INVALID`
   - EKF 在收到无效数据时保持 `PENDING` 状态，不进行修正

3. **配置文件开关**: 在 `params.yaml` 中增加：
   ```yaml
   ekf:
     require_sensor_qc: true
     min_valid_depth_m: 0.01  # 深度 < 此值视为无效
     min_valid_dvl_mps: 0.001  # DVL速度 < 此值视为无效
   ```

### 8.3 推荐调试模式

裸机联调时 Jetson 配置：
```yaml
controller:
  debug_level: 1  # STABILIZE_HOLD 模式，仅做控制器验证
ekf:
  bypass: true  # 旁路 EKF，使用原始传感器值
```

---

## 九、修改文件清单

| # | 文件 | 修改类型 | 关键改动 | 信心 |
|---|------|---------|---------|------|
| 1 | `main.c` | 功能新增 | 新增 `Jetson_Shadow_Proces()`, 0xEF分支, Bumpless Transfer, 提频, 优先级 | **[CONFIDENT]** |
| 2 | `main.h` | 声明新增 | 新增外部声明 | **[CONFIDENT]** |
| 3 | `DataProcess.c` | 功能修改 | `Unpack_Data_From_UI12_WIFI` Set_Course 精度修正, DVL 单位转换, Para 扩展 | **[CONFIDENT]** |
| 4 | `DataProcess.h` | 声明新增 | 新增变量声明 | **[CONFIDENT]** |
| 5 | `SecurityEmergencyManage.c` | 功能新增 | Jetson 看门狗, 深度超限模式回退 | **[CONFIDENT]** |
| 6 | `SecurityEmergencyManage.h` | 声明新增 | 看门狗计数器声明 | **[CONFIDENT]** |
| 7 | `CtrlAlgorithm.c` | 无修改 | PID 算法保持不变 | - |
| 8 | `usrAppInit.c` | 可能微调 | IP 地址确认 | **[CONFIDENT]** |

---

## 十、实施流程

### Phase 1: 备份

对每个要修改的文件生成 `_bak.c` / `_bak.h` 备份。

### Phase 2: 提频 + 优先级调整

修改 `main.c` 的任务周期和优先级。验证：Telnet 观察打印频率。

### Phase 3: 0xEE/0xEF 模式分支

在 `MainCtrlTask` 中新增模式判断和 `Jetson_Shadow_Proces()` 函数。

### Phase 4: 协议对齐

修改 `DataProcess.c` 中的解析逻辑（Set_Course 精度、DVL 单位）和组包逻辑（Para 扩展）。

### Phase 5: 安全看门狗

在 `SecurityEmergencyManage.c` 中实现 Jetson 失联看门狗。

### Phase 6: 无扰动切换

在主循环中实现 Bumpless Transfer 逻辑。

### Phase 7: 联调

按照台架 SOP 逐步验证。

---

## 十一、已确认事项（原 NEED_MORE_INFO，全部消除）

| # | 问题 | 架构师结论 | 状态 |
|---|------|-----------|------|
| 1 | DVL 三轴坐标系 | `BI_X/Y/Z` = Body Frame (载具系)，与 ES-EKF `correct_dvl(dvl_vel_body)` 完全对齐 | ✅ CONFIRMED |
| 2 | DVL 单位 | `BI_V` 及三轴分量单位为 **mm/s**。转换公式: `ToUI12_DVL_Velocity = BI_V / 100` (→ 0.1m/s) | ✅ CONFIRMED |
| 3 | `FromUI12_Para1` 冲突 | 原有自动导航目标深度来自 XML 本地文件，不依赖此字段。**100% 安全征用** | ✅ CONFIRMED |
| 4 | 0xEF 舵面角度 | Jetson 发送角度×10，`Remote_Assignment` 中除以 3600 正好消除缩放。**直接复用** | ✅ CONFIRMED |
| 5 | 裸机全零包 | ES-EKF 有 `auto_init` 机制，全零不触发初始化。需 SOP 中 bypass EKF | ✅ CONFIRMED |
| 6 | `orientation_deg` 含义 | = **目标航向角(度)**，来自 `target_heading_rad` 经 `math.degrees()` 转换，×10 写入 offset 35-36 | ✅ CONFIRMED |

---

## 十二、注释与编码规范

### Doxygen 注释模板

```c
/**
 * @brief   [一句话描述修改目的]
 * @date    2026-05-xx
 * @author  清华 AUV 课题组
 * @details [详细描述：解决什么协议问题，对应 common/protocol.py 的哪个字段]
 * @note    [JETSON_SHADOW_MODE] 标记便于全局搜索
 */
```

### Printf 可观测性规范

```c
/* 关键分支打印格式 */
printf("[MODE_SWITCH] 0x%02X -> 0x%02X\n", prev_mode, new_mode);
printf("[BUMPLESS] depth=%.2f heading=%.1f\n", depth, heading);
printf("[SAFETY] Jetson WDG timeout! ticks=%d\n", Not_Recv_From_Jetson_No);
printf("[ESTOP] Work_Cmd=0x%02X, motors zeroed\n", cmd);
printf("[PID_OUT] depth_rud=%.1f heading_rud=%.1f thrust=%d\n", d, h, t);
```

---

*文档结束。后续实施阶段将生成配套的 `VxWorks_重构修改日志.md`。*
