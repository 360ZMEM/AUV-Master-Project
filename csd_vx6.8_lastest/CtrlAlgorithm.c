
#include<stdio.h>
#include<math.h>
#include<com.h>
#include  "CtrlAlgorithm.h" 


#define PI 3.1415926
#define ARC 6371393 /*����뾶 ��λ����*/
u16 LH_Ref_Location = 2048;
u16 RH_Ref_Location = 2048;
u16 UV_Ref_Location = 2048;
u16 LV_Ref_Location = 2048;
	
float LH_Rud_Back_Angle = 0;
float RH_Rud_Back_Angle = 0;
float UV_Rud_Back_Angle = 0;
float LV_Rud_Back_Angle = 0;

float Course_Keep_UV_Set_Rud_Angle = 0;
float Course_Keep_LV_Set_Rud_Angle = 0;





/**************������֮ǰ�Ĺ��̶���ı���****************************/
u16 MaxMotorRpm = 900;
u16 DivingMotorRpm = 1650; /*����*/
float RunningPointAccuracy = 30;  /*�ܵ㾫��*/
u8 MaxDeltaMotorSpeedSet = 50;

float MaxLeftRudder = -20.0;   /*��е�ṹ����*/           
float MaxRightRudder = 20.0;   /*��е�ṹ����*/

float MaxFloatingRudder = -20.0;  /*��е�ṹ����*/
float MaxDivingRudder = 20.0;     /*��е�ṹ����*/

float MaxSailingSpeed = 5.0;
float MaxSailingDepth = 400.0;
float MaxSailingHeight = 100.0;

float parameter_P;  /*��λ���´����*/
float parameter_I;
float parameter_D;


short int VelocityCtrl_para1 = 40;  /*P*/  /*λ��ʽPD*/
short int VelocityCtrl_para2 = 300;/*D*/  /*VelocityCtrl_para1*(Velocity_Target - Velocity_Now)+VelocityCtrl_para2*(Velocity_Now - Velocity_LastTime)*/

float CourseCtrl_para1=2.0;  /*P*/  /*λ��ʽPD*/
float CourseCtrl_para2=1.0;  /*D*/  /*CourseCtrl_para1*+CourseCtrl_para2*������ٶ�*/

float DepthCtrl_para1=4.0;     /*������Ʋ���������ģʽ*/
float DepthCtrl_para2=2.0;    
float DepthCtrl_para3 = 2.0;
float ballance_pitch = 3.0;     /*ƽ�⹥��*/

float HeightCtrl_para1  = 3.0;/*���߿��Ʋ���������ģʽ*/
float HeightCtrl_para2  = 1.5;
float HeightCtrl_para3 = 1.5;

float pitch_set = 0.0;
float PitchCtrl_para1 = 2.0;     /*��������Ǳ*/
float PitchCtrl_para2 = 2.0;

float FollowLaneCtrl_para1 = 0.8;
float FollowLaneCtrl_para2 = 1.2;  /*FollowLaneCtrl_para1*ƫ����+FollowLaneCtrl_para2*����ƫ��*/


float Pitch[120]={0};
unsigned char moshi;
float Pinch_Angle_change;

float Temp_e[60] = {0};
float Temp_e_ave ;
unsigned char abc=0;

unsigned char Temp_e_num = 0;

Trajectory_Para FollowLane_CtrlPara;

Calc_Situation_Para Calc_Situation_CtrlPara;

float RollAngle_para1;
float RollAngle_para2;
float RollAngle_para3;











/*
 brief  Function to control the  velocity                                                                                        
 param  Velocity_Target  		: target velocity       ��                             
                                                                             
 param  Velocity_Now        	: current velocity		 �� 

 param  Velocity_LastTime 		:last time of velocity ��
 
return  Delta_MotorSpeedSet      :increment of MotorSpeedSet  rpm
*/ 

