#include "AgreedTerms.h"


extern void UnpackBEIDOUDataTask(void);
extern void UnpackNetDataTask(void);
extern void UnpackPSDDataTask(void);
extern void UnpackGPSDataTask(void);
extern void UnpackDVLDataTask(void);
extern void UnpackLORADataTask(void);
extern void UnpackBMSDataTask(void);


extern void PackBEIDOUDataTask(void);
extern void PackPSDDataTask(void);
extern void UnpackIMUDataTask(void);
extern void PackNetDataTask(void);






typedef struct  
{
    u16 Total_Voltage;
    u16 Total_Current;
    u8 SOC;
    u8 SOH;
    u16 Single_Max_Voltage;
    u16 Single_Min_Voltage;
    u16 Single_Max_Temp;
    u16 Single_Min_Temp;
    uint32 BMS_Abnorm_Inf;
    
}_From_BMS;



typedef struct  
{
	u8 FromUI12_Head_BUF[4]; /*3*/
    u8 FromUI12_Msg_Length;  /*4*/
	u8 FromUI12_Msg_Num; /*5*/
    u8 FromUI12_ID;    /*6*/
	u8 FromUI12_Ctrl_Mode; /*7*/
	u16 FromUI12_Depth_Para1;/*8*/
	u16 FromUI12_Depth_Para2;/*10*/
	u16 FromUI12_Height_Para1;/*12*/
	u16 FromUI12_Height_Para2;/*14*/
	u16 FromUI12_Remain_Time;/*16*/
	short int FromUI12_Spare_Para1;/*18*/
	short int FromUI12_Spare_Para2;/*20*/
	u8 FromUI12_Work_Cmd;    /*22*/
	short int FromUI12_Motor_Speed1;/*23*/
	short int FromUI12_Motor_Speed2;/*25*/
	short int FromUI12_RCD_LH_Set_Rud_Angle;/*27*/
	short int FromUI12_RCD_RH_Set_Rud_Angle;/*29*/
	short int FromUI12_RCD_UV_Set_Rud_Angle;/*31*/
	short int FromUI12_RCD_LV_Set_Rud_Angle;/*33*/
	u16 FromUI12_Set_Course;/*35*/
	int32 FromUI12_Para1;/*37*/
	int32 FromUI12_Para2;/*41*/
	int32 FromUI12_Para3;/*45*/
	int32 FromUI12_Para4;/*49*/
	short int FromUI12_Para5;/*53*/
	short int FromUI12_Para6;/*55*/
	short int FromUI12_Para7;/*57*/
	short int FromUI12_Para8;/*59*/
	short int FromUI12_Para9;/*61*/
	short int FromUI12_Para10;/*63*/
	short int FromUI12_Para11;/*65*/
	short int FromUI12_Para12;/*67*/
	u8 FromUI12_Check_Sum; /*69*/
	u8 FromUI12_End_Buf[2]; /*71*/
}_From_UI_LORA;                             


typedef struct  
{
	u8 FromUI12_Head_BUF[4]; /*3*/
	u8 FromUI12_Msg_Length;  /*4*/
    u8 FromUI12_Msg_Num; /*5*/
	u8 FromUI12_ID;    /*6*/
	u8 FromUI12_Ctrl_Mode; /*7*/
	u16 FromUI12_Depth_Para1;/*8*/
	u16 FromUI12_Depth_Para2;/*10*/
	u16 FromUI12_Height_Para1;/*12*/
	u16 FromUI12_Height_Para2;/*14*/
	u16 FromUI12_Remain_Time;/*16*/
	short int FromUI12_Spare_Para1;/*18*/
	short int FromUI12_Spare_Para2;/*20*/
	u8 FromUI12_Work_Cmd;    /*22*/
	short int FromUI12_Motor_Speed1;/*23*/
	short int FromUI12_Motor_Speed2;/*25*/
	short int FromUI12_RCD_LH_Set_Rud_Angle;/*27*/
	short int FromUI12_RCD_RH_Set_Rud_Angle;/*29*/
	short int FromUI12_RCD_UV_Set_Rud_Angle;/*31*/
	short int FromUI12_RCD_LV_Set_Rud_Angle;/*33*/
	u16 FromUI12_Set_Course;/*35*/
	int32 FromUI12_Para1;/*37*/
	int32 FromUI12_Para2;/*41*/
	int32 FromUI12_Para3;/*45*/
	int32 FromUI12_Para4;/*49*/
	short int FromUI12_Para5;/*53*/
	short int FromUI12_Para6;/*55*/
	short int FromUI12_Para7;/*57*/
	short int FromUI12_Para8;/*59*/
	short int FromUI12_Para9;/*61*/
	short int FromUI12_Para10;/*63*/
	short int FromUI12_Para11;/*65*/
	short int FromUI12_Para12;/*67*/
	u8 FromUI12_Check_Sum; /*69*/
	u8 FromUI12_End_Buf[2]; /*71*/
	
}_From_UI_WIFI;                             



