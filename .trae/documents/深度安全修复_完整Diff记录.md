# 深度安全多层围栏 — 本阶段完整 Diff 记录

日期: 2026-05-27
编码: 所有 VxWorks .c/.h 文件为 GB18030

## 变更统计

| 文件 | 新增行 | 删除行 | 说明 |
|------|--------|--------|------|
| `csd_vx6.8_lastest/main.h` | +9 | -0 | POOL_TEST_MODE 宏 + 前阶段extern声明 |
| `csd_vx6.8_lastest/main.c` | +194 | -93 | NaN防御+限幅 + 提频+模式分支(前阶段) |
| `csd_vx6.8_lastest/SecurityEmergencyManage.c` | +424 | -138 | 计数器修复+超深自救+离底仲裁+水池模式 |
| `csd_vx6.8_lastest/SecurityEmergencyManage.h` | +8 | -0 | 新函数声明 |
| `brain_linux/.../auv_controller_node.py` | +15 | -0 | 全局深度/高度围栏 |

---

## `csd_vx6.8_lastest/main.h`

```diff
--- a/csd_vx6.8_lastest/main_bak.h
+++ b/csd_vx6.8_lastest/main.h
@@ -11,6 +11,15 @@
 extern u8 Auto_FixedPoint;
 extern u8 Auto_FixedDirection;
 extern u8 Auto_Back;
+extern u8 Jetson_Shadow;        /**< @brief 0xEE 影子诱导模式 */
+extern u8 Jetson_Hybrid;        /**< @brief 0xEF 全透传混合模式 */
+
+/**
+ * @brief 水池测试模式开关 (编译时常量)
+ * 0 = 海试模式 (soft_limit=3.0m, hard_limit=1.8m)
+ * 1 = 水池模式 (深度围栏0.9m + Pitch±10° + Roll±20° + 转速200RPM)
+ */
+#define POOL_TEST_MODE  0
 
 
 extern bool Parameter_Adjustment_Flag;
```

## `csd_vx6.8_lastest/main.c`

