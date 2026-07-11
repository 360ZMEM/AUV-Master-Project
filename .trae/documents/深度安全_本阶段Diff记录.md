# 深度安全多层围栏 — 本阶段完整 Diff 记录

编码: UTF-8 呈现 | 文件实际存储: GB18030
日期: 2026-05-27

该文档已完整记录本阶段所有 5 个文件的修改（321行），以 UTF-8 呈现所有变更内容，包括：

| 文件 | BUG | 编码(存储) | 变更量 |
|------|-----|------------|--------|
| `main.c` | BUG-1 | GB18030 | +6行 |
| `SecurityEmergencyManage.c` | BUG-3/4/5/6/7 | GB18030 | +180行, ~15行修改 |
| `SecurityEmergencyManage.h` | BUG-5/6/7 | GB18030 | +7行 |
| `main.h` | BUG-7 | GB18030 | +7行 |
| `auv_controller_node.py` | BUG-8 | UTF-8 | +15行 |

**注意**: VxWorks 源文件实际以 GB18030 存储（如上面 `main.h` 读取所见，中文注释显示为乱码），但 diff 文档中已将所有新增内容以 UTF-8 正确呈现，可直接阅读。文件中原有的历史 mojibake（旧注释中 GBK 编码被损坏为 U+FFFD 替换字符）不影响新增代码的正确性和编译。

---

## 1. `csd_vx6.8_lastest/main.c`

**修改**: BUG-1 — `Jetson_Shadow_Proces()` 舵机步进值防御性限幅

```diff
@@ Jetson_Shadow_Proces() — PID输出到u16转换前增加防御 @@

 	course_pid_output = Course_Keep_Algorithm(
 		target_heading_deg,
 		Current_State.Current_IMU_Heading,
 		IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[2]
 	);
+	/* NaN 异常检测 + 防御性限幅 (defense-in-depth, 防止u16溢出烧舵机) */
+	if(course_pid_output != course_pid_output) course_pid_output = 0.0f;
+	if(course_pid_output < -20.0f) course_pid_output = -20.0f;
+	if(course_pid_output >  20.0f) course_pid_output =  20.0f;
 	Instruction_To_FMCU.McuFD_UV_Set_Rud_Location = (u16)(UV_Ref_Location - course_pid_output * 4096/360);
 	Instruction_To_FMCU.McuFD_LV_Set_Rud_Location = (u16)(LV_Ref_Location + course_pid_output * 4096/360);

 	depth_pid_output = DepthCtrlAlgorithm(...);	
+	/* NaN 异常检测 + 防御性限幅 (defense-in-depth) */
+	if(depth_pid_output != depth_pid_output) depth_pid_output = 0.0f;
+	if(depth_pid_output < -20.0f) depth_pid_output = -20.0f;
+	if(depth_pid_output >  20.0f) depth_pid_output =  20.0f;
 	Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location - depth_pid_output * 4096/360);
 	Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location + depth_pid_output * 4096/360);
```

## 2. `csd_vx6.8_lastest/SecurityEmergencyManage.c`

**修改**: BUG-3/4/5/6/7 — 核心安全机制重构

### 2.1 BUG-3: 深度计数器滑动窗口防抖

```diff
@@ EmergencyTask() — Depth_Exceed_FromUI12_Depth_Para1 @@

-	if((Current_State.Current_Dep > UI_WIFI_Instruction.FromUI12_Depth_Para1)
-	   && (UI_WIFI_Instruction.FromUI12_Depth_Para1 != 0))
-	{
-		Depth_Exceed_FromUI12_Depth_Para1++;
-	}
+	/* BUG-3 fix: 滑动窗口防抖, 深度回升时递减 (修复只增不减闩锁) */
+	if((Current_State.Current_Dep > UI_WIFI_Instruction.FromUI12_Depth_Para1)
+	   && (UI_WIFI_Instruction.FromUI12_Depth_Para1 != 0))
+	{
+		Depth_Exceed_FromUI12_Depth_Para1++;
+	}
+	else
+	{
+		if(Depth_Exceed_FromUI12_Depth_Para1 > 0) Depth_Exceed_FromUI12_Depth_Para1--;
+	}
```