typedef struct  
{
	u8 ToUI12_Head_Buf[4]; /*3*/
	u8 ToUI12_Msg_Length;  /*4*/
	u8 ToUI12_Msg_Num; /*5*/
	u8 ToUI12_ID;    /*6*/
	u8 ToUI12_Ctrl_Mode; /*7*/
	u16 ToUI12_Depth_Para1;/*8*/
	u16 ToUI12_Depth_Para2;/*10*/
	u16 ToUI12_Height_Para1;/*12*/
	u16 ToUI12_Height_Para2;/*14*/
	u16 ToUI12_Remain_Time;/*16*/
	short int ToUI12_Spare_Para1;/*18*/
	short int ToUI12_Spare_Para2;/*20*/
	u8 ToUI12_Work_Cmd;    /*22*/
	short int ToUI12_Motor_Speed1;/*23*/
	short int ToUI12_Motor_Speed2;/*25*/
	short int ToUI12_HL_Rud_Angle;/*27*/
	short int ToUI12_HR_Rud_Angle;/*29*/
	short int ToUI12_VU_Rud_Angle;/*31*/
	short int ToUI12_VL_Rud_Angle;/*33*/
	short int ToUI12_Pres;/*35*/
	int8 ToUI12_Temp;/*37*/
	u16 ToUI12_Depth;/*38*/
	int32 ToUI12_Para1;/*40*/
	int32 ToUI12_Para2;/*44*/
	int32 ToUI12_Para3;/*48*/
	int32 ToUI12_Para4;/*52*/
	short int ToUI12_Para5;/*56*/
	short int ToUI12_Para6;/*58*/
	short int ToUI12_Para7;/*60*/
	short int ToUI12_Para8;/*62*/
	short int ToUI12_Para9;/*64*/
	short int ToUI12_Para10;/*66*/
	short int ToUI12_Para11;/*68*/
	short int ToUI12_Para12;/*70*/
	u16 ToUI12_IMU_Heading;/*72*/
	short int ToUI12_IMU_Pitch;/*74*/
	short int ToUI12_IMU_Roll;/*76*/
	u16 ToUI12_GPS_Heading;/*78*/
	u16 ToUI12_GPS_Velocity;/*80*/
	short int ToUI12_DVL_Velocity;/*82*/
	u16 ToUI12_Height;/*84*/
	int32 ToUI12_Cal_Longitude;/*86*/
	int32 ToUI12_Cal_Latitude;/*90**/
	int32 ToUI12_GPS_Longitude;/*94*/
	int32 ToUI12_GPS_Latitude;/*98*/
	u16  ToUI12_Total_Voltage;/*102*/
	u16  ToUI12_Total_Current;/*104*/
	u8 ToUI12_SOC;/*106*/
	u8 ToUI12_SOH;/*107*/
	u16 ToUI12_SingleMax_Voltage;/*108*/
	u16 ToUI12_SingleMin_Voltage;/*110*/
	int8 ToUI12_SingleMax_Temp;/*112*/
	int8 ToUI12_SingleMin_Temp;/*113*/
	uint32 ToUI12_DevicePower_State; /*114*/
	uint32 ToUI12_Cmd_State; /*118*/
	uint32 ToUI12_Sail_State; /*122*/
	uint32 ToUI12_Sys_Abnorm_Inf; /*126*/
	uint32 ToUI12_Dev_Abnorm_Inf; /*130*/
	uint32 ToUI12_BMS_Abnorm_Inf; /*134*/
	uint32 ToUI12_Dev_Abnorm_Inf_Detail; /*138*/
	u8 ToUI12_Check_Sum; /*142*/
	u8 ToUI12_End_Buf[2]; /*144*/
	
}_To_UI12;                              



