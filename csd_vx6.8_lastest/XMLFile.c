#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "main.h"
#include "XMLFile.h"
#include "AgreedTerms.h"
#include "DataProcess.h"
#include <time.h>


#include <sysLib.h>

#include "CtrlAlgorithm.h"

#include "SecurityEmergencyManage.h"

#include <math.h>

void unpack_FixedPoint_XML(_XMLData *temp);
void unpack_FixedDirection_XML(_XMLData *temp);

void Auto_FixedPoint_Assignment(_FixedPoint_PathPlanning *temp);
void Auto_FixedDirection_Assignment(_FixedDirection_PathPlanning *temp);

void diving_proc(void);
void floating_proc(void);

void FixedDirection_diving_proc(void);
void FixedDirection_floating_proc(void);

_XMLData XMLData;

_FixedPoint_PathPlanning FixedPoint_PathPlanning;
_FixedDirection_PathPlanning FixedDirection_PathPlanning;

bool diving_flag = false; /*下潜开始标志位*/
bool floating_flag = false; /*上浮开始标志位*/

bool FixedDirection_diving_flag = false; /*定向下潜开始标志位*/
bool FixedDirection_floating_flag = false; /*定向上浮开始标志位*/


void unpack_FixedDirection_XML(_XMLData *temp)
{

	u16 ii = 0, jj = 0;

	FixedDirection_PathPlanning.TaskNumber = NULL;
	FixedDirection_PathPlanning.TotalTimeOut = 0;
	FixedDirection_PathPlanning.TotalNumber=0;
	
	for(jj = 0; jj < 1024; jj++)
	{
		if((NULL == FixedDirection_PathPlanning.TaskNumber) || (0 == FixedDirection_PathPlanning.TotalTimeOut) || (0 == FixedDirection_PathPlanning.TotalNumber))
		{
			if(((*temp).attribute_name[jj] != NULL) && ((*temp).attribute_value[jj] != NULL))
			{
				if(strncmp((*temp).attribute_name[jj], "TaskNumber", strlen("TaskNumber")) == 0)
				{
					FixedDirection_PathPlanning.TaskNumber = (*temp).attribute_value[jj]; 
					printf("TaskNumber:%s\n", FixedDirection_PathPlanning.TaskNumber);
					continue;
				}
				
				else if(strncmp((*temp).attribute_name[jj], "TotalTimeout", strlen("TotalTimeout")) == 0)
				{
					FixedDirection_PathPlanning.TotalTimeOut = atoi((*temp).attribute_value[jj]);
					printf("TotalTimeOut:%d\n", FixedDirection_PathPlanning.TotalTimeOut);
					continue;
				}
				
				if(strncmp((*temp).attribute_name[jj], "TotalNumber", strlen("TotalNumber")) == 0)
				{
					FixedDirection_PathPlanning.TotalNumber = atoi((*temp).attribute_value[jj]);
					printf("TotalNumber:%d\n", FixedDirection_PathPlanning.TotalNumber);
					continue;
				}
				
				else
				{
					break;
				}
			}
			else
			{
				break;
			}
		}
		else
		{
			break;
		}
	}
	
	for(jj = 0; jj < 1024; jj++)
	{		
		if(ii <= FixedDirection_PathPlanning.TotalNumber)
		{
			if((*temp).element_name[jj] != NULL)
			{
				printf("jj=%d element_name:%s\n", jj, (*temp).element_name[jj]);
				if(strncmp((*temp).element_name[jj], "TrackDirection", strlen("TrackDirection")) == 0)  
				{
					ii =  atoi((*temp).element_value[jj]);
					FixedDirection_PathPlanning.TrackDirection[ii] = ii;
					printf("TrackDirection:%d\n", FixedDirection_PathPlanning.TrackDirection[ii]);
					continue;
				}
				
				else if(strncmp((*temp).element_name[jj], "Course", strlen("Course")) == 0) 
				{
					FixedDirection_PathPlanning.Course[ii] = atof((*temp).element_value[jj]);
					printf("Course:%f\n", FixedDirection_PathPlanning.Course[ii]);
					continue;
				}
					
				else if(strncmp((*temp).element_name[jj], "Duration", strlen("Duration")) == 0)  
				{
					FixedDirection_PathPlanning.Duration[ii] = atof((*temp).element_value[jj]);
					printf("Duration:%f\n", FixedDirection_PathPlanning.Duration[ii]);
					continue;
				}
				
				else if(strncmp((*temp).element_name[jj], "Strategy", strlen("Strategy")) == 0)
				{
					FixedDirection_PathPlanning.Strategy[ii] = atoi((*temp).element_value[jj]);
					printf("Strategy:%d\n", FixedDirection_PathPlanning.Strategy[ii]);
					continue;
				}
				
				else if(strncmp((*temp).element_name[jj], "Parameter", strlen("Parameter")) == 0)
				{
					FixedDirection_PathPlanning.Parameter[ii] = atoi((*temp).element_value[jj]);
					printf("Parameter:%d\n", FixedDirection_PathPlanning.Parameter[ii]);
					continue;
				}
				
				else if(strncmp((*temp).element_name[jj], "MotorSetSpeed", strlen("MotorSetSpeed")) == 0) 
				{
					FixedDirection_PathPlanning.MotorSetSpeed[ii] = atoi((*temp).element_value[jj]);
					printf("MotorSetSpeed:%d\n", FixedDirection_PathPlanning.MotorSetSpeed[ii]);
					continue;
				}
				
				else if(strncmp((*temp).element_name[jj], "Device", strlen("Device")) == 0)  
				{
					FixedDirection_PathPlanning.Device[ii] = atoi((*temp).element_value[jj]);
					printf("Device:%d\n", FixedDirection_PathPlanning.Device[ii]);
					continue;
				}
				
				
				else
				{
					continue;
				}
			}
			else
			{
				break;
			}
		}
		else
		{
			break;
		}
	}
	
	for(ii = FixedDirection_PathPlanning.TotalNumber + 1; ii < 256; ii++)  /*剩余目标点未赋值，清0*/
	{
	
		FixedDirection_PathPlanning.Course[ii] = 0;
		FixedDirection_PathPlanning.Duration[ii] = 0;
		FixedDirection_PathPlanning.Strategy[ii] = 0;
		FixedDirection_PathPlanning.Parameter[ii] = 0;
		FixedDirection_PathPlanning.MotorSetSpeed[ii] = 0;
		FixedDirection_PathPlanning.Device[ii] = 0;                      
	}

}



