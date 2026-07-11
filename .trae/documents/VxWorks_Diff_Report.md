# VxWorks 源码修改 Diff 报告

> 基准: `csd_vx6.8_lastest_bak/` (未修改原始代码)  
> 修改: `csd_vx6.8_lastest/` (当前工作目录)  
> 生成日期: 2026-05-30  
> 说明: 仅展示**实质性功能修改**，过滤掉纯 GBK 编码差异噪声（中文注释字节表示变化）

---

## 修改文件总览

| # | 文件 | 修改类型 | 行数变化 |
|---|------|---------|---------|
| 1 | main.c | 核心控制逻辑 | +93 |
| 2 | main.h | extern声明 | +2 |
| 3 | DataProcess.c | 协议解析/上行扩展 | +15 |
| 4 | SecurityEmergencyManage.c | 安全机制 | +35 |
| 5 | SecurityEmergencyManage.h | extern声明 | +2 |
| 6 | CtrlAlgorithm.c | Bumpless Transfer接口 | +20 |
| 7 | CtrlAlgorithm.h | 函数声明 | +5 |
| - | DataProcess.h | 无修改 | 0 |

---

## 1. main.c

### 1.1 主控周期提频 (1.67Hz → 10Hz)

```diff
-const float Main_Ctrl_Task_Period = 6;
+const float Main_Ctrl_Task_Period = 1;             /**< @brief 主控周期 0.1s (10Hz), was 6 (1.67Hz) */
```

### 1.2 新增函数声明

```diff
 void Auto_Back_Proces(void);
+void Jetson_Shadow_Proces(void);   /**< @brief 0xEE 影子诱导模式处理 */
```

### 1.3 新增模式变量

```diff
 u8 Auto_Back = 0x04;
+u8 Jetson_Shadow = 0xEE;       /**< @brief 影子诱导模式: 推力透传 + 航向/深度PID闭环 */
+u8 Jetson_Hybrid = 0xEF;       /**< @brief 全透传混合模式: 复用 Remote_Assignment */
+
+/** @brief 上一周期控制模式, 用于 Bumpless Transfer 检测 */
+static u8 prev_ctrl_mode = 0x01;
```

### 1.4 MainCtrlTask 新增 0xEE/0xEF 分支

```diff
 			Auto_Back_Proces();
 			semGive(semNetSendTask);
 		}
-
-		    
+
+		/**
+		 * @brief 0xEE 影子诱导模式: Jetson 推力透传 + VxWorks 航向/深度 PID 闭环
+		 * Bumpless Transfer: 模式切入瞬间重置 PID 积分器
+		 */
+		if(Current_State.Current_Mode == Jetson_Shadow)
+		{
+			if(prev_ctrl_mode != Jetson_Shadow)
+			{
+				/* Bumpless Transfer: 模式切换瞬间清除 PID 积分状态 */
+				Course_Keep_Integral_Reset();
+				Depth_Ctrl_Integral_Reset();
+			}
+			Jetson_Shadow_Proces();
+			semGive(semNetSendTask);
+		}
+
+		/**
+		 * @brief 0xEF 全透传混合模式: 复用 Remote_Assignment (推力+舵角全透传)
+		 */
+		if(Current_State.Current_Mode == Jetson_Hybrid)
+		{
+			Remote_Proces();
+			semGive(semNetSendTask);
+		}
+
+		/* 记录当前模式用于下一周期 Bumpless Transfer 检测 */
+		prev_ctrl_mode = Current_State.Current_Mode;
```

### 1.5 网络任务优先级提升 (125 → 115)