typedef struct
{	
	char BEIDOU_Head_Buf[6];/*$CCTXA*/
	char BEIDOUID[6];	
	char ToUI3_Head_Buf[4];/*$AUV*/
	u8 ToUI3_Msg_Length;  /*4*/
	u8 ToUI3_Msg_Num; /*5*/
	u8 ToUI3_ID;    /*6*/
	u8 ToUI3_Ctrl_Mode; /*7*/
	u16 ToUI3_Depth_Para1;/*8*/
	u16 ToUI3_Depth_Para2;/*10*/
	u16 ToUI3_Height_Para1;/*12*/
	u16 ToUI3_Height_Para2;/*14*/
	u16 ToUI3_Remain_Time;/*16*/
	short int ToUI3_Spare_Para1;/*18*/
	short int ToUI3_Spare_Para2;/*20*/
    int32 ToUI3_Back_Longitude;/*22*/
    int32 ToUI3_Back_Latitude;/*26*/
	short int ToUI3_Pres;/*30*/
	int8 ToUI3_Temp;/*32*/
	u16 ToUI3_Depth;/*33*/
	u16 ToUI3_IMU_Heading;/*35*/
	short int ToUI3_IMU_Pitch;/*37*/
	short int ToUI3_IMU_Roll;/*39*/
	u16 ToUI3_GPS_Heading;/*41*/
	u16 ToUI3_GPS_Velocity;/*43*/
	short int ToUI3_DVL_Velocity;/*45*/
	u16 ToUI3_Height;/*47*/
	int32 ToUI3_GPS_Longitude;/*49*/
	int32 ToUI3_GPS_Latitude;/*53*/
	u16  ToUI3_Total_Voltage;/*57*/
	u8 ToUI3_SOC;/*59*/
	u8 ToUI3_SOH;/*60*/
	uint32 ToUI3_Sail_State; /*61*/
	uint32 ToUI3_Sys_Abnorm_Inf; /*65*/
	u8 ToUI3_Check_Sum; /*69*/
	u8 ToUI3_End_Buf[2]; /*71*/
	
	u8 BEIDOU_CRC_H; 
	u8 BEIDOU_CRC_L; 
	u8 BEIDOU_End_Buf[2];
}_ToUI3;/*CPU发送给北斗的通讯信息*/



typedef struct
{
	/*$MCUFD 对应的16进制显示24 4D 43 55 46 44*/
	char McuFD_Head_Buf[6];	
	u8 McuFD_Msg_Num;
	u32 McuFD_UTC_Date;  
	u32 McuFD_UTC_Time; 	
	u16 McuFD_Pre_Para1;
	u16 McuFD_Pre_Para2;
	u16 McuFD_Pre_Para3;	
	char McuFD_Action_Cmd[2];
	int16 McuFD_Motor1_Set_Speed;
	int16 McuFD_Motor2_Set_Speed;
	u16 McuFD_LH_Set_Rud_Location;
	u16 McuFD_RH_Set_Rud_Location;
	u16 McuFD_UV_Set_Rud_Location;
	u16 McuFD_LV_Set_Rud_Location;
	u16 McuFD_Power_Control;
	/*    *\R\N 对应的16进制显示2A 5C 52 5C 4E*/
	char McuFD_End_Buf[3];
}_To_MCUFD;