short int VelocityCtrlAlgorithm(float Velocity_Target, float Velocity_Now, float Velocity_LastTime)
{
	float VelocityDifference=0.0;
	float VelocityDifference1=0.0;
	short int Delta_MotorSpeedSet=0;
	
	if(Velocity_Target > MaxSailingSpeed)
	{
		Velocity_Target = MaxSailingSpeed;
	}

	VelocityDifference = Velocity_Target - Velocity_Now;	
	VelocityDifference1 = Velocity_Now - Velocity_LastTime; 
	/*printf("Velocity_Target:%3.2f Velocity_Now:%3.2f Velocity_LastTime:%3.2f\n",Velocity_Target,Velocity_Now,Velocity_LastTime);
	printf("VelocityDifference:%3.2f VelocityDifference1:%3.2f\n",VelocityDifference,VelocityDifference1);*/
	
	if(VelocityDifference == 0)
	{
		Delta_MotorSpeedSet = 0;
	}
	else
	{
		Delta_MotorSpeedSet = (short int)(VelocityCtrl_para1*VelocityDifference -VelocityCtrl_para2*VelocityDifference1);	
	}


	if(Delta_MotorSpeedSet > MaxDeltaMotorSpeedSet)
	{
		Delta_MotorSpeedSet = MaxDeltaMotorSpeedSet;
	}
	else if(Delta_MotorSpeedSet < -MaxDeltaMotorSpeedSet)
	{
		Delta_MotorSpeedSet = -MaxDeltaMotorSpeedSet;
	}  
	/*printf("Delta_MotorSpeedSet:%d\n",Delta_MotorSpeedSet);*/
	return Delta_MotorSpeedSet;
	
}










/******************************************************************************
*                                                                             
* \brief  Function to control the  course            
*                                                                             
* \param  Course_Target  		: target course     ��Χ0-360��,����Ϊ0�㣬��ƫ��Ϊ����                            
*                                                                             
* \param  Course_Now        	: current course	��Χ0-360��,����Ϊ0�㣬��ƫ��Ϊ����	   
*
* \param  IMU_AngRateZ 		:angular velocity of Course    ������������ʱ��Ϊ������ȷ�ϣ�������
*                                                
* \return Vertical Rudder Angle  ����Χ��MaxLeftRudder-MaxRightRudder���������������Ϊ�����Ҷ�Ϊ��                                                            
*                                                                             
******************************************************************************/

float Course_Keep_Algorithm(float Course_Target, float Course_Now,float IMU_AngRateZ) 
{
	float para1;
	float para2;
	float x1;
	float VerticalRudder_Angle;
	
	if(Course_Target < 0.0) Course_Target = 0.0;
	if(Course_Target >359.0) Course_Target = 0.0;  /*��Ч��У��*/
		
	x1 = Course_Target - Course_Now;  
	if(x1 < -180.0)
	x1 = x1 + 360.0;
	if(x1 > 180.0)
	x1 = x1 - 360.0;
	
	/*para1 = CourseCtrl_para1*x1;*/
	/*printf("course_delta:%3.4f para1:%3.4f\n",x1,para1);*/
	/*para2 = CourseCtrl_para2*IMU_AngRateZ;*/
	/*printf("IMU_AngRateZ:%3.4f para2:%3.4f\n",IMU_AngRateZ,para2);*/
	
	para1 = CourseCtrl_para1*x1;
		
	para2 = CourseCtrl_para2*IMU_AngRateZ;
	
	
	VerticalRudder_Angle = para2 + para1;
	/*printf("(para2-para1):%3.4f\n",para2-para1);
	printf("CourseCtrl_para1:%3.2f CourseCtrl_para2:%3.2f\n",CourseCtrl_para1,CourseCtrl_para2);*/
	
	if(VerticalRudder_Angle < MaxLeftRudder)          
	{
		VerticalRudder_Angle = MaxLeftRudder;
	}
	else if(VerticalRudder_Angle > MaxRightRudder)
	{
		VerticalRudder_Angle = MaxRightRudder;
	}
	else
	{
		;
	}
	return VerticalRudder_Angle;
}