```diff
-	taskSpawn("NetRecvTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)NetRecvTask, 0,0,0,0,0,0,0,0,0,0);
-	taskSpawn("PackNetDataTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)PackNetDataTask, 0,0,0,0,0,0,0,0,0,0);
-	taskSpawn("UnpackNetDataTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)UnpackNetDataTask, 0,0,0,0,0,0,0,0,0,0);
+	taskSpawn("NetRecvTask" , 115 ,VX_FP_TASK , 5120 ,(FUNCPTR)NetRecvTask, 0,0,0,0,0,0,0,0,0,0);
+	taskSpawn("PackNetDataTask" , 115 ,VX_FP_TASK , 5120 ,(FUNCPTR)PackNetDataTask, 0,0,0,0,0,0,0,0,0,0);
+	taskSpawn("UnpackNetDataTask" , 115 ,VX_FP_TASK , 5120 ,(FUNCPTR)UnpackNetDataTask, 0,0,0,0,0,0,0,0,0,0);
```

### 1.6 看门狗递增 (FuncWd_InfoOutputCtrl)

```diff
  Net_Recv_Interval_Num++;
+
+ Not_Recv_From_Jetson_No++;  /**< @brief Jetson 失联计数器递增, 收到包时在 Unpack 中清零 */
```

### 1.7 新增 Jetson_Shadow_Proces 完整实现

```diff
+/**
+ * @brief 0xEE 影子诱导模式处理函数
+ *
+ * 功能: Jetson 推力透传 + VxWorks 本地航向/深度 PID 闭环
+ * - 推力: 直接使用 FromUI12_Motor_Speed1 (thrust_percent × 15.0 由 Jetson 计算)
+ * - 航向: Course_Keep_Algorithm(target_heading, current_heading, gyro_z)
+ * - 深度: DepthCtrlAlgorithm(target_depth, current_depth, pitch, gyro_pitch, vx)
+ * - 目标航向: FromUI12_Set_Course / 10.0 (Jetson 发送 orientation_deg×10)
+ * - 目标深度: FromUI12_Para1 / 1000.0 (Jetson 发送 depth_m×1000, int32)
+ * - 深度防超限: 0-50m 硬限幅
+ */
+void Jetson_Shadow_Proces(void)
+{
+	float target_heading_deg;
+	float target_depth_m;
+	float course_pid_output;
+	float depth_pid_output;
+
+	/* 推力透传: 直接取 Jetson 下发的电机转速指令 */
+	if(UI_Channel_Selection_Down == 0x02)
+	{
+		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = UI_WIFI_Instruction.FromUI12_Motor_Speed1;
+		Instruction_To_FMCU.McuFD_Motor2_Set_Speed = UI_WIFI_Instruction.FromUI12_Motor_Speed2;
+	}
+
+	/* 目标航向: FromUI12_Set_Course 存储 orientation_deg×10, 需÷10 */
+	target_heading_deg = (float)UI_WIFI_Instruction.FromUI12_Set_Course / 10.0f;
+
+	/* 目标深度: FromUI12_Para1 存储 depth_m×1000 (int32), 需÷1000 */
+	target_depth_m = (float)UI_WIFI_Instruction.FromUI12_Para1 / 1000.0f;
+
+	/* 深度防超限保护: 硬限幅 0~50m */
+	if(target_depth_m < 0.0f) target_depth_m = 0.0f;
+	if(target_depth_m > 50.0f) target_depth_m = 50.0f;
+
+	/* 航向 PID 闭环 → 垂直舵角 */
+	course_pid_output = Course_Keep_Algorithm(
+		target_heading_deg,
+		Current_State.Current_IMU_Heading,
+		IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[2]
+	);
+	Instruction_To_FMCU.McuFD_UV_Set_Rud_Location = (u16)(UV_Ref_Location - course_pid_output * 4096/360);
+	Instruction_To_FMCU.McuFD_LV_Set_Rud_Location = (u16)(LV_Ref_Location + course_pid_output * 4096/360);
+
+	/* 深度 PID 闭环 → 水平舵角 */
+	depth_pid_output = DepthCtrlAlgorithm(
+		target_depth_m,
+		Current_State.Current_Dep,
+		Current_State.Current_IMU_Pitch,
+		IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1],
+		Current_State.Current_DVL_Velocity_Kn
+	);
+	Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location - depth_pid_output * 4096/360);
+	Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location + depth_pid_output * 4096/360);
+
+	/* 打包并发送到 MCU */
+	Remote_Assignment(&Instruction_To_FMCU);
+}
```