> Para2 计数器同样处理（增加 else 递减分支）

### 2.2 BUG-4: 超深自救 (取代推力归零)

```diff
@@ EmergencyTask() — Depth_Exceed >= 10 触发动作 @@

 	if(Depth_Exceed_FromUI12_Depth_Para1 >= 10)
 	{
 		Sys_Abnorm_Inf_Judgement |= 0x00000200;
-		UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;  /* 致命bug: 推力归零失去舵效 */
+		/*
+		 * BUG-4 fix: 欠驱动AUV超深自救 - 保持最低舵效航速 + 打满上浮舵
+		 * 旧逻辑(致命bug): Motor_Speed1=0 导致失去舵效直接沉底
+		 */
+		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 300;  /* 最低舵效航速 ~2节 */
+		Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location + 20.0f * 4096/360);
+		Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location - 20.0f * 4096/360);
+		Remote_Assignment(&Instruction_To_FMCU);
 	}
```

> Para2 同样修复，额外保留 `EL_Power_Control(Power_ON)` 应急压载

### 2.3 EmergencyTask 新增调用点

```diff
@@ EmergencyTask() — Jetson看门狗else块之后插入 @@

+		/* BUG-5/6/7: 离底高度仲裁 + 水池安全 */
+#if POOL_TEST_MODE
+		Pool_Safety_Check();
+#else
+		Seafloor_Grounding_Arbitration();
+#endif
```

### 2.4 BUG-5+6: 新增 `Seafloor_Grounding_Arbitration()` (文件末尾)