/* \brief  Function to control the  depth and pitch            
*                                                                             
* \param  Depth_Target		: the target depth�������ж���׼��ˮ��Ϊ����ˮ��Ϊ0
*                                                                                                                 
* \param  Depth_Now      : the depth now �������ж���׼��ˮ��Ϊ����ˮ��Ϊ0	  
*            
* \param  Pitch_Angle_Now      : the pitch_angle now,��Χ����-180�㣩-180�㣬�����ж���׼��������������̧ͷΪ������ͷΪ��
*
* \param  Angular_ins_pitch 	: the Angular_ins_pitch now�������ж���׼��������������̧ͷ���ٶ�Ϊ������ͷ���ٶ�Ϊ��
*
* \param  vx                 	: the forward speed of AUV�������ж���׼��ǰ���ٶ�Ϊ���������ٶ�Ϊ��
*                                                
* \return WspdAngleSet          : ˮƽ�棬��Ƿ�Χ��MaxFloatingRudder-MaxDivingRudder�������������ϸ���Ϊ������Ǳ��Ϊ��*/


float DepthCtrlAlgorithm(float Depth_Target, float Depth_Now, float Pitch_Angle_Now, float Angular_ins_pitch, float vx)
{	
	float delta1,delta2,delta3;
	float WspdAngleSet;
	
	if(Depth_Target > MaxSailingDepth)  Depth_Target = MaxSailingDepth;
	if(Depth_Target < 0.0)   Depth_Target = 0.0;
	
	delta1 = DepthCtrl_para1*(Depth_Target - Depth_Now);  /*P1*/
	if(delta1 < MaxFloatingRudder)
	{
		delta1 = MaxFloatingRudder;
	}
	else if(delta1 > MaxDivingRudder)
	{
		delta1 = MaxDivingRudder;
	}
	
	delta2 = DepthCtrl_para2*(Pitch_Angle_Now + ballance_pitch); /*P2  ���ȿ��Ƹ�����,ƽ�⹥�Ǵ��⣿������*/
	delta3 = DepthCtrl_para3*(Angular_ins_pitch);/*D*/
	
	WspdAngleSet = delta1 + delta2 + delta3;
	
	if(Pitch_Angle_Now<-15)
		WspdAngleSet=-20;
	
	if(WspdAngleSet < MaxFloatingRudder)
	WspdAngleSet = MaxFloatingRudder;
	if(WspdAngleSet > MaxDivingRudder)         
	WspdAngleSet = MaxDivingRudder;
	
	return WspdAngleSet;
}










/* \brief  Function to control the  hight and pitch            
*                                                                             
* \param  Height_Target		: the target hight�������ж���׼��ˮ��Ϊ����ˮ��Ϊ0
*                                                                                                                 
* \param  Height_Now      : the depth now �������ж���׼��ˮ��Ϊ����ˮ��Ϊ0	  
*            
* \param  Pitch_Angle_Now      : the pitch_angle now,��Χ����-180�㣩-180�㣬�����ж���׼��������������̧ͷΪ������ͷΪ��
*
* \param  Angular_ins_pitch 	: the Angular_ins_pitch now�������ж���׼��������������̧ͷ���ٶ�Ϊ������ͷ���ٶ�Ϊ��
*
* \param  vx                 	: the forward speed of AUV�������ж���׼��ǰ���ٶ�Ϊ���������ٶ�Ϊ��
*                                                
* \return WspdAngleSet          : ˮƽ�棬��Ƿ�Χ��MaxFloatingRudder-MaxDivingRudder�������������ϸ���Ϊ������Ǳ��Ϊ��*/
float HightCtrlAlgorithm(float Height_Target, float Height_Now, float Pitch_Angle_Now, float Angular_ins_pitch, float vx)
{
	float delta1,delta2,delta3;
	float WspdAngleSet;
	
	if(Height_Target > MaxSailingHeight)  Height_Target = MaxSailingHeight;
	if(Height_Target < 0.0)     Height_Target = 0.0;
	
	delta1 = HeightCtrl_para1*(Height_Target - Height_Now);  /*P1*/
	
	if(delta1 < MaxFloatingRudder)           /*����޷�30�㣬��ǹ�������ж����������������ԣ�����*/
	{
		delta1 = MaxFloatingRudder;
	}
	else if(delta1 > MaxDivingRudder)
	{
		delta1 = MaxDivingRudder;
	}
	
	/*	delta2=HeightCtrl_para2*(Pitch_Angle_Now+2.5); P2  ���ȿ��Ƹ�����*/
	
	delta2=HeightCtrl_para2*(Pitch_Angle_Now  + ballance_pitch); /*P2  ���ȿ��Ƹ�����*/
	
	delta3=HeightCtrl_para3*(Angular_ins_pitch);

	WspdAngleSet= -delta1 + delta2 + delta3 ;
	
		
	if(WspdAngleSet < MaxFloatingRudder)
	WspdAngleSet = MaxFloatingRudder;
	if(WspdAngleSet > MaxDivingRudder)     
	WspdAngleSet = MaxDivingRudder;
	
	return WspdAngleSet;
}