void unpack_FixedPoint_XML(_XMLData *temp)
{
	u16 ii = 0, jj = 0;
	
	FixedPoint_PathPlanning.TaskNumber = NULL; /*指针在使用前必须先初始化*/
	FixedPoint_PathPlanning.TotalTimeOut = 0;
	FixedPoint_PathPlanning.TotalNumber=0;
	
	for(jj = 0; jj < 1024; jj++)
	{
		if((NULL == FixedPoint_PathPlanning.TaskNumber) || (0 == FixedPoint_PathPlanning.TotalTimeOut) || (0 == FixedPoint_PathPlanning.TotalNumber))
		{
			if(((*temp).attribute_name[jj] != NULL) && ((*temp).attribute_value[jj] != NULL))
			{
				if(strncmp((*temp).attribute_name[jj], "TaskNumber", strlen("TaskNumber")) == 0)
				{
					FixedPoint_PathPlanning.TaskNumber = (*temp).attribute_value[jj];   /*此处不能用memcpy，因为PathPlanning.task_coding为空指针，不指向任何地址*/
					printf("TaskNumber:%s\n", FixedPoint_PathPlanning.TaskNumber);
					continue;
				}
				
				else if(strncmp((*temp).attribute_name[jj], "TotalTimeout", strlen("TotalTimeout")) == 0)
				{
					FixedPoint_PathPlanning.TotalTimeOut = atoi((*temp).attribute_value[jj]);
					printf("TotalTimeOut:%d\n", FixedPoint_PathPlanning.TotalTimeOut);
					continue;
				}
				
				if(strncmp((*temp).attribute_name[jj], "TotalNumber", strlen("TotalNumber")) == 0)
				{
					FixedPoint_PathPlanning.TotalNumber = atoi((*temp).attribute_value[jj]);
					printf("TotalNumber:%d\n", FixedPoint_PathPlanning.TotalNumber);
					continue;
				}
				
				else
				{
					break;
				}
			}
			else
			{
				break;
			}
		}
		else
		{
			break;
		}
	}
	
	for(jj = 0; jj < 1024; jj++)
	{		
		if(ii <= FixedPoint_PathPlanning.TotalNumber)
		{
			if((*temp).element_name[jj] != NULL)
			{
				printf("jj=%d element_name:%s\n", jj, (*temp).element_name[jj]);
				if(strncmp((*temp).element_name[jj], "TrackPoint", strlen("TrackPoint")) == 0)  
				{
					ii =  atoi((*temp).element_value[jj]);
					FixedPoint_PathPlanning.TrackPoint[ii] = ii;
					printf("TrackPoint:%d\n", FixedPoint_PathPlanning.TrackPoint[ii]);
					continue;
				}
				
				else if(strncmp((*temp).element_name[jj], "Longitude", strlen("Longitude")) == 0) 
				{
					FixedPoint_PathPlanning.Longitude[ii] = atof((*temp).element_value[jj]);
					printf("Longitude:%3.6f\n", FixedPoint_PathPlanning.Longitude[ii]);
					continue;
				}
					
				else if(strncmp((*temp).element_name[jj], "Latitude", strlen("Latitude")) == 0)  
				{
					FixedPoint_PathPlanning.Latitude[ii] = atof((*temp).element_value[jj]);
					printf("Latitude:%2.6f\n", FixedPoint_PathPlanning.Latitude[ii]);
					continue;
				}
				
				else if(strncmp((*temp).element_name[jj], "Strategy", strlen("Strategy")) == 0)
				{
					FixedPoint_PathPlanning.Strategy[ii] = atoi((*temp).element_value[jj]);
					printf("Strategy:%d\n", FixedPoint_PathPlanning.Strategy[ii]);
					continue;
				}
				
				else if(strncmp((*temp).element_name[jj], "Parameter", strlen("Parameter")) == 0)
				{
					FixedPoint_PathPlanning.Parameter[ii] = atoi((*temp).element_value[jj]);
					printf("Parameter:%d\n", FixedPoint_PathPlanning.Parameter[ii]);
					continue;
				}
				
				else if(strncmp((*temp).element_name[jj], "MotorSetSpeed", strlen("MotorSetSpeed")) == 0) 
				{
					FixedPoint_PathPlanning.MotorSetSpeed[ii] = atoi((*temp).element_value[jj]);
					printf("MotorSetSpeed:%d\n", FixedPoint_PathPlanning.MotorSetSpeed[ii]);
					continue;
				}
				
				else if(strncmp((*temp).element_name[jj], "Device", strlen("Device")) == 0)  
				{
					FixedPoint_PathPlanning.Device[ii] = atoi((*temp).element_value[jj]);
					printf("Device:%d\n", FixedPoint_PathPlanning.Device[ii]);
					continue;
				}
				
				
				else
				{
					continue;
				}
			}
			else
			{
				break;
			}
		}
		else
		{
			break;
		}
	}
	
	for(ii = FixedPoint_PathPlanning.TotalNumber + 1; ii < 256; ii++)  /*剩余目标点未赋值，清0*/
	{	
		FixedPoint_PathPlanning.Longitude[ii] = 0;
		FixedPoint_PathPlanning.Latitude[ii] = 0;
		FixedPoint_PathPlanning.Strategy[ii] = 0;
		FixedPoint_PathPlanning.Parameter[ii] = 0;
		FixedPoint_PathPlanning.MotorSetSpeed[ii] = 0;
		FixedPoint_PathPlanning.Device[ii] = 0;                      
	}
}

