#include <vxWorks.h>
#include <sysLib.h>
#include <taskLib.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>


#include "SecurityEmergencyManage.h"
#include "com.h"
#include "DataProcess.h"
#include "PowerManage.h"
#include "CtrlAlgorithm.h" 
#include "XMLFile.h"
#include "main.h"



void EmergencyTask(void);
void Emergency_Level1(void);
void Emergency_Level2(void);
void Emergency_Level3(void);


u16 Not_Recv_From_WIFI_No = 0;
u16 Not_Recv_From_FMCU_No = 0;
u16 Not_Recv_From_BMS_No = 0;
u16 Not_Recv_From_LORA_No = 0;
u16 Not_Recv_From_IMU_No = 0;
u16 Not_Recv_From_PSD_No = 0;
u16 Not_Recv_From_GPS_No = 0;
u16 Not_Recv_From_BEIDOU_No = 0;
u16 Not_Recv_From_DVL_No = 0;

u16 Not_Recv_From_BI_DVL_No = 0;
u16 Not_Recv_From_WI_DVL_No = 0;

u32 Device_Power_State_Judgement=0;
u32 Cmd_State_Judgement=0;
u32 Sail_State_Judgement=0;
u32 Sys_Abnorm_Inf_Judgement=0;
u32 Dev_Abnorm_Inf_Judgement=0;
u32 BMS_Abnorm_Inf_Judgement=0;
u32 Dev_Abnorm_Inf_Detail_Judgement=0;


u16 Depth_Exceed_FromUI12_Depth_Para1 = 0;
u16 Depth_Exceed_FromUI12_Depth_Para2 = 0;