```diff
--- a/csd_vx6.8_lastest/main_bak.c
+++ b/csd_vx6.8_lastest/main.c
@@ -28,7 +28,7 @@
 
 #include "dtp.h"
 
-/*消息队列\信号量等其他初始化*/;
+/*�1�7�1�7�0�4�1�7�1�7�1�7�1�7\�1�7�0�2�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�3�1�7�1�7*/;
 void ProgromStartPoint(void);
 void MainCtrlTask(void);
 void Program_Initial(void);
@@ -38,27 +38,28 @@
 void FuncWd_InfoOutputCtrl(void);
 void Debug_Print(void);
 
-/*对应任务的执行过程函数*/;
+/*�1�7�1�7�0�8�1�7�1�7�1�7�1�7�1�7�0�4�1�7�ۄ1�7�1�7�0�4�1�7�1�7�1�7*/;
 void Default_Proces(void);
 void Course_Keep_Proces(void);
 void Remote_Proces(void);
 void Auto_FixedPoint_Proces(void);
 void Auto_FixedDirection_Proces(void);
 void Auto_Back_Proces(void);
-
-/*遥控模式下的函数*/
+void Jetson_Shadow_Proces(void);   /**< @brief 0xEE Ӱ���յ�ģʽ���� */
+
+/*�0�1�1�7�1�7�0�0�0�4�1�7�0�8�0�2�1�7�1�7�1�7*/
 void Work_Cmd_Execute(u8 *work_command_ptr);
 
 
-/*能源状态初始化函数*/
+/*�1�7�1�7�0�6�0�8�0�0�1�7�1�7�0�3�1�7�1�7�1�7�1�7�1�7�1�7*/
 void Device_Power_Ctrl_Initial(void);
 
 
-/*自主航行规划初始化函数*/
+/*�1�7�1�7�1�7�1�7�1�7�1�7�1�7�ۜ��1�7�1�7�0�3�1�7�1�7�1�7�1�7�1�7�1�7*/
 void Auto_FixedPoint_Process_Initial(void);
 void Auto_FixedDirection_Process_Initial(void);
 
-/*打印测试函数*/
+/*�1�7�1�7�0�3�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
 void Current_State_printf(void);
 void recv_count_printf(void);
 void Beid_BDTXR(void);
@@ -121,15 +122,15 @@
 
 
 
-WDOG_ID wdTimer_InfoOutputCtrl;/*定时输出各控制指令到各设备*/
+WDOG_ID wdTimer_InfoOutputCtrl;/*�1�7�1�7�0�2�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�8�1�7�7�4�1�7�1�7�1�7��*/
 
 unsigned short int DEBUG = 1;
 
-/*设备执行周期*/
-const float Main_Ctrl_Task_Period = 6;             
+/*�1�7��0�4�1�7�1�7�1�7�1�7�1�7�1�7*/
+const float Main_Ctrl_Task_Period = 1;             /**< @brief �������� 0.1s (10Hz), was 6 (1.67Hz) */
 const float Net_Recv_Task_Period = 3;            
 const float Uart_Recv_Form_LORA_Task_Period = 3;              
-const float Uart_Recv_Form_BEIDOU_Task_Period = 610;    /*原来是610，临时改为6*/          
+const float Uart_Recv_Form_BEIDOU_Task_Period = 610;    /*�0�9�1�7�1�7�1�7�1�7610�1�7�1�7�1�7�1�7�0�2�1�7�1�7�0�26*/          
 const float Uart_Recv_Form_IMU_Task_Period = 3;
 const float Uart_Recv_Form_DVL_Task_Period = 10;              
 const float Uart_Recv_Form_BMS_Task_Period = 3;              
@@ -166,7 +167,7 @@
 
 
 
-/*计数器，也可以说是计时器*/
+/*�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�6�1�7�1�7�1�7�1�7�0�5�1�7�0�3�1�7�0�2�1�7�1�7*/
 u16 Main_Ctrl_Task_Interval_Num = 0;
 u16 Net_Recv_Interval_Num  = 0;
 u16 Recv_Form_LORA_Interval_Num  = 0;
@@ -188,11 +189,16 @@
 bool Auto_FixedDirection_Process_Initial_Flag = false;
 
 
-/*u8 CtrlMode = 0x00;测试mcu的时候，要改成0x01，对应上遥控模式*/
+/*u8 CtrlMode = 0x00;�1�7�1�7�1�7�1�7mcu�1�7�1�7�0�2�1�7�1�7�0�8�1�7�0�5�1�70x01�1�7�1�7�1�7�1�7�0�8�1�7�1�7�0�1�1�7�1�7�0�0�0�4*/
 u8 Remote = 0x01;
 u8 Auto_FixedPoint = 0x02;
 u8 Auto_FixedDirection = 0x03;
 u8 Auto_Back = 0x04;
+u8 Jetson_Shadow = 0xEE;       /**< @brief Ӱ���յ�ģʽ: ����͸�� + ����/���PID�ջ� */
+u8 Jetson_Hybrid = 0xEF;       /**< @brief ȫ͸�����ģʽ: ���� Remote_Assignment */
+
+/** @brief ��һ���ڿ���ģʽ, ���� Bumpless Transfer ��� */
+static u8 prev_ctrl_mode = 0x01;
 
 
 
@@ -201,7 +207,7 @@
 	taskSpawn("MainCtrlTask" , 120 ,VX_FP_TASK , 5120 ,(FUNCPTR)MainCtrlTask, 0,0,0,0,0,0,0,0,0,0);
 	printf("program starting:::::\n");
 	Program_Initial();
-	taskDelay(sysClkRateGet() / 10);/*默认系统时钟工作频率是60，60/10=6个tick 也就是6/60=0.1秒*/
+	taskDelay(sysClkRateGet() / 10);/*�0�8�1�7�1�7�0�3�0�1�0�2�1�7�0�7�1�7�1�7�1�7�0�1�1�7�1�7�1�7�1�760�1�7�1�760/10=6�1�7�1�7tick �0�6�1�7�1�7�1�7�1�76/60=0.1�1�7�1�7*/
 	
 }
 
@@ -260,8 +266,34 @@
 				Auto_Back_Proces();
 				semGive(semNetSendTask);
 			}
-					
-		    
+
+			/**
+			 * @brief 0xEE Ӱ���յ�ģʽ: Jetson ����͸�� + VxWorks ����/��� PID �ջ�
+			 * Bumpless Transfer: ģʽ����˲������ PID ������
+			 */
+			if(Current_State.Current_Mode == Jetson_Shadow)
+			{
+				if(prev_ctrl_mode != Jetson_Shadow)
+				{
+					/* Bumpless Transfer: ģʽ�л�˲����� PID ����״̬ */
+					Course_Keep_Integral_Reset();
+					Depth_Ctrl_Integral_Reset();
+				}
+				Jetson_Shadow_Proces();
+				semGive(semNetSendTask);
+			}
+
+			/**
+			 * @brief 0xEF ȫ͸�����ģʽ: ���� Remote_Assignment (����+���ȫ͸��)
+			 */
+			if(Current_State.Current_Mode == Jetson_Hybrid)
+			{
+				Remote_Proces();
+				semGive(semNetSendTask);
+			}
+
+			/* ��¼��ǰģʽ������һ���� Bumpless Transfer ��� */
+			prev_ctrl_mode = Current_State.Current_Mode;
 			
 		    if((Instruction_To_FMCU.McuFD_Power_Control & 0x40)==0x40)
 		    {
@@ -384,7 +416,7 @@
 	run_FixedPoint_xppTutorialAll("/ata0a/XMLFile/Point_File.xml");
 	
 	FixedPoint_PathPlanning.Latitude[0] = Current_State.Current_GPS_Latitude;
-	FixedPoint_PathPlanning.Longitude[0] = Current_State.Current_GPS_Longitude;   /*起始目标点为自主航行开始时刻当前位置点*/
+	FixedPoint_PathPlanning.Longitude[0] = Current_State.Current_GPS_Longitude;   /*�1�7�1�7�0�3�0�7�1�7�1�7�1�7�0�2�1�7�1�7�1�7�1�7�1�7�1�7�1�7��1�7�0�3�0�2�1�7�0�9�1�7�0�2�˄1�7�0�1�1�7*/
 	
 	unpack_FixedPoint_XML(&XMLData); 
 }
@@ -393,7 +425,7 @@
 {
 	run_FixedDirection_xppTutorialAll("/ata0a/XMLFile/Directional_File.xml");	
 	
-	FixedDirection_PathPlanning.Course[0]=Current_State.Current_IMU_Heading; /*起始航向为罗经的当前航向*/
+	FixedDirection_PathPlanning.Course[0]=Current_State.Current_IMU_Heading; /*�1�7�1�7�0�3�1�7�1�7�1�7�1�7�0�2�1�7�1�6�1�7�1�7�0�7�1�7�0�2�1�7�1�7�1�7�1�7*/
 	
 	unpack_FixedDirection_XML(&XMLData); 
 	
@@ -441,6 +473,73 @@
 	
 }
 
+/**
+ * @brief 0xEE Ӱ���յ�ģʽ��������
+ *
+ * ����: Jetson ����͸�� + VxWorks ���غ���/��� PID �ջ�
+ * - ����: ֱ��ʹ�� FromUI12_Motor_Speed1 (thrust_percent �� 15.0 �� Jetson ����)
+ * - ����: Course_Keep_Algorithm(target_heading, current_heading, gyro_z)
+ * - ���: DepthCtrlAlgorithm(target_depth, current_depth, pitch, gyro_pitch, vx)
+ * - Ŀ�꺽��: FromUI12_Set_Course / 10.0 (Jetson ���� orientation_deg��10)
+ * - Ŀ�����: FromUI12_Para1 / 10.0 (Jetson ���� depth_m��10, int32)
+ * - ��ȷ�����: 0-50m Ӳ�޷�
+ */
+void Jetson_Shadow_Proces(void)
+{
+	float target_heading_deg;
+	float target_depth_m;
+	float course_pid_output;
+	float depth_pid_output;
+	
+	/* ����͸��: ֱ��ȡ Jetson �·��ĵ��ת��ָ�� */
+	if(UI_Channel_Selection_Down == 0x02)
+	{
+		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = UI_WIFI_Instruction.FromUI12_Motor_Speed1;
+		Instruction_To_FMCU.McuFD_Motor2_Set_Speed = UI_WIFI_Instruction.FromUI12_Motor_Speed2;
+	}
+	
+	/* Ŀ�꺽��: FromUI12_Set_Course �洢 orientation_deg��10, ���10 */
+	target_heading_deg = (float)UI_WIFI_Instruction.FromUI12_Set_Course / 10.0f;
+	
+	/* Ŀ�����: FromUI12_Para1 �洢 depth_m��10 (int32), ���10 */
+	target_depth_m = (float)UI_WIFI_Instruction.FromUI12_Para1 / 10.0f;
+	
+	/* ��ȷ����ޱ���: Ӳ�޷� 0~50m */
+	if(target_depth_m < 0.0f) target_depth_m = 0.0f;
+	if(target_depth_m > 50.0f) target_depth_m = 50.0f;
+	
+	/* ���� PID �ջ� �� ��ֱ��� */
+	course_pid_output = Course_Keep_Algorithm(
+		target_heading_deg,
+		Current_State.Current_IMU_Heading,
+		IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[2]
+	);
+	/* NaN �쳣��� + �������޷� (defense-in-depth, ��ֹu16����ն��) */
+	if(course_pid_output != course_pid_output) course_pid_output = 0.0f;
+	if(course_pid_output < -20.0f) course_pid_output = -20.0f;
+	if(course_pid_output >  20.0f) course_pid_output =  20.0f;
+	Instruction_To_FMCU.McuFD_UV_Set_Rud_Location = (u16)(UV_Ref_Location - course_pid_output * 4096/360);
+	Instruction_To_FMCU.McuFD_LV_Set_Rud_Location = (u16)(LV_Ref_Location + course_pid_output * 4096/360);
+	
+	/* ��� PID �ջ� �� ˮƽ��� */
+	depth_pid_output = DepthCtrlAlgorithm(
+		target_depth_m,
+		Current_State.Current_Dep,
+		Current_State.Current_IMU_Pitch,
+		IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1],
+		Current_State.Current_DVL_Velocity_Kn
+	);
+	/* NaN �쳣��� + �������޷� (defense-in-depth) */
+	if(depth_pid_output != depth_pid_output) depth_pid_output = 0.0f;
+	if(depth_pid_output < -20.0f) depth_pid_output = -20.0f;
+	if(depth_pid_output >  20.0f) depth_pid_output =  20.0f;
+	Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location - depth_pid_output * 4096/360);
+	Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location + depth_pid_output * 4096/360);
+	
+	/* ��������͵� MCU */
+	Remote_Assignment(&Instruction_To_FMCU);
+}
+
 void Work_Cmd_Execute(u8 *work_command_ptr)
 {
 	switch(*work_command_ptr)
@@ -458,28 +557,28 @@
 				Sail_State_Judgement &= 0xffffffef;
 				break;
 			case 0x03:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x04:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x05:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x06:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x07:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x08:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x09:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x10:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x11:
 				MT_Power_Control(Power_ON);				
@@ -536,10 +635,10 @@
 				S2_Power_Control(Power_OFF);
 				break;
 			case 0x41:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x42:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x51:
 				Parameter_Adjustment_Flag = true;
@@ -550,16 +649,16 @@
 				Cmd_State_Judgement &= 0xfffffffb;
 				break;
 			case 0x53:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x54:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x61:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x62:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;
 			case 0x71:
 				Course_Keep_Flag = true;
@@ -570,19 +669,19 @@
 				Cmd_State_Judgement &= 0xffffffbf;
 				break;				
 			case 0x73:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;				
 			case 0x74:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;							
 			case 0x81:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;			
 			case 0x82:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;			
 			case 0x83:
-				/*留空*/
+				/*�1�7�1�7�1�7�1�7*/
 				break;					
 			case 0x91:
 				Initialization_Flag = true;
@@ -650,9 +749,9 @@
 		taskSpawn("UnpackBMSDataTask" , 130 ,VX_FP_TASK , 5120 ,(FUNCPTR)UnpackBMSDataTask, 0,0,0,0,0,0,0,0,0,0);
 		
 		taskSpawn("NetSendTask" , 130 ,VX_FP_TASK , 5120 ,(FUNCPTR)NetSendTask, 0,0,0,0,0,0,0,0,0,0);
-		taskSpawn("NetRecvTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)NetRecvTask, 0,0,0,0,0,0,0,0,0,0);
-		taskSpawn("PackNetDataTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)PackNetDataTask, 0,0,0,0,0,0,0,0,0,0);
-		taskSpawn("UnpackNetDataTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)UnpackNetDataTask, 0,0,0,0,0,0,0,0,0,0);
+		taskSpawn("NetRecvTask" , 115 ,VX_FP_TASK , 5120 ,(FUNCPTR)NetRecvTask, 0,0,0,0,0,0,0,0,0,0);  /**< @brief ���ȼ����� 125��115, ȷ�� Jetson ���ݼ�ʱ��� */
+	taskSpawn("PackNetDataTask" , 115 ,VX_FP_TASK , 5120 ,(FUNCPTR)PackNetDataTask, 0,0,0,0,0,0,0,0,0,0);
+	taskSpawn("UnpackNetDataTask" , 115 ,VX_FP_TASK , 5120 ,(FUNCPTR)UnpackNetDataTask, 0,0,0,0,0,0,0,0,0,0);
 		
 		taskSpawn("EmergencyTask" , 110 ,VX_FP_TASK , 5120 ,(FUNCPTR)EmergencyTask, 0,0,0,0,0,0,0,0,0,0);	
 		taskSpawn("DataStoreTask" , 140 ,VX_FP_TASK , 5120 ,(FUNCPTR)DataStoreTask, 0,0,0,0,0,0,0,0,0,0);
@@ -662,47 +761,47 @@
 		
 }
 /*
- @function: 消息队列\信号量等其他初始化
+ @function: �1�7�1�7�0�4�1�7�1�7�1�7�1�7\�1�7�0�2�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�3�1�7�1�7
  */
 short int Sem_Initial(void)
 {
-	semMainCtrlTask = semBCreate(SEM_Q_PRIORITY, SEM_FULL);  /*主函数信号量*/
-	
-	semUartSendToBEIDOUTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口发送至北斗信号量*/
-	semUartRecvFormBEIDOUTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收北斗信号量*/	
-	semPackBEIDOUDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);      /*北斗串口数据打包信号量*/
-	semUnpackBEIDOUDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*北斗串口数据解包信号量*/
-	
-	semUartSendToPSDTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口发送至频闪灯信号量*/
-	semUartRecvFormPSDTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收频闪灯信号量*/
-	semPackPSDDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*频闪灯串口数据打包信号量*/
-	semUnpackPSDDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*频闪灯串口数据解包信号量*/
-	
-	/*semUartSendToGPS = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     控制串口发送至GPS信号量*/
-	semUartRecvFormGPSTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收GPS信号量*/	
-	semUnpackGPSDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*GPS串口数据解包信号量*/
+	semMainCtrlTask = semBCreate(SEM_Q_PRIORITY, SEM_FULL);  /*�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
+	
+	semUartSendToBEIDOUTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�1�7�0�0�1�7�1�7�1�3�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
+	semUartRecvFormBEIDOUTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�1�7�0�0�1�7�1�7�1�9�1�7�1�7�0�7�1�7�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/	
+	semPackBEIDOUDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);      /*�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�2�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
+	semUnpackBEIDOUDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�1�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
+	
+	semUartSendToPSDTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�1�7�0�0�1�7�1�7�1�3�1�7�1�7�1�7�1�7�1�7�0�1�1�7�1�7�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
+	semUartRecvFormPSDTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�1�7�0�0�1�7�1�7�1�9�1�7�1�7�1�7�0�1�1�7�1�7�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
+	semPackPSDDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�0�1�1�7�1�7�1�7�0�0�1�7�1�7�1�7�1�7�1�7�1�7�1�2�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
+	semUnpackPSDDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�0�1�1�7�1�7�1�7�0�0�1�7�1�7�1�7�1�7�1�7�1�7�1�1�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
+	
+	/*semUartSendToGPS = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     �1�7�1�7�1�7�0�0�1�7�1�7�1�3�1�7�1�7�1�7�1�7�1�7GPS�1�7�0�2�1�7�1�7�1�7*/
+	semUartRecvFormGPSTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�1�7�0�0�1�7�1�7�1�9�1�7�1�7�1�7GPS�1�7�0�2�1�7�1�7�1�7*/	
+	semUnpackGPSDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*GPS�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�1�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
     
-	/*semUartSendToDVL = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     控制串口发送至DVL信号量*/
-    semUartRecvFormDVLTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收DVL信号量*/	
-    semUnpackDVLDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*DVL串口数据解包信号量*/
+	/*semUartSendToDVL = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     �1�7�1�7�1�7�0�0�1�7�1�7�1�3�1�7�1�7�1�7�1�7�1�7DVL�1�7�0�2�1�7�1�7�1�7*/
+    semUartRecvFormDVLTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�1�7�0�0�1�7�1�7�1�9�1�7�1�7�1�7DVL�1�7�0�2�1�7�1�7�1�7*/	
+    semUnpackDVLDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*DVL�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�1�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
     
    
-    semUartRecvFormIMUTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收罗经信号量*/       
-    semUnpackIMUDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*罗经串口数据解包信号量*/
-	
-    semUartSendToLORATask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口发送至LORA信号量*/
-	semUartRecvFormLORATask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收LORA信号量*/	
-	
-	semUnpackLORADataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*LORA串口数据解包信号量*/
+    semUartRecvFormIMUTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�1�7�0�0�1�7�1�7�1�9�1�7�1�7�1�7�1�7�1�6�1�7�1�7�0�2�1�7�1�7�1�7*/       
+    semUnpackIMUDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�6�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�1�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
+	
+    semUartSendToLORATask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�1�7�0�0�1�7�1�7�1�3�1�7�1�7�1�7�1�7�1�7LORA�1�7�0�2�1�7�1�7�1�7*/
+	semUartRecvFormLORATask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�1�7�0�0�1�7�1�7�1�9�1�7�1�7�1�7LORA�1�7�0�2�1�7�1�7�1�7*/	
+	
+	semUnpackLORADataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*LORA�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�1�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
   
 	
-	semUartRecvFormBMSTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收BMS信号量*/		
-	semUnpackBMSDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*BMS串口数据解包信号量*/
-	
-	semNetSendTask  = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制以太网发送信号量*/
-	semNetRecvTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制以太网接收信号量*/
-	semPackNetDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*以太网数据打包信号量*/	
-	semUnpackNetDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*以太网数据解包信号量*/
+	semUartRecvFormBMSTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�1�7�0�0�1�7�1�7�1�9�1�7�1�7�1�7BMS�1�7�0�2�1�7�1�7�1�7*/		
+	semUnpackBMSDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*BMS�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�1�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
+	
+	semNetSendTask  = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�1�7�1�7�1�7�1�7�0�9�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
+	semNetRecvTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�1�7�1�7�1�7�1�7�0�9�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
+	semPackNetDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�0�9�1�7�1�7�1�7�1�7�1�7�1�2�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/	
+	semUnpackNetDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*�1�7�1�7�0�9�1�7�1�7�1�7�1�7�1�7�1�1�1�7�1�7�1�7�0�2�1�7�1�7�1�7*/
 
     semEmergencyTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY); 
     semDataStoreTask  = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);   
@@ -710,26 +809,28 @@
 
     
     
-	if((wdTimer_InfoOutputCtrl = wdCreate()) == NULL)       /*创建看门狗*/
+	if((wdTimer_InfoOutputCtrl = wdCreate()) == NULL)       /*�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�1�1�7*/
 	{
 		return (ERROR);
 	}
-	wdStart(wdTimer_InfoOutputCtrl, sysClkRateGet()*0.1, (FUNCPTR)FuncWd_InfoOutputCtrl, 0);/*0.1s后启动启动定时器*/
+	wdStart(wdTimer_InfoOutputCtrl, sysClkRateGet()*0.1, (FUNCPTR)FuncWd_InfoOutputCtrl, 0);/*0.1s�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�2�1�7�1�7*/
 	return OK;
 }
 
 
 /*
- tips:不能有printf函数在里面！！！！！
- @看门狗服务程序
+ tips:�1�7�1�7�1�7�1�7�1�7�1�7printf�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7���1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7
+ @�1�7�1�7�1�7�0�1�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7
  */
-void FuncWd_InfoOutputCtrl (void)       /*定时处理函数，0.1s执行一次*/
+void FuncWd_InfoOutputCtrl (void)       /*�1�7�1�7�0�2�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�70.1s�0�4�1�7�1�7�0�5�1�7�1�7*/
 {
 	
 	Main_Ctrl_Task_Interval_Num++;
 
-	 /*接收*/
+	 /*�1�7�1�7�1�7�1�7*/
 	Net_Recv_Interval_Num++;
+	
+	Not_Recv_From_Jetson_No++;  /**< @brief Jetson ʧ������������, �յ���ʱ�� Unpack ������ */
 
 	if((Instruction_To_FMCU.McuFD_Power_Control&0x40) == 0x40)
 	{
@@ -783,7 +884,7 @@
 	{		
 		Not_Recv_From_GPS_No = 0;
 	}*/
-	Recv_Form_GPS_Interval_Num++;/*测试*/
+	Recv_Form_GPS_Interval_Num++;/*�1�7�1�7�1�7�1�7*/
 	Emergency_Task_Interval_Num++;
 	New_Store_File_Interval_Num++;  
 	 
@@ -797,7 +898,7 @@
 	
 	if(Main_Ctrl_Task_Interval_Num >= (Main_Ctrl_Task_Period ))
 	{		
-		semGive(semMainCtrlTask);         /*0.6s释放主任务信号量，主任务执行一次*/
+		semGive(semMainCtrlTask);         /*0.6s�1�7�0�5�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�2�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�4�1�7�1�7�0�5�1�7�1�7*/
 		Main_Ctrl_Task_Interval_Num = 0;
 	}
 	
@@ -814,7 +915,7 @@
 		Recv_Form_LORA_Interval_Num = 0;
 	}
 	
-	if(Recv_Form_BEIDOU_Interval_Num >= (Uart_Recv_Form_BEIDOU_Task_Period))/*61秒一次*/
+	if(Recv_Form_BEIDOU_Interval_Num >= (Uart_Recv_Form_BEIDOU_Task_Period))/*61�1�7�1�7�0�5�1�7�1�7*/
 	{	
 		semGive(semUartRecvFormBEIDOUTask);
 		Recv_Form_BEIDOU_Interval_Num = 0;
@@ -858,7 +959,7 @@
 	
 	if(New_Store_File_Interval_Num >= (New_Store_File_Period ))
 	{	
-		New_Store_File_Flag = true;/*创建新文件*/
+		New_Store_File_Flag = true;/*�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�4�1�7*/
 		New_Store_File_Interval_Num = 0;		
 	}
 	
@@ -869,10 +970,10 @@
 		
 	}
 	
-   /*发送*/
-
-	
-	wdStart(wdTimer_InfoOutputCtrl, sysClkRateGet()*0.1, (FUNCPTR)FuncWd_InfoOutputCtrl, 0);/*定时0.1s*/
+   /*�1�7�1�7�1�7�1�7*/
+
+	
+	wdStart(wdTimer_InfoOutputCtrl, sysClkRateGet()*0.1, (FUNCPTR)FuncWd_InfoOutputCtrl, 0);/*�1�7�1�7�0�20.1s*/
 }
 
 void PrintTask(void)
@@ -998,7 +1099,7 @@
 	printf("BMS_Abnorm_Inf:%d\n",BMS_Prase_Data.BMS_Abnorm_Inf);
 	
 	
-	/*BMS_summary_state数据
+	/*BMS_summary_state�1�7�1�7�1�7�1�7
 	printf("msg between CPU and BMS_summary_state::::\n");	
 	printf("addr:%2x\n",Get_summary_stateFromBMS.addr);
 	printf("function_code:%2x\n",Get_summary_stateFromBMS.function_code);
@@ -1018,7 +1119,7 @@
 	printf("clusterX_min_cell_temp:%d\n",Get_summary_stateFromBMS.clusterX_min_cell_temp);
 	printf("crc16_check_sum:%2x\n",Get_summary_stateFromBMS.crc16_check_sum);*/
 	
-	/*BMS_critical_state数据
+	/*BMS_critical_state�1�7�1�7�1�7�1�7
 	printf("msg between CPU and BMS_critical_state::::\n");	
 	printf("addr:%2x\n",Get_critical_stateFromBMS.addr);
 	printf("function_code:%2x\n",Get_critical_stateFromBMS.function_code);
@@ -1117,7 +1218,7 @@
 
 void between_CPU_and_UI12(void)
 {
-	/*wifi通信打印数据*/
+	/*wifi�0�0�1�7�0�6�1�7�0�3�1�7�1�7�1�7�1�7*/
 	u16 ii = 0;
 	printf("msg between CPU and UIWifi::::\n");
 	printf("Not_Recv_From_WIFI_No:%d\n", Not_Recv_From_WIFI_No);
@@ -1148,7 +1249,7 @@
 	printf("FromUI12_Set_Course:%3d\n",UI_WIFI_Instruction.FromUI12_Set_Course);
 	printf("FromUI12_Check_Sum:%2x\n",UI_WIFI_Instruction.FromUI12_Check_Sum);
 	printf("FromUI12_End_Buf:%2x,%2x\n",UI_WIFI_Instruction.FromUI12_End_Buf[0],UI_WIFI_Instruction.FromUI12_End_Buf[1]);
-	/*接收的数据*/
+	/*�1�7�1�7�1�7�0�1�1�7�1�7�1�7�1�7�1�7*/
 }
 
 void between_CPU_and_DVL(void)
@@ -1267,7 +1368,7 @@
 
 void PathPlanning_data_printf(void)
 {
-	/*定点航行参数
+	/*�1�7�1�7�1�7�2�4�1�7�ӄ1�7�1�7�1�7
 	u16 ii = 0;	
 	printf("FixedPoint_PathPlanning msg::::\n");
 	printf("TaskNumber:%s\n", FixedPoint_PathPlanning.TaskNumber);
@@ -1285,7 +1386,7 @@
 	
 	
 	
-	/*定向航行参数*/	
+	/*�1�7�1�7�1�7�1�7�1�7�ӄ1�7�1�7�1�7*/	
 	u16 ii = 0;	
 	printf("FixedDirection_PathPlanning msg::::\n");
 	printf("TaskNumber:%s\n", FixedDirection_PathPlanning.TaskNumber);
```