void Auto_FixedPoint_Assignment(_FixedPoint_PathPlanning *temp)
{
	
	static u8 ii = 0;  /*这个static作用就是保证了加1了，下次再次执行的时候也不会重置为0*/
	static unsigned long AutoTime_t_s = 0;
	
	if((time(NULL) - AutoTime_t_s) <= temp->TotalTimeOut)	
	{
		if(ii< (temp->TotalNumber))
		{	
			
			if(temp->MotorSetSpeed[ii+1])			
			{
				Instruction_To_FMCU.McuFD_Motor1_Set_Speed=temp->MotorSetSpeed[ii+1];	
				Instruction_To_FMCU.McuFD_Motor2_Set_Speed=temp->MotorSetSpeed[ii+1];		
				
				
			}
			ii++;
		}
		else
		{
			
				
		}
		
	}
	else
	{
		
	}
	
	
}

void Auto_FixedDirection_Assignment(_FixedDirection_PathPlanning *temp)
{
	static u8 FixedDirection_ii = 0;  /*这个static作用就是保证了加1了，下次再次执行的时候也不会重置为0*/
	
	static u8 FixedDirection_jj = 0;  /*循环次数*/
	
	static char FixedDirection_auto_mode_step = 0;
	
	static unsigned long FixedDirection_AutoTime_t_s = 0;
	
	static float FixedDirection_floating_couse_target = 0.0;
	
	static float FixedDirection_temp_course_angle = 0.0;
	
	static bool FixedDirection_diving_suceess_flag=false;

	if(Auto_Task_Carry_Flag == false)/*自主航行取消的时候，将局部变量初始化*/
	{
		FixedDirection_ii = 0;
		FixedDirection_jj = 0;
		FixedDirection_auto_mode_step = 0;
		FixedDirection_AutoTime_t_s = 0;
		FixedDirection_floating_couse_target = 0.0;
		FixedDirection_diving_suceess_flag=false;
	}	
	
	if( FixedDirection_auto_mode_step == 0)    /*下潜阶段*/
	{
		FixedDirection_AutoTime_t_s = 0;
		FixedDirection_ii = 0;   
		FixedDirection_AutoTime_t_s = time(NULL);
		FixedDirection_auto_mode_step = 1; 		
		
	}
	
	
 if(1 == FixedDirection_auto_mode_step)  /*巡航阶段*/
 {	
	
	if((time(NULL) - FixedDirection_AutoTime_t_s) <= temp->TotalTimeOut)	
	{
		if(FixedDirection_ii< (temp->TotalNumber))
		{	
			/*根据xml中的Course方向控制上下垂直舵机*/
			Instruction_To_FMCU.McuFD_UV_Set_Rud_Location = (u16)(UV_Ref_Location - (Course_Keep_Algorithm(temp->Course[FixedDirection_ii+1], IMU_Prase_Data.Roll_Pitch_Yaw[2], IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[2])) * 4096/360);		
			Instruction_To_FMCU.McuFD_LV_Set_Rud_Location = (u16)(LV_Ref_Location - (Course_Keep_Algorithm(temp->Course[FixedDirection_ii+1], IMU_Prase_Data.Roll_Pitch_Yaw[2], IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[2])) * 4096/360);
			Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);/*打包下发命令*/
			
			FixedDirection_floating_couse_target = IMU_Prase_Data.Roll_Pitch_Yaw[2];
			
			/*主推转速控制*/
			if(temp->MotorSetSpeed[FixedDirection_ii+1])			
			{
				Instruction_To_FMCU.McuFD_Motor1_Set_Speed=temp->MotorSetSpeed[FixedDirection_ii+1];	
				Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
			}
			
			
			/*计算AUV偏转角度*/
			if(IMU_Prase_Data.Roll_Pitch_Yaw[2] > 180)   
			{
				FixedDirection_temp_course_angle += (360 - IMU_Prase_Data.Roll_Pitch_Yaw[2]);
			}
			else
			{
				FixedDirection_temp_course_angle += (-IMU_Prase_Data.Roll_Pitch_Yaw[2]);
			}
			 /*AUV转圈,则抛弃这一点，防止由于外部环境时钟无法到达目标点而不断绕着它转圈
			if(FixedDirection_temp_course_angle >= 720.0)                      
			{
				FixedDirection_temp_course_angle = 0.0;
				ii++;
			}*/
			
			
			
			
			/*如果控制策略是0：深度控制*/
			if(temp->Strategy[FixedDirection_ii+1] == 0)
			{
				if(temp->Parameter[FixedDirection_ii+1] > 0)  /*0:深度参数*/
				{
					/*根据深度控制算法，控制左右水平舵机*/
					Instruction_To_FMCU.McuFD_LH_Set_Rud_Location=
					(u16)(2050-	(DepthCtrlAlgorithm(temp->Parameter[FixedDirection_ii+1], Data_From_FMCU.McuFU_Dep, IMU_Prase_Data.Roll_Pitch_Yaw[1], IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1], DVL_Prase_Data.BI_X))*4096/360);
					
					
					Instruction_To_FMCU.McuFD_RH_Set_Rud_Location=
					(u16)(2040-	(DepthCtrlAlgorithm(temp->Parameter[FixedDirection_ii+1], Data_From_FMCU.McuFU_Dep, IMU_Prase_Data.Roll_Pitch_Yaw[1], IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1], DVL_Prase_Data.BI_X))*4096/360);
					
					Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
					
					if(FixedDirection_diving_suceess_flag==false)
					{	
						if(fabs(temp->Parameter[FixedDirection_ii+1] - Data_From_FMCU.McuFU_Dep)>2.0)/**/
						{
							FixedDirection_diving_proc();  
						}
						else
						{	
							FixedDirection_diving_suceess_flag=true;
						}	
					}
					
					
				}
				
				if(temp->Parameter[FixedDirection_ii+1] == 0)
				{
					if(Data_From_FMCU.McuFU_Dep<1.5)/*深度小于1.5m*/
					{
						Instruction_To_FMCU.McuFD_LH_Set_Rud_Location=2050 - ((-15)*(4096/360));/*打舵-15°*/
						Instruction_To_FMCU.McuFD_RH_Set_Rud_Location=2050 - ((-15)*(4096/360));
						
						Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
					}
				}
				
				
				
				 /*跑点判断与定深精度*/
			     if((fabs(FollowLane_CtrlPara.Temp_s) <= RunningPointAccuracy) && (fabs(DVL_Prase_Data.BD_Height - temp->Parameter[FixedDirection_ii+1]) < 1.0))
			     {
			    	 FixedDirection_temp_course_angle = 0.0;
			    	 FixedDirection_ii++;
				
			     }
				
			}
	
			
			/*如果控制策略是1：离地高度控制*/
			if(temp->Strategy[FixedDirection_ii+1] == 1)
			{
				if(temp->Parameter[FixedDirection_ii+1] > 0)  /*0:离地高度参数*/
				{
					/*根据离地高度控制算法，控制左右水平舵机*/
					Instruction_To_FMCU.McuFD_LH_Set_Rud_Location=
					(u16)(2050-	(HightCtrlAlgorithm(temp->Parameter[FixedDirection_ii+1], DVL_Prase_Data.BD_Height, IMU_Prase_Data.Roll_Pitch_Yaw[1], IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1], DVL_Prase_Data.BI_X))*4096/360);
					
					Instruction_To_FMCU.McuFD_RH_Set_Rud_Location=
					(u16)(2040-	(HightCtrlAlgorithm(temp->Parameter[FixedDirection_ii+1], DVL_Prase_Data.BD_Height, IMU_Prase_Data.Roll_Pitch_Yaw[1], IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1], DVL_Prase_Data.BI_X))*4096/360);
					
					Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
				}
				
				if(temp->Parameter[FixedDirection_ii+1] == 0)
				{
					if(Data_From_FMCU.McuFU_Dep<1.5)/*深度小于1.5m*/
					{
						Instruction_To_FMCU.McuFD_LH_Set_Rud_Location=2050 - ((-15)*(4096/360));/*打舵-15°*/
						Instruction_To_FMCU.McuFD_RH_Set_Rud_Location=2050 - ((-15)*(4096/360));
						
						Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
					}
				}
				
				 /*判断定深精度*/
			     if((fabs(DVL_Prase_Data.BD_Height - temp->Parameter[FixedDirection_ii+1]) < 1.0))
			     {
			    	 FixedDirection_temp_course_angle = 0.0;
			    	 FixedDirection_ii++;
				
			     }
				
			
			}
		}
		else
		{
			if(FixedDirection_jj>0)   
			{
				/*循环超过 次，自主结束，成功*/
				FixedDirection_auto_mode_step = 2;
				Sail_State_Judgement |= 0x00000001;
				Sail_State_Judgement |= 0x00000010;  /*自主成功标志位*/
			}
			else
			{
				FixedDirection_jj++;
				FixedDirection_ii=0;
				FixedDirection_auto_mode_step=0;
			}			
				
		}
		
	}
	else
	{
		FixedDirection_auto_mode_step = 2;
	}
 }	

	if( FixedDirection_auto_mode_step == 2)  /*上浮阶段*/
	{ 
		if(Data_From_FMCU.McuFU_Dep > 2.0) /*以目标深度为0航行至水面*/
		{
			/*湖试专用*/
			FixedDirection_floating_proc();
			
			/*海试专用*/
			/*FixedDirection_floating_flag=true;*/
			/*DepthCtrlAlgorithm(0.0, Data_From_FMCU.McuFU_Dep, IMU_Prase_Data.Roll_Pitch_Yaw[1], IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1], DVL_Prase_Data.BI_X);*/
			/*Course_Keep_Algorithm(floating_couse_target, Current_State.Current_IMU_Heading, IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[2]);*/
			/*此处海试情况下课考虑重新回到起始点上浮*/
		}
		else
		{
			FixedDirection_auto_mode_step = 0;
			FixedDirection_AutoTime_t_s = 0;
			FixedDirection_ii = 0;        /*初始化变量*/
			/*FixedDirection_floating_flag=false;*/
			FixedDirection_diving_suceess_flag=false;
			FixedDirection_floating_proc();
			Current_State.Current_Mode = 0x01;/*切回遥控模式*/
			
		}
	}
 
	/*有故障退出巡航*/
	if(Sys_Abnorm_Inf_Judgement|Dev_Abnorm_Inf_Judgement|BMS_Abnorm_Inf_Judgement|Dev_Abnorm_Inf_Detail_Judgement)
	{
	   
		FixedDirection_ii=0;          
		FixedDirection_jj=0;
		FixedDirection_auto_mode_step=2;
		FixedDirection_diving_flag=false;
		FixedDirection_diving_suceess_flag=false;
	   Instruction_To_FMCU.McuFD_UV_Set_Rud_Location=2030;/*回归中位*/
	   Instruction_To_FMCU.McuFD_LV_Set_Rud_Location=2020;
	   Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
	}
	
	Auto_Task_Carry_Flag=false;          /*取消自主置零,等待下一次自主命令*/
	
		
	/*static u8 ii = 0;  这个static作用就是保证了加1了，下次再次执行的时候也不会重置为0
	static unsigned long AutoTime_t_s = 0;
	
	if((time(NULL) - AutoTime_t_s) <= temp->TotalTimeOut)	
	{
		if(ii< (temp->TotalNumber))
		{	
			
			if(temp->MotorSetSpeed[ii+1])			
			{
				printf("dgsdgfdhgfjhfjdhgbfbvdcfvxd");
				Instruction_To_FMCU.McuFD_Motor1_Set_Speed=temp->MotorSetSpeed[ii+1];	
				Instruction_To_FMCU.McuFD_Motor2_Set_Speed=temp->MotorSetSpeed[ii+1];	
				
				Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
			}
			ii++;
		}
		else
		{
			
				
		}
		
	}
	else
	{
		
	}	*/
	
}


