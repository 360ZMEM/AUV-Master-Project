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
extern void Remote_Assignment_Set_Output_Override(u8 enable);

static void Emergency_Remote_Assignment(_To_MCUFD *temp)
{
	/**
	 * @brief Send one emergency frame without letting Remote_Assignment rebuild outputs from UI shadow.
	 * @note  This is used by software self-rescue paths whose actuator outputs are already computed in
	 *        Instruction_To_FMCU and must not be overwritten by stale UI/LORA motor or rudder commands.
	 */
	Remote_Assignment_Set_Output_Override(1);
	Remote_Assignment(temp);
}


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

/**
 * @brief Jetson ʧ��������, ÿ 0.1s ����һ�� (�� FuncWd_InfoOutputCtrl ��)
 * �յ� Jetson ���ݰ�ʱ���� (�� Unpack_Data_From_UI12_WIFI ��)
 * ��ֵ 10 = 1.0s ��ʱ
 */
u16 Not_Recv_From_Jetson_No = 0;
static u8 Jetson_Timeout_Latched = 0;

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
				u8 jetson_mode_active;
			printf("EmergencyTask start::::\n");	
			
			/*�1�7�1�7�1�7�1�7�1�7�0�2�0�8�0�0�1�7�1�7�0�1�1�7�1�7�1�7�1�7�0�4�1�7�1�7�1�7�0�1�1�7�1�7�0�2�0�0�1�7�1�7�1�7�1�7�1�7�0�5�0�2-1�1�7�0�3�1�7�1�7�1�7�0�8�1�7�1�7�0�4�1�7�1�7�1�7�0�1�1�7wifi�1�7�1�7�1�7�1�7*/
	        if(Not_Recv_From_WIFI_No >=  20)           /*�1�7�1�7�1�7�0�6�0�0�1�7�1�7�1�7�4�4*/
			{
				UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;/*�1�7�1�7�1�7�1�7�0�5�1�7�1�7*/
			}

			/**
			 * @brief Jetson ʧ�����Ź� (1.0s ��ʱ)
			 * ��������: Not_Recv_From_Jetson_No >= 10 (10��0.1s = 1.0s)
			 * ���� 0xEE/0xEF ģʽ����Ч
			 * ��������: ģʽ������ Remote(0x01), ��������, ��ͣ
			 */
				jetson_mode_active = (Current_State.Current_Mode == 0xEE || Current_State.Current_Mode == 0xEF);
				if(jetson_mode_active)
				{
					if(Not_Recv_From_Jetson_No >= 10)
					{
						Jetson_Timeout_Latched = 1;
						UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0x01;  /* ������ң��ģʽ */
						UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;  /* �������� */
						UI_WIFI_Instruction.FromUI12_Motor_Speed2 = 0;
						Sys_Abnorm_Inf_Judgement |= 0x00004000;  /* Bit14: Jetsonͨ�ų�ʱ�澯 */
					}
					else
					{
						Jetson_Timeout_Latched = 0;
						Sys_Abnorm_Inf_Judgement &= 0xffffbfff;  /* ��� Bit14 */
					}
				}
				else
				{
					/*
					 * PC104 may boot and idle before Jetson starts. Do not let this
					 * stale counter cause an immediate timeout when Jetson mode is
					 * selected later. If a real timeout was latched, keep Bit14
					 * observable until a Jetson packet resets the counter.
					 */
					if(Not_Recv_From_Jetson_No < 10)
					{
						Jetson_Timeout_Latched = 0;
					}
					if(Jetson_Timeout_Latched)
					{
						Sys_Abnorm_Inf_Judgement |= 0x00004000;
					}
					else
					{
						Not_Recv_From_Jetson_No = 0;
						Sys_Abnorm_Inf_Judgement &= 0xffffbfff;  /* ��� Bit14 */
					}
				}
			
			/* BUG-5/6/7: ��׸߶��ٲ� + ˮ�ذ�ȫ */
#if POOL_TEST_MODE
			Pool_Safety_Check();
#else
			Seafloor_Grounding_Arbitration();