---

## 2. main.h

```diff
 extern u8 Auto_Back;
+extern u8 Jetson_Shadow;        /**< @brief 0xEE 影子诱导模式 */
+extern u8 Jetson_Hybrid;        /**< @brief 0xEF 全透传混合模式 */
```

---

## 3. DataProcess.c

### 3.1 Jetson 看门狗喂狗 (UnpackNetDataTask)

```diff
 			Unpack_Data_From_UI12_WIFI(From_WIFI_Buf);
-			Not_Recv_From_WIFI_No = 0;     /*数据接收重置超时计数器*/
+			Not_Recv_From_WIFI_No = 0;     /*数据接收重置超时计数器*/
+			Not_Recv_From_Jetson_No = 0;   /**< @brief Jetson看门狗喂狗: 收到有效WIFI包即清零 */
```

### 3.2 DVL 三轴速度上行扩展 (Pack_Data_To_UI12)

```diff
 temp->ToUI12_Para12=(Current_State.Current_Para12);
+
+/**
+ * @brief DVL 三轴速度上行扩展 (Body Frame, mm/s)
+ * 辅助 Jetson ES-EKF 状态估计
+ *
+ * 极性标定说明 (台架联调时确认):
+ *   BI_X: 前进为正 (surge, +X = forward)
+ *   BI_Y: 右移为正 (sway,  +Y = starboard)  [待实测确认]
+ *   BI_Z: 下潜为正 (heave, +Z = down)       [待实测确认]
+ * 若极性反转, 在此处取反即可, 例如: -DVL_Prase_Data.BI_Y
+ */
+temp->ToUI12_Para5 = (short int)DVL_Prase_Data.BI_X;  /* DVL Body X (mm/s) */
+temp->ToUI12_Para6 = (short int)DVL_Prase_Data.BI_Y;  /* DVL Body Y (mm/s) */
+temp->ToUI12_Para7 = (short int)DVL_Prase_Data.BI_Z;  /* DVL Body Z (mm/s) */
```

### 3.3 DVL 速度单位变更

```diff
-temp->ToUI12_DVL_Velocity=(Current_State.Current_DVL_Velocity_Kn)*10;
+temp->ToUI12_DVL_Velocity=(short int)(DVL_Prase_Data.BI_V / 100.0f);  /**< @brief DVL速度 m/s×10, was knots×10. BI_V(mm/s)/100=m/s×10 */
```

---

## 4. SecurityEmergencyManage.c

### 4.1 新增 Jetson 失联计数器变量

```diff
 u16 Not_Recv_From_WI_DVL_No = 0;

+/**
+ * @brief Jetson 失联计数器, 每 0.1s 递增一次 (在 FuncWd_InfoOutputCtrl 中)
+ * 收到 Jetson 数据包时清零 (在 Unpack_Data_From_UI12_WIFI 中)
+ * 阈值 10 = 1.0s 超时
+ */
+u16 Not_Recv_From_Jetson_No = 0;
```

### 4.2 Jetson 失联看门狗逻辑 (EmergencyTask)

```diff
+		/**
+		 * @brief Jetson 失联看门狗 (1.0s 超时)
+		 * 触发条件: Not_Recv_From_Jetson_No >= 10 (10×0.1s = 1.0s)
+		 * 仅在 0xEE/0xEF 模式下生效
+		 * 降级动作: 模式回退至 Remote(0x01), 推力归零, 急停
+		 */
+		if(Not_Recv_From_Jetson_No >= 10)
+		{
+			if(Current_State.Current_Mode == 0xEE || Current_State.Current_Mode == 0xEF)
+			{
+				UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0x01;  /* 降级到遥控模式 */
+				UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;  /* 推力归零 */
+				UI_WIFI_Instruction.FromUI12_Motor_Speed2 = 0;
+				Sys_Abnorm_Inf_Judgement |= 0x00004000;  /* Bit14: Jetson通信超时告警 */
+			}
+		}
+		else
+		{
+			Sys_Abnorm_Inf_Judgement &= 0xffffbfff;  /* 清除 Bit14 */
+		}
```