void diving_proc(void)  /*AUV下潜到2m位置时的运动控制*/
{

	if(Data_From_FMCU.McuFU_Dep<1.5)
	{	
		diving_flag=true;
		
		if(DVL_Prase_Data.BI_X>2)
		{	
			Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = 2050 - (15*(4096/360));/*打舵15°*/
			Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = 2040 - (15*(4096/360));/*打舵15°*/ 
			Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
		}
		else
		{
			Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = 2050 - ((-10)*(4096/360));/*打舵-10°*/
			Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = 2040 - ((-10)*(4096/360));/*打舵-10°*/  
			Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
		}
		
	}
	else
	{
		diving_flag=false;
	}
	
	if(IMU_Prase_Data.Roll_Pitch_Yaw[1]<=-15.0)
	{
		Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = 2050 - (0*(4096/360));
		Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = 2040 - (0*(4096/360));  /*俯仰角过大时，打上浮舵0*/
		Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
	    if(IMU_Prase_Data.Roll_Pitch_Yaw[1]<=-20.0)
	    {
			Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = 2050 - ((-20)*(4096/360));
			Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = 2040 - ((-20)*(4096/360));/*俯仰角过大时，打上浮舵15度*/
			Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
	    }
	}
		
	
}

void FixedDirection_diving_proc(void)  /*定向 AUV下潜到2m位置时的运动控制*/
{

	if(Data_From_FMCU.McuFU_Dep<1.5)
	{	
		FixedDirection_diving_flag=true;
		
		if(DVL_Prase_Data.BI_X>2)
		{	
			Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = 2050 - (15*(4096/360));/*打舵15°*/
			Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = 2040 - (15*(4096/360));/*打舵15°*/ 
			Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
		}
		else
		{
			Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = 2050 - ((-10)*(4096/360));/*打舵-10°*/
			Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = 2040 - ((-10)*(4096/360));/*打舵-10°*/  
			Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
		}
		
	}
	else
	{
		FixedDirection_diving_flag=false;
	}
	
	if(IMU_Prase_Data.Roll_Pitch_Yaw[1]<=-15.0)
	{
		Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = 2050 - (0*(4096/360));
		Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = 2040 - (0*(4096/360));  /*俯仰角过大时，打上浮舵0*/
		Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
	    if(IMU_Prase_Data.Roll_Pitch_Yaw[1]<=-20.0)
	    {
			Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = 2050 - ((-20)*(4096/360));
			Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = 2040 - ((-20)*(4096/360));/*俯仰角过大时，打上浮舵15度*/
			Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
	    }
	}
		
	
}