#endif
	       
			/*�1�7�1�7�1�7�1�7�1�7�1�7�1�7�Ԅ1�7�1�7�7�2�1�7�1�7�1�7�1�7�1�7�1�71�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�5�1�7�1�7*/
	        /* BUG-3 fix: �������ڷ���, ��Ȼ���ʱ�ݼ� (�޸�ֻ����������) */
	        if((Current_State.Current_Dep > UI_WIFI_Instruction.FromUI12_Depth_Para1) && (UI_WIFI_Instruction.FromUI12_Depth_Para1 != 0))
	        {
	        	Depth_Exceed_FromUI12_Depth_Para1++;
	        }
	        else
	        {
	        	if(Depth_Exceed_FromUI12_Depth_Para1 > 0) Depth_Exceed_FromUI12_Depth_Para1--;
	        }

            
	        if(Depth_Exceed_FromUI12_Depth_Para1 >= 10)
	        {
	        	Sys_Abnorm_Inf_Judgement |= 0x00000200;
	        	
	        	/*
	        	 * BUG-4 fix: Ƿ����AUV�����Ծ� - ������Ͷ�Ч���� + �����ϸ���
	        	 * ���߼�(����bug): Motor_Speed1=0 ����ʧȥ��Чֱ�ӳ���
	        	 */
                        Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 300;
                        Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location + 20.0f * 4096/360);
                        Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location - 20.0f * 4096/360);
                        /* BUG-4 runtime fix: Remote_Assignment rebuilds outputs from UI/LORA shadow commands. */
                        UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 300;
                        UI_WIFI_Instruction.FromUI12_RCD_LH_Set_Rud_Angle = -20;
                        UI_WIFI_Instruction.FromUI12_RCD_RH_Set_Rud_Angle = -20;
                        UI_LORA_Instruction.FromUI12_Motor_Speed1 = 300;
                        UI_LORA_Instruction.FromUI12_RCD_LH_Set_Rud_Angle = -20;
                        UI_LORA_Instruction.FromUI12_RCD_RH_Set_Rud_Angle = -20;
	        	Emergency_Remote_Assignment(&Instruction_To_FMCU);
	        }
	        
	        /*�1�7�1�7�1�7�1�7�1�7�1�7�1�7�Ԅ1�7�1�7�7�2�1�7�1�7�1�7�1�7�1�7�1�71�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�5�1�7�1�7,�1�7�1�7�0�9�1�7�1�7*/
	        if((Current_State.Current_Dep > UI_WIFI_Instruction.FromUI12_Depth_Para2) && (UI_WIFI_Instruction.FromUI12_Depth_Para2 != 0))
	        {
	        	Depth_Exceed_FromUI12_Depth_Para2++;
	        }
	        else
	        {
	        	if(Depth_Exceed_FromUI12_Depth_Para2 > 0) Depth_Exceed_FromUI12_Depth_Para2--;
	        }

	        
	        if(Depth_Exceed_FromUI12_Depth_Para2 >= 10)
	        {
	        	Sys_Abnorm_Inf_Judgement |= 0x00000400;
	        	
	        	/* BUG-4 fix: ���ֶ�Ч + �����ϸ��� + Ӧ��ѹ�� */
                        Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 300;
                        Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location + 20.0f * 4096/360);
                        Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location - 20.0f * 4096/360);
                        /* BUG-4 runtime fix: Remote_Assignment rebuilds outputs from UI/LORA shadow commands. */
                        UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 300;
                        UI_WIFI_Instruction.FromUI12_RCD_LH_Set_Rud_Angle = -20;
                        UI_WIFI_Instruction.FromUI12_RCD_RH_Set_Rud_Angle = -20;
                        UI_LORA_Instruction.FromUI12_Motor_Speed1 = 300;
                        UI_LORA_Instruction.FromUI12_RCD_LH_Set_Rud_Angle = -20;
                        UI_LORA_Instruction.FromUI12_RCD_RH_Set_Rud_Angle = -20;
	        	
	        	EL_Power_Control(Power_ON);
	        	Emergency_Remote_Assignment(&Instruction_To_FMCU);
	        }

	        /**
	         * @brief ��ȳ���ģʽ���� (0xEE/0xEF ģʽר��)
	         * �� Depth_Para1 ������ȳ���(����10��), �� Jetson ����ģʽ��
	         * ����ִ��ģʽ����: ������ Remote(0x01), ��ֹ Jetson ������Ǳ
	         */
	        if(Depth_Exceed_FromUI12_Depth_Para1 >= 10)
	        {
	        	if(Current_State.Current_Mode == 0xEE || Current_State.Current_Mode == 0xEF)
	        	{
	        		UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0x01;  /* ģʽ���� */
	        		UI_WIFI_Instruction.FromUI12_Motor_Speed2 = 0;
	        	}
	        }	 
	        
	        if(Not_Recv_From_GPS_No >= 30)/*�1�7�1�7�1�7�0�8�1�7�1�7�1�7GPS�1�7�0�2�0�0�1�75�1�7�1�7*/
	        {
	        	Recv_From_GPS_QC_Flag = false;
	        }
	        
	        
	        if(Not_Recv_From_BI_DVL_No >= 20 )
	        {
	          BI_Cal_Data_Flag = false;/*BI�1�7�1�7�1�7�1�7 �1�7�1�7�0�4�� �1�7�1�7�1�7�1�7*/
	        }
	        
	        if(Not_Recv_From_WI_DVL_No >= 20 )
	        {
	          WI_Cal_Data_Flag = false;/*BI�1�7�1�7�1�7�1�7 �1�7�1�7�0�4�� �1�7�1�7�1�7�1�7*/
	        }
	        
			/*�1�7�1�7�1�7�1�7Data_From_FMCU.McuFD_Sys_Abnorm_Inf*/
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0:  �1�7�1�7�1�7�1�7�0�8�0�8�1�7�1�7�1�7�1�7*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000001;		
				Emergency_Level3();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffffe;	
			}		
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: �1�7�1�7�1�7�1�7�1�7�0�9�0�8�1�7�1�7�1�3�1�7�1�7�1�7*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000002;		
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffffd;
			}	
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: �1�7�1�7�1�7�1�7�0�9�1�7�1�7�1�7�4�4�1�7�1�7�1�7�1�7*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000004;	    
				Emergency_Level3();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffffb;
			}
					
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: �0�3�0�1�1�7�1�7�0�6�1�7�4�4�1�7��*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000008;
				Emergency_Level2();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffff7;
			}
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: �1�7��1�7�1�7�0�6�1�7�4�4�1�7��*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000010;	
				Emergency_Level2();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xffffffef;
			}
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: �0�3�0�1�0�0�1�7�1�7�1�7�4�4�1�7��*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000020;	 
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xffffffdf;
			}
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: �1�7��0�8�0�0�1�7�4�4�1�7��*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000040;	
				Emergency_Level2();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xffffffbf;
			}
				
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: MCU�1�7�1�7CPU�0�0�1�7�1�7�1�7�4�4�1�7��*/
			{	
				Sys_Abnorm_Inf_Judgement |= 0x00000080;	  
				Emergency_Level2();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xffffff7f;
			}
				
		/*****************************************************************************/	
			
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: CPU�1�7�1�7MCU�0�0�1�7�1�7�1�7�4�4�1�7��*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000100;	
				Emergency_Level2();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffeff;	
			}
					
			/*if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0200) == 0x0200)  Bit9�1�7�1�7�1�7�1�7�1�7�Ԅ1�7�1�7�7�2�1�7�1�7�1�7�1�7�1�7�1�71�1�7��
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000200;	
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffdff;
			}*/
			
			/*if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0400) == 0x0400)Bit10: �1�7�1�7�1�7�Ԅ1�7�1�7�7�2�1�7�1�7�1�7�1�7�1�7�1�72�1�7��
			{
				Sys_Abnorm_Inf_Judgement |= 0x00000400;	
				Emergency_Level2();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffffbff;
			}*/
				
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11: �1�7�1�7�0�7�1�7�1�7�1�3�1�7�1�7�1�7�1�7�1�7�1�7�1�71�1�7��*/
			{
				/**
				 * @brief Preserve software-arbitrated DVL protection bits in EmergencyTask.
				 * @note  Seafloor_Grounding_Arbitration() can assert Bit11/12/13 before MCU
				 *        feedback carries the same bits. Mirror MCU-set bits here, but do
				 *        not clear software-owned DVL protection bits from this path.
				 */
				Sys_Abnorm_Inf_Judgement |= 0x00000800;	
				Emergency_Level1();
			}
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12�1�7�1�7�1�7�1�7�0�7�1�7�1�7�1�3�1�7�1�7�1�7�1�7�1�7�1�7�1�72�1�7��*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00001000;	
				Emergency_Level2();
			}
					
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: �1�7�1�7�0�3�1�7�1�7�0�2�1�7��*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00002000;	
				Emergency_Level1();
			}		
				
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:�1�7�1�7�1�7�Ԅ1�7�0�2�1�7��*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00004000;	
				Emergency_Level1();
			}
			else
			{
				if(Jetson_Timeout_Latched == 0)
				{
					Sys_Abnorm_Inf_Judgement &= 0xffffbfff;
				}
			}
				
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:�1�7�1�7�0�3�1�7�1�7�0�0�1�7�1�7�1�7�1�0��*/
			{	
				Sys_Abnorm_Inf_Judgement |= 0x00008000;	
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xffff7fff;
			}
				
				
			/********************************************************************************/		
			
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: �1�7�1�7�1�7�1�7�1�7�1�7�0�0�1�7�1�7�1�7�1�0��*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00010000;	
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffeffff;	
			}			
			
			if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: �0�1�1�7�1�7�1�7�2�2�1�7�1�0��*/
			{
				Sys_Abnorm_Inf_Judgement |= 0x00020000;	
				Emergency_Level1();
			}
			else
			{
				Sys_Abnorm_Inf_Judgement &= 0xfffdffff;
			}					
			
	

			
			/*�1�7�1�7�1�7�1�7Data_From_FMCU.McuFD_Dev_Abnorm_Inf*/		
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0: �1�7�1�7�1�7�1�7�1�7�1�7�0�6�1�7�4�4�1�7�� */
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000001;		
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffffe;	
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: �1�7�1�7�1�7�1�7�1�7�1�7�0�6�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000002;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffffd;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: �0�8�0�9�1�7�1�7�1�7�1�7�1�7�0�6�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000004;	  
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffffb;
			}		
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: �0�8�0�9�1�7�0�0�1�7�1�7�1�7�0�6�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000008;	  
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffff7;
			}		
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: �1�7�1�7�0�1�1�7�0�4�1�7�1�7�1�7�0�6�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000010;	
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffffef;
			}
					
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: �1�7�1�7�0�1�1�7�0�9�1�7�1�7�1�7�0�6�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000020;	  
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffffdf;
			}
						
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: �0�8�1�7�1�7�0�9�1�7�1�7�1�7�1�7�0�6�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000040;		
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffffbf;
			}
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: DVL�1�7�1�7�0�6�1�7�4�4�1�7��*/
			{	
				Dev_Abnorm_Inf_Judgement |= 0x00000080;	  
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffff7f;
			}
				
		/*****************************************************************************/	
			
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: �1�7�1�7�1�7�1�71�1�7�1�7�0�6�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000100;	
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffeff;	
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0200) == 0x0200)  /*Bit9�1�7�1�7�1�7�1�7�1�7�1�72�1�7�1�7�0�6�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000200;		
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffdff;
			}
					
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0400) == 0x0400)/*Bit10: �1�7�1�7�1�7�1�7�0�0�1�7�1�7�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000400;	 
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffffbff;
			}
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11:�1�7�1�7�1�7�1�7�0�0�1�7�1�7�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00000800;	 
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffff7ff;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12�1�7�1�7�0�8�0�9�1�7�1�7�1�7�0�0�1�7�1�7�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00001000;	
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffefff;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: �0�8�0�9�1�7�0�0�1�7�0�0�1�7�1�7�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00002000;	  
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffdfff;
			}
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:�1�7�1�7�0�1�1�7�0�4�1�7�0�0�1�7�1�7�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00004000;	
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffffbfff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:�1�7�1�7�0�1�1�7�0�9�1�7�0�0�1�7�1�7�1�7�4�4�1�7��*/
			{	
				Dev_Abnorm_Inf_Judgement |= 0x00008000;	  
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffff7fff;
			}
				
				
			/********************************************************************************/		
			
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: DVL�0�0�1�7�1�7�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00010000;	
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffeffff;	
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: �1�7�1�6�1�7�0�0�1�7�1�7�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00020000;		
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffdffff;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00040000) == 0x00040000)/*bit18:�1�7�1�7�1�7�1�71�0�0�1�7�1�7�1�7�4�4�1�7�� */
			{
				Dev_Abnorm_Inf_Judgement |= 0x00040000;	  
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfffbffff;
			}		
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00080000) == 0x00080000)/*bit19: �1�7�1�7�1�7�1�72�0�0�1�7�1�7�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00080000;	   
				Emergency_Level2();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfff7ffff;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00100000) == 0x00100000)  /*Bit20: �1�7�1�7�1�7�1�7�0�8�0�0�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00100000;	
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffefffff;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00200000) == 0x00200000) /*Bit21: �1�7�1�7�1�7�1�7�0�8�0�0�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00200000;	    
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffdfffff;
			}
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00400000) == 0x00400000)  /*Bit22: �0�8�0�9�1�7�1�7�1�7�0�8�0�0�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x00400000;	
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xffbfffff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00800000) == 0x00800000)  /*Bit23:�0�8�0�9�1�7�0�0�1�7�0�8�0�0�1�7�4�4�1�7��*/
			{	
				Dev_Abnorm_Inf_Judgement |= 0x00800000;	 
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xff7fffff;	
			}		
			/********************************************************************************/		

			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x01000000) == 0x01000000)    /*Bit24: �1�7�1�7�0�1�1�7�0�4�1�7�0�8�0�0�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x01000000;		
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfeffffff;	
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x02000000) == 0x02000000)  /*Bit25�1�7�1�7�1�7�1�7�0�1�1�7�0�9�1�7�0�8�0�0�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x02000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfdffffff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x04000000) == 0x04000000)/*Bit26:�0�8�1�7�1�7�0�9�1�7�1�7�0�8�0�0�1�7�4�4�1�7�ӄ1�7�1�7�1�7�1�7���1�7�1�7�1�7�0�1 */
			{
				Dev_Abnorm_Inf_Judgement |= 0x04000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xfbffffff;
			}
						
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x08000000) == 0x08000000)/*Bit27: DVL�0�8�0�0�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x08000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xf7ffffff;
			}		
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x10000000) == 0x10000000)  /*Bit28�1�7�1�7�1�7�1�6�1�7�0�8�0�0�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x10000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xefffffff;
			}		
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x20000000) == 0x20000000) /*Bit29:�1�7�1�7�1�7�1�71�0�8�0�0�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x20000000;	  
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xdfffffff;
			}
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x40000000) == 0x40000000)  /*Bit30:�1�7�1�7�1�7�1�72�0�8�0�0�1�7�4�4�1�7��*/
			{
				Dev_Abnorm_Inf_Judgement |= 0x40000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0xbfffffff;
			}		
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x80000000) == 0x80000000)  /*Bit31:�0�0�1�7�1�7�0�0�1�7�1�7�1�7�1�7�0�6�1�7�4�4�1�7��*/
			{	
				Dev_Abnorm_Inf_Judgement |= 0x80000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Judgement &= 0x7fffffff;		
			}
					
			

			
			/*�1�7�1�7�1�7�1�7BMS_Prase_Data.BMS_Abnorm_Inf�0�8�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�8�0�0�1�7�؄1�7*/
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0:  �1�7�1�7�1�7�1�7�1�7�0�9�0�5�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000001;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffffe;	
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: �0�3�0�1�1�7�1�7�0�9�0�5�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000002;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffffd;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: �1�7�1�7�1�7�1�7�1�7�1�7�0�5�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000004;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffffb;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: �1�7�1�7�1�7�1�7�0�9�0�9�0�5�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000008;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffff7;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: �0�3�0�1�0�9�0�9�0�5�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000010;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffffef;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: �1�7�0�7�1�7�1�7�1�7�1�7�0�5�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000020;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffffdf;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: �1�7�1�7�1�7�1�7�0�9�0�4�1�7�1�7�1�7�0�5�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000040;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffffbf;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: �1�7�1�7�1�7�1�7�0�9�0�4�1�7�1�7�1�7�0�5�1�7�1�7�1�7�1�7�1�7�1�7*/
			{	
				BMS_Abnorm_Inf_Judgement |= 0x00000080;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffff7f;
			}
				
		/*****************************************************************************/	
			
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: SOC�1�7�1�7�1�7�1�7�0�5�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000100;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffeff;	
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0200) == 0x0200)  /*Bit9�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7��*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000200;
				Emergency_Level3();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffdff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0400) == 0x0400)/*Bit10: �1�7�1�7�1�7�1�7�1�7�0�9�0�4�1�7�1�7�1�7�0�5�1�7�1�7�1�7��*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000400;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffffbff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11: �1�7�1�7�1�7�1�7�1�7�0�9�0�4�1�7�1�7�1�7�0�5�1�7�1�7�1�7��*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00000800;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffff7ff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�9�0�4�1�7�1�7�1�7�0�5�1�7�1�7�1�7��*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00001000;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffefff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: �1�7�0�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�ӄ1�7�1�7�1�7�1�7���1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00002000;
				Emergency_Level3();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffdfff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:�1�7�0�7�1�7�1�7�0�9�0�4�1�7�1�7�1�7�0�5�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00004000;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffffbfff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:�1�7�0�7�1�7�1�7�0�9�0�4�1�7�1�7�1�7�0�5�1�7�1�7�1�7�1�7�1�7�1�7*/
			{	
				BMS_Abnorm_Inf_Judgement |= 0x00008000;
				Emergency_Level1();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffff7fff;
			}
				
				
			/********************************************************************************/		
			
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: �1�7�1�7�1�7�1�7�1�7�0�9�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00010000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffeffff;	
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: �0�3�0�1�1�7�1�7�0�9�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00020000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffdffff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00040000) == 0x00040000)/*bit18: �1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00040000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfffbffff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00080000) == 0x00080000)/*bit19: �1�7�1�7�1�7�1�7�0�9�0�9�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00080000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfff7ffff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00100000) == 0x00100000)  /*Bit20: �0�3�0�1�0�9�0�9�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00100000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffefffff;	
			}
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00200000) == 0x00200000) /*Bit21: �1�7�0�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00200000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffdfffff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00400000) == 0x00400000)  /*Bit22: �1�7�1�7�1�7�1�7�0�9�0�4�1�7�1�7�1�2�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x00400000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xffbfffff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00800000) == 0x00800000)  /*Bit23: �1�7�1�7�1�7�1�7�0�9�0�4�1�7�1�7�0�4�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{	
				BMS_Abnorm_Inf_Judgement |= 0x00800000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xff7fffff;	
			}
				
			/********************************************************************************/		

			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x01000000) == 0x01000000)    /*Bit24: SOC�1�7�1�7�1�7�0�4�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x01000000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfeffffff;	
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x02000000) == 0x02000000)  /*Bit25�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7��*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x02000000;
				Emergency_Level3();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfdffffff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x04000000) == 0x04000000)/*Bit26: �1�7�1�7�1�7�1�7�1�7�0�9�0�4�1�7�1�7�1�2�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x04000000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xfbffffff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x08000000) == 0x08000000)/*Bit27: �1�7�1�7�1�7�1�7�1�7�0�9�0�4�1�7�1�7�1�2�1�7�1�7�1�7�1�7��*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x08000000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xf7ffffff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x10000000) == 0x10000000)  /*Bit28�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�9�0�4�1�7�1�7�0�4�1�7�1�7�1�7�1�7��*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x10000000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xefffffff;
			}
				
			
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x20000000) == 0x20000000) /*Bit29: �1�7�0�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7��*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x20000000;
				Emergency_Level3();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xdfffffff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x40000000) == 0x40000000)  /*Bit30:�1�7�0�7�1�7�1�7�0�9�0�4�1�7�1�7�1�2�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				BMS_Abnorm_Inf_Judgement |= 0x40000000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0xbfffffff;
			}
				
				
			if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x80000000) == 0x80000000)  /*Bit31:�1�7�0�7�1�7�1�7�0�9�0�4�1�7�1�7�0�4�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{	
				BMS_Abnorm_Inf_Judgement |= 0x80000000;
				Emergency_Level2();
			}
			else
			{
				BMS_Abnorm_Inf_Judgement &= 0x7fffffff;		
			}
								
			
			
			/*�1�7�1�7�1�7�1�7Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail*/
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0001) == 0x0001)    /*bit0: �0�8�0�9�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000001;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffffe;	
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0002) == 0x0002)  /*bit1: �0�8�0�9�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000002;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffffd;
			}
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0004) == 0x0004)/*bit2: �0�8�0�9�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000004;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffffb;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0008) == 0x0008)/*bit3: �0�8�0�9�1�7�1�7�1�7�1�7�1�7�1�7�0�8�0�9�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000008;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffff7;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0010) == 0x0010)  /*Bit4: �0�8�0�9�1�7�1�7�1�7�1�7�1�7�1�7�1�7�0�9�0�9�0�9*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000010;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffffef;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0020) == 0x0020) /*Bit5: �1�7�1�7�0�8�0�9�1�7�0�0�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000020;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffffdf;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0040) == 0x0040)  /*Bit6: �0�8�0�9�1�7�0�0�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000040;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffffbf;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0080) == 0x0080)  /*Bit7: �0�8�0�9�1�7�0�0�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{	
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000080;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffff7f;
			}
				
		/*****************************************************************************/	
			
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0100) == 0x0100)    /*Bit8: �0�8�0�9�1�7�0�0�1�7�1�7�1�7�1�7�0�8�0�9�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000100;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffeff;	
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0200) == 0x0200)  /*Bit9�1�7�1�7�0�8�0�9�1�7�0�0�1�7�1�7�1�7�1�7�1�7�0�9�0�9�0�9*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000200;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffdff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0400) == 0x0400)/*Bit10: �1�7�1�7�0�1�1�7�0�4�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000400;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffbff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0800) == 0x0800)/*Bit11: �1�7�1�7�0�1�1�7�0�4�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00000800;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffff7ff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x1000) == 0x1000)  /*Bit12�1�7�1�7�1�7�1�7�0�1�1�7�0�4�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00001000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffefff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x2000) == 0x2000) /*Bit13: �1�7�1�7�0�1�1�7�0�4�1�7�1�7�1�7�1�7�0�8�0�9�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00002000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffdfff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x4000) == 0x4000)  /*Bit14:�1�7�1�7�0�1�1�7�0�4�1�7�1�7�1�7�1�7�1�7�0�9�0�9�0�9*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00004000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffffbfff;
			}		
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x8000) == 0x8000)  /*Bit15: �1�7�1�7�0�1�1�7�0�9�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{	
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00008000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffff7fff;
			}
				
				
			/********************************************************************************/		
			
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00010000) == 0x00010000)    /*bit16: �1�7�1�7�0�1�1�7�0�9�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00010000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffeffff;
			}
					
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00020000) == 0x00020000)  /*bit17: �1�7�1�7�0�1�1�7�0�9�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00020000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffdffff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00040000) == 0x00040000)/*bit18: �1�7�1�7�0�1�1�7�0�9�1�7�1�7�1�7�1�7�0�8�0�9�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00040000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfffbffff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00080000) == 0x00080000)/*bit19: �1�7�1�7�0�1�1�7�0�9�1�7�1�7�1�7�1�7�1�7�0�9�0�9�0�9*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00080000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfff7ffff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00100000) == 0x00100000)  /*Bit20: �1�7�1�7�1�7�0�2�1�7�0�8�0�5�0�9*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00100000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffefffff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00200000) == 0x00200000) /*Bit21:�1�7�1�7�1�7�0�8�1�7�1�7�1�7�1�7�1�7 */
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00200000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffdfffff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00400000) == 0x00400000)  /*Bit22: �1�7�1�7�1�7�0�7�1�7�1�7�1�7�1�7�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00400000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xffbfffff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00800000) == 0x00800000)  /*Bit23: �1�7�1�7���1�7�1�7�1�7�1�7*/
			{	
				Dev_Abnorm_Inf_Detail_Judgement |= 0x00800000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xff7fffff;	
			}
				
			/********************************************************************************/		

			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x01000000) == 0x01000000)    /*Bit24: �1�7�1�7���1�7�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x01000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfeffffff;	
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x02000000) == 0x02000000)  /*Bit25�1�7�1�7�1�7�1�7���1�7�1�7�1�7�1�7*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x02000000;
				Emergency_Level1();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfdffffff;
			}
				
			
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x04000000) == 0x04000000)/*Bit26: DVL�1�7�0�4�1�7�1�7�4�4*/
			{
				Dev_Abnorm_Inf_Detail_Judgement |= 0x04000000;
				Emergency_Level3();
			}
			else
			{
				Dev_Abnorm_Inf_Detail_Judgement &= 0xfbffffff;
			}
				
				
			if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x08000000) == 0x08000000)/*Bit27:DVL�1�7�0�7�1�7�1�7�1�7�� */
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
	UI_WIFI_Instruction.FromUI12_Motor_Speed1 = 0;/*�1�7�1�7�1�7�1�7�0�5�1�7�1�7*/
	
	/*EL_Power_Control(Power_ON);�0�8�1�7�1�7�0�9�1�7�1�7�1�7�0�3�1�7*/
	
	/*	Remote_Assignment(&Instruction_To_FMCU);*/
}