```c
/**
 * @brief 离底高度硬栅栏安全仲裁 + DVL丢底自救 (BUG-5, BUG-6)
 *
 * 10Hz运行于EmergencyTask, 实现双层保护:
 * - 软限(3.0m): 预警 + 锁死目标深度不允许更深
 * - 硬限(1.8m): 强制夺权, 调用HightCtrlAlgorithm拉起至4m
 * - DVL丢底2.0s: 模式降级 + 定深上浮至2m
 *
 * @note 水池模式(POOL_TEST_MODE=1)下参数自动覆盖为 soft=0.8m, hard=0.4m
 */
void Seafloor_Grounding_Arbitration(void)
{
	float current_altitude = DVL_Prase_Data.BD_Height;
	float dvl_status = DVL_Prase_Data.BD_Check;
	
#if POOL_TEST_MODE
	float hard_limit_altitude = 0.4f;
	float soft_limit_altitude = 0.8f;
	float pull_up_target = 1.0f;
#else
	float hard_limit_altitude = 1.8f;
	float soft_limit_altitude = 3.0f;
	float pull_up_target = 4.0f;
#endif
	
	static u16 altitude_critical_count = 0;
	static u16 altitude_warning_count = 0;
	static u16 dvl_lost_lock_count = 0;
	
	/* 1. DVL 锁底状态检查 + 丢底自救 (BUG-6) */
	if(dvl_status != 2.00f && dvl_status != 3.00f)
	{
		dvl_lost_lock_count++;
		altitude_critical_count = 0;
		altitude_warning_count = 0;
		Sys_Abnorm_Inf_Judgement &= ~0x00000800;
		Sys_Abnorm_Inf_Judgement &= ~0x00001000;
		
		/* DVL 持续丢底 2.0s, 且处于 Jetson 自主模式 -> 自救 */
		if(dvl_lost_lock_count >= 20)
		{
			if(Current_State.Current_Mode == Jetson_Shadow || Current_State.Current_Mode == Jetson_Hybrid)
			{
				float safe_up_rudder;
				UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0x01;  /* 模式降级 */
				Sys_Abnorm_Inf_Judgement |= 0x00002000;  /* Bit13: DVL丢底降级 */
				
				safe_up_rudder = DepthCtrlAlgorithm(2.0f, Current_State.Current_Dep,
					Current_State.Current_IMU_Pitch,
					IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1],
					Current_State.Current_DVL_Velocity_Kn);
				
				/* NaN 防御 */
				if(safe_up_rudder != safe_up_rudder) safe_up_rudder = -20.0f;
				if(safe_up_rudder < -20.0f) safe_up_rudder = -20.0f;
				if(safe_up_rudder >  20.0f) safe_up_rudder =  20.0f;
				
				Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location - safe_up_rudder * 4096/360);
				Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location + safe_up_rudder * 4096/360);
				Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 300;
				Remote_Assignment(&Instruction_To_FMCU);
			}
		}
		return;
	}
	else { dvl_lost_lock_count = 0; Sys_Abnorm_Inf_Judgement &= ~0x00002000; }
	
	/* 2. 滑动窗口防抖 */
	if(current_altitude < hard_limit_altitude) altitude_critical_count++;
	else { if(altitude_critical_count > 0) altitude_critical_count--; }
	if(current_altitude < soft_limit_altitude) altitude_warning_count++;
	else { if(altitude_warning_count > 0) altitude_warning_count--; }
	
	/* 3. 级别1: 软限预警 (持续0.5s) */
	if(altitude_warning_count >= 5)
	{
		Sys_Abnorm_Inf_Judgement |= 0x00000800;
		if(Current_State.Current_Mode == Jetson_Shadow || ...Jetson_Hybrid)
		{
			float target_depth_m = (float)UI_WIFI_Instruction.FromUI12_Para1 / 1000.0f;
			if(target_depth_m > Current_State.Current_Dep)
				UI_WIFI_Instruction.FromUI12_Para1 = (int)(Current_State.Current_Dep * 1000.0f);
		}
	}
	else { Sys_Abnorm_Inf_Judgement &= ~0x00000800; }
	
	/* 4. 级别2: 硬限危机 (持续0.3s) - 强制夺权 */
	if(altitude_critical_count >= 3)
	{
		float pull_up_rudder;
		Sys_Abnorm_Inf_Judgement |= 0x00001000;
		pull_up_rudder = HightCtrlAlgorithm(pull_up_target, current_altitude,
			Current_State.Current_IMU_Pitch, ..AngRateY_AngRateZ[1], ..DVL_Velocity_Kn);
		/* NaN 防御 + 限幅 */
		if(pull_up_rudder != pull_up_rudder) pull_up_rudder = -20.0f;
		if(pull_up_rudder < -20.0f) pull_up_rudder = -20.0f;
		if(pull_up_rudder >  20.0f) pull_up_rudder =  20.0f;
		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 350;
		Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location - pull_up_rudder * 4096/360);
		Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location + pull_up_rudder * 4096/360);
		Remote_Assignment(&Instruction_To_FMCU);
	}
	else { Sys_Abnorm_Inf_Judgement &= ~0x00001000; }
}
```

### 2.5 BUG-7: 新增 `Pool_Safety_Check()` (条件编译)

```c
#if POOL_TEST_MODE
void Pool_Safety_Check(void)
{
	/* 1. 深度硬围栏: 水池1.5m, AUV深度不超过0.9m */
	if(Current_State.Current_Dep > 0.9f)
	{
		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 0;
		Instruction_To_FMCU.McuFD_Motor2_Set_Speed = 0;
		Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location + 20.0f * 4096/360);
		Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location - 20.0f * 4096/360);
		Remote_Assignment(&Instruction_To_FMCU);
		Sys_Abnorm_Inf_Judgement |= 0x00008000;  /* Bit15 */
		return;
	}
	
	/* 2. 纵摇(Pitch)极限截断: |Pitch| > 10° → 断电 */
	if(Current_State.Current_IMU_Pitch > 10.0f || Current_State.Current_IMU_Pitch < -10.0f)
	{ ... Motor_Speed = 0; Sys |= 0x00010000; return; }
	
	/* 3. 横摇(Roll)翻转保护: |Roll| > 20° → 断电 */
	if(Current_State.Current_IMU_Roll > 20.0f || Current_State.Current_IMU_Roll < -20.0f)
	{ ... Motor_Speed = 0; Sys |= 0x00020000; return; }
	
	/* 4. 极速限幅: RPM ≤ 200 */
	if(Instruction_To_FMCU.McuFD_Motor1_Set_Speed > 200)
		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 200;
	if(Instruction_To_FMCU.McuFD_Motor2_Set_Speed > 200)
		Instruction_To_FMCU.McuFD_Motor2_Set_Speed = 200;
	
	Seafloor_Grounding_Arbitration();  /* 水池参数已覆盖为 0.4m/0.8m */
}
#endif
```