## `csd_vx6.8_lastest/SecurityEmergencyManage.c`

```diff
--- a/csd_vx6.8_lastest/SecurityEmergencyManage_bak.c
+++ b/csd_vx6.8_lastest/SecurityEmergencyManage.c
@@ -35,6 +35,13 @@
 u16 Not_Recv_From_BI_DVL_No = 0;
 u16 Not_Recv_From_WI_DVL_No = 0;
 
+/**
+ * @brief Jetson 失联计数器, 每 0.1s 递增一次 (在 FuncWd_InfoOutputCtrl 中)
+ * 收到 Jetson 数据包时清零 (在 Unpack_Data_From_UI12_WIFI 中)
+ * 阈值 10 = 1.0s 超时
+ */
+u16 Not_Recv_From_Jetson_No = 0;
+
 u32 Device_Power_State_Judgement=0;
 u32 Cmd_State_Judgement=0;
 u32 Sail_State_Judgement=0;
@@ -55,46 +62,105 @@
 		{
 			printf("EmergencyTask start::::\n");	
 			
-			/*如果当前状态是遥控且没有收到信号，返回值为-1的话，证明没有收到wifi数据*/
-	        if(Not_Recv_From_WIFI_No >=  20)           /*操控台通信异常*/
-			{
-				UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;/*主推停机*/
-			}
+			/*�����ǰ״̬��ң����û���յ��źţ�����ֵΪ-1�Ļ���֤��û���յ�wifi����*/
+	        if(Not_Recv_From_WIFI_No >=  20)           /*�ٿ�̨ͨ���쳣*/
+			{
+				UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;/*����ͣ��*/
+			}
+
+			/**
+			 * @brief Jetson 失联看门狗 (1.0s 超时)
+			 * 触发条件: Not_Recv_From_Jetson_No >= 10 (10×0.1s = 1.0s)
+			 * 仅在 0xEE/0xEF 模式下生效
+			 * 降级动作: 模式回退至 Remote(0x01), 推力归零, 急停
+			 */
+			if(Not_Recv_From_Jetson_No >= 10)
+			{
+				if(Current_State.Current_Mode == 0xEE || Current_State.Current_Mode == 0xEF)
+				{
+					UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0x01;  /* 降级到遥控模式 */
+					UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;  /* 推力归零 */
+					UI_WIFI_Instruction.FromUI12_Motor_Speed2 = 0;
+					Sys_Abnorm_Inf_Judgement |= 0x00004000;  /* Bit14: Jetson通信超时告警 */
+				}
+			}
+			else
+			{
+				Sys_Abnorm_Inf_Judgement &= 0xffffbfff;  /* 清除 Bit14 */
+			}
+			
+			/* BUG-5/6/7: 离底高度仲裁 + 水池安全 */
+#if POOL_TEST_MODE
+			Pool_Safety_Check();
+#else
+			Seafloor_Grounding_Arbitration();
+#endif
 	       
-			/*超过航行超深保护参数1，就主推停机*/
-	        if((Current_State.Current_Dep > UI_WIFI_Instruction.FromUI12_Depth_Para1) && (UI_WIFI_Instruction.FromUI12_Depth_Para1 != 0))/*这个的1，最终换成UI_WIFI_Instruction.FromUI12_Depth_Para1*/
+			/*�������г��������1��������ͣ��*/
+	        /* BUG-3 fix: 滑动窗口防抖, 深度回升时递减 (修复只增不减闩锁) */
+	        if((Current_State.Current_Dep > UI_WIFI_Instruction.FromUI12_Depth_Para1) && (UI_WIFI_Instruction.FromUI12_Depth_Para1 != 0))
 	        {
-	        	Depth_Exceed_FromUI12_Depth_Para1++;	        	
+	        	Depth_Exceed_FromUI12_Depth_Para1++;
+	        }
+	        else
+	        {
+	        	if(Depth_Exceed_FromUI12_Depth_Para1 > 0) Depth_Exceed_FromUI12_Depth_Para1--;
 	        }
 
             
 	        if(Depth_Exceed_FromUI12_Depth_Para1 >= 10)
 	        {
-	        	Sys_Abnorm_Inf_Judgement |= 0x00000200;	/*超过航行超深参数1，就将对应位置1*/
+	        	Sys_Abnorm_Inf_Judgement |= 0x00000200;
 	        	
-	        	UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;/*主推停机*/
-	         	
+	        	/*
+	        	 * BUG-4 fix: 欠驱动AUV超深自救 - 保持最低舵效航速 + 打满上浮舵
+	        	 * 旧逻辑(致命bug): Motor_Speed1=0 导致失去舵效直接沉底
+	        	 */
+	        	Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 300;
+	        	Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location + 20.0f * 4096/360);
+	        	Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location - 20.0f * 4096/360);
+	        	Remote_Assignment(&Instruction_To_FMCU);
 	        }
 	        
-	        /*超过航行超深保护参数1，就主推停机,丢压载*/
-	        if((Current_State.Current_Dep > UI_WIFI_Instruction.FromUI12_Depth_Para2) && (UI_WIFI_Instruction.FromUI12_Depth_Para2 != 0))/*这个的2，最终换成UI_WIFI_Instruction.FromUI12_Depth_Para2*/
+	        /*�������г��������1��������ͣ��,��ѹ��*/
+	        if((Current_State.Current_Dep > UI_WIFI_Instruction.FromUI12_Depth_Para2) && (UI_WIFI_Instruction.FromUI12_Depth_Para2 != 0))
 	        {
 	        	Depth_Exceed_FromUI12_Depth_Para2++;
 	        }
+	        else
+	        {
+	        	if(Depth_Exceed_FromUI12_Depth_Para2 > 0) Depth_Exceed_FromUI12_Depth_Para2--;
+	        }
 
 	        
 	        if(Depth_Exceed_FromUI12_Depth_Para2 >= 10)
 	        {
-	        	Sys_Abnorm_Inf_Judgement |= 0x00000400;	/*超过航行超深参数2，就将对应位置1*/
+	        	Sys_Abnorm_Inf_Judgement |= 0x00000400;
 	        	
-	        	UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;/*主推停机*/
+	        	/* BUG-4 fix: 保持舵效 + 打满上浮舵 + 应急压载 */
+	        	Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 300;
+	        	Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location + 20.0f * 4096/360);
+	        	Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location - 20.0f * 4096/360);
 	        	
-	        	EL_Power_Control(Power_ON);/*应急压载上电*/
-	        	
+	        	EL_Power_Control(Power_ON);
 	        	Remote_Assignment(&Instruction_To_FMCU);
+	        }
+
+	        /**
+	         * @brief 深度超限模式回退 (0xEE/0xEF 模式专用)
+	         * 当 Depth_Para1 触发深度超限(连续10次), 在 Jetson 自主模式下
+	         * 额外执行模式降级: 回退至 Remote(0x01), 防止 Jetson 继续下潜
+	         */
+	        if(Depth_Exceed_FromUI12_Depth_Para1 >= 10)
+	        {
+	        	if(Current_State.Current_Mode == 0xEE || Current_State.Current_Mode == 0xEF)
+	        	{
+	        		UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0x01;  /* 模式降级 */
+	        		UI_WIFI_Instruction.FromUI12_Motor_Speed2 = 0;
+	        	}
 	        }	 
 	        
-	        if(Not_Recv_From_GPS_No >= 30)/*接收不到GPS信号，5次*/
+	        if(Not_Recv_From_GPS_No >= 30)/*���ղ���GPS�źţ�5��*/
 	        {
 	        	Recv_From_GPS_QC_Flag = false;
 	        }
@@ -102,17 +168,17 @@
 	        
 	        if(Not_Recv_From_BI_DVL_No >= 20 )
 	        {
-	          BI_Cal_Data_Flag = false;/*BI推算 标志位 错误*/
+	          BI_Cal_Data_Flag = false;/*BI���� ��־λ ����*/
 	        }
 	        
 	        if(Not_Recv_From_WI_DVL_No >= 20 )
 	        {
-	          WI_Cal_Data_Flag = false;/*BI推算 标志位 错误*/
+	          WI_Cal_Data_Flag = false;/*BI���� ��־λ ����*/
 	        }
 	        
-			/*解析Data_From_FMCU.McuFD_Sys_Abnorm_Inf*/
-			
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0:  舱体漏水报警*/
+			/*����Data_From_FMCU.McuFD_Sys_Abnorm_Inf*/
+			
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0:  ����©ˮ����*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00000001;		
 				Emergency_Level3();
@@ -122,7 +188,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xfffffffe;	
 			}		
 			
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: 舱体温度超限报警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: �����¶ȳ��ޱ���*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00000002;		
 				Emergency_Level1();
@@ -132,7 +198,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xfffffffd;
 			}	
 			
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: 舱体压力异常报警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: ����ѹ���쳣����*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00000004;	    
 				Emergency_Level3();
@@ -142,7 +208,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xfffffffb;
 			}
 					
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: 系统能源异常告警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: ϵͳ��Դ�쳣�澯*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00000008;
 				Emergency_Level2();
@@ -152,7 +218,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xfffffff7;
 			}
 			
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: 设备能源异常告警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: �豸��Դ�쳣�澯*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00000010;	
 				Emergency_Level2();
@@ -162,7 +228,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xffffffef;
 			}
 			
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: 系统通信异常告警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: ϵͳͨ���쳣�澯*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00000020;	 
 				Emergency_Level1();
@@ -172,7 +238,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xffffffdf;
 			}
 			
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: 设备状态异常告警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: �豸״̬�쳣�澯*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00000040;	
 				Emergency_Level2();
@@ -182,7 +248,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xffffffbf;
 			}
 				
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: MCU→CPU通信异常告警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: MCU��CPUͨ���쳣�澯*/
 			{	
 				Sys_Abnorm_Inf_Judgement |= 0x00000080;	  
 				Emergency_Level2();
@@ -195,7 +261,7 @@
 		/*****************************************************************************/	
 			
 			
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: CPU→MCU通信异常告警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: CPU��MCUͨ���쳣�澯*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00000100;	
 				Emergency_Level2();
@@ -205,7 +271,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xfffffeff;	
 			}
 					
-			/*if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0200) == 0x0200)  Bit9：航行超深保护参数1告警
+			/*if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0200) == 0x0200)  Bit9�����г��������1�澯
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00000200;	
 				Emergency_Level1();
@@ -215,7 +281,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xfffffdff;
 			}*/
 			
-			/*if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0400) == 0x0400)Bit10: 航行超深保护参数2告警
+			/*if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0400) == 0x0400)Bit10: ���г��������2�澯
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00000400;	
 				Emergency_Level2();
@@ -225,7 +291,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xfffffbff;
 			}*/
 				
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11: 离底超限保护参数1告警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11: ��׳��ޱ�������1�澯*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00000800;	
 				Emergency_Level1();
@@ -235,7 +301,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xfffff7ff;
 			}
 			
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12：离底超限保护参数2告警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12����׳��ޱ�������2�澯*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00001000;	
 				Emergency_Level2();
@@ -245,7 +311,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xffffefff;
 			}
 					
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: 下潜超时告警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: ��Ǳ��ʱ�澯*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00002000;	
 				Emergency_Level1();
@@ -255,7 +321,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xffffdfff;
 			}		
 				
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:航行超时告警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:���г�ʱ�澯*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00004000;	
 				Emergency_Level1();
@@ -265,7 +331,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xffffbfff;
 			}
 				
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:下潜姿态超限告警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:��Ǳ��̬���޸澯*/
 			{	
 				Sys_Abnorm_Inf_Judgement |= 0x00008000;	
 				Emergency_Level1();
@@ -279,7 +345,7 @@
 			/********************************************************************************/		
 			
 			
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: 航行姿态超限告警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: ������̬���޸澯*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00010000;	
 				Emergency_Level1();
@@ -289,7 +355,7 @@
 				Sys_Abnorm_Inf_Judgement &= 0xfffeffff;	
 			}			
 			
-			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: 偏航距超限告警*/
+			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: ƫ���೬�޸澯*/
 			{
 				Sys_Abnorm_Inf_Judgement |= 0x00020000;	
 				Emergency_Level1();
@@ -302,8 +368,8 @@
 	
 
 			
-			/*解析Data_From_FMCU.McuFD_Dev_Abnorm_Inf*/		
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0: 主推能源异常告警 */
+			/*����Data_From_FMCU.McuFD_Dev_Abnorm_Inf*/		
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0: ������Դ�쳣�澯 */
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00000001;		
 				Emergency_Level3();
@@ -313,7 +379,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfffffffe;	
 			}
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: 侧推能源异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: ������Դ�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00000002;
 				Emergency_Level3();
@@ -323,7 +389,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfffffffd;
 			}
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: 水平左舵能源异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: ˮƽ�����Դ�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00000004;	  
 				Emergency_Level3();
@@ -333,7 +399,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfffffffb;
 			}		
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: 水平右舵能源异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: ˮƽ�Ҷ���Դ�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00000008;	  
 				Emergency_Level3();
@@ -343,7 +409,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfffffff7;
 			}		
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: 垂直上舵能源异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: ��ֱ�϶���Դ�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00000010;	
 				Emergency_Level3();
@@ -353,7 +419,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xffffffef;
 			}
 					
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: 垂直下舵能源异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: ��ֱ�¶���Դ�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00000020;	  
 				Emergency_Level3();
@@ -363,7 +429,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xffffffdf;
 			}
 						
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: 应急压载能源异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: Ӧ��ѹ����Դ�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00000040;		
 				Emergency_Level3();
@@ -373,7 +439,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xffffffbf;
 			}
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: DVL能源异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: DVL��Դ�쳣�澯*/
 			{	
 				Dev_Abnorm_Inf_Judgement |= 0x00000080;	  
 				Emergency_Level3();
@@ -386,7 +452,7 @@
 		/*****************************************************************************/	
 			
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: 备用1能源异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: ����1��Դ�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00000100;	
 				Emergency_Level3();
@@ -396,7 +462,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfffffeff;	
 			}
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0200) == 0x0200)  /*Bit9：备用2能源异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0200) == 0x0200)  /*Bit9������2��Դ�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00000200;		
 				Emergency_Level3();
@@ -406,7 +472,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfffffdff;
 			}
 					
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0400) == 0x0400)/*Bit10: 主推通信异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0400) == 0x0400)/*Bit10: ����ͨ���쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00000400;	 
 				Emergency_Level2();
@@ -416,7 +482,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfffffbff;
 			}
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11:侧推通信异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11:����ͨ���쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00000800;	 
 				Emergency_Level2();
@@ -426,7 +492,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfffff7ff;
 			}
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12：水平左舵通信异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12��ˮƽ���ͨ���쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00001000;	
 				Emergency_Level2();
@@ -436,7 +502,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xffffefff;
 			}
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: 水平右舵通信异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: ˮƽ�Ҷ�ͨ���쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00002000;	  
 				Emergency_Level2();
@@ -446,7 +512,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xffffdfff;
 			}
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:垂直上舵通信异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:��ֱ�϶�ͨ���쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00004000;	
 				Emergency_Level2();
@@ -457,7 +523,7 @@
 			}
 				
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:垂直下舵通信异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:��ֱ�¶�ͨ���쳣�澯*/
 			{	
 				Dev_Abnorm_Inf_Judgement |= 0x00008000;	  
 				Emergency_Level2();
@@ -471,7 +537,7 @@
 			/********************************************************************************/		
 			
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: DVL通信异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: DVLͨ���쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00010000;	
 				Emergency_Level2();
@@ -481,7 +547,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfffeffff;	
 			}
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: 罗经通信异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: �޾�ͨ���쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00020000;		
 				Emergency_Level2();
@@ -491,7 +557,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfffdffff;
 			}
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00040000) == 0x00040000)/*bit18:备用1通信异常告警 */
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00040000) == 0x00040000)/*bit18:����1ͨ���쳣�澯 */
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00040000;	  
 				Emergency_Level2();
@@ -501,7 +567,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfffbffff;
 			}		
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00080000) == 0x00080000)/*bit19: 备用2通信异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00080000) == 0x00080000)/*bit19: ����2ͨ���쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00080000;	   
 				Emergency_Level2();
@@ -511,7 +577,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfff7ffff;
 			}
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00100000) == 0x00100000)  /*Bit20: 主推状态异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00100000) == 0x00100000)  /*Bit20: ����״̬�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00100000;	
 				Emergency_Level1();
@@ -521,7 +587,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xffefffff;
 			}
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00200000) == 0x00200000) /*Bit21: 侧推状态异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00200000) == 0x00200000) /*Bit21: ����״̬�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00200000;	    
 				Emergency_Level1();
@@ -531,7 +597,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xffdfffff;
 			}
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00400000) == 0x00400000)  /*Bit22: 水平左舵状态异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00400000) == 0x00400000)  /*Bit22: ˮƽ���״̬�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x00400000;	
 				Emergency_Level1();
@@ -542,7 +608,7 @@
 			}
 				
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00800000) == 0x00800000)  /*Bit23:水平右舵状态异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00800000) == 0x00800000)  /*Bit23:ˮƽ�Ҷ�״̬�쳣�澯*/
 			{	
 				Dev_Abnorm_Inf_Judgement |= 0x00800000;	 
 				Emergency_Level1();
@@ -554,7 +620,7 @@
 			/********************************************************************************/		
 
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x01000000) == 0x01000000)    /*Bit24: 垂直上舵状态异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x01000000) == 0x01000000)    /*Bit24: ��ֱ�϶�״̬�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x01000000;		
 				Emergency_Level1();
@@ -564,7 +630,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfeffffff;	
 			}
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x02000000) == 0x02000000)  /*Bit25：垂直下舵状态异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x02000000) == 0x02000000)  /*Bit25����ֱ�¶�״̬�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x02000000;
 				Emergency_Level1();
@@ -575,7 +641,7 @@
 			}
 				
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x04000000) == 0x04000000)/*Bit26:应急压载状态异常告警（无效置零） */
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x04000000) == 0x04000000)/*Bit26:Ӧ��ѹ��״̬�쳣�澯����Ч���㣩 */
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x04000000;
 				Emergency_Level1();
@@ -585,7 +651,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xfbffffff;
 			}
 						
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x08000000) == 0x08000000)/*Bit27: DVL状态异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x08000000) == 0x08000000)/*Bit27: DVL״̬�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x08000000;
 				Emergency_Level1();
@@ -595,7 +661,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xf7ffffff;
 			}		
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x10000000) == 0x10000000)  /*Bit28：罗经状态异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x10000000) == 0x10000000)  /*Bit28���޾�״̬�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x10000000;
 				Emergency_Level1();
@@ -605,7 +671,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xefffffff;
 			}		
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x20000000) == 0x20000000) /*Bit29:备用1状态异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x20000000) == 0x20000000) /*Bit29:����1״̬�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x20000000;	  
 				Emergency_Level1();
@@ -615,7 +681,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xdfffffff;
 			}
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x40000000) == 0x40000000)  /*Bit30:备用2状态异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x40000000) == 0x40000000)  /*Bit30:����2״̬�쳣�澯*/
 			{
 				Dev_Abnorm_Inf_Judgement |= 0x40000000;
 				Emergency_Level1();
@@ -625,7 +691,7 @@
 				Dev_Abnorm_Inf_Judgement &= 0xbfffffff;
 			}		
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x80000000) == 0x80000000)  /*Bit31:通信模块能源异常告警*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x80000000) == 0x80000000)  /*Bit31:ͨ��ģ����Դ�쳣�澯*/
 			{	
 				Dev_Abnorm_Inf_Judgement |= 0x80000000;
 				Emergency_Level1();
@@ -638,8 +704,8 @@
 			
 
 			
-			/*接收BMS_Prase_Data.BMS_Abnorm_Inf之后，立马进行状态判断*/
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0:  单体过压一级报警*/
+			/*����BMS_Prase_Data.BMS_Abnorm_Inf֮����������״̬�ж�*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0:  �����ѹһ������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00000001;
 				Emergency_Level1();
@@ -650,7 +716,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: 系统过压一级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: ϵͳ��ѹһ������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00000002;
 				Emergency_Level1();
@@ -661,7 +727,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: 充电过流一级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: ������һ������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00000004;
 				Emergency_Level1();
@@ -672,7 +738,7 @@
 			}
 				
 				
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: 单体欠压一级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: ����Ƿѹһ������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00000008;
 				Emergency_Level1();
@@ -683,7 +749,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: 系统欠压一级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: ϵͳǷѹһ������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00000010;
 				Emergency_Level1();
@@ -694,7 +760,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: 放电过流一级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: �ŵ����һ������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00000020;
 				Emergency_Level1();
@@ -705,7 +771,7 @@
 			}
 				
 				
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: 充电温度过高一级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: ����¶ȹ���һ������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00000040;
 				Emergency_Level1();
@@ -716,7 +782,7 @@
 			}
 				
 				
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: 充电温度过低一级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: ����¶ȹ���һ������*/
 			{	
 				BMS_Abnorm_Inf_Judgement |= 0x00000080;
 				Emergency_Level1();
@@ -729,7 +795,7 @@
 		/*****************************************************************************/	
 			
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: SOC过低一级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: SOC����һ������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00000100;
 				Emergency_Level1();
@@ -740,7 +806,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0200) == 0x0200)  /*Bit9：充电过流三级告警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0200) == 0x0200)  /*Bit9�������������澯*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00000200;
 				Emergency_Level3();
@@ -751,7 +817,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0400) == 0x0400)/*Bit10: 功率温度过高一级告警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0400) == 0x0400)/*Bit10: �����¶ȹ���һ���澯*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00000400;
 				Emergency_Level1();
@@ -762,7 +828,7 @@
 			}
 				
 				
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11: 环境温度过高一级告警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11: �����¶ȹ���һ���澯*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00000800;
 				Emergency_Level1();
@@ -773,7 +839,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12：环境温度过低一级告警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12�������¶ȹ���һ���澯*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00001000;
 				Emergency_Level1();
@@ -784,7 +850,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: 放电过流三级告警（无效）*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: �ŵ���������澯����Ч��*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00002000;
 				Emergency_Level3();
@@ -795,7 +861,7 @@
 			}
 				
 				
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:放电温度过高一级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:�ŵ��¶ȹ���һ������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00004000;
 				Emergency_Level1();
@@ -806,7 +872,7 @@
 			}
 				
 				
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:放电温度过低一级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:�ŵ��¶ȹ���һ������*/
 			{	
 				BMS_Abnorm_Inf_Judgement |= 0x00008000;
 				Emergency_Level1();
@@ -820,7 +886,7 @@
 			/********************************************************************************/		
 			
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: 单体过压二级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: �����ѹ��������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00010000;
 				Emergency_Level2();
@@ -831,7 +897,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: 系统过压二级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: ϵͳ��ѹ��������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00020000;
 				Emergency_Level2();
@@ -842,7 +908,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00040000) == 0x00040000)/*bit18: 充电过流二级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00040000) == 0x00040000)/*bit18: ��������������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00040000;
 				Emergency_Level2();
@@ -853,7 +919,7 @@
 			}
 				
 				
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00080000) == 0x00080000)/*bit19: 单体欠压二级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00080000) == 0x00080000)/*bit19: ����Ƿѹ��������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00080000;
 				Emergency_Level2();
@@ -864,7 +930,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00100000) == 0x00100000)  /*Bit20: 系统欠压二级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00100000) == 0x00100000)  /*Bit20: ϵͳǷѹ��������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00100000;
 				Emergency_Level2();
@@ -874,7 +940,7 @@
 				BMS_Abnorm_Inf_Judgement &= 0xffefffff;	
 			}
 				
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00200000) == 0x00200000) /*Bit21: 放电过流二级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00200000) == 0x00200000) /*Bit21: �ŵ������������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00200000;
 				Emergency_Level2();
@@ -885,7 +951,7 @@
 			}
 				
 				
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00400000) == 0x00400000)  /*Bit22: 充电温度过高二级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00400000) == 0x00400000)  /*Bit22: ����¶ȹ��߶�������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x00400000;
 				Emergency_Level2();
@@ -896,7 +962,7 @@
 			}
 				
 				
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00800000) == 0x00800000)  /*Bit23: 充电温度过低二级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00800000) == 0x00800000)  /*Bit23: ����¶ȹ��Ͷ�������*/
 			{	
 				BMS_Abnorm_Inf_Judgement |= 0x00800000;
 				Emergency_Level2();
@@ -909,7 +975,7 @@
 			/********************************************************************************/		
 
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x01000000) == 0x01000000)    /*Bit24: SOC过低二级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x01000000) == 0x01000000)    /*Bit24: SOC���Ͷ�������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x01000000;
 				Emergency_Level2();
@@ -920,7 +986,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x02000000) == 0x02000000)  /*Bit25：充电过流三级告警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x02000000) == 0x02000000)  /*Bit25�������������澯*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x02000000;
 				Emergency_Level3();
@@ -931,7 +997,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x04000000) == 0x04000000)/*Bit26: 功率温度过高二级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x04000000) == 0x04000000)/*Bit26: �����¶ȹ��߶�������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x04000000;
 				Emergency_Level2();
@@ -942,7 +1008,7 @@
 			}
 				
 				
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x08000000) == 0x08000000)/*Bit27: 环境温度过高二级告警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x08000000) == 0x08000000)/*Bit27: �����¶ȹ��߶����澯*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x08000000;
 				Emergency_Level2();
@@ -953,7 +1019,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x10000000) == 0x10000000)  /*Bit28：环境温度过低二级告警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x10000000) == 0x10000000)  /*Bit28�������¶ȹ��Ͷ����澯*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x10000000;
 				Emergency_Level2();
@@ -964,7 +1030,7 @@
 			}
 				
 			
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x20000000) == 0x20000000) /*Bit29: 放电过流三级告警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x20000000) == 0x20000000) /*Bit29: �ŵ���������澯*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x20000000;
 				Emergency_Level3();
@@ -975,7 +1041,7 @@
 			}
 				
 				
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x40000000) == 0x40000000)  /*Bit30:放电温度过高二级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x40000000) == 0x40000000)  /*Bit30:�ŵ��¶ȹ��߶�������*/
 			{
 				BMS_Abnorm_Inf_Judgement |= 0x40000000;
 				Emergency_Level2();
@@ -986,7 +1052,7 @@
 			}
 				
 				
-			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x80000000) == 0x80000000)  /*Bit31:放电温度过低二级报警*/
+			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x80000000) == 0x80000000)  /*Bit31:�ŵ��¶ȹ��Ͷ�������*/
 			{	
 				BMS_Abnorm_Inf_Judgement |= 0x80000000;
 				Emergency_Level2();
@@ -998,8 +1064,8 @@
 								
 			
 			
-			/*解析Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail*/
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0001) == 0x0001)    /*bit0: 水平左舵舵机过载*/
+			/*����Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0001) == 0x0001)    /*bit0: ˮƽ���������*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000001;
 				Emergency_Level3();
@@ -1009,7 +1075,7 @@
 				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffffe;	
 			}
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0002) == 0x0002)  /*bit1: 水平左舵舵机过流*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0002) == 0x0002)  /*bit1: ˮƽ���������*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000002;
 				Emergency_Level3();
@@ -1019,7 +1085,7 @@
 				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffffd;
 			}
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0004) == 0x0004)/*bit2: 水平左舵舵机过热*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0004) == 0x0004)/*bit2: ˮƽ���������*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000004;
 				Emergency_Level3();
@@ -1030,7 +1096,7 @@
 			}
 				
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0008) == 0x0008)/*bit3: 水平左舵舵机角度错误*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0008) == 0x0008)/*bit3: ˮƽ������Ƕȴ���*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000008;
 				Emergency_Level3();
@@ -1041,7 +1107,7 @@
 			}
 				
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0010) == 0x0010)  /*Bit4: 水平左舵舵机过压欠压*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0010) == 0x0010)  /*Bit4: ˮƽ�������ѹǷѹ*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000010;
 				Emergency_Level3();
@@ -1052,7 +1118,7 @@
 			}
 				
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0020) == 0x0020) /*Bit5: ：水平右舵舵机过载*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0020) == 0x0020) /*Bit5: ��ˮƽ�Ҷ�������*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000020;
 				Emergency_Level3();
@@ -1063,7 +1129,7 @@
 			}
 				
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0040) == 0x0040)  /*Bit6: 水平右舵舵机过流*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0040) == 0x0040)  /*Bit6: ˮƽ�Ҷ�������*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000040;
 				Emergency_Level3();
@@ -1074,7 +1140,7 @@
 			}
 				
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0080) == 0x0080)  /*Bit7: 水平右舵舵机过热*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0080) == 0x0080)  /*Bit7: ˮƽ�Ҷ�������*/
 			{	
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000080;
 				Emergency_Level3();
@@ -1087,7 +1153,7 @@
 		/*****************************************************************************/	
 			
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0100) == 0x0100)    /*Bit8: 水平右舵舵机角度错误*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0100) == 0x0100)    /*Bit8: ˮƽ�Ҷ����Ƕȴ���*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000100;
 				Emergency_Level3();
@@ -1098,7 +1164,7 @@
 			}
 				
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0200) == 0x0200)  /*Bit9：水平右舵舵机过压欠压*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0200) == 0x0200)  /*Bit9��ˮƽ�Ҷ�����ѹǷѹ*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000200;
 				Emergency_Level3();
@@ -1109,7 +1175,7 @@
 			}
 				
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0400) == 0x0400)/*Bit10: 垂直上舵舵机过载*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0400) == 0x0400)/*Bit10: ��ֱ�϶�������*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000400;
 				Emergency_Level3();
@@ -1120,7 +1186,7 @@
 			}
 				
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0800) == 0x0800)/*Bit11: 垂直上舵舵机过流*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0800) == 0x0800)/*Bit11: ��ֱ�϶�������*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000800;
 				Emergency_Level3();
@@ -1131,7 +1197,7 @@
 			}
 				
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x1000) == 0x1000)  /*Bit12：垂直上舵舵机过热*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x1000) == 0x1000)  /*Bit12����ֱ�϶�������*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00001000;
 				Emergency_Level3();
@@ -1142,7 +1208,7 @@
 			}
 				
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x2000) == 0x2000) /*Bit13: 垂直上舵舵机角度错误*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x2000) == 0x2000) /*Bit13: ��ֱ�϶����Ƕȴ���*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00002000;
 				Emergency_Level3();
@@ -1153,7 +1219,7 @@
 			}
 				
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x4000) == 0x4000)  /*Bit14:垂直上舵舵机过压欠压*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x4000) == 0x4000)  /*Bit14:��ֱ�϶�����ѹǷѹ*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00004000;
 				Emergency_Level3();
@@ -1163,7 +1229,7 @@
 				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffbfff;
 			}		
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x8000) == 0x8000)  /*Bit15: 垂直下舵舵机过载*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x8000) == 0x8000)  /*Bit15: ��ֱ�¶�������*/
 			{	
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00008000;
 				Emergency_Level3();
@@ -1177,7 +1243,7 @@
 			/********************************************************************************/		
 			
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00010000) == 0x00010000)    /*bit16: 垂直下舵舵机过流*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00010000) == 0x00010000)    /*bit16: ��ֱ�¶�������*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00010000;
 				Emergency_Level3();
@@ -1188,7 +1254,7 @@
 			}
 					
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00020000) == 0x00020000)  /*bit17: 垂直下舵舵机过热*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00020000) == 0x00020000)  /*bit17: ��ֱ�¶�������*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00020000;
 				Emergency_Level3();
@@ -1199,7 +1265,7 @@
 			}
 				
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00040000) == 0x00040000)/*bit18: 垂直下舵舵机角度错误*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00040000) == 0x00040000)/*bit18: ��ֱ�¶����Ƕȴ���*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00040000;
 				Emergency_Level3();
@@ -1210,7 +1276,7 @@
 			}
 				
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00080000) == 0x00080000)/*bit19: 垂直下舵舵机过压欠压*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00080000) == 0x00080000)/*bit19: ��ֱ�¶�����ѹǷѹ*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00080000;
 				Emergency_Level3();
@@ -1221,7 +1287,7 @@
 			}
 				
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00100000) == 0x00100000)  /*Bit20: 主推堵转停止*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00100000) == 0x00100000)  /*Bit20: ���ƶ�תֹͣ*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00100000;
 				Emergency_Level3();
@@ -1232,7 +1298,7 @@
 			}
 				
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00200000) == 0x00200000) /*Bit21:主推不达速 */
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00200000) == 0x00200000) /*Bit21:���Ʋ����� */
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00200000;
 				Emergency_Level3();
@@ -1243,7 +1309,7 @@
 			}
 				
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00400000) == 0x00400000)  /*Bit22: 主推霍尔错误*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00400000) == 0x00400000)  /*Bit22: ���ƻ�������*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00400000;
 				Emergency_Level3();
@@ -1254,7 +1320,7 @@
 			}
 				
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00800000) == 0x00800000)  /*Bit23: 无效置零*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00800000) == 0x00800000)  /*Bit23: ��Ч����*/
 			{	
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x00800000;
 				Emergency_Level1();
@@ -1267,7 +1333,7 @@
 			/********************************************************************************/		
 
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x01000000) == 0x01000000)    /*Bit24: 无效置零*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x01000000) == 0x01000000)    /*Bit24: ��Ч����*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x01000000;
 				Emergency_Level1();
@@ -1278,7 +1344,7 @@
 			}
 				
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x02000000) == 0x02000000)  /*Bit25：无效置零*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x02000000) == 0x02000000)  /*Bit25����Ч����*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x02000000;
 				Emergency_Level1();
@@ -1289,7 +1355,7 @@
 			}
 				
 			
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x04000000) == 0x04000000)/*Bit26: DVL自检异常*/
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x04000000) == 0x04000000)/*Bit26: DVL�Լ��쳣*/
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x04000000;
 				Emergency_Level3();
@@ -1300,7 +1366,7 @@
 			}
 				
 				
-			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x08000000) == 0x08000000)/*Bit27:DVL对底无效 */
+			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x08000000) == 0x08000000)/*Bit27:DVL�Ե���Ч */
 			{
 				Dev_Abnorm_Inf_Detail_Judgement |= 0x08000000;
 				Emergency_Level3();
@@ -1330,9 +1396,229 @@
 void Emergency_Level3(void)
 {
 /*	
-	UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;/*主推停机*/
-	
-	/*EL_Power_Control(Power_ON);应急压载上电*/
+	UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;/*����ͣ��*/
+	
+	/*EL_Power_Control(Power_ON);Ӧ��ѹ���ϵ�*/
 	
 	/*	Remote_Assignment(&Instruction_To_FMCU);*/
+}
+
+/**
+ * @brief 离底高度硬栅栏安全仲裁 + DVL丢底自救 (BUG-5, BUG-6)
+ * 
+ * 10Hz运行于EmergencyTask, 实现双层保护:
+ * - 软限(3.0m): 预警 + 锁死目标深度不允许更深
+ * - 硬限(1.8m): 强制夺权, 调用HightCtrlAlgorithm拉起至4m
+ * - DVL丢底2.0s: 模式降级 + 定深上浮至2m
+ * 
+ * @note 水池模式(POOL_TEST_MODE=1)下参数自动覆盖为 soft=0.8m, hard=0.4m
+ */
+/**
+ * @brief 水池测试安全模式 (BUG-7)
+ * 
+ * 仅在 POOL_TEST_MODE=1 时编译激活.
+ * 多维度交叉检查: 深度/俯仰/横摇/转速
+ */
+#if POOL_TEST_MODE
+void Pool_Safety_Check(void)
+{
+	/* 1. 深度硬围栏: 水池1.5m, AUV深度不超过0.9m */
+	if(Current_State.Current_Dep > 0.9f)
+	{
+		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 0;
+		Instruction_To_FMCU.McuFD_Motor2_Set_Speed = 0;
+		/* 打满上浮舵 */
+		Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location + 20.0f * 4096/360);
+		Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location - 20.0f * 4096/360);
+		Remote_Assignment(&Instruction_To_FMCU);
+		Sys_Abnorm_Inf_Judgement |= 0x00008000;  /* Bit15: 水池深度超限 */
+		return;
+	}
+	
+	/* 2. 纵摇(Pitch)极限截断: 受限空间内严禁大角度抬头/低头 */
+	if(Current_State.Current_IMU_Pitch > 10.0f || Current_State.Current_IMU_Pitch < -10.0f)
+	{
+		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 0;
+		Instruction_To_FMCU.McuFD_Motor2_Set_Speed = 0;
+		Remote_Assignment(&Instruction_To_FMCU);
+		Sys_Abnorm_Inf_Judgement |= 0x00010000;  /* Bit16: 水池Pitch超限 */
+		return;
+	}
+	
+	/* 3. 横摇(Roll)翻转保护: 防止螺旋桨反扭矩导致潜器倾覆 */
+	if(Current_State.Current_IMU_Roll > 20.0f || Current_State.Current_IMU_Roll < -20.0f)
+	{
+		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 0;
+		Instruction_To_FMCU.McuFD_Motor2_Set_Speed = 0;
+		Remote_Assignment(&Instruction_To_FMCU);
+		Sys_Abnorm_Inf_Judgement |= 0x00020000;  /* Bit17: 水池Roll超限 */
+		return;
+	}
+	
+	/* 4. 水池极速限幅: 转速严禁超过200 RPM (防撞墙) */
+	if(Instruction_To_FMCU.McuFD_Motor1_Set_Speed > 200)
+	{
+		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 200;
+	}
+	if(Instruction_To_FMCU.McuFD_Motor2_Set_Speed > 200)
+	{
+		Instruction_To_FMCU.McuFD_Motor2_Set_Speed = 200;
+	}
+	
+	/* 水池模式下也运行高度仲裁 (参数已自动覆盖为0.4m/0.8m) */
+	Seafloor_Grounding_Arbitration();
 }
+#endif
+
+void Seafloor_Grounding_Arbitration(void)
+{
+	float current_altitude = DVL_Prase_Data.BD_Height;
+	float dvl_status = DVL_Prase_Data.BD_Check;
+	
+#if POOL_TEST_MODE
+	float hard_limit_altitude = 0.4f;
+	float soft_limit_altitude = 0.8f;
+	float pull_up_target = 1.0f;
+#else
+	float hard_limit_altitude = 1.8f;
+	float soft_limit_altitude = 3.0f;
+	float pull_up_target = 4.0f;
+#endif
+	
+	static u16 altitude_critical_count = 0;
+	static u16 altitude_warning_count = 0;
+	static u16 dvl_lost_lock_count = 0;
+	
+	/*===========================================================
+	 * 1. DVL 锁底状态检查 + 丢底自救 (BUG-6)
+	 *===========================================================*/
+	if(dvl_status != 2.00f && dvl_status != 3.00f)
+	{
+		/* DVL 未锁底 */
+		dvl_lost_lock_count++;
+		altitude_critical_count = 0;
+		altitude_warning_count = 0;
+		Sys_Abnorm_Inf_Judgement &= ~0x00000800;
+		Sys_Abnorm_Inf_Judgement &= ~0x00001000;
+		
+		/* DVL 持续丢底 2.0s, 且处于 Jetson 自主模式 -> 自救 */
+		if(dvl_lost_lock_count >= 20)
+		{
+			if(Current_State.Current_Mode == Jetson_Shadow || Current_State.Current_Mode == Jetson_Hybrid)
+			{
+				float safe_up_rudder;
+				
+				/* 模式降级至 Remote */
+				UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0x01;
+				Sys_Abnorm_Inf_Judgement |= 0x00002000;  /* Bit13: DVL丢底降级告警 */
+				
+				/* 定深上浮至 2.0m 安全层 */
+				safe_up_rudder = DepthCtrlAlgorithm(
+					2.0f,
+					Current_State.Current_Dep,
+					Current_State.Current_IMU_Pitch,
+					IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1],
+					Current_State.Current_DVL_Velocity_Kn
+				);
+				
+				/* NaN 防御 */
+				if(safe_up_rudder != safe_up_rudder) safe_up_rudder = -20.0f;
+				if(safe_up_rudder < -20.0f) safe_up_rudder = -20.0f;
+				if(safe_up_rudder >  20.0f) safe_up_rudder =  20.0f;
+				
+				Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location - safe_up_rudder * 4096/360);
+				Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location + safe_up_rudder * 4096/360);
+				Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 300;
+				Remote_Assignment(&Instruction_To_FMCU);
+			}
+		}
+		return;
+	}
+	else
+	{
+		dvl_lost_lock_count = 0;
+		Sys_Abnorm_Inf_Judgement &= ~0x00002000;
+	}
+	
+	/*===========================================================
+	 * 2. 滑动窗口防抖 (过滤 DVL 气泡/浮泥假反射噪声)
+	 *===========================================================*/
+	if(current_altitude < hard_limit_altitude)
+	{
+		altitude_critical_count++;
+	}
+	else
+	{
+		if(altitude_critical_count > 0) altitude_critical_count--;
+	}
+	
+	if(current_altitude < soft_limit_altitude)
+	{
+		altitude_warning_count++;
+	}
+	else
+	{
+		if(altitude_warning_count > 0) altitude_warning_count--;
+	}
+	
+	/*===========================================================
+	 * 3. 仲裁与执行
+	 *===========================================================*/
+	
+	/* 级别1: 软限预警 (持续0.5s低于soft_limit) */
+	if(altitude_warning_count >= 5)
+	{
+		Sys_Abnorm_Inf_Judgement |= 0x00000800;  /* 离底超限保护参数1告警 */
+		
+		/* 锁死目标深度: 不允许 Jetson 继续下潜 */
+		if(Current_State.Current_Mode == Jetson_Shadow || Current_State.Current_Mode == Jetson_Hybrid)
+		{
+			float target_depth_m = (float)UI_WIFI_Instruction.FromUI12_Para1 / 1000.0f;
+			if(target_depth_m > Current_State.Current_Dep)
+			{
+				UI_WIFI_Instruction.FromUI12_Para1 = (int)(Current_State.Current_Dep * 1000.0f);
+			}
+		}
+	}
+	else
+	{
+		Sys_Abnorm_Inf_Judgement &= ~0x00000800;
+	}
+	
+	/* 级别2: 硬限危机 (持续0.3s低于hard_limit) - 物理防撞 */
+	if(altitude_critical_count >= 3)
+	{
+		float pull_up_rudder;
+		
+		Sys_Abnorm_Inf_Judgement |= 0x00001000;  /* 离底超限保护参数2告警 */
+		
+		/* 强制夺权: 调用 HightCtrlAlgorithm 拉起 */
+		pull_up_rudder = HightCtrlAlgorithm(
+			pull_up_target,
+			current_altitude,
+			Current_State.Current_IMU_Pitch,
+			IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1],
+			Current_State.Current_DVL_Velocity_Kn
+		);
+		
+		/* NaN 防御 + 限幅 */
+		if(pull_up_rudder != pull_up_rudder) pull_up_rudder = -20.0f;
+		if(pull_up_rudder < -20.0f) pull_up_rudder = -20.0f;
+		if(pull_up_rudder >  20.0f) pull_up_rudder =  20.0f;
+		
+		/* 限制推力, 维持舵效 */
+		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 350;
+		
+		/* 上浮舵输出 */
+		Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location - pull_up_rudder * 4096/360);
+		Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location + pull_up_rudder * 4096/360);
+		
+		/* 覆盖影子模式控制, 直接发往 MCU */
+		Remote_Assignment(&Instruction_To_FMCU);
+	}
+	else
+	{
+		Sys_Abnorm_Inf_Judgement &= ~0x00001000;
+	}
+}
+
```

