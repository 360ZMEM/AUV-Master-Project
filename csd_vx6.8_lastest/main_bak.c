/**********************
 * review time:
 * author:
 * modification record:
 
 * ***************************/

#include <vxWorks.h>
#include <sysLib.h>
#include <taskLib.h>
#include <stdio.h>
#include <stdlib.h>
#include <wdLib.h>
#include <string.h>
#include <time.h>
#include <math.h>


#include "main.h"
#include "com.h"
#include "DataProcess.h"
#include "SecurityEmergencyManage.h"
#include "SailingBox.h"
#include "XMLFile.h"
#include "PowerManage.h"
#include "CtrlAlgorithm.h"
#include "AgreedTerms.h"

#include "dtp.h"

/*消息队列\信号量等其他初始化*/;
void ProgromStartPoint(void);
void MainCtrlTask(void);
void Program_Initial(void);
void Task_Creation(void);
void PrintTask(void);
short int Sem_Initial(void);	
void FuncWd_InfoOutputCtrl(void);
void Debug_Print(void);

/*对应任务的执行过程函数*/;
void Default_Proces(void);
void Course_Keep_Proces(void);
void Remote_Proces(void);
void Auto_FixedPoint_Proces(void);
void Auto_FixedDirection_Proces(void);
void Auto_Back_Proces(void);

/*遥控模式下的函数*/
void Work_Cmd_Execute(u8 *work_command_ptr);


/*能源状态初始化函数*/
void Device_Power_Ctrl_Initial(void);


/*自主航行规划初始化函数*/
void Auto_FixedPoint_Process_Initial(void);
void Auto_FixedDirection_Process_Initial(void);

/*打印测试函数*/
void Current_State_printf(void);
void recv_count_printf(void);
void Beid_BDTXR(void);
void PathPlanning_data_printf(void);
void between_CPU_and_UI12(void);
void between_CPU_and_MCU(void);
void between_CPU_and_PSD(void);
void between_CPU_and_GPS(void);
void between_CPU_and_Compass(void);
void between_CPU_and_LORA(void);
void between_CPU_and_DVL(void);
void between_CPU_and_BMS(void);
void between_UI_and_MCU(void);




SEM_ID semMainCtrlTask;

SEM_ID semUartSendToBEIDOUTask;
SEM_ID semUartRecvFormBEIDOUTask;
SEM_ID semPackBEIDOUDataTask;
SEM_ID semUnpackBEIDOUDataTask;

SEM_ID semUartSendToPSDTask;
SEM_ID semUartRecvFormPSDTask;
SEM_ID semPackPSDDataTask;
SEM_ID semUnpackPSDDataTask;                                                                       


SEM_ID semUartRecvFormGPSTask;
SEM_ID semUnpackGPSDataTask; 


SEM_ID semUartRecvFormDVLTask;
SEM_ID semUnpackDVLDataTask; 

SEM_ID semUartSendToLORATask;
SEM_ID semUartRecvFormLORATask;

SEM_ID semUnpackLORADataTask;   


SEM_ID semUartRecvFormBMSTask;
SEM_ID semUnpackBMSDataTask; 

SEM_ID semNetSendTask;
SEM_ID semNetRecvTask;
SEM_ID semPackNetDataTask;
SEM_ID semUnpackNetDataTask;


SEM_ID semUartRecvFormIMUTask;
SEM_ID semUnpackIMUDataTask; 

SEM_ID semEmergencyTask;
SEM_ID semDataStoreTask;
SEM_ID semPrintTask;




WDOG_ID wdTimer_InfoOutputCtrl;/*定时输出各控制指令到各设备*/

unsigned short int DEBUG = 1;

/*设备执行周期*/
const float Main_Ctrl_Task_Period = 6;             
const float Net_Recv_Task_Period = 3;            
const float Uart_Recv_Form_LORA_Task_Period = 3;              
const float Uart_Recv_Form_BEIDOU_Task_Period = 610;    /*原来是610，临时改为6*/          
const float Uart_Recv_Form_IMU_Task_Period = 3;
const float Uart_Recv_Form_DVL_Task_Period = 10;              
const float Uart_Recv_Form_BMS_Task_Period = 3;              
const float Uart_Recv_Form_PSD_Task_Period = 3;               
const float Uart_Recv_Form_GPS_Task_Period = 3;  
const float Emergency_Task_Period = 5;              
const float New_Store_File_Period = 36000;               
const float Print_Task_Period = 3;  



static u8 Main_Ctrl_Task_Count_No = 0;
static bool UTC_Time_Calibrate_Flag = false;
u8 UI_Channel_Selection_Down = 0x00;
u8 UI_Channel_Selection_Up = 0x00;
bool Auto_Task_Carry_Flag = false;
bool Course_Keep_Flag = false;
bool Parameter_Adjustment_Flag = false;



bool Initialization_Flag = false;

bool Send_To_WIFI_Ready = false;

bool Send_To_FMCU_Ready = false;

bool Auto_FixedPoint_Process_Initial_Complete_Flag = false;

bool Auto_FixedDirection_Process_Initial_Complete_Flag = false;

bool BEIDOU_Data_Ready = false;




/*计数器，也可以说是计时器*/
u16 Main_Ctrl_Task_Interval_Num = 0;
u16 Net_Recv_Interval_Num  = 0;
u16 Recv_Form_LORA_Interval_Num  = 0;
u16 Recv_Form_BEIDOU_Interval_Num  = 0;
u16 Recv_Form_IMU_Interval_Num  = 0;
u16 Recv_Form_DVL_Interval_Num  = 0;
u16 Recv_Form_BMS_Interval_Num  = 0;
u16 Recv_Form_PSD_Interval_Num  = 0;
u16 Recv_Form_GPS_Interval_Num  = 0;
u16 Emergency_Task_Interval_Num  = 0;
u16 New_Store_File_Interval_Num  = 0;
u16 Print_Task_Interval_Num  = 0;

/*static u16 Pack_To_UI3_No  = 0;*/
u16 Pack_To_UI3_No  = 0;


bool Auto_FixedPoint_Process_Initial_Flag = false;
bool Auto_FixedDirection_Process_Initial_Flag = false;


/*u8 CtrlMode = 0x00;测试mcu的时候，要改成0x01，对应上遥控模式*/
u8 Remote = 0x01;
u8 Auto_FixedPoint = 0x02;
u8 Auto_FixedDirection = 0x03;
u8 Auto_Back = 0x04;



void ProgromStartPoint (void)
{
	taskSpawn("MainCtrlTask" , 120 ,VX_FP_TASK , 5120 ,(FUNCPTR)MainCtrlTask, 0,0,0,0,0,0,0,0,0,0);
	printf("program starting:::::\n");
	Program_Initial();
	taskDelay(sysClkRateGet() / 10);/*默认系统时钟工作频率是60，60/10=6个tick 也就是6/60=0.1秒*/
	
}

void Program_Initial(void)
{
	Sem_Initial();
	Task_Creation();
	Device_Power_Ctrl_Initial();
}