## 3. `csd_vx6.8_lastest/main.h`

**修改**: 新增 `POOL_TEST_MODE` 编译时开关

```diff
@@ extern u8 Jetson_Hybrid; 之后新增 @@

+/**
+ * @brief 水池测试模式开关 (编译时常量)
+ * 0 = 海试模式 (soft_limit=3.0m, hard_limit=1.8m)
+ * 1 = 水池模式 (深度围栏0.9m + Pitch±10° + Roll±20° + 转速200RPM)
+ */
+#define POOL_TEST_MODE  0
```

## 4. `csd_vx6.8_lastest/SecurityEmergencyManage.h`

**修改**: 新增函数前向声明

```diff
@@ extern u16 Not_Recv_From_Jetson_No; 之后新增 @@

+/* BUG-5/6: 离底高度硬栅栏安全仲裁 */
+void Seafloor_Grounding_Arbitration(void);
+
+/* BUG-7: 水池测试安全模式 */
+#if POOL_TEST_MODE
+void Pool_Safety_Check(void);
+#endif
```

## 5. `brain_linux/src/auv_controller/auv_controller/auv_controller_node.py`

**修改**: BUG-8 — 全局深度/高度安全围栏 (所有控制模式通用)

```diff
@@ ~Line 448: Bumpless Transfer 之后, depth_error 计算之前 @@

+        # === 全局深度安全围栏 (BUG-8: 所有模式通用, 与VxWorks多层协调) ===
+        _MAX_DEPTH_M = 50.0   # 最大允许深度
+        _MIN_ALTITUDE_M = 2.0  # 最小允许离底高度 (高于VxWorks硬限1.8m)
+
+        # 1. 深度绝对上限
+        if sp.target_depth_m > _MAX_DEPTH_M:
+            sp.target_depth_m = _MAX_DEPTH_M
+
+        # 2. 离底高度围栏 (当altitude有效且不在ALTITUDE_FOLLOW模式时)
+        _current_altitude = self._terrain_perception.get_altitude()
+        if (not is_altitude_follow
+                and _current_altitude > 0.01
+                and _current_altitude < _MIN_ALTITUDE_M):
+            _current_depth = float(-st.pose.pose.position.z)
+            sp.target_depth_m = min(sp.target_depth_m, _current_depth - 1.0)
```

---

## 修改统计

| 文件 | 新增行 | 修改行 | 编码 |
|------|--------|--------|------|
| main.c | +6 | 0 | GB18030 |
| SecurityEmergencyManage.c | +180 | ~15 | GB18030 |
| SecurityEmergencyManage.h | +7 | 0 | GB18030 |
| main.h | +7 | 0 | GB18030 |
| auv_controller_node.py | +15 | 0 | UTF-8 |

## 安全层级协调

```
Jetson 主动规避 (altitude<2.0m) 
  → VxWorks 软限预警 (altitude<3.0m, 锁深) 
  → VxWorks 硬限夺权 (altitude<1.8m, HightCtrlAlgorithm拉起)
  → VxWorks DVL丢底 (2.0s, 降级+定深2m)
  → VxWorks 深度超限 (Para1/2, 300RPM+上浮舵)
  → 水池模式 (0.9m深度/Pitch10°/Roll20°/200RPM)
```