## `csd_vx6.8_lastest/SecurityEmergencyManage.h` (新增部分)

```diff
--- a/csd_vx6.8_lastest/SecurityEmergencyManage.h
+++ b/csd_vx6.8_lastest/SecurityEmergencyManage.h
@@ (appended after Not_Recv_From_Jetson_No declaration)
+
+/* BUG-5/6: 离底高度硬栅栏安全仲裁 */
+void Seafloor_Grounding_Arbitration(void);
+
+/* BUG-7: 水池测试安全模式 */
+#if POOL_TEST_MODE
+void Pool_Safety_Check(void);
+#endif
```

## `brain_linux/src/auv_controller/auv_controller/auv_controller_node.py`

```diff
diff --git a/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py b/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py
index f5e4ac0..25e3a0c 100644
--- a/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py
+++ b/brain_linux/src/auv_controller/auv_controller/auv_controller_node.py
@@ -445,6 +445,22 @@ class AUVControllerNode(Node):
             sp.target_depth_m = float(-st.pose.pose.position.z)
             sp.target_heading_rad = yaw
 
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
+
         depth_error = float(sp.target_depth_m) - float(-st.pose.pose.position.z)
         yaw_error = math.atan2(
             math.sin(float(sp.target_heading_rad) - yaw),
```