/******************************************************************************
*                                                                             
* \brief  Function to control the  trajectory            
*                                                                             
* \param  SLongitude,SLatitude 		: the first target point ,��Χ��γ�ȣ�-90��-90�㣩�����ȣ�-180��-180�㣩���������ж�������Ϊ��������Ϊ������γΪ������γΪ��
*                                                                                                                 
* \param  TLongitude,TLatitude      : the second target point 	��Χ��γ�ȣ�-90��-90�㣩�����ȣ�-180��-180�㣩���������ж�������Ϊ��������Ϊ������γΪ������γΪ��	  
*            
* \param  Longitude,Latitude      : the current INS point of AUV ��Χ��γ�ȣ�-90��-90�㣩�����ȣ�-180��-180�㣩���������ж�������Ϊ��������Ϊ������γΪ������γΪ��
*
* \param  Heading_Angle 	: the current Heading_Angle of AUV  ��Χ0-360��,����Ϊ0�㣬��ƫ��Ϊ����
*
* \param  Trajectory_Para��Temp_e       : ƫ���ࣺ ��ƫΪ������ƫΪ����
*  
* \param Trajectory_Para��Temp_s              :the distance between (Longitude,Latitude) projection point on the path( SLongitude,SLatitude to TLongitude,TLatitude)  to (TLongitude,TLatitude)
*                                                
* \return Trajectory_Para��Vertical_Rudder Angle   ��Χ��MaxLeftRudder-MaxRightRudder���������������Ϊ�����Ҷ�Ϊ��                                                              
*                                                                             
******************************************************************************/
Trajectory_Para FollowLane_CtrlAlgorithm(double SLongitude, double SLatitude,double TLongitude, double TLatitude, double Longitude, double Latitude,float Heading_Angle,float Angular_ins_head)
{
	float x1;
	double Longitude_1;
	double Latitude_1;
	double Longitude_2;
	double Latitude_2;
	double Angle_Los;
	double Angle_Trk;

	double Temp1;
	double Temp_d;
	double Temp_L;
	
	
	Trajectory_Para Route_Para;
	Route_Para.Temp_s=0;
	Route_Para.Temp_e=0;
	Route_Para.VerticalRudder_Angle=0;
	Route_Para.distance=0;
	
	if(SLongitude > 180.0)  SLongitude = 180;
	if(SLongitude < -180.0)  SLongitude = -180;
	
	if(SLatitude > 90.0)  SLatitude = 90;
	if(SLatitude < -90.0)  SLatitude = -90;
	
	if(TLongitude > 180.0)  TLongitude = 180;
	if(TLongitude < -180.0)  TLongitude = -180;
	
	if(TLatitude > 90.0)  TLatitude = 90;
	if(TLatitude < -90.0)  TLatitude = -90;
	
	/*printf("%3.6f %3.6f %3.6f %3.6f %3.6f %3.6f %3.2f %3.2f\n",SLongitude,SLatitude,TLongitude,TLatitude,Longitude,Latitude,Heading_Angle,Angular_ins_head);*/
	
	Latitude_1 = (TLatitude - Latitude)*110946;
	Longitude_1 = (TLongitude - Longitude)*cos(Latitude*3.14159/180.)*111319;
	Temp_d = sqrt(Longitude_1 * Longitude_1 + Latitude_1 * Latitude_1);
	
	if((fabs(Latitude_1) <= 0.01) && (fabs(Longitude_1) <= 0.01)) /*����ͬʱΪo*/
	Angle_Los = Heading_Angle;
	else
	Angle_Los = ((PI / 2) - atan2(Latitude_1, Longitude_1))*180./3.14159;            /*ת��Ϊ�౱��γ���ߣ����߽Ƕ�*/
		
	if(Angle_Los < 0)
	Angle_Los += 360.0;
	else
	Angle_Los += 0.0;                  /*ת������ƫ��˳ʱ������ϵ*/
	
	Latitude_2 = (TLatitude - SLatitude)*110946;
	Longitude_2 = (TLongitude - SLongitude)*cos(SLatitude*3.14159/180.)*111319;
	Temp_L = sqrt(Longitude_2 * Longitude_2 + Latitude_2 * Latitude_2);
	
	if((fabs(Latitude_2) <= 0.01) && (fabs(Longitude_2) <= 0.01)) /*����ͬʱΪo*/
	Angle_Trk = Heading_Angle;
	else
	Angle_Trk = ((PI / 2) - atan2(Latitude_2, Longitude_2))*180./3.14159;            /*ת��Ϊ�౱��γ���ߣ����߽Ƕ�*/
	
	
	if(Angle_Trk < 0)
	Angle_Trk += 360.0;
	else
	Angle_Trk += 0.0;             /*ת������ƫ��˳ʱ������ϵ*/
	
	
	Temp1 = Angle_Trk - Angle_Los;         /*��������ߵļн�*/
	if(Temp1 < -180.0)
	Temp1 = Temp1 + 360.0;
	if(Temp1 > 180.0)
	Temp1 = Temp1 - 360.0;             
	
		
	Route_Para.distance = (float)Temp_d;
	Route_Para.Temp_e = Route_Para.distance * sin(Temp1*3.14159/180.);   /*ƫ����*/
	Route_Para.Temp_s = Route_Para.distance * cos(Temp1*3.14159/180.);
	

	/*Temp_e[30] .=. 0.R0
	 * .0
	 * .
	 * oute_Para.Temp_e;
	
	for(ii = 1 ;ii< 31;ii++)
	{
		Temp_e[ii-1] = Temp_e[ii];
		
	}
	
	Temp_e_sum = 0;
	for(ii = 0;ii < 30;ii++)
	{
		Temp_e_sum = Temp_e_sum + (fabs(Temp_e[ii]));
	}
	
	Temp_e_ave = Temp_e_sum /30.0;
	
	if(Temp_e_ave > 10)      
	{
		Temp_e_num++ ;
	}
	*/
	

	x1 = Angle_Los-Heading_Angle;  /*hy review 2017.8.3*/
	
	if(x1 < -180.0)
	x1 = x1 + 360.0;
	if(x1 > 180.0)
	x1 = x1-360.0;

	Route_Para.Angle_Difference=x1;
	/*printf("Angle_Trk:%3.2f Angle_Los:%3.2f Heading_Angle:%3.2f Temp1:%3.2f Angular_ins_head:%3.2f x1:%3.2f\n",Angle_Trk,Angle_Los,Heading_Angle,Temp1,Angular_ins_head,x1);
	printf("%6.6f %6.6f %6.6f\n",Route_Para.distance,Route_Para.Temp_e,Route_Para.Temp_s);*/
	/*Route_Para.VerticalRudder_Angle =FollowLaneCtrl_para1*Route_Para.Temp_e+FollowLaneCtrl_para2*CourseCtrlAlgorithm(Angle_Los, Heading_Angle,Angular_ins_head);*/
	
	Route_Para.VerticalRudder_Angle = 
	-parameter_P*Route_Para.Temp_e + parameter_D*(CourseCtrl_para2*Angular_ins_head + CourseCtrl_para1*x1);
	/*printf("%3.2f %3.2f\n",FollowLaneCtrl_para1*Route_Para.Temp_e,FollowLaneCtrl_para2*(CourseCtrl_para2*Angular_ins_head-CourseCtrl_para1*x1));*/

	if(Route_Para.VerticalRudder_Angle < MaxLeftRudder)         /*����޷�30�㣬��ǹ�������ж����������������ԣ�����*/
	{
		Route_Para.VerticalRudder_Angle = MaxLeftRudder;
	}
	else if(Route_Para.VerticalRudder_Angle > MaxRightRudder)
	{
		Route_Para.VerticalRudder_Angle = MaxRightRudder;
	}
	else
	{
		Route_Para.VerticalRudder_Angle  =Route_Para.VerticalRudder_Angle;
	}
	return Route_Para;
}