### 4.3 深度超限模式回退

```diff
+		/**
+		 * @brief 深度超限模式回退 (0xEE/0xEF 模式专用)
+		 * 当 Depth_Para1 触发深度超限(连续10次), 在 Jetson 自主模式下
+		 * 额外执行模式降级: 回退至 Remote(0x01), 防止 Jetson 继续下潜
+		 */
+		if(Depth_Exceed_FromUI12_Depth_Para1 >= 10)
+		{
+			if(Current_State.Current_Mode == 0xEE || Current_State.Current_Mode == 0xEF)
+			{
+				UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0x01;  /* 模式降级 */
+				UI_WIFI_Instruction.FromUI12_Motor_Speed2 = 0;
+			}
+		}
```

---

## 5. SecurityEmergencyManage.h

```diff
 extern u16 Not_Recv_From_WI_DVL_No;

+extern u16 Not_Recv_From_Jetson_No;  /**< @brief Jetson失联计数器 (0.1s/tick, 阈值10=1.0s) */
```

---

## 6. CtrlAlgorithm.c

### 新增 Bumpless Transfer 预留接口 (文件末尾)

```diff
+/**
+ * @brief Bumpless Transfer: 重置航向PID积分器
+ * 当前 Course_Keep_Algorithm 为纯PD控制器, 无积分状态
+ * 此函数为预留接口, 后续若加入积分项需在此清零
+ */
+void Course_Keep_Integral_Reset(void)
+{
+	/* PD controller - no integral state to reset (reserved for future PID) */
+}
+
+/**
+ * @brief Bumpless Transfer: 重置深度PID积分器
+ * 当前 DepthCtrlAlgorithm 为P1+P2+D控制器, 无积分状态
+ * 此函数为预留接口, 后续若加入积分项需在此清零
+ */
+void Depth_Ctrl_Integral_Reset(void)
+{
+	/* P+P+D controller - no integral state to reset (reserved for future PID) */
+}
```

---

## 7. CtrlAlgorithm.h

### `#endif` 前新增声明

```diff
+/** @brief Bumpless Transfer: 重置航向PID积分器 (当前PD无积分, 预留接口) */
+void Course_Keep_Integral_Reset(void);
+/** @brief Bumpless Transfer: 重置深度PID积分器 (当前PD无积分, 预留接口) */
+void Depth_Ctrl_Integral_Reset(void);
+
 #endif
```

---

## 协议契约总结

| 字段 | 偏移 | 方向 | 含义 | 单位/编码 |
|------|------|------|------|-----------|
| `FromUI12_Ctrl_Mode` | 7 | 下行 | 控制模式 | 0x01/0xEE/0xEF |
| `FromUI12_Motor_Speed1/2` | 23-26 | 下行 | 推力指令 | RPM (thrust%×15) |
| `FromUI12_Set_Course` | 35-36 | 下行 | 目标航向 | deg×10, u16 |
| `FromUI12_Para1` | 37-40 | 下行 | 目标深度 | mm (depth_m×1000), int32 |
| `ToUI12_Para5` | 56-57 | 上行 | DVL Body X | mm/s, short |
| `ToUI12_Para6` | 58-59 | 上行 | DVL Body Y | mm/s, short |
| `ToUI12_Para7` | 60-61 | 上行 | DVL Body Z | mm/s, short |
| `ToUI12_DVL_Velocity` | 82-83 | 上行 | DVL合速度 | m/s×10, short |

---

## 备注

1. **编码差异**: diff 中大量形如 `/*ң..*/` 的变化是 GBK 中文注释在不同 locale 下的字节表示差异，**不影响编译和功能**
2. **FTP安全性**: 所有修改的任务优先级 ≥110，VxWorks FTP/tNetTask 运行在优先级 50-100，不会被抢占
3. **模式隔离**: 0xEE/0xEF 分支仅在 Jetson 主动发送该模式字节时触发，当前遥控模式完全走原有路径
4. **DataProcess.h**: 经 diff 确认无修改