void MainCtrlTask(void)
{
	
	FOREVER
	{
		if(OK == semTake(semMainCtrlTask,WAIT_FOREVER));
		{
			Main_Ctrl_Task_Count_No++;
			printf("Main_Ctrl_Task_Count_No:%d\n", Main_Ctrl_Task_Count_No);
			if((UTC_Time_Calibrate_Flag == false)&&((GPS_Prase_Data.GPS_Position_QC&0x01)==0x01))
			{
				setBiosTime(&BiosTimeSetting);
				Default_Proces();
			}
			else
			{
				Default_Proces();/**/	
				semGive(semNetSendTask);
			}
			
			if(Current_State.Current_Mode == Remote)
			{			
				Remote_Proces();
				semGive(semNetSendTask);
			}

			if(Current_State.Current_Mode == Auto_FixedPoint)
			{
				Auto_Task_Carry_Flag = true;
				Auto_FixedPoint_Proces();
				semGive(semNetSendTask);
			}
			

			if(Current_State.Current_Mode == Auto_FixedDirection)
			{
				Auto_Task_Carry_Flag = true;
				Auto_FixedDirection_Proces();
				semGive(semNetSendTask);
			}
			

			if(Current_State.Current_Mode == Auto_Back)
			{
				Auto_Back_Proces();
				semGive(semNetSendTask);
			}
					
		    
			
		    if((Instruction_To_FMCU.McuFD_Power_Control & 0x40)==0x40)
		    {
			  
		    	if(Main_Ctrl_Task_Interval_Num >= 212)
			    {
			    	semGive(semUartSendToBEIDOUTask);
			    	Main_Ctrl_Task_Interval_Num = 0;
			    }
		    	
			   
		    	semGive(semUartSendToLORATask);
		    	/*semGive(semUartSendToPSDTask);*/
		    }
		    
		    
		    
		    
		}
	}
}

void Default_Proces(void)
{

	Pack_To_UI3_No++;
	Current_state(&Current_State);
	if((Instruction_To_FMCU.McuFD_Power_Control&0x40) == 0x40)
	{
		Pack_Data_To_UI12(&To_UI12);
		if(UI_Channel_Selection_Up == 0x01)
		{
			semGive(semUartSendToLORATask);	
			ReadBIOSRealTime();
		}
		
		if(UI_Channel_Selection_Up == 0x02)
		{
			Send_To_WIFI_Ready = true;
			ReadBIOSRealTime();
		}
				
		if(Pack_To_UI3_No >= 105)/**/
		{
			Pack_To_UI3_No = 0;
			Pack_Data_To_UI3(&ToUI3);
			semGive(semUartSendToBEIDOUTask);
			ReadBIOSRealTime();
		}
		
		
	}
	
	
}
void Course_Keep_Proces(void)
{
	
	
	
}


void Remote_Proces(void)
{		
	
   /**/Work_Cmd_Execute(&Current_State.Current_Work_Cmd);
	Remote_Assignment(&Instruction_To_FMCU);	
}

void Auto_FixedPoint_Proces(void)
{
	if(Auto_Task_Carry_Flag == true)
	{
		if(Auto_FixedPoint_Process_Initial_Flag == false)
		{
			Auto_FixedPoint_Process_Initial();
			if(Auto_FixedPoint_Process_Initial_Flag == true)
			{
				Current_State.Current_Sail_State= (Sail_State_Judgement & 0x1F);
				Current_State.Current_Sail_State= (Sail_State_Judgement | 0x10);
				Auto_FixedPoint_Assignment(&FixedPoint_PathPlanning);
			}
			else
			{
				Current_State.Current_Sail_State= (Sail_State_Judgement & 0x8F);
				Current_State.Current_Sail_State= (Sail_State_Judgement | 0x80);				
			}
		}		
				
	}
	else
	{
		Auto_FixedPoint_Process_Initial_Flag = false;
		Current_State.Current_Sail_State= (Sail_State_Judgement | 0x20);
		Current_State.Current_Sail_State= (Sail_State_Judgement & 0x2F);	
	}
	

}


void Device_Power_Ctrl_Initial(void)
{
	MT_Power_Control(Power_OFF);
	LT_Power_Control(Power_OFF);
	HR_Power_Control(Power_OFF);
	VR_Power_Control(Power_OFF);
	EL_Power_Control(Power_OFF);
	DVL_Power_Control(Power_OFF);
	CM_Power_Control(Power_OFF);
	S1_Power_Control(Power_OFF);
	S2_Power_Control(Power_OFF);
}



void Auto_FixedPoint_Process_Initial(void)
{
	run_FixedPoint_xppTutorialAll("/ata0a/XMLFile/Point_File.xml");
	
	FixedPoint_PathPlanning.Latitude[0] = Current_State.Current_GPS_Latitude;
	FixedPoint_PathPlanning.Longitude[0] = Current_State.Current_GPS_Longitude;   /*起始目标点为自主航行开始时刻当前位置点*/
	
	unpack_FixedPoint_XML(&XMLData); 
}

void Auto_FixedDirection_Process_Initial(void)
{
	run_FixedDirection_xppTutorialAll("/ata0a/XMLFile/Directional_File.xml");	
	
	FixedDirection_PathPlanning.Course[0]=Current_State.Current_IMU_Heading; /*起始航向为罗经的当前航向*/
	
	unpack_FixedDirection_XML(&XMLData); 
	
	Auto_FixedDirection_Process_Initial_Flag = true;
}




void Auto_FixedDirection_Proces(void)
{
	if(Auto_Task_Carry_Flag == true)
	{
		if(Auto_FixedDirection_Process_Initial_Flag == false)
		{
			Auto_FixedDirection_Process_Initial();
			if(Auto_FixedDirection_Process_Initial_Flag == true)
			{
				Current_State.Current_Sail_State= (Sail_State_Judgement & 0xF1);
				Current_State.Current_Sail_State= (Sail_State_Judgement & 0x01);
				Auto_FixedDirection_Assignment(&FixedDirection_PathPlanning);
			}
			else
			{
				Current_State.Current_Sail_State= (Sail_State_Judgement & 0xF8);
				Current_State.Current_Sail_State= (Sail_State_Judgement & 0x08);				
			}
		}	
	}
	else
	{
		Auto_FixedDirection_Process_Initial_Flag = false;
		Current_State.Current_Sail_State= (Sail_State_Judgement | 0x02);
		Current_State.Current_Sail_State= (Sail_State_Judgement & 0xF2);	
	}
		
	
}
void Auto_Back_Proces(void)
{
	
	
	
	
	
}