/**
 * @brief ��׸߶�Ӳդ����ȫ�ٲ� + DVL�����Ծ� (BUG-5, BUG-6)
 * 
 * 10Hz������EmergencyTask, ʵ��˫�㱣��:
 * - ����(3.0m): Ԥ�� + ����Ŀ����Ȳ���������
 * - Ӳ��(1.8m): ǿ�ƶ�Ȩ, ����HightCtrlAlgorithm������4m
 * - DVL����2.0s: ģʽ���� + �����ϸ���2m
 * 
 * @note ˮ��ģʽ(POOL_TEST_MODE=1)�²����Զ�����Ϊ soft=0.8m, hard=0.4m
 */
/**
 * @brief ˮ�ز��԰�ȫģʽ (BUG-7)
 * 
 * ���� POOL_TEST_MODE=1 ʱ���뼤��.
 * ��ά�Ƚ�����: ���/����/��ҡ/ת��
 */
#if POOL_TEST_MODE
void Pool_Safety_Check(void)
{
	/* 1. ���ӲΧ��: ˮ��1.5m, AUV��Ȳ�����0.9m */
	if(Current_State.Current_Dep > 0.9f)
	{
		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 0;
		Instruction_To_FMCU.McuFD_Motor2_Set_Speed = 0;
		/* �����ϸ��� */
		Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location + 20.0f * 4096/360);
		Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location - 20.0f * 4096/360);
		Emergency_Remote_Assignment(&Instruction_To_FMCU);
		Sys_Abnorm_Inf_Judgement |= 0x00008000;  /* Bit15: ˮ����ȳ��� */
		return;
	}
	
	/* 2. ��ҡ(Pitch)���޽ض�: ���޿ռ����Ͻ���Ƕ�̧ͷ/��ͷ */
	if(Current_State.Current_IMU_Pitch > 10.0f || Current_State.Current_IMU_Pitch < -10.0f)
	{
		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 0;
		Instruction_To_FMCU.McuFD_Motor2_Set_Speed = 0;
		Emergency_Remote_Assignment(&Instruction_To_FMCU);
		Sys_Abnorm_Inf_Judgement |= 0x00010000;  /* Bit16: ˮ��Pitch���� */
		return;
	}
	
	/* 3. ��ҡ(Roll)��ת����: ��ֹ��������Ť�ص���Ǳ���㸲 */
	if(Current_State.Current_IMU_Roll > 20.0f || Current_State.Current_IMU_Roll < -20.0f)
	{
		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 0;
		Instruction_To_FMCU.McuFD_Motor2_Set_Speed = 0;
		Emergency_Remote_Assignment(&Instruction_To_FMCU);
		Sys_Abnorm_Inf_Judgement |= 0x00020000;  /* Bit17: ˮ��Roll���� */
		return;
	}
	
	/* 4. ˮ�ؼ����޷�: ת���Ͻ�����200 RPM (��ײǽ) */
	if(Instruction_To_FMCU.McuFD_Motor1_Set_Speed > 200)
	{
		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 200;
	}
	if(Instruction_To_FMCU.McuFD_Motor2_Set_Speed > 200)
	{
		Instruction_To_FMCU.McuFD_Motor2_Set_Speed = 200;
	}
	
	/* ˮ��ģʽ��Ҳ���и߶��ٲ� (�������Զ�����Ϊ0.4m/0.8m) */
	Seafloor_Grounding_Arbitration();
}
#endif

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
	
	/*===========================================================
	 * 1. DVL ����״̬��� + �����Ծ� (BUG-6)
	 *===========================================================*/
	if(dvl_status != 2.00f && dvl_status != 3.00f)
	{
		/* DVL δ���� */
		dvl_lost_lock_count++;
		altitude_critical_count = 0;
		altitude_warning_count = 0;
		Sys_Abnorm_Inf_Judgement &= ~0x00000800;
		Sys_Abnorm_Inf_Judgement &= ~0x00001000;
		
		/* DVL �������� 2.0s, �Ҵ��� Jetson ����ģʽ -> �Ծ� */
		if(dvl_lost_lock_count >= 20)
		{
			if(Current_State.Current_Mode == Jetson_Shadow || Current_State.Current_Mode == Jetson_Hybrid)
			{
				float safe_up_rudder;
				
				/* ģʽ������ Remote */
				UI_WIFI_Instruction.FromUI12_Ctrl_Mode = 0x01;
				Sys_Abnorm_Inf_Judgement |= 0x00002000;  /* Bit13: DVL���׽����澯 */
				
				/* �����ϸ��� 2.0m ��ȫ�� */
				safe_up_rudder = DepthCtrlAlgorithm(
					2.0f,
					Current_State.Current_Dep,
					Current_State.Current_IMU_Pitch,
					IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1],
					Current_State.Current_DVL_Velocity_Kn
				);
				
				/* NaN ���� */
				if(safe_up_rudder != safe_up_rudder) safe_up_rudder = -20.0f;
				if(safe_up_rudder < -20.0f) safe_up_rudder = -20.0f;
				if(safe_up_rudder >  20.0f) safe_up_rudder =  20.0f;
				
				Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location - safe_up_rudder * 4096/360);
				Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location + safe_up_rudder * 4096/360);
				Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 300;
				Emergency_Remote_Assignment(&Instruction_To_FMCU);
			}
		}
		return;
	}
	else
	{
		dvl_lost_lock_count = 0;
		Sys_Abnorm_Inf_Judgement &= ~0x00002000;
	}
	
	/*===========================================================
	 * 2. �������ڷ��� (���� DVL ����/����ٷ�������)
	 *===========================================================*/
	if(current_altitude < hard_limit_altitude)
	{
		altitude_critical_count++;
	}
	else
	{
		if(altitude_critical_count > 0) altitude_critical_count--;
	}
	
	if(current_altitude < soft_limit_altitude)
	{
		altitude_warning_count++;
	}
	else
	{
		if(altitude_warning_count > 0) altitude_warning_count--;
	}
	
	/*===========================================================
	 * 3. �ٲ���ִ��
	 *===========================================================*/
	
	/* ����1: ����Ԥ�� (����0.5s����soft_limit) */
	if(altitude_warning_count >= 5)
	{
		Sys_Abnorm_Inf_Judgement |= 0x00000800;  /* ��׳��ޱ�������1�澯 */
		
		/* ����Ŀ�����: ������ Jetson ������Ǳ */
		if(Current_State.Current_Mode == Jetson_Shadow || Current_State.Current_Mode == Jetson_Hybrid)
		{
			float target_depth_m = (float)UI_WIFI_Instruction.FromUI12_Para1 / 1000.0f;
			if(target_depth_m > Current_State.Current_Dep)
			{
				UI_WIFI_Instruction.FromUI12_Para1 = (int)(Current_State.Current_Dep * 1000.0f);
			}
		}
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= ~0x00000800;
	}
	
	/* ����2: Ӳ��Σ�� (����0.3s����hard_limit) - ������ײ */
	if(altitude_critical_count >= 3)
	{
		float pull_up_rudder;
		
		Sys_Abnorm_Inf_Judgement |= 0x00001000;  /* ��׳��ޱ�������2�澯 */
		
		/* ǿ�ƶ�Ȩ: ���� HightCtrlAlgorithm ���� */
		pull_up_rudder = HightCtrlAlgorithm(
			pull_up_target,
			current_altitude,
			Current_State.Current_IMU_Pitch,
			IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1],
			Current_State.Current_DVL_Velocity_Kn
		);
		
		/* NaN ���� + �޷� */
		if(pull_up_rudder != pull_up_rudder) pull_up_rudder = -20.0f;
		if(pull_up_rudder < -20.0f) pull_up_rudder = -20.0f;
		if(pull_up_rudder >  20.0f) pull_up_rudder =  20.0f;
		
		/* ��������, ά�ֶ�Ч */
		Instruction_To_FMCU.McuFD_Motor1_Set_Speed = 350;
		
		/* �ϸ������ */
		Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location - pull_up_rudder * 4096/360);
		Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location + pull_up_rudder * 4096/360);
		
		/* ����Ӱ��ģʽ����, ֱ�ӷ��� MCU */
		Emergency_Remote_Assignment(&Instruction_To_FMCU);
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= ~0x00001000;
	}
}