typedef struct
{
	/*$MCUFU 对应的16进制显示 24 4D 43 55 46 55*/
	char McuFU_Head_Buf[6];
	u8 McuFU_Msg_Num;
	char McuFU_Back_ID[2];/*FK 对应的16进制显示46 4B*/
	u16 McuFU_Pre_Para1;
	u16 McuFU_Pre_Para2;
	u16 McuFU_Pre_Para3;
	short int McuFU_Motor1_Back_Speed;
	short int McuFU_Motor2_Back_Speed;	
	u16 McuFU_LH_Back_Rud_Location;
	u16 McuFU_RH_Back_Rud_Location;
	u16 McuFU_UV_Back_Rud_Location;
	u16 McuFU_LV_Back_Rud_Location;	
	short int McuFU_Pres;
	int16 McuFU_Temp;
	u16 McuFU_Dep;	
	u16 McuFD_Power_State;
	u32 McuFD_Sys_Abnorm_Inf;
	u32 McuFD_Dev_Abnorm_Inf;
	u32 McuFD_Dev_Abnorm_Inf_Detail;	
	/*    *\R\N 对应的16进制显示2A 5C 52 5C 4E*/
	char McuFU_End_Buf[3];
}_From_FMCU;



typedef struct
{
     u8 head_buf[3];  /*3*/
	 int BI_X;
	 int BI_Y;
	 int BI_Z;
	 float BI_V; 
	 bool BI_Valid_Flag;
	 float BD_Height;
	 float BD_Time;
	 float BD_Check;/*这里确定是char吗？不应该是float吗？*/
	 
	 int WI_X;
	 int WI_Y;
	 int WI_Z;
	 float WI_V;
	 bool WI_Valid_Flag;
	 float WD_Depth;
	 float WD_Time;	
	 float WD_Check;
	 
}_From_DVL;


typedef struct
{
	double UTC_Time;
	double GPS_Latitude;
	double GPS_Longtitude;
	u8 GPS_Position_QC;
	float GPS_Course;
	float GPS_Velocity_Kn;
	float GPS_Velocity_Kmph;
}_From_GPS;




typedef struct
{
	u8 head_buf[4];  /*4*/
	double F_selftest;
	double A_channel;
	double B_channel;
	double C_channel;
	double D_channel;
}_FromACK;




typedef struct
{
	u8 head_buf;  /*1*/	
	float Roll_Pitch_Yaw[3];/*单位是弧度，转换为角度，就对应上了，1弧度约为57.3度，1弧度=（180除以π）度*/	 
	float AngRateX_AngRateY_AngRateZ[3];
	u16 check_sum; /*31*/
	
}_From_IMU;


typedef struct
{	
	u8 $BDTXR_Flag[5];/*5*/
	u8 FromUI3_Head_BUF[4];  
	u8 FromUI3_Msg_Length;
	u8 FromUI3_Msg_Num;
	u8 FromUI3_ID;
	u8 FromUI3_Ctrl_Mode;
	u16 FromUI3_Depth_Para1;
	u16 FromUI3_Depth_Para2;
	u16 FromUI3_Height_Para1;
	u16 FromUI3_Height_Para2;
	u16 FromUI3_Remain_Time;
	short int FromUI3_Spare_Para1;
	short int FromUI3_Spare_Para2;
	u8 FromUI3_Work_Cmd;
	int32 FromUI3_Back_Lat;
	int32 FromUI3_Back_Lon;
	u8 FromUI3_Check_Sum; 
	u8 FromUI3_End_Buf[2]; 

}_From_UI_BEIDOU;/*CPU接收来自北斗的通讯信息*/