void floating_proc(void)  /*AUV上浮到到2m位置后的运动控制*/
{
	/*AnswerDataToPropelModule.motor_set_speed = 0;*/
	/*AnswerDataToPropelModule.motor_set_speed = Motorspeed_Ctrl(0,GetDataFromPropelModule.motor_readback_speed);*/
	Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = 2050 - (30*(4096/360));
	Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = 2040 - (30*(4096/360));;  /*上浮舵30°上浮，待定*/
	Instruction_To_FMCU.McuFD_UV_Set_Rud_Location = 2030;
	Instruction_To_FMCU.McuFD_LV_Set_Rud_Location = 2020;   /*垂直舵归中位*/
	
	Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
	Current_State.Current_Mode = 0x01;/**/  /*切回遥控模式*/
}

void FixedDirection_floating_proc(void)  /*定向 AUV上浮到到2m位置后的运动控制*/
{
	/*AnswerDataToPropelModule.motor_set_speed = 0;*/
	/*AnswerDataToPropelModule.motor_set_speed = Motorspeed_Ctrl(0,GetDataFromPropelModule.motor_readback_speed);*/
	Instruction_To_FMCU.McuFD_LH_Set_Rud_Location = 2050 - (30*(4096/360));
	Instruction_To_FMCU.McuFD_RH_Set_Rud_Location = 2040 - (30*(4096/360));;  /*上浮舵30°上浮，待定*/
	Instruction_To_FMCU.McuFD_UV_Set_Rud_Location = 2030;
	Instruction_To_FMCU.McuFD_LV_Set_Rud_Location = 2020;   /*垂直舵归中位*/
	
	Auto_FixedDirection_Remote_Assignment(&Instruction_To_FMCU);
	Current_State.Current_Mode = 0x01;/**/  /*切回遥控模式*/
}