void EmergencyTask(void)
{	
	FOREVER
	{
		if(OK == semTake(semEmergencyTask,WAIT_FOREVER))
		{
			printf("EmergencyTask start::::\n");	
			
			/*如果当前状态是遥控且没有收到信号，返回值为-1的话，证明没有收到wifi数据*/
	        if(Not_Recv_From_WIFI_No >=  20)           /*操控台通信异常*/
			{
				UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;/*主推停机*/
			}
	       
			/*超过航行超深保护参数1，就主推停机*/
	        if((Current_State.Current_Dep > UI_WIFI_Instruction.FromUI12_Depth_Para1) && (UI_WIFI_Instruction.FromUI12_Depth_Para1 != 0))/*这个的1，最终换成UI_WIFI_Instruction.FromUI12_Depth_Para1*/
	        {
	        	Depth_Exceed_FromUI12_Depth_Para1++;	        	
	        }

            
	        if(Depth_Exceed_FromUI12_Depth_Para1 >= 10)
	        {
	        	Sys_Abnorm_Inf_Judgement |= 0x00000200;	/*超过航行超深参数1，就将对应位置1*/
	        	
	        	UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;/*主推停机*/
	         	
	        }
	        
	        /*超过航行超深保护参数1，就主推停机,丢压载*/
	        if((Current_State.Current_Dep > UI_WIFI_Instruction.FromUI12_Depth_Para2) && (UI_WIFI_Instruction.FromUI12_Depth_Para2 != 0))/*这个的2，最终换成UI_WIFI_Instruction.FromUI12_Depth_Para2*/
	        {
	        	Depth_Exceed_FromUI12_Depth_Para2++;
	        }

	        
	        if(Depth_Exceed_FromUI12_Depth_Para2 >= 10)
	        {
	        	Sys_Abnorm_Inf_Judgement |= 0x00000400;	/*超过航行超深参数2，就将对应位置1*/
	        	
	        	UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;/*主推停机*/
	        	
	        	EL_Power_Control(Power_ON);/*应急压载上电*/
	        	
	        	Remote_Assignment(&Instruction_To_FMCU);
	        }	 
	        
	        if(Not_Recv_From_GPS_No >= 30)/*接收不到GPS信号，5次*/
	        {
	        	Recv_From_GPS_QC_Flag = false;
	        }
	        
	        
	        if(Not_Recv_From_BI_DVL_No >= 20 )
	        {
	          BI_Cal_Data_Flag = false;/*BI推算 标志位 错误*/
	        }
	        
	        if(Not_Recv_From_WI_DVL_No >= 20 )
	        {
	          WI_Cal_Data_Flag = false;/*BI推算 标志位 错误*/
	        }
	        
			/*解析Data_From_FMCU.McuFD_Sys_Abnorm_Inf*/
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0:  舱体漏水报警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000001;		
				Emergency_Level3();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffffe;	
			}		
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: 舱体温度超限报警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000002;		
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffffd;
			}	
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: 舱体压力异常报警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000004;	    
				Emergency_Level3();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffffb;
			}
					
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: 系统能源异常告警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000008;
				Emergency_Level2();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffff7;
			}
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: 设备能源异常告警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000010;	
				Emergency_Level2();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xffffffef;
			}
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: 系统通信异常告警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000020;	 
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xffffffdf;
			}
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: 设备状态异常告警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000040;	
				Emergency_Level2();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xffffffbf;
			}
				
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: MCU→CPU通信异常告警*/
			{	
				Sys_Abnorm_Inf_Judgement |= 0x00000080;	  
				Emergency_Level2();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xffffff7f;
			}
				
		/*****************************************************************************/	
			
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: CPU→MCU通信异常告警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000100;	
				Emergency_Level2();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffeff;	
			}
					
			/*if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0200) == 0x0200)  Bit9：航行超深保护参数1告警
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000200;	
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffdff;
			}*/
			
			/*if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0400) == 0x0400)Bit10: 航行超深保护参数2告警
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000400;	
				Emergency_Level2();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffbff;
			}*/
				
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11: 离底超限保护参数1告警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000800;	
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffff7ff;
			}
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12：离底超限保护参数2告警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00001000;	
				Emergency_Level2();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xffffefff;
			}
					
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: 下潜超时告警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00002000;	
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xffffdfff;
			}		
				
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:航行超时告警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00004000;	
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xffffbfff;
			}
				
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:下潜姿态超限告警*/
			{	
				Sys_Abnorm_Inf_Judgement |= 0x00008000;	
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xffff7fff;
			}
				
				
			/********************************************************************************/		
			
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: 航行姿态超限告警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00010000;	
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffeffff;	
			}			
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: 偏航距超限告警*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00020000;	
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffdffff;
			}					
			
	

			
			/*解析Data_From_FMCU.McuFD_Dev_Abnorm_Inf*/		
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0: 主推能源异常告警 */
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000001;		
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffffe;	
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: 侧推能源异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000002;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffffd;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: 水平左舵能源异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000004;	  
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffffb;
			}		
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: 水平右舵能源异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000008;	  
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffff7;
			}		
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: 垂直上舵能源异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000010;	
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffffef;
			}
					
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: 垂直下舵能源异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000020;	  
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffffdf;
			}
						
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: 应急压载能源异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000040;		
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffffbf;
			}
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: DVL能源异常告警*/
			{	
				Dev_Abnorm_Inf_Judgement |= 0x00000080;	  
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffff7f;
			}
				
		/*****************************************************************************/	
			
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: 备用1能源异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000100;	
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffeff;	
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0200) == 0x0200)  /*Bit9：备用2能源异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000200;		
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffdff;
			}
					
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0400) == 0x0400)/*Bit10: 主推通信异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000400;	 
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffbff;
			}
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11:侧推通信异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000800;	 
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffff7ff;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12：水平左舵通信异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00001000;	
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffefff;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: 水平右舵通信异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00002000;	  
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffdfff;
			}
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:垂直上舵通信异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00004000;	
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffbfff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:垂直下舵通信异常告警*/
			{	
				Dev_Abnorm_Inf_Judgement |= 0x00008000;	  
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffff7fff;
			}
				
				
			/********************************************************************************/		
			
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: DVL通信异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00010000;	
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffeffff;	
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: 罗经通信异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00020000;		
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffdffff;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00040000) == 0x00040000)/*bit18:备用1通信异常告警 */
			{
				Dev_Abnorm_Inf_Judgement |= 0x00040000;	  
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffbffff;
			}		
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00080000) == 0x00080000)/*bit19: 备用2通信异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00080000;	   
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfff7ffff;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00100000) == 0x00100000)  /*Bit20: 主推状态异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00100000;	
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffefffff;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00200000) == 0x00200000) /*Bit21: 侧推状态异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00200000;	    
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffdfffff;
			}
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00400000) == 0x00400000)  /*Bit22: 水平左舵状态异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00400000;	
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffbfffff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00800000) == 0x00800000)  /*Bit23:水平右舵状态异常告警*/
			{	
				Dev_Abnorm_Inf_Judgement |= 0x00800000;	 
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xff7fffff;	
			}		
			/********************************************************************************/		

			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x01000000) == 0x01000000)    /*Bit24: 垂直上舵状态异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x01000000;		
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfeffffff;	
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x02000000) == 0x02000000)  /*Bit25：垂直下舵状态异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x02000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfdffffff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x04000000) == 0x04000000)/*Bit26:应急压载状态异常告警（无效置零） */
			{
				Dev_Abnorm_Inf_Judgement |= 0x04000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfbffffff;
			}
						
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x08000000) == 0x08000000)/*Bit27: DVL状态异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x08000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xf7ffffff;
			}		
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x10000000) == 0x10000000)  /*Bit28：罗经状态异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x10000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xefffffff;
			}		
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x20000000) == 0x20000000) /*Bit29:备用1状态异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x20000000;	  
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xdfffffff;
			}
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x40000000) == 0x40000000)  /*Bit30:备用2状态异常告警*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x40000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xbfffffff;
			}		
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x80000000) == 0x80000000)  /*Bit31:通信模块能源异常告警*/
			{	
				Dev_Abnorm_Inf_Judgement |= 0x80000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0x7fffffff;		
			}
					
			

			
			/*接收BMS_Prase_Data.BMS_Abnorm_Inf之后，立马进行状态判断*/
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0:  单体过压一级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000001;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffffe;	
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: 系统过压一级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000002;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffffd;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: 充电过流一级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000004;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffffb;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: 单体欠压一级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000008;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffff7;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: 系统欠压一级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000010;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffffef;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: 放电过流一级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000020;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffffdf;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: 充电温度过高一级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000040;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffffbf;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: 充电温度过低一级报警*/
			{	
				BMS_Abnorm_Inf_Judgement |= 0x00000080;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffff7f;
			}
				
		/*****************************************************************************/	
			
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: SOC过低一级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000100;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffeff;	
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0200) == 0x0200)  /*Bit9：充电过流三级告警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000200;
				Emergency_Level3();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffdff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0400) == 0x0400)/*Bit10: 功率温度过高一级告警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000400;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffbff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11: 环境温度过高一级告警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000800;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffff7ff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12：环境温度过低一级告警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00001000;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffefff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: 放电过流三级告警（无效）*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00002000;
				Emergency_Level3();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffdfff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:放电温度过高一级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00004000;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffbfff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:放电温度过低一级报警*/
			{	
				BMS_Abnorm_Inf_Judgement |= 0x00008000;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffff7fff;
			}
				
				
			/********************************************************************************/		
			
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: 单体过压二级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00010000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffeffff;	
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: 系统过压二级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00020000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffdffff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00040000) == 0x00040000)/*bit18: 充电过流二级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00040000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffbffff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00080000) == 0x00080000)/*bit19: 单体欠压二级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00080000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfff7ffff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00100000) == 0x00100000)  /*Bit20: 系统欠压二级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00100000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffefffff;	
			}
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00200000) == 0x00200000) /*Bit21: 放电过流二级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00200000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffdfffff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00400000) == 0x00400000)  /*Bit22: 充电温度过高二级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00400000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffbfffff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00800000) == 0x00800000)  /*Bit23: 充电温度过低二级报警*/
			{	
				BMS_Abnorm_Inf_Judgement |= 0x00800000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xff7fffff;	
			}
				
			/********************************************************************************/		

			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x01000000) == 0x01000000)    /*Bit24: SOC过低二级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x01000000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfeffffff;	
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x02000000) == 0x02000000)  /*Bit25：充电过流三级告警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x02000000;
				Emergency_Level3();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfdffffff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x04000000) == 0x04000000)/*Bit26: 功率温度过高二级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x04000000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfbffffff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x08000000) == 0x08000000)/*Bit27: 环境温度过高二级告警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x08000000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xf7ffffff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x10000000) == 0x10000000)  /*Bit28：环境温度过低二级告警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x10000000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xefffffff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x20000000) == 0x20000000) /*Bit29: 放电过流三级告警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x20000000;
				Emergency_Level3();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xdfffffff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x40000000) == 0x40000000)  /*Bit30:放电温度过高二级报警*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x40000000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xbfffffff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x80000000) == 0x80000000)  /*Bit31:放电温度过低二级报警*/
			{	
				BMS_Abnorm_Inf_Judgement |= 0x80000000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0x7fffffff;		
			}
								
			
			
			/*解析Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail*/
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0001) == 0x0001)    /*bit0: 水平左舵舵机过载*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000001;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffffe;	
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0002) == 0x0002)  /*bit1: 水平左舵舵机过流*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000002;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffffd;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0004) == 0x0004)/*bit2: 水平左舵舵机过热*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000004;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffffb;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0008) == 0x0008)/*bit3: 水平左舵舵机角度错误*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000008;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffff7;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0010) == 0x0010)  /*Bit4: 水平左舵舵机过压欠压*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000010;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffffef;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0020) == 0x0020) /*Bit5: ：水平右舵舵机过载*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000020;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffffdf;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0040) == 0x0040)  /*Bit6: 水平右舵舵机过流*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000040;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffffbf;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0080) == 0x0080)  /*Bit7: 水平右舵舵机过热*/
			{	
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000080;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffff7f;
			}
				
		/*****************************************************************************/	
			
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0100) == 0x0100)    /*Bit8: 水平右舵舵机角度错误*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000100;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffeff;	
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0200) == 0x0200)  /*Bit9：水平右舵舵机过压欠压*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000200;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffdff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0400) == 0x0400)/*Bit10: 垂直上舵舵机过载*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000400;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffbff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0800) == 0x0800)/*Bit11: 垂直上舵舵机过流*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000800;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffff7ff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x1000) == 0x1000)  /*Bit12：垂直上舵舵机过热*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00001000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffefff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x2000) == 0x2000) /*Bit13: 垂直上舵舵机角度错误*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00002000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffdfff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x4000) == 0x4000)  /*Bit14:垂直上舵舵机过压欠压*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00004000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffbfff;
			}		
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x8000) == 0x8000)  /*Bit15: 垂直下舵舵机过载*/
			{	
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00008000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffff7fff;
			}
				
				
			/********************************************************************************/		
			
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00010000) == 0x00010000)    /*bit16: 垂直下舵舵机过流*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00010000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffeffff;
			}
					
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00020000) == 0x00020000)  /*bit17: 垂直下舵舵机过热*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00020000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffdffff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00040000) == 0x00040000)/*bit18: 垂直下舵舵机角度错误*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00040000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffbffff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00080000) == 0x00080000)/*bit19: 垂直下舵舵机过压欠压*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00080000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfff7ffff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00100000) == 0x00100000)  /*Bit20: 主推堵转停止*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00100000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffefffff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00200000) == 0x00200000) /*Bit21:主推不达速 */
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00200000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffdfffff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00400000) == 0x00400000)  /*Bit22: 主推霍尔错误*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00400000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffbfffff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00800000) == 0x00800000)  /*Bit23: 无效置零*/
			{	
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00800000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xff7fffff;	
			}
				
			/********************************************************************************/		

			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x01000000) == 0x01000000)    /*Bit24: 无效置零*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x01000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfeffffff;	
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x02000000) == 0x02000000)  /*Bit25：无效置零*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x02000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfdffffff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x04000000) == 0x04000000)/*Bit26: DVL自检异常*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x04000000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfbffffff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x08000000) == 0x08000000)/*Bit27:DVL对底无效 */
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x08000000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xf7ffffff;
			}
		
		}
	}
}




void Emergency_Level1(void)
{

	
	
}
void Emergency_Level2(void)
{
	
}
void Emergency_Level3(void)
{
/*	
	UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;/*主推停机*/
	
	/*EL_Power_Control(Power_ON);应急压载上电*/
	
	/*	Remote_Assignment(&Instruction_To_FMCU);*/
}
