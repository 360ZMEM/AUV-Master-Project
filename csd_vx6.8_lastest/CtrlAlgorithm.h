#ifndef _CTRL_ALGORITHM_H
#define _CTRL_ALGORITHM_H

#include "AgreedTerms.h"

typedef struct
{
	float distance; /*��ǰ���Ŀ������*/
	float Temp_e;  /*ƫ����*/
	float Temp_s;  /*ͶӰ���Ŀ���ľ���*/
	float VerticalRudder_Angle;
	float Angle_Difference;
}Trajectory_Para;

typedef struct
{
	 double Sec_Longitude;	
	 double Sec_Latitude;
}Calc_Situation_Para;

short int VelocityCtrlAlgorithm(float Velocity_Target, float Velocity_Now, float Velocity_LastTime); /*hy review 2017.7.5*/


float Course_Keep_Algorithm(float Course_Target, float Course_Now,float IMU_AngRateZ);
/*float CourseCtrlAlgorithm(float Course_Target, float Course_Now, float Course_LastTime); */
float CourseCtrlAlgorithm(float Course_Target, float Course_Now,float Angular_ins_head);/*hy review 2017.7.5*/

float DepthCtrlAlgorithm(float Depth_Target, float Depth_Now, float Pitch_Angle_Now, float Angular_ins_pitch, float vx);

float HightCtrlAlgorithm(float Height_Target, float Height_Now, float Pitch_Angle_Now, float Angular_ins_pitch, float vx);

short int Motorspeed_Ctrl(int Rotate_Target, short int Rotate_Now);

/*float DepthCtrlAlgorithm(float Depth_Target, float Depth_Now, float Pitch_Angle_Now, float Pitch_Angle_LastTime, float vx); */

Trajectory_Para FollowLane_CtrlAlgorithm(double SLongitude, double SLatitude,double ELongitude, double ELatitude, double Longitude, double Latitude,float Heading_Angle,float Angular_ins_head);


Calc_Situation_Para Calc_Situation(double First_Point_Longitude,double First_Point_Latitude,double Second_Point_Longitude, double Second_Point_Latitude, float IMU_Yaw,  float Displayment);
extern u16 LH_Ref_Location;
extern u16 RH_Ref_Location;
extern u16 UV_Ref_Location;
extern u16 LV_Ref_Location;


extern float LH_Rud_Back_Angle;
extern float RH_Rud_Back_Angle;
extern float UV_Rud_Back_Angle;
extern float LV_Rud_Back_Angle;
extern float Course_Keep_UV_Set_Rud_Angle;
extern float Course_Keep_LV_Set_Rud_Angle;







extern Trajectory_Para FollowLane_CtrlPara;
extern Calc_Situation_Para Calc_Situation_CtrlPara;

extern u16 MaxMotorRpm;
extern u16 DivingMotorRpm;
extern u8 MaxDeltaMotorSpeedSet;
extern float RunningPointAccuracy;

extern float MaxLeftRudder;
extern float MaxRightRudder;

extern float MaxFloatingRudder;
extern float MaxDivingRudder;
	
extern float Pitch[120];
extern unsigned char moshi;
extern float Pinch_Angle_change;

extern float Temp_e[60] ;
extern float Temp_e_ave ;
extern unsigned char Temp_e_num ;
extern unsigned char abc;


extern short int VelocityCtrl_para1;  /*P*/
extern short int VelocityCtrl_para2;/*D*/  /*VelocityCtrl_para1*(Velocity_Target - Velocity_Now)+VelocityCtrl_para2*(Velocity_Now - Velocity_LastTime)*/

extern float CourseCtrl_para1;  /*P*/
extern float CourseCtrl_para2;  /*D*/  /*CourseCtrl_para1*+CourseCtrl_para2*������ٶ�*/

extern float DepthCtrl_para1;
extern float DepthCtrl_para2;
extern float spd_set;
extern float ballance_pitch;


extern float pitch_set ;

extern float FollowLaneCtrl_para1;
extern float FollowLaneCtrl_para2;  /*FollowLaneCtrl_para1*ƫ����+FollowLaneCtrl_para2*����ƫ��*/


extern float HeightCtrl_para1 ;
extern float HeightCtrl_para2 ;
extern float HeightCtrl_para3 ;

extern float parameter_P;
extern float parameter_I;
extern float parameter_D;

/** @brief Bumpless Transfer: 重置航向PID积分器 (当前PD无积分, 预留接口) */
void Course_Keep_Integral_Reset(void);
/** @brief Bumpless Transfer: 重置深度PID积分器 (当前PD无积分, 预留接口) */
void Depth_Ctrl_Integral_Reset(void);

#endif