void Work_Cmd_Execute(u8 *work_command_ptr)
{
	switch(*work_command_ptr)
		{
			case 0x00:
				break;
			case 0x01:
				Auto_Task_Carry_Flag = true;
				Sail_State_Judgement |= 0x00000001;
				Sail_State_Judgement |= 0x00000010;
				break;
			case 0x02:
				Auto_Task_Carry_Flag = false;
				Sail_State_Judgement &= 0xfffffffe;	
				Sail_State_Judgement &= 0xffffffef;
				break;
			case 0x03:
				/*留空*/
				break;
			case 0x04:
				/*留空*/
				break;
			case 0x05:
				/*留空*/
				break;
			case 0x06:
				/*留空*/
				break;
			case 0x07:
				/*留空*/
				break;
			case 0x08:
				/*留空*/
				break;
			case 0x09:
				/*留空*/
				break;
			case 0x10:
				/*留空*/
				break;
			case 0x11:
				MT_Power_Control(Power_ON);				
				break;
			case 0x12:
				MT_Power_Control(Power_OFF);				
				break;
			case 0x13:
				LT_Power_Control(Power_ON);				
				break;
			case 0x14:
				LT_Power_Control(Power_OFF);
				break;
			case 0x15:
				HR_Power_Control(Power_ON);
				break;
			case 0x16:
				HR_Power_Control(Power_OFF);
				break;
			case 0x17:
				VR_Power_Control(Power_ON);
				break;
			case 0x18:
				VR_Power_Control(Power_OFF);
				break;
			case 0x19:
				EL_Power_Control(Power_ON);
				break;
			case 0x20:
				EL_Power_Control(Power_OFF);
				break;
			case 0x21:
				DVL_Power_Control(Power_ON);
				break;
			case 0x22:
				DVL_Power_Control(Power_OFF);
				break;
			case 0x23:
				CM_Power_Control(Power_ON);
				break;
			case 0x24:
				CM_Power_Control(Power_OFF);
				break;
			case 0x25:
				S1_Power_Control(Power_ON);
				break;
			case 0x26:
				S1_Power_Control(Power_OFF);
				break;
			case 0x27:
				S2_Power_Control(Power_ON);
				break;
			case 0x28:
				S2_Power_Control(Power_OFF);
				break;
			case 0x41:
				/*留空*/
				break;
			case 0x42:
				/*留空*/
				break;
			case 0x51:
				Parameter_Adjustment_Flag = true;
				Cmd_State_Judgement |= 0x00000004;
				break;
			case 0x52:
				Parameter_Adjustment_Flag = false;
				Cmd_State_Judgement &= 0xfffffffb;
				break;
			case 0x53:
				/*留空*/
				break;
			case 0x54:
				/*留空*/
				break;
			case 0x61:
				/*留空*/
				break;
			case 0x62:
				/*留空*/
				break;
			case 0x71:
				Course_Keep_Flag = true;
				Cmd_State_Judgement |= 0x00000040;
				break;
			case 0x72:
				Course_Keep_Flag = false;
				Cmd_State_Judgement &= 0xffffffbf;
				break;				
			case 0x73:
				/*留空*/
				break;				
			case 0x74:
				/*留空*/
				break;							
			case 0x81:
				/*留空*/
				break;			
			case 0x82:
				/*留空*/
				break;			
			case 0x83:
				/*留空*/
				break;					
			case 0x91:
				Initialization_Flag = true;
				Device_Power_State_Judgement = 0;
				Cmd_State_Judgement = 0;
				Sail_State_Judgement = 0;
				Sys_Abnorm_Inf_Judgement = 0;
				Dev_Abnorm_Inf_Judgement = 0;				
				BMS_Abnorm_Inf_Judgement = 0;
				Dev_Abnorm_Inf_Detail_Judgement = 0;	
				
				Cmd_State_Judgement |= 0x00000800;
				
				Depth_Exceed_FromUI12_Depth_Para1=0;
				Depth_Exceed_FromUI12_Depth_Para2=0;
				break;	
			case 0x92:
				Initialization_Flag = false;
				Cmd_State_Judgement |= 0x00001000;
			   /*Cmd_State_Judgement &= 0xffffefff;*/
				break;	
			default:
				break;
		}
			
		*work_command_ptr = 0; 	
}