/*
 brief  Function to control the  Roll angle                                                                                        
 param  RollAngle_Target  		: target angle       ��                             
                                                                             
 param  RollAngle_Now        	: current angle		 ��  

 param  RollAngle_LastTime 		: last time of angle �� 
 
return  VRud2_AngleSet          : angle of vertical rudder  ��
*/ 

short int Motorspeed_Ctrl(int Rotate_Target, short int Rotate_Now)
{
	short int Rotate_Feedback;
	
	return 	Rotate_Feedback;	
}



/*
 brief  Function to calc the Situation
 param  GPS_Longitude GPS_Latitude:��ʼ�ĵ�һ����γ��
 param  IMU_Yaw ����
*/ 

Calc_Situation_Para Calc_Situation_Test={0.0,0.0};

Calc_Situation_Para Calc_Situation(double First_Point_Longitude,double First_Point_Latitude,double Second_Point_Longitude, double Second_Point_Latitude, float IMU_Yaw,  float Displayment)
{

	if(Calc_Situation_Test.Sec_Longitude == 0 || Calc_Situation_Test.Sec_Latitude == 0)/*����ڶ��������û����ֵ���õ�һ��gps������*/
	{
	  Calc_Situation_Test.Sec_Longitude = First_Point_Longitude + (Displayment* sin(IMU_Yaw))/(ARC*cos(First_Point_Latitude)*2*PI/360);
		
	  Calc_Situation_Test.Sec_Latitude = First_Point_Latitude + (Displayment* cos(IMU_Yaw))/(ARC*2*PI/360);
	}
	else/*����ڶ������������ֵ����ֻ�õڶ���������*/
	{
	  Calc_Situation_Test.Sec_Longitude = Second_Point_Longitude + (Displayment* sin(IMU_Yaw))/(ARC*cos(Second_Point_Latitude)*2*PI/360);
	
	  Calc_Situation_Test.Sec_Latitude = Second_Point_Latitude + (Displayment* cos(IMU_Yaw))/(ARC*2*PI/360);		
	}
	
	return Calc_Situation_Test;
	
	
}

/**
 * @brief Bumpless Transfer: 重置航向PID积分器
 * 当前 Course_Keep_Algorithm 为纯PD控制器, 无积分状态
 * 此函数为预留接口, 后续若加入积分项需在此清零
 */
void Course_Keep_Integral_Reset(void)
{
	/* PD controller - no integral state to reset (reserved for future PID) */
}

/**
 * @brief Bumpless Transfer: 重置深度PID积分器
 * 当前 DepthCtrlAlgorithm 为P1+P2+D控制器, 无积分状态
 * 此函数为预留接口, 后续若加入积分项需在此清零
 */
void Depth_Ctrl_Integral_Reset(void)
{
	/* P+P+D controller - no integral state to reset (reserved for future PID) */
}