typedef struct  
{ 
     u8 Msg_Num;
     u8 ID;
     u8 Current_Mode;
     u16 Current_Depth_Para1;
     u16 Current_Depth_Para2;
     u16 Current_Height_Para1;
     u16 Current_Height_Para2;
     u16 Current_Remain_Time;     
     int16 Current_Spare_Para1;     
     int16 Current_Spare_Para2;     
     u8 Current_Work_Cmd;
     int16 Current_Motor_Speed1;
     int16 Current_Motor_Speed2;
     u16 Current_LH_Rud_Location;
     u16 Current_RH_Rud_Location;
     u16 Current_UV_Rud_Location;
     u16 Current_LV_Rud_Location;
     float Current_Pres;
     int16 Current_Temp;
     float Current_Dep;
     float Current_Para1;
     float Current_Para2;     
     float Current_Para3;
     float Current_Para4;
     float Current_Para5;
     float Current_Para6;
     float Current_Para7;
     float Current_Para8;
     float Current_Para9;
     float Current_Para10;
     float Current_Para11;
     float Current_Para12;     
     float Current_IMU_Heading;
     float Current_IMU_Pitch;
     float Current_IMU_Roll;
     float Current_GPS_Heading;     
     float Current_GPS_Velocity_Kn;
     float Current_DVL_Velocity_Kn;
     float Current_Height;
     float Current_Cal_Longitude; 
     float Current_Cal_Latitude;
     float Current_GPS_Longitude;
     float Current_GPS_Latitude;
     float Current_Total_Voltage;
     float Current_Total_Current;
     u8 Current_SOC;
     u8 Current_SOH;     
     float Current_Single_Max_Voltage;
     float Current_Single_Min_Voltage;     
     u8 Current_Single_Max_Temp;
     u8 Current_Single_Min_Temp; 
     u32 Current_Device_Power_State;     
     u32 Current_Cmd_State;
     u32 Current_Sail_State;
     u32 Current_Sys_Abnorm_Inf;
     u32 Current_Dev_Abnorm_Inf;
     u32 Current_BMS_Abnorm_Inf;
     u32 Current_Dev_Abnorm_Inf_Detail;  
    
     float Back_Lon; 
     float Back_Lat;
}_Current_State;                         




typedef struct  
{
	u8 _From_PSD;  
	
}_From_PSD;                           /*中央控制单元发往频闪灯*/

/*位域定义*/
typedef struct  
{
	u8 head_buf;
	u8 command_code;
	u8 msg_length;	
	u8 white_led_power;  
	u8 blue_led_power ;
	u8 red_led_power ;
	u8 yellow_led_power ;
	u8 check_sum;
}_ToPSD;                           /*中央控制单元发往频闪灯*/

typedef unsigned char       BYTE;

extern _Current_State Current_State;
extern _From_UI_WIFI UI_WIFI_Instruction;
extern _From_UI_LORA UI_LORA_Instruction;
extern _To_UI12 To_UI12;
extern _From_BMS BMS_Prase_Data;
extern _ToUI3 ToUI3;
extern _To_MCUFD Instruction_To_FMCU;
extern _From_FMCU Data_From_FMCU;
extern _From_GPS GPS_Prase_Data;
extern _From_DVL DVL_Prase_Data;
extern _FromACK GetACKfromDVL;
extern _From_UI_BEIDOU UI_BEIDOU_Instruction;
extern _From_PSD PSD_Prase_Data;
extern _ToPSD AnswerDataToPSD;
extern _From_IMU IMU_Prase_Data;

extern void Pack_Data_To_UI12(_To_UI12 *temp);
extern void Pack_Data_To_UI3(_ToUI3 *temp);

extern void Pack_Data_To_PSD(_ToPSD *temp);
extern void Remote_Assignment(_To_MCUFD *temp);
extern void Auto_FixedDirection_Remote_Assignment(_To_MCUFD *temp);
extern void Current_state(_Current_State *temp);
extern u8 HEX_to_ASCII(u8  aHex);
extern uint8_t Data_XOR(uint8_t* data, uint8_t num);
extern SEM_ID semPackBEIDOUDataTask;
extern SEM_ID semUnpackBEIDOUDataTask;
extern SEM_ID semPackPSDDataTask;
extern SEM_ID semUnpackPSDDataTask;         
extern SEM_ID semUnpackGPSDataTask; 
extern SEM_ID semUnpackDVLDataTask; 
extern SEM_ID semUnpackLORADataTask;   
extern SEM_ID semUnpackBMSDataTask; 
extern SEM_ID semPackNetDataTask;
extern SEM_ID semUnpackNetDataTask;
extern SEM_ID semUnpackIMUDataTask; 

extern unsigned short int DEBUG;


extern bool PSD_Power_State_Flag;
extern float BI_displayment[2];
extern float WI_displayment[2];