void Task_Creation(void)
{
		
		taskSpawn("UartSendToBEIDOUTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)UartSendToBEIDOUTask, 0,0,0,0,0,0,0,0,0,0);
		taskSpawn("UartRecvFormBEIDOUTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)UartRecvFormBEIDOUTask, 0,0,0,0,0,0,0,0,0,0);
		taskSpawn("PackBEIDOUDataTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)PackBEIDOUDataTask, 0,0,0,0,0,0,0,0,0,0);
		taskSpawn("UnpackBEIDOUDataTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)UnpackBEIDOUDataTask, 0,0,0,0,0,0,0,0,0,0);
		
		taskSpawn("UartSendToPSDTask" , 135 ,VX_FP_TASK , 5120 ,(FUNCPTR)UartSendToPSDTask, 0,0,0,0,0,0,0,0,0,0);
		taskSpawn("UartRecvFormPSDTask" , 135 ,VX_FP_TASK , 5120 ,(FUNCPTR)UartRecvFormPSDTask, 0,0,0,0,0,0,0,0,0,0);
		taskSpawn("PackPSDDataTask" , 135 ,VX_FP_TASK , 5120 ,(FUNCPTR)PackPSDDataTask, 0,0,0,0,0,0,0,0,0,0);
		taskSpawn("UnpackPSDDataTask" , 135 ,VX_FP_TASK , 5120 ,(FUNCPTR)UnpackPSDDataTask, 0,0,0,0,0,0,0,0,0,0);
		

		taskSpawn("UartRecvFormGPSTask" , 130 ,VX_FP_TASK , 5120 ,(FUNCPTR)UartRecvFormGPSTask, 0,0,0,0,0,0,0,0,0,0);
		taskSpawn("UnpackGPSDataTask" , 130 ,VX_FP_TASK , 5120 ,(FUNCPTR)UnpackGPSDataTask, 0,0,0,0,0,0,0,0,0,0);
		

		taskSpawn("UartRecvFormDVLTask" , 130 ,VX_FP_TASK , 5120 ,(FUNCPTR)UartRecvFormDVLTask, 0,0,0,0,0,0,0,0,0,0);
		taskSpawn("UnpackDVLDataTask" , 130 ,VX_FP_TASK , 5120 ,(FUNCPTR)UnpackDVLDataTask, 0,0,0,0,0,0,0,0,0,0);
		
		
		taskSpawn("UartRecvFormIMUTask" , 130 ,VX_FP_TASK , 5120 ,(FUNCPTR)UartRecvFormIMUTask, 0,0,0,0,0,0,0,0,0,0);		
		taskSpawn("UnpackIMUDataTask" , 130 ,VX_FP_TASK , 5120 ,(FUNCPTR)UnpackIMUDataTask, 0,0,0,0,0,0,0,0,0,0);
		
		taskSpawn("UartSendToLORATask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)UartSendToLORATask, 0,0,0,0,0,0,0,0,0,0);
	    taskSpawn("UartRecvFormLORATask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)UartRecvFormLORATask, 0,0,0,0,0,0,0,0,0,0);
	
		taskSpawn("UnpackLORADataTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)UnpackLORADataTask, 0,0,0,0,0,0,0,0,0,0);
		
		
	    taskSpawn("UartRecvFormBMSTask" , 130 ,VX_FP_TASK , 5120 ,(FUNCPTR)UartRecvFormBMSTask, 0,0,0,0,0,0,0,0,0,0);	 
		taskSpawn("UnpackBMSDataTask" , 130 ,VX_FP_TASK , 5120 ,(FUNCPTR)UnpackBMSDataTask, 0,0,0,0,0,0,0,0,0,0);
		
		taskSpawn("NetSendTask" , 130 ,VX_FP_TASK , 5120 ,(FUNCPTR)NetSendTask, 0,0,0,0,0,0,0,0,0,0);
		taskSpawn("NetRecvTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)NetRecvTask, 0,0,0,0,0,0,0,0,0,0);
		taskSpawn("PackNetDataTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)PackNetDataTask, 0,0,0,0,0,0,0,0,0,0);
		taskSpawn("UnpackNetDataTask" , 125 ,VX_FP_TASK , 5120 ,(FUNCPTR)UnpackNetDataTask, 0,0,0,0,0,0,0,0,0,0);
		
		taskSpawn("EmergencyTask" , 110 ,VX_FP_TASK , 5120 ,(FUNCPTR)EmergencyTask, 0,0,0,0,0,0,0,0,0,0);	
		taskSpawn("DataStoreTask" , 140 ,VX_FP_TASK , 5120 ,(FUNCPTR)DataStoreTask, 0,0,0,0,0,0,0,0,0,0);
		taskSpawn("PrintTask" , 145 ,VX_FP_TASK , 5120 ,(FUNCPTR)PrintTask, 0,0,0,0,0,0,0,0,0,0);
		
		
		
}
/*
 @function: 消息队列\信号量等其他初始化
 */
short int Sem_Initial(void)
{
	semMainCtrlTask = semBCreate(SEM_Q_PRIORITY, SEM_FULL);  /*主函数信号量*/
	
	semUartSendToBEIDOUTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口发送至北斗信号量*/
	semUartRecvFormBEIDOUTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收北斗信号量*/	
	semPackBEIDOUDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);      /*北斗串口数据打包信号量*/
	semUnpackBEIDOUDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*北斗串口数据解包信号量*/
	
	semUartSendToPSDTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口发送至频闪灯信号量*/
	semUartRecvFormPSDTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收频闪灯信号量*/
	semPackPSDDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*频闪灯串口数据打包信号量*/
	semUnpackPSDDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*频闪灯串口数据解包信号量*/
	
	/*semUartSendToGPS = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     控制串口发送至GPS信号量*/
	semUartRecvFormGPSTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收GPS信号量*/	
	semUnpackGPSDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*GPS串口数据解包信号量*/
    
	/*semUartSendToDVL = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     控制串口发送至DVL信号量*/
    semUartRecvFormDVLTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收DVL信号量*/	
    semUnpackDVLDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*DVL串口数据解包信号量*/
    
   
    semUartRecvFormIMUTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收罗经信号量*/       
    semUnpackIMUDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*罗经串口数据解包信号量*/
	
    semUartSendToLORATask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口发送至LORA信号量*/
	semUartRecvFormLORATask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收LORA信号量*/	
	
	semUnpackLORADataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*LORA串口数据解包信号量*/
  
	
	semUartRecvFormBMSTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制串口接收BMS信号量*/		
	semUnpackBMSDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*BMS串口数据解包信号量*/
	
	semNetSendTask  = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制以太网发送信号量*/
	semNetRecvTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*控制以太网接收信号量*/
	semPackNetDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*以太网数据打包信号量*/	
	semUnpackNetDataTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);     /*以太网数据解包信号量*/

    semEmergencyTask = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY); 
    semDataStoreTask  = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);   
    semPrintTask  = semBCreate(SEM_Q_PRIORITY, SEM_EMPTY);

    
    
	if((wdTimer_InfoOutputCtrl = wdCreate()) == NULL)       /*创建看门狗*/
	{
		return (ERROR);
	}
	wdStart(wdTimer_InfoOutputCtrl, sysClkRateGet()*0.1, (FUNCPTR)FuncWd_InfoOutputCtrl, 0);/*0.1s后启动启动定时器*/
	return OK;
}


/*
 tips:不能有printf函数在里面！！！！！
 @看门狗服务程序
 */
void FuncWd_InfoOutputCtrl (void)       /*定时处理函数，0.1s执行一次*/
{
	
	Main_Ctrl_Task_Interval_Num++;

	 /*接收*/
	Net_Recv_Interval_Num++;

	if((Instruction_To_FMCU.McuFD_Power_Control&0x40) == 0x40)
	{
		Recv_Form_LORA_Interval_Num++;
	}
	else
	{		
		Not_Recv_From_LORA_No = 0;
	}
	
	if((Instruction_To_FMCU.McuFD_Power_Control&0x40) == 0x40)
	{
		Recv_Form_BEIDOU_Interval_Num++;	
	}
	else
	{		
		Not_Recv_From_BEIDOU_No = 0;
	}
	
	
	Recv_Form_IMU_Interval_Num++;
	
	
	/*if((Instruction_To_FMCU.McuFD_Power_Control&0x20) == 0x20)
	{
		Recv_Form_DVL_Interval_Num++;
	}
	else
	{		
		Not_Recv_From_DVL_No = 0;
	}*/
	
	Recv_Form_DVL_Interval_Num++;
	Recv_Form_BMS_Interval_Num++;
	
	
	if((Instruction_To_FMCU.McuFD_Power_Control&0x40) == 0x40)
	{
		Recv_Form_PSD_Interval_Num++;
	}
	else
	{		
		Not_Recv_From_PSD_No = 0;
	}	
	
	/*if((Instruction_To_FMCU.McuFD_Power_Control&0x40) == 0x40)
	{
		Recv_Form_GPS_Interval_Num++;   
	}
	else
	{		
		Not_Recv_From_GPS_No = 0;
	}*/
	Recv_Form_GPS_Interval_Num++;/*测试*/
	Emergency_Task_Interval_Num++;
	New_Store_File_Interval_Num++;  
	 
	
	if(DEBUG)
	{
		Print_Task_Interval_Num++;
	}
	

	
	if(Main_Ctrl_Task_Interval_Num >= (Main_Ctrl_Task_Period ))
	{		
		semGive(semMainCtrlTask);         /*0.6s释放主任务信号量，主任务执行一次*/
		Main_Ctrl_Task_Interval_Num = 0;
	}
	
	if(Net_Recv_Interval_Num >= (Net_Recv_Task_Period))
	{		
		semGive(semNetRecvTask); 	
		Net_Recv_Interval_Num = 0;
	}
	
	
	if(Recv_Form_LORA_Interval_Num >= (Uart_Recv_Form_LORA_Task_Period))
	{	
		semGive(semUartRecvFormLORATask);
		Recv_Form_LORA_Interval_Num = 0;
	}
	
	if(Recv_Form_BEIDOU_Interval_Num >= (Uart_Recv_Form_BEIDOU_Task_Period))/*61秒一次*/
	{	
		semGive(semUartRecvFormBEIDOUTask);
		Recv_Form_BEIDOU_Interval_Num = 0;
	}
		
	if(Recv_Form_IMU_Interval_Num >= (Uart_Recv_Form_IMU_Task_Period))
	{	
		semGive(semUartRecvFormIMUTask);
		Recv_Form_IMU_Interval_Num = 0;	
	}
	
	if(Recv_Form_DVL_Interval_Num >= (Uart_Recv_Form_DVL_Task_Period))
	{	
		semGive(semUartRecvFormDVLTask);
		Recv_Form_DVL_Interval_Num = 0;
	}
	
	if(Recv_Form_BMS_Interval_Num >= (Uart_Recv_Form_BMS_Task_Period ))
	{	
		semGive(semUartRecvFormBMSTask);
		Recv_Form_BMS_Interval_Num = 0;
	}
	
	if(Recv_Form_PSD_Interval_Num >= (Uart_Recv_Form_PSD_Task_Period))
	{	
		semGive(semUartRecvFormPSDTask);
		Recv_Form_PSD_Interval_Num = 0;
	}
	
	if(Recv_Form_GPS_Interval_Num >= (Uart_Recv_Form_GPS_Task_Period))
	{	
		semGive(semUartRecvFormGPSTask);
		Recv_Form_GPS_Interval_Num = 0;
	}
			
	if(Emergency_Task_Interval_Num >= (Emergency_Task_Period ))
	{	
		semGive(semEmergencyTask);
		Emergency_Task_Interval_Num = 0;
	}
	
	if(New_Store_File_Interval_Num >= (New_Store_File_Period ))
	{	
		New_Store_File_Flag = true;/*创建新文件*/
		New_Store_File_Interval_Num = 0;		
	}
	
	if(Print_Task_Interval_Num >= (Print_Task_Period  ))
	{	
		semGive(semPrintTask);
		Print_Task_Interval_Num = 0;
		
	}
	
   /*发送*/

	
	wdStart(wdTimer_InfoOutputCtrl, sysClkRateGet()*0.1, (FUNCPTR)FuncWd_InfoOutputCtrl, 0);/*定时0.1s*/
}

void PrintTask(void)
{
	FOREVER
	{
		semTake(semPrintTask,WAIT_FOREVER);
		Debug_Print();
	}
}


void Debug_Print(void)
{
	if(DEBUG)
			{
		       /*Current_State_printf();
		        /*recv_count_printf();*/
		        /*between_CPU_and_UI12();*/
		        /*Beid_BDTXR();*/
		        /*between_CPU_and_GPS();*/
		        between_CPU_and_DVL();
		        /*PathPlanning_data_printf();*/
			    /*debug_test();*/
		        /*between_CPU_and_MCU();
				/*between_CPU_and_PSD();*/
		        /*between_CPU_and_IMU();*/	       
		        /*between_CPU_and_BMS();*/
				/*between_UI_and_MCU();*/
				
			}	
}







void Current_State_printf(void)
{
	/*printf("Msg_Num:%d\n",Current_State.Msg_Num);
	printf("ID:%2x\n",Current_State.ID);
	printf("Current_Mode:%2x\n",Current_State.Current_Mode);
	
	printf("Current_Depth_Para1:%3d\n",Current_State.Current_Depth_Para1);
	printf("Current_Depth_Para2:%3d\n",Current_State.Current_Depth_Para2);
	printf("Current_Height_Para1:%3d\n",Current_State.Current_Height_Para1);
	printf("Current_Height_Para2:%3d\n",Current_State.Current_Height_Para2);
	printf("Current_Remain_Time:%3d\n",Current_State.Current_Remain_Time);
	printf("Current_Spare_Para1:%3d\n",Current_State.Current_Spare_Para1);	
	printf("Current_Spare_Para2:%3d\n",Current_State.Current_Spare_Para2);
	
	printf("Current_Work_Cmd:%2x\n",Current_State.Current_Work_Cmd);
	printf("Current_Motor_Speed1:%3d\n",Current_State.Current_Motor_Speed1);	
	printf("Current_Motor_Speed2:%3d\n",Current_State.Current_Motor_Speed2);		
	printf("Current_LH_Rud_Location:%3d\n",Current_State.Current_LH_Rud_Location);	
	printf("Current_RH_Rud_Location:%3d\n",Current_State.Current_RH_Rud_Location);	
	printf("Current_UV_Rud_Location:%3d\n",Current_State.Current_UV_Rud_Location);	
	printf("Current_LV_Rud_Location:%3d\n",Current_State.Current_LV_Rud_Location);		
	
	printf("Current_Pres:%f\n",Current_State.Current_Pres);
	printf("Current_Temp:%3d\n",Current_State.Current_Temp);*/	
	printf("Current_Dep:%f\n",Current_State.Current_Dep);
	/*
	printf("Current_Para1:%f\n",Current_State.Current_Para1);
	printf("Current_Para2:%f\n",Current_State.Current_Para2);
	printf("Current_Para3:%f\n",Current_State.Current_Para3);
	printf("Current_Para4:%f\n",Current_State.Current_Para4);	
	printf("Current_Para5:%f\n",Current_State.Current_Para5);
	printf("Current_Para6:%f\n",Current_State.Current_Para6);
	printf("Current_Para7:%f\n",Current_State.Current_Para7);
	printf("Current_Para8:%f\n",Current_State.Current_Para8);	
	printf("Current_Para9:%f\n",Current_State.Current_Para9);
	printf("Current_Para10:%f\n",Current_State.Current_Para10);
	printf("Current_Para11:%f\n",Current_State.Current_Para11);
	printf("Current_Para12:%f\n",Current_State.Current_Para12);
	
	printf("Current_IMU_Heading:%f\n",Current_State.Current_IMU_Heading);
	printf("Current_IMU_Pitch:%f\n",Current_State.Current_IMU_Pitch);	
	printf("Current_IMU_Roll:%f\n",Current_State.Current_IMU_Roll);
	printf("Current_GPS_Heading:%f\n",Current_State.Current_GPS_Heading);
	printf("Current_GPS_Velocity_Kn:%f\n",Current_State.Current_GPS_Velocity_Kn);
	printf("Current_DVL_Velocity_Kn:%f\n",Current_State.Current_DVL_Velocity_Kn);	
	printf("Current_Height:%f\n",Current_State.Current_Height);
	printf("Current_Cal_Longitude:%f\n",Current_State.Current_Cal_Longitude);		
	printf("Current_Cal_Latitude:%f\n",Current_State.Current_Cal_Latitude);
	printf("Current_GPS_Longitude:%f\n",Current_State.Current_GPS_Longitude);	
	printf("Current_GPS_Latitude:%f\n",Current_State.Current_GPS_Latitude);		
	printf("Current_Total_Voltage:%f\n",Current_State.Current_Total_Voltage);
	printf("Current_Total_Current:%f\n",Current_State.Current_Total_Current);
	printf("Current_SOC:%2x\n",Current_State.Current_SOC);		
	printf("Current_SOH:%2x\n",Current_State.Current_SOH);	
	printf("Current_Single_Max_Temp:%d\n",Current_State.Current_Single_Max_Temp);
	printf("Current_Single_Min_Temp:%d\n",Current_State.Current_Single_Min_Temp);	
	printf("Current_Device_Power_State:%d\n",Current_State.Current_Device_Power_State);
	printf("Current_Cmd_State:%d\n",Current_State.Current_Cmd_State);
	printf("Current_Sail_State:%d\n",Current_State.Current_Sail_State);
	printf("Current_Sys_Abnorm_Inf:%d\n",Current_State.Current_Sys_Abnorm_Inf);	
	printf("Current_Dev_Abnorm_Inf:%d\n",Current_State.Current_Dev_Abnorm_Inf);
	printf("Current_BMS_Abnorm_Inf:%d\n",Current_State.Current_BMS_Abnorm_Inf);
	printf("Current_Dev_Abnorm_Inf_Detail:%d\n",Current_State.Current_Dev_Abnorm_Inf_Detail);	
	printf("Back_Lon:%f\n",Current_State.Back_Lon);
	printf("Back_Lat:%f\n",Current_State.Back_Lat);*/
	
	printf("Depth_Exceed_FromUI12_Depth_Para2:%d\n",Depth_Exceed_FromUI12_Depth_Para2);
}




void between_CPU_and_BMS(void)
{
	printf("msg between CPU and BMS_summary_state::::\n");	
	printf("Total_Voltage:%d\n",BMS_Prase_Data.Total_Voltage);
	printf("Total_Current:%d\n",BMS_Prase_Data.Total_Current);
	printf("SOC:%d\n",BMS_Prase_Data.SOC);
	printf("SOH:%d\n",BMS_Prase_Data.SOH);
	printf("Single_Max_Voltage:%d\n",BMS_Prase_Data.Single_Max_Voltage);
	printf("Single_Min_Voltage:%d\n",BMS_Prase_Data.Single_Min_Voltage);
	printf("Single_Max_Temp:%d\n",BMS_Prase_Data.Single_Max_Temp);
	printf("Single_Min_Temp:%d\n",BMS_Prase_Data.Single_Min_Temp);
	printf("BMS_Abnorm_Inf:%d\n",BMS_Prase_Data.BMS_Abnorm_Inf);
	
	
	/*BMS_summary_state数据
	printf("msg between CPU and BMS_summary_state::::\n");	
	printf("addr:%2x\n",Get_summary_stateFromBMS.addr);
	printf("function_code:%2x\n",Get_summary_stateFromBMS.function_code);
	printf("number_bytes:%2x\n",Get_summary_stateFromBMS.number_bytes);	
	printf("clusterX_voltage:%f\n",Get_summary_stateFromBMS.clusterX_voltage);
	printf("clusterX_current:%f\n",Get_summary_stateFromBMS.clusterX_current);
	printf("clusterX_charge_state:%2x\n",Get_summary_stateFromBMS.clusterX_charge_state);
	printf("clusterX_SOC:%f\n",Get_summary_stateFromBMS.clusterX_SOC);
	printf("clusterX_SOH:%f\n",Get_summary_stateFromBMS.clusterX_SOH);
	printf("clusterX_max_cell_vol_id:%d\n",Get_summary_stateFromBMS.clusterX_max_cell_vol_id);
	printf("clusterX_max_cell_vol:%f\n",Get_summary_stateFromBMS.clusterX_max_cell_vol);
	printf("clusterX_min_cell_vol_id:%d\n",Get_summary_stateFromBMS.clusterX_min_cell_vol_id);
	printf("clusterX_min_cell_vol:%f\n",Get_summary_stateFromBMS.clusterX_min_cell_vol);	
	printf("clusterX_max_cell_temp_id:%d\n",Get_summary_stateFromBMS.clusterX_max_cell_temp_id);
	printf("clusterX_max_cell_temp:%d\n",Get_summary_stateFromBMS.clusterX_max_cell_temp);
	printf("clusterX_min_cell_temp_id:%d\n",Get_summary_stateFromBMS.clusterX_min_cell_temp_id);
	printf("clusterX_min_cell_temp:%d\n",Get_summary_stateFromBMS.clusterX_min_cell_temp);
	printf("crc16_check_sum:%2x\n",Get_summary_stateFromBMS.crc16_check_sum);*/
	
	/*BMS_critical_state数据
	printf("msg between CPU and BMS_critical_state::::\n");	
	printf("addr:%2x\n",Get_critical_stateFromBMS.addr);
	printf("function_code:%2x\n",Get_critical_stateFromBMS.function_code);
	printf("number_bytes:%2x\n",Get_critical_stateFromBMS.number_bytes);	
	printf("system_stop_info:%d\n",Get_critical_stateFromBMS.system_stop_info);
	printf("system_alarm_info:%d\n",Get_critical_stateFromBMS.system_alarm_info);
	printf("crc16_check_sum:%2x\n",Get_critical_stateFromBMS.crc16_check_sum);*/
	
}





void between_CPU_and_IMU(void)
{
	printf("head_buf:%2x\n",IMU_Prase_Data.head_buf);
	printf("Roll:%f,Pitch:%f,Yaw:%f",(IMU_Prase_Data.Roll_Pitch_Yaw[0])*(180/PI),(IMU_Prase_Data.Roll_Pitch_Yaw[1])*(180/PI),(IMU_Prase_Data.Roll_Pitch_Yaw[2])*(180/PI));
	printf("AngRateX:%f,AngRateY:%f,AngRateZ:%f",IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[0],IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1],IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[2]);

}



void between_CPU_and_PSD(void)
{

	printf("_From_PSD:%2x\n",PSD_Prase_Data._From_PSD);

}

void between_UI_and_MCU(void)
{
	printf("McuFD_Action_Cmd:%c%c\n",Instruction_To_FMCU.McuFD_Action_Cmd[0],Instruction_To_FMCU.McuFD_Action_Cmd[1]);
	
	
	printf("McuFD_Motor1_Set_Speed:%d\n",Instruction_To_FMCU.McuFD_Motor1_Set_Speed);
	printf("McuFD_LH_Set_Rud_Location:%d\n",Instruction_To_FMCU.McuFD_LH_Set_Rud_Location);
	printf("McuFD_RH_Set_Rud_Location:%d\n",Instruction_To_FMCU.McuFD_RH_Set_Rud_Location);
	printf("McuFD_UV_Set_Rud_Location:%d\n",Instruction_To_FMCU.McuFD_UV_Set_Rud_Location);
	printf("McuFD_LV_Set_Rud_Location:%d\n",Instruction_To_FMCU.McuFD_LV_Set_Rud_Location);	
	printf("McuFD_Power_Control:%d\n",Instruction_To_FMCU.McuFD_Power_Control);	
	
}


void between_CPU_and_MCU(void)
{

	
	/*printf("McuFU_Head_Buf:%c%c%c%c%c%c\n",Data_From_FMCU.McuFU_Head_Buf[0],Data_From_FMCU.McuFU_Head_Buf[1],Data_From_FMCU.McuFU_Head_Buf[2],
			                               Data_From_FMCU.McuFU_Head_Buf[3],Data_From_FMCU.McuFU_Head_Buf[4],Data_From_FMCU.McuFU_Head_Buf[5]);
*/
	/*printf("McuFU_Msg_Num:%03d\n",Data_From_FMCU.McuFU_Msg_Num);
	/*printf("McuFU_Back_ID:%c%c\n",Data_From_FMCU.McuFU_Back_ID[0],Data_From_FMCU.McuFU_Back_ID[1]);*/
	
	/*printf("McuFU_Pre_Para1:%02d\n",Data_From_FMCU.McuFU_Pre_Para1);
	printf("McuFU_Pre_Para2:%02d\n",Data_From_FMCU.McuFU_Pre_Para2);
	printf("McuFU_Pre_Para3:%02d\n",Data_From_FMCU.McuFU_Pre_Para3);
	
	printf("McuFU_Motor1_Back_Speed:%04d\n",Data_From_FMCU.McuFU_Motor1_Back_Speed);
	printf("McuFU_Motor2_Back_Speed:%04d\n",Data_From_FMCU.McuFU_Motor2_Back_Speed);*/
	printf("McuFU_LH_Back_Rud_Location:%04d\n",Data_From_FMCU.McuFU_LH_Back_Rud_Location);
	printf("McuFU_RH_Back_Rud_Location:%04d\n",Data_From_FMCU.McuFU_RH_Back_Rud_Location);
	printf("McuFU_UV_Back_Rud_Location:%04d\n",Data_From_FMCU.McuFU_UV_Back_Rud_Location);
	printf("McuFU_LV_Back_Rud_Location:%04d\n",Data_From_FMCU.McuFU_LV_Back_Rud_Location);
	/*
	printf("McuFU_Pres:%03d\n",Data_From_FMCU.McuFU_Pres);
	printf("McuFU_Temp:%03d\n",Data_From_FMCU.McuFU_Temp);
	printf("McuFU_Dep:%03d\n",Data_From_FMCU.McuFU_Dep);*/
	/*
	printf("McuFD_Power_State:%02d\n",Data_From_FMCU.McuFD_Power_State);
	printf("McuFD_Sys_Abnorm_Inf:%04d\n",Data_From_FMCU.McuFD_Sys_Abnorm_Inf);
	printf("McuFD_Dev_Abnorm_Inf:%04d\n",Data_From_FMCU.McuFD_Dev_Abnorm_Inf);
	printf("McuFD_Dev_Abnorm_Inf_Detail:%04d\n",Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail);
	
	printf("McuFU_End_Buf:%c%c%c\n",Data_From_FMCU.McuFU_End_Buf[0],Data_From_FMCU.McuFU_End_Buf[1],Data_From_FMCU.McuFU_End_Buf[2]);*/
	
	

}



void recv_count_printf(void)
{
	
	printf("Not_Recv_From_PSD_No:%d\n", Not_Recv_From_PSD_No);
	printf("Not_Recv_From_WIFI_No:%d\n", Not_Recv_From_WIFI_No);
	printf("Not_Recv_From_GPS_No:%d\n", Not_Recv_From_GPS_No);


}



void between_CPU_and_UI12(void)
{
	/*wifi通信打印数据*/
	u16 ii = 0;
	printf("msg between CPU and UIWifi::::\n");
	printf("Not_Recv_From_WIFI_No:%d\n", Not_Recv_From_WIFI_No);
	printf("from_UIWifi_buf: \n");
	for(ii=0 ; ii<From_UI_WIFI_Length; ii++)
	{
		printf("%2x ", From_WIFI_Buf[ii]);
	}
	printf("\n");
	printf("FromUI12_Head_BUF:%2x,%2x,%2x,%2x\n",UI_WIFI_Instruction.FromUI12_Head_BUF[0], UI_WIFI_Instruction.FromUI12_Head_BUF[1],
			UI_WIFI_Instruction.FromUI12_Head_BUF[2],UI_WIFI_Instruction.FromUI12_Head_BUF[3]);
	printf("FromUI12_Msg_Length:%d\n",UI_WIFI_Instruction.FromUI12_Msg_Length);
	printf("FromUI12_Msg_Num:%d\n",UI_WIFI_Instruction.FromUI12_Msg_Num);
	printf("FromUI12_ID:%2x\n",UI_WIFI_Instruction.FromUI12_ID);
	printf("FromUI12_Ctrl_Mode:%2x\n",UI_WIFI_Instruction.FromUI12_Ctrl_Mode);
	printf("FromUI12_Depth_Para1:%3d\n",UI_WIFI_Instruction.FromUI12_Depth_Para1);
	printf("FromUI12_Depth_Para2:%3d\n",UI_WIFI_Instruction.FromUI12_Depth_Para2);
	printf("FromUI12_Height_Para1:%3d\n",UI_WIFI_Instruction.FromUI12_Height_Para1);
	printf("FromUI12_Height_Para2:%3d\n",UI_WIFI_Instruction.FromUI12_Height_Para2);
	printf("FromUI12_Remain_Time:%3d\n",UI_WIFI_Instruction.FromUI12_Remain_Time);
	printf("FromUI12_Work_Cmd:%2x\n",UI_WIFI_Instruction.FromUI12_Work_Cmd);
	printf("FromUI12_Motor_Speed1:%3d\n",UI_WIFI_Instruction.FromUI12_Motor_Speed1);
	printf("FromUI12_Motor_Speed2:%3d\n",UI_WIFI_Instruction.FromUI12_Motor_Speed2);
	printf("FromUI12_RCD_LH_Set_Rud_Angle:%3d\n",UI_WIFI_Instruction.FromUI12_RCD_LH_Set_Rud_Angle);
	printf("FromUI12_RCD_RH_Set_Rud_Angle:%3d\n",UI_WIFI_Instruction.FromUI12_RCD_RH_Set_Rud_Angle);
	printf("FromUI12_RCD_UV_Set_Rud_Angle:%3d\n",UI_WIFI_Instruction.FromUI12_RCD_UV_Set_Rud_Angle);
	printf("FromUI12_RCD_LV_Set_Rud_Angle:%3d\n",UI_WIFI_Instruction.FromUI12_RCD_LV_Set_Rud_Angle);
	printf("FromUI12_Set_Course:%3d\n",UI_WIFI_Instruction.FromUI12_Set_Course);
	printf("FromUI12_Check_Sum:%2x\n",UI_WIFI_Instruction.FromUI12_Check_Sum);
	printf("FromUI12_End_Buf:%2x,%2x\n",UI_WIFI_Instruction.FromUI12_End_Buf[0],UI_WIFI_Instruction.FromUI12_End_Buf[1]);
	/*接收的数据*/
}

void between_CPU_and_DVL(void)
{
/*	
	printf("msg between CPU and DVL::::\n");
	printf("DVL_Prase_Data.head_buf: %c%c%c\n",DVL_Prase_Data.head_buf[0],DVL_Prase_Data.head_buf[1],DVL_Prase_Data.head_buf[2]);
	printf("BI_X:%d\n",DVL_Prase_Data.BI_X);
	printf("BI_Y:%d\n",DVL_Prase_Data.BI_Y);
	printf("BI_Z:%d\n",DVL_Prase_Data.BI_Z);
	printf("BI_V:%f\n",DVL_Prase_Data.BI_V);	
	printf("BI_Valid_Flag:%d\n",DVL_Prase_Data.BI_Valid_Flag);	
	printf("BD_Height:%f\n",DVL_Prase_Data.BD_Height);	
	printf("BD_Check:%d\n",DVL_Prase_Data.BD_Check);	*/	

	printf("WI_X:%d\n",DVL_Prase_Data.WI_X);
	printf("WI_Y:%d\n",DVL_Prase_Data.WI_Y);
	printf("WI_Z:%d\n",DVL_Prase_Data.WI_Z);
	printf("WI_V:%f\n",DVL_Prase_Data.WI_V);	
	printf("WI_Valid_Flag:%d\n",DVL_Prase_Data.WI_Valid_Flag);	
	printf("WD_Depth:%f\n",DVL_Prase_Data.WD_Depth);	
	printf("WD_Check:%d\n",DVL_Prase_Data.WD_Check);	
	
	
	/*
	printf("msg between CPU and DVL_BI::::\n");
	printf("GetBIfromDVL.head_buf: %c%c%c\n",GetBIfromDVL.head_buf[0],GetBIfromDVL.head_buf[1],GetBIfromDVL.head_buf[2]);
	printf("speedX:%f\n",GetBIfromDVL.speedX);
	printf("speedY:%f\n",GetBIfromDVL.speedY);
	printf("speedZ:%f\n",GetBIfromDVL.speedZ);
	printf("spare:%f\n",GetBIfromDVL.spare);
	printf("valid_flag: %c\n",GetBIfromDVL.valid_flag[0]);*/
	
	/*
	printf("msg between CPU and DVL_BD::::\n");
	printf("GetBDfromDVL.head_buf: %c%c%c\n",GetBDfromDVL.head_buf[0],GetBDfromDVL.head_buf[1],GetBDfromDVL.head_buf[2]);
	printf("acoustic_flag:%f\n",GetBDfromDVL.acoustic_flag);
	printf("selftest_flag:%f\n",GetBDfromDVL.selftest_flag);
	printf("transducer_array_depth:%f\n",GetBDfromDVL.transducer_array_depth);
	printf("transducer_array_vertical_distance:%f\n",GetBDfromDVL.transducer_array_vertical_distance);
	printf("last_data_valid_time:%f\n",GetBDfromDVL.last_data_valid_time);*/
	
	/*
	printf("msg between CPU and DVL_WI::::\n");
	printf("GetWIfromDVL.head_buf: %c%c%c\n",GetWIfromDVL.head_buf[0],GetWIfromDVL.head_buf[1],GetWIfromDVL.head_buf[2]);
	printf("speedX:%f\n",GetWIfromDVL.speedX);
	printf("speedY:%f\n",GetWIfromDVL.speedY);
	printf("speedZ:%f\n",GetWIfromDVL.speedZ);
	printf("spare:%f\n",GetWIfromDVL.spare);
	printf("valid_flag: %c\n",GetWIfromDVL.valid_flag[0]);*/	
	
	/*
	printf("msg between CPU and DVL_WD::::\n");
	printf("GetWDfromDVL.head_buf: %c%c%c\n",GetWDfromDVL.head_buf[0],GetWDfromDVL.head_buf[1],GetWDfromDVL.head_buf[2]);
	printf("acoustic_flag:%f\n",GetWDfromDVL.acoustic_flag);
	printf("selftest_flag:%f\n",GetWDfromDVL.selftest_flag);
	printf("transducer_array_depth:%f\n",GetWDfromDVL.transducer_array_depth);
	printf("transducer_array_track_bottom_depth:%f\n",GetWDfromDVL.transducer_array_track_bottom_depth);
	printf("last_data_valid_time:%f\n",GetWDfromDVL.last_data_valid_time);*/
	
	/*
	printf("msg between CPU and DVL_ACK::::\n");
	printf("GetACKfromDVL.head_buf: %c%c%c%c\n",GetACKfromDVL.head_buf[0],GetACKfromDVL.head_buf[1],GetACKfromDVL.head_buf[2],GetACKfromDVL.head_buf[3]);
	printf("F:%f\n",GetACKfromDVL.F_selftest);	
	printf("A:%f\n",GetACKfromDVL.A_channel);	
	printf("B:%f\n",GetACKfromDVL.B_channel);	
	printf("C:%f\n",GetACKfromDVL.C_channel);	
	printf("D:%f\n",GetACKfromDVL.D_channel);*/
	
	
}




void between_CPU_and_GPS(void)
{
	/*printf("GPS_Recv_num:%d\n",GPS_Recv_num);*/
	/*GPGGA*/
	printf("msg between CPU and GPS::::\n");	
	printf("UTC_Time: %2d:%2d:%2d\n", BiosTimeSetting.hour, BiosTimeSetting.minute, BiosTimeSetting.second);	
    printf("%3.6f %2.6f\n", GPS_Prase_Data.GPS_Longtitude, GPS_Prase_Data.GPS_Latitude);
	printf("GPS_State:%d\n",GPS_Prase_Data.GPS_Position_QC);
	
	
	/*GPVTG*/	
	printf("GPS_Course:%2.6f\n",GPS_Prase_Data.GPS_Course);
	printf("GPS_Velocity_Kn:%2.6f\n",GPS_Prase_Data.GPS_Velocity_Kn);
	printf("GPS_Velocity_Kmph:%2.6f\n",GPS_Prase_Data.GPS_Velocity_Kmph);

}


void Beid_BDTXR(void)
{
	printf("Beid $BDTXR::::\n");
	printf("$BDTXR_Flag:%c%c%c%c%c%c\n",UI_BEIDOU_Instruction.$BDTXR_Flag[0],UI_BEIDOU_Instruction.$BDTXR_Flag[1],UI_BEIDOU_Instruction.$BDTXR_Flag[2],UI_BEIDOU_Instruction.$BDTXR_Flag[3],UI_BEIDOU_Instruction.$BDTXR_Flag[4],UI_BEIDOU_Instruction.$BDTXR_Flag[5]);
	printf("FromUI3_Head_BUF:%c%c%c%c\n",UI_BEIDOU_Instruction.FromUI3_Head_BUF[0],UI_BEIDOU_Instruction.FromUI3_Head_BUF[1],UI_BEIDOU_Instruction.FromUI3_Head_BUF[2],UI_BEIDOU_Instruction.FromUI3_Head_BUF[3]);
	printf("FromUI3_Msg_Length:%2x\n",UI_BEIDOU_Instruction.FromUI3_Msg_Length);
	printf("FromUI3_Msg_Num:%d\n",UI_BEIDOU_Instruction.FromUI3_Msg_Num);
	printf("FromUI3_ID:%2x\n",UI_BEIDOU_Instruction.FromUI3_ID);
	printf("FromUI3_Ctrl_Mode:%2x\n",UI_BEIDOU_Instruction.FromUI3_Ctrl_Mode);	
	printf("FromUI3_Depth_Para1:%d\n",UI_BEIDOU_Instruction.FromUI3_Depth_Para1);
	printf("FromUI3_Depth_Para2:%d\n",UI_BEIDOU_Instruction.FromUI3_Depth_Para2);
	printf("FromUI3_Height_Para1:%d\n",UI_BEIDOU_Instruction.FromUI3_Height_Para1);
	printf("FromUI3_Height_Para2:%d\n",UI_BEIDOU_Instruction.FromUI3_Height_Para2);
	printf("FromUI3_Remain_Time:%d\n",UI_BEIDOU_Instruction.FromUI3_Remain_Time);
	printf("FromUI3_Work_Cmd:%2x\n",UI_BEIDOU_Instruction.FromUI3_Work_Cmd);
	printf("FromUI3_Back_Lat:%d FromUI3_Back_Lon:%d\n", UI_BEIDOU_Instruction.FromUI3_Back_Lat, UI_BEIDOU_Instruction.FromUI3_Back_Lon);
	printf("FromUI3_Check_Sum:%2x\n", UI_BEIDOU_Instruction.FromUI3_Check_Sum);
	printf("FromUI3_End_Buf:%2x,%2x\n", UI_BEIDOU_Instruction.FromUI3_End_Buf[0],UI_BEIDOU_Instruction.FromUI3_End_Buf[1]);

}



void PathPlanning_data_printf(void)
{
	/*定点航行参数
	u16 ii = 0;	
	printf("FixedPoint_PathPlanning msg::::\n");
	printf("TaskNumber:%s\n", FixedPoint_PathPlanning.TaskNumber);
	printf("TotalTimeOut:%d\n", FixedPoint_PathPlanning.TotalTimeOut);
	printf("TotalNumber:%d\n", FixedPoint_PathPlanning.TotalNumber);	
	for(ii = 0; ii <= 11; ii++)
	{	
	    printf("Parameter:%d\n", FixedPoint_PathPlanning.Parameter[ii]);
	}
	
	for(ii = 0; ii <= 11; ii++)
	{	
		printf("MotorSetSpeed:%d\n", FixedPoint_PathPlanning.MotorSetSpeed[ii]);
	}*/
	
	
	
	/*定向航行参数*/	
	u16 ii = 0;	
	printf("FixedDirection_PathPlanning msg::::\n");
	printf("TaskNumber:%s\n", FixedDirection_PathPlanning.TaskNumber);
	printf("TotalTimeOut:%d\n", FixedDirection_PathPlanning.TotalTimeOut);
	printf("TotalNumber:%d\n", FixedDirection_PathPlanning.TotalNumber);	
	/*for(ii = 0; ii <= 11; ii++)
	{	
	    printf("Parameter:%d\n", FixedDirection_PathPlanning.Parameter[ii]);
	}*/	
	
	for(ii = 0; ii <= 2; ii++)
	{	
		printf("MotorSetSpeed:%d\n", FixedDirection_PathPlanning.MotorSetSpeed[ii]);
	}
	
	
	
	
	
	
}





