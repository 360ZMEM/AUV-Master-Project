#include <vxWorks.h>
#include <sysLib.h>
#include <taskLib.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
#include <arpa/inet.h>
#include <time.h>


#include "DataProcess.h"
#include "SecurityEmergencyManage.h"
#include "PowerManage.h"
#include "com.h"
#include "SailingBox.h"
#include "CtrlAlgorithm.h" 
#include "main.h"

#define UIBeidID 0989564
#define AUVBeidID 0989565
#define PC104_UPTIME_VALID_MARKER 0x5453
#define PC104_DOWNLINK_ECHO_MARKER 0x4543

static volatile bool g_pc104_timing_downlink_echo_valid = false;
static volatile u8 g_pc104_timing_last_downlink_frame = 0;
static volatile int32 g_pc104_timing_last_downlink_rx_uptime_ms = 0;

/**
 * @brief Return PC104 relative uptime in signed 32-bit milliseconds.
 * @details The value is derived from the VxWorks tick counter and does not
 *          depend on RTC, GPS, or wall-clock synchronization. The value wraps
 *          before the signed 32-bit millisecond range is exceeded.
 * @return Relative uptime in milliseconds.
 * @author Tsinghua AUV Group
 */
static int32 Get_PC104_Uptime_Ms(void)
{
	unsigned long ticks;
	unsigned long rate;
	unsigned long seconds;
	unsigned long remain_ticks;
	unsigned long uptime_ms;

	ticks = (unsigned long)tickGet();
	rate = (unsigned long)sysClkRateGet();
	if(rate == 0)
	{
		return 0;
	}

	seconds = ticks / rate;
	remain_ticks = ticks % rate;
	uptime_ms = (seconds % 2147483UL) * 1000UL + (remain_ticks * 1000UL) / rate;
	return (int32)uptime_ms;
}

/**
 * @brief Record the latest UI WIFI downlink receive timestamp for echo timing.
 * @details Called immediately after a $CKTH WIFI frame passes checksum in the
 *          UDP receive path. The timestamp is PC104-relative uptime and is
 *          echoed in the next $AUV frame for RTT and firmware-internal timing.
 * @param [in] frame_number Downlink $CKTH frame number at byte offset 5.
 * @author Tsinghua AUV Group
 */
void PC104_Timing_Record_WIFI_Downlink(u8 frame_number)
{
	g_pc104_timing_last_downlink_rx_uptime_ms = Get_PC104_Uptime_Ms();
	g_pc104_timing_last_downlink_frame = frame_number;
	g_pc104_timing_downlink_echo_valid = true;
}

/**
 * @brief Inject a synthetic timing echo sample from the VxWorks shell.
 * @details This is a telnet-shell diagnostic hook only. It proves that the
 *          $AUV uplink echo fields are visible, but formal latency tests should
 *          use PC104_Timing_Record_WIFI_Downlink() from the UDP receive path.
 * @param [in] frame_number Frame number to expose in the next $AUV echo.
 * @author Tsinghua AUV Group
 */
void PC104_Timing_Echo_Test(int frame_number)
{
	PC104_Timing_Record_WIFI_Downlink((u8)(frame_number & 0xFF));
	printf("[pc104-echo] injected frame=%d rx_uptime_ms=%ld\r\n",
		(int)g_pc104_timing_last_downlink_frame,
		(long)g_pc104_timing_last_downlink_rx_uptime_ms);
}

/**
 * @brief Clear the synthetic/recorded downlink echo state.
 * @author Tsinghua AUV Group
 */
void PC104_Timing_Echo_Clear(void)
{
	g_pc104_timing_downlink_echo_valid = false;
	g_pc104_timing_last_downlink_frame = 0;
	g_pc104_timing_last_downlink_rx_uptime_ms = 0;
	printf("[pc104-echo] cleared\r\n");
}

void UnpackNetDataTask(void);
void UnpackBEIDOUDataTask(void);
void UnpackPSDDataTask(void);
void UnpackGPSDataTask(void);
void UnpackLORADataTask(void);
void UnpackDVLDataTask(void);
void UnpackBMSDataTask(void);
void UnpackIMUDataTask(void);

void PackBEIDOUDataTask(void);
void PackPSDDataTask(void);
void PackNetDataTask(void);


void Unpack_Data_From_UI12_WIFI(u8 *temp_buf);
void Pack_Data_To_UI12(_To_UI12 *temp);


void Unpack_Data_From_UI3(u8 *temp_buf);
void Pack_Data_To_UI3(_ToUI3 *temp);


void Remote_Assignment(_To_MCUFD *temp);
void Unpack_Data_From_FMCU(u8 *temp_buf);

void Auto_FixedDirection_Remote_Assignment(_To_MCUFD *temp);


void Unpack_Data_From_BMS_SS(u8 *temp_buf);
void Unpack_Data_From_BMS_CS(u8 *temp_buf);


void Unpack_Data_From_PSD(u8 *temp_buf);
void Pack_Data_To_PSD(_ToPSD *temp);


void Unpack_Data_From_IMU(u8 *temp_buf);

void Unpack_Data_From_GPS_GGA(u8 *temp_buf);
void Unpack_Data_From_GPS_VTG(u8 *temp_buf);

void Unpack_Data_From_DVL_BI(u8 *temp_buf);
void Unpack_Data_From_DVL_BD(u8 *temp_buf);
void Unpack_Data_From_DVL_WI(u8 *temp_buf);
void Unpack_Data_From_DVL_WD(u8 *temp_buf);
void Unpack_Data_From_DVL_ACK(u8 *temp_buf);/*����ֻ���ack�Լ����*/

void Unpack_Data_From_UI12_LORA(u8 *temp_buf);


void Current_state(_Current_State *temp);

float Calculate_Location(void);/*�����voidҪ�ĳɴ���������ĺ���*/

void DVL_BI_Speed_Integral(void);
void DVL_WI_Speed_Integral(void);

u16 CRC16_MODBUS(u8* puchMsg, int usDataLen);
u16 Check_Sum (u8* puchMsg1, int usDataLen);
byte InvertUint8(byte srcBuf);
u16 InvertUint16(u16 srcBuf);
float FloatFromBytes(const unsigned char* pBytes);

u8 HEX_to_ASCII(u8 aChar);
u8 ASCII_to_HEX(u8 aHex);
uint8_t Data_XOR(uint8_t* data, uint8_t num);

float BD_Time_Pass[2]={0,0};
float BI_V_Pass[2]={0,0};
float BI_displayment[2]={0,0};


float WD_Time_Pass[2]={0};
float WI_V_Pass[2]={0};
float WI_displayment[2]={0,0};



_From_UI_WIFI UI_WIFI_Instruction;
_To_UI12 To_UI12;

_From_UI_LORA UI_LORA_Instruction;


_From_BMS BMS_Prase_Data;

_ToUI3 ToUI3;

_To_MCUFD Instruction_To_FMCU;
_From_FMCU Data_From_FMCU;

_From_GPS GPS_Prase_Data;

_From_DVL DVL_Prase_Data;
static int32 DVL_BI_Uptime_Ms = 0;

_FromACK GetACKfromDVL;

_From_UI_BEIDOU UI_BEIDOU_Instruction;

_From_PSD PSD_Prase_Data;

_From_IMU IMU_Prase_Data;

_ToPSD AnswerDataToPSD;

_BIOSRealTime BIOS_RealTime; 

_Current_State Current_State;

u8 Vehicle_No=0x01;/*����1�Ż�����*/
float Course_set_angle = 0.0;

float Heading_Deviation=0.0;

double One_Point_Longitude = 0.0;
double One_Point_Latitude = 0.0;
double Next_Point_Longitude = 0.0;
double Next_Point_Latitude = 0.0;

int32 Integ_t1=0;
int32 Integ_t2=0;

void PackBEIDOUDataTask(void)
{
    FOREVER
	{
		if(OK == semTake(semPackBEIDOUDataTask,WAIT_FOREVER))
		{
			printf("PackBEIDOUDataTask start::::\r\n");	
			Pack_Data_To_UI3(&ToUI3);
			
			
		}
	}	
}

void PackPSDDataTask(void)
{
    FOREVER
	{
		if(OK == semTake(semPackPSDDataTask,WAIT_FOREVER))
		{
			printf("PackPSDDataTask start::::\r\n");	
			Pack_Data_To_PSD(&AnswerDataToPSD);
		}
	}	
	
}


void PackNetDataTask(void)
{
    FOREVER
	{
		if(OK == semTake(semPackNetDataTask,WAIT_FOREVER))
		{
			printf("PackNetDataTask start::::\r\n");	
			Pack_Data_To_UI12(&To_UI12);
		}
	}		
}

float Calculate_Location(void)
{
	float Calculate_Longitude = 0.00;
	float Calculate_Latitude  = 0.00;
	if(1)
	{
		return Calculate_Longitude;
	}
	else
	{
		return Calculate_Latitude;
	}
	
}

void Current_state(_Current_State *temp)
{

	
	
	
	if((temp->Msg_Num) < 255)
	{
		(temp->Msg_Num)++;
	}
	else
	{
		(temp->Msg_Num) = 0;
	}
	
	temp->ID=0x01;
	
	if(UI_Channel_Selection_Down == 0x01)
	{
		temp->Current_Mode=UI_LORA_Instruction.FromUI12_Ctrl_Mode;
	}
	
	
	if(UI_Channel_Selection_Down == 0x02)
	{
		temp->Current_Mode=UI_WIFI_Instruction.FromUI12_Ctrl_Mode;
	}	
	
	if(Parameter_Adjustment_Flag == true)
	{
		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Depth_Para1=UI_LORA_Instruction.FromUI12_Depth_Para1;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Depth_Para1=UI_WIFI_Instruction.FromUI12_Depth_Para1;
		}	
		
	}
	
	
	if(Parameter_Adjustment_Flag == true)
	{
		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Depth_Para2=UI_LORA_Instruction.FromUI12_Depth_Para2;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Depth_Para2=UI_WIFI_Instruction.FromUI12_Depth_Para2;
		}	
		
	}
		
	if(Parameter_Adjustment_Flag == true)
	{
		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Height_Para1=UI_LORA_Instruction.FromUI12_Height_Para1;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Height_Para1=UI_WIFI_Instruction.FromUI12_Height_Para1;
		}	
		
	}	

	
	if(Parameter_Adjustment_Flag == true)
	{
		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Height_Para2=UI_LORA_Instruction.FromUI12_Height_Para2;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Height_Para2=UI_WIFI_Instruction.FromUI12_Height_Para2;
		}	
		
	}	

	
	if(Parameter_Adjustment_Flag == true)
	{
		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Remain_Time=UI_LORA_Instruction.FromUI12_Remain_Time;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Remain_Time=UI_WIFI_Instruction.FromUI12_Remain_Time;
		}	
		
	}	
		
	
	
		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Spare_Para1=UI_LORA_Instruction.FromUI12_Spare_Para1;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Spare_Para1=UI_WIFI_Instruction.FromUI12_Spare_Para1;
		}	
		

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Spare_Para2=UI_LORA_Instruction.FromUI12_Spare_Para2;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Spare_Para2=UI_WIFI_Instruction.FromUI12_Spare_Para2;
		}	
			

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Work_Cmd=UI_LORA_Instruction.FromUI12_Work_Cmd;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Work_Cmd=UI_WIFI_Instruction.FromUI12_Work_Cmd;
		}	

		if(BEIDOU_Data_Ready == true)
		{
			BEIDOU_Data_Ready = false;
			temp->Current_Work_Cmd = UI_BEIDOU_Instruction.FromUI3_Work_Cmd;
		}
		/*��ʱ����
		temp->Current_Work_Cmd=	0x23;*/
		
	
		
		
		
		
		
		
		temp->Current_Motor_Speed1=Data_From_FMCU.McuFU_Motor1_Back_Speed;
		temp->Current_Motor_Speed2=Data_From_FMCU.McuFU_Motor2_Back_Speed;
	
		temp->Current_LH_Rud_Location=Data_From_FMCU.McuFU_LH_Back_Rud_Location;
		temp->Current_RH_Rud_Location=Data_From_FMCU.McuFU_RH_Back_Rud_Location;
		temp->Current_UV_Rud_Location=Data_From_FMCU.McuFU_UV_Back_Rud_Location;
		temp->Current_LV_Rud_Location=Data_From_FMCU.McuFU_LV_Back_Rud_Location;
		
		temp->Current_Pres=Data_From_FMCU.McuFU_Pres;
		temp->Current_Temp=Data_From_FMCU.McuFU_Temp;
		temp->Current_Dep=(Data_From_FMCU.McuFU_Dep/1000);
		

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Para1=UI_LORA_Instruction.FromUI12_Para1;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Para1=UI_WIFI_Instruction.FromUI12_Para1;
		}	
				

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Para2=UI_LORA_Instruction.FromUI12_Para2;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Para2=UI_WIFI_Instruction.FromUI12_Para2;
		}	
						

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Para3=UI_LORA_Instruction.FromUI12_Para3;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Para3=UI_WIFI_Instruction.FromUI12_Para3;
		}	
			

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Para4=UI_LORA_Instruction.FromUI12_Para4;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Para4=UI_WIFI_Instruction.FromUI12_Para4;
		}	
					

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Para5=UI_LORA_Instruction.FromUI12_Para5;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Para5=UI_WIFI_Instruction.FromUI12_Para5;
		}	
					

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Para6=UI_LORA_Instruction.FromUI12_Para6;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Para6=UI_WIFI_Instruction.FromUI12_Para6;
		}	
					

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Para7=UI_LORA_Instruction.FromUI12_Para7;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Para7=UI_WIFI_Instruction.FromUI12_Para7;
		}	
					

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Para8=UI_LORA_Instruction.FromUI12_Para8;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Para8=UI_WIFI_Instruction.FromUI12_Para8;
		}	
					

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Para9=UI_LORA_Instruction.FromUI12_Para9;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Para9=UI_WIFI_Instruction.FromUI12_Para9;
		}	
					

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Para10=UI_LORA_Instruction.FromUI12_Para10;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Para10=UI_WIFI_Instruction.FromUI12_Para10;
		}	
					

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Para11=UI_LORA_Instruction.FromUI12_Para11;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Para11=UI_WIFI_Instruction.FromUI12_Para11;
		}	
					

		if(UI_Channel_Selection_Down == 0x01)
	    {
			temp->Current_Para12=UI_LORA_Instruction.FromUI12_Para12;
		}	
		
		if(UI_Channel_Selection_Down == 0x02)
	    {
			temp->Current_Para12=UI_WIFI_Instruction.FromUI12_Para12;
		}	
	

		
		
		temp->Current_IMU_Heading = IMU_Prase_Data.Roll_Pitch_Yaw[2];
		
		temp->Current_IMU_Pitch = IMU_Prase_Data.Roll_Pitch_Yaw[1];
		temp->Current_IMU_Roll = IMU_Prase_Data.Roll_Pitch_Yaw[0];
		
		temp->Current_GPS_Heading = GPS_Prase_Data.GPS_Course;
		
		temp->Current_GPS_Velocity_Kn = GPS_Prase_Data.GPS_Velocity_Kn;
		
		/*if(DVL_Prase_Data.BI_Valid_Flag == true)
		{
			temp->Current_DVL_Velocity_Kn = (DVL_Prase_Data.BI_V)/514.4444;
		}*/

		if(BI_Cal_Data_Flag == true || WI_Cal_Data_Flag == false)
		{
			temp->Current_DVL_Velocity_Kn = (DVL_Prase_Data.BI_V)/514.4444;
		}		
		
		/*if(DVL_Prase_Data.BI_Valid_Flag == false)
		{
			temp->Current_DVL_Velocity_Kn = (DVL_Prase_Data.WI_V)/514.4444;
		}*/
		
		if(BI_Cal_Data_Flag == false || WI_Cal_Data_Flag == true)
		{
			temp->Current_DVL_Velocity_Kn = (DVL_Prase_Data.WI_V)/514.4444;
		}
		
		if(DVL_Prase_Data.BD_Check == 2.00 || DVL_Prase_Data.BD_Check == 3.00)
		{
			temp-> Current_Height = DVL_Prase_Data.BD_Height;
		}
		
		
		if(DVL_Prase_Data.WD_Check == 2.00 || DVL_Prase_Data.WD_Check == 3.00)
		{
			temp-> Current_Height = DVL_Prase_Data.WD_Depth;
		}
				
		/*�����㺽λ*/		
		if(BI_Cal_Data_Flag == true)/*�Եף�������һ����ľ�γ��*/
		{		   
		    if(Recv_From_GPS_QC_Flag == true)/*�յ�gps������Ч�Ϳ�ʼ���㣬�ղ���gps���ݾͲ�������*/
			{
		    	   One_Point_Longitude = GPS_Prase_Data.GPS_Longtitude;
		    	   One_Point_Latitude = GPS_Prase_Data.GPS_Latitude;
		    	   
				   Next_Point_Longitude = Calc_Situation_CtrlPara.Sec_Longitude;
			       Next_Point_Latitude = Calc_Situation_CtrlPara.Sec_Latitude;
			       
				   Calc_Situation(One_Point_Longitude, One_Point_Latitude, Next_Point_Longitude,Next_Point_Latitude , IMU_Prase_Data.Roll_Pitch_Yaw[2],BI_displayment[1]);					   
			}
		}

		if(WI_Cal_Data_Flag == true)/*��ˮ��������һ����ľ�γ��*/		
		{
		    if(Recv_From_GPS_QC_Flag == true)/*�յ�gps���ݾͿ�ʼ���㣬�ղ���gps���ݾͲ�������*/
			{
		    	   One_Point_Longitude = GPS_Prase_Data.GPS_Longtitude;
		    	   One_Point_Latitude = GPS_Prase_Data.GPS_Latitude;
		    	   
				   Next_Point_Longitude = Calc_Situation_CtrlPara.Sec_Longitude;
			       Next_Point_Latitude = Calc_Situation_CtrlPara.Sec_Latitude;
			       
				   Calc_Situation(One_Point_Longitude, One_Point_Latitude, Next_Point_Longitude,Next_Point_Latitude , IMU_Prase_Data.Roll_Pitch_Yaw[2],WI_displayment[1]);					   
			}
		}
		temp->Current_Cal_Longitude = Calc_Situation_CtrlPara.Sec_Longitude;
		temp->Current_Cal_Latitude  = Calc_Situation_CtrlPara.Sec_Latitude;
		/*
		temp->Current_Cal_Longitude = GPS_Prase_Data.GPS_Longtitude;
		temp->Current_Cal_Latitude  = GPS_Prase_Data.GPS_Latitude;		*/
		
		if((GPS_Prase_Data.GPS_Position_QC & 0x01 )== 0x01)
		{
			temp->Current_GPS_Longitude = GPS_Prase_Data.GPS_Longtitude;
		}
		
		if((GPS_Prase_Data.GPS_Position_QC & 0x01 )== 0x01)
		{
			temp->Current_GPS_Latitude = GPS_Prase_Data.GPS_Latitude;
		}
				
		temp->Current_Total_Voltage = (float)((BMS_Prase_Data.Total_Voltage)/10);
		temp->Current_Total_Current = (float)((BMS_Prase_Data.Total_Current)/10);
		
		temp->Current_SOC =BMS_Prase_Data.SOC;
		temp->Current_SOH =(u8)((BMS_Prase_Data.SOH)/10);
		
		temp->Current_Single_Max_Voltage=(float)((BMS_Prase_Data.Single_Max_Voltage)/1000);
		temp->Current_Single_Min_Voltage=(float)((BMS_Prase_Data.Single_Min_Voltage)/1000);
		
		temp->Current_Single_Max_Temp = BMS_Prase_Data.Single_Max_Temp;		
		temp->Current_Single_Min_Temp = BMS_Prase_Data.Single_Min_Temp;
		
		temp->Current_Device_Power_State= Device_Power_State_Judgement ;		
		temp->Current_Cmd_State= Cmd_State_Judgement;
		temp->Current_Sail_State= Sail_State_Judgement;
		temp->Current_Sys_Abnorm_Inf= Sys_Abnorm_Inf_Judgement;
		/**
		 * @brief Mirror software depth-protection bits into the exported state snapshot.
		 * @note  Runtime evidence shows the self-rescue execution chain can close while
		 *        Sys_Abnorm_Inf_Judgement is observed as 0x00000000. Export the depth
		 *        protection bits from the authoritative counters so UI/$AUV keeps the
		 *        same software alarm semantics as EmergencyTask.
		 */
		if(Depth_Exceed_FromUI12_Depth_Para1 >= 10)
		{
			temp->Current_Sys_Abnorm_Inf |= 0x00000200;
		}
		if(Depth_Exceed_FromUI12_Depth_Para2 >= 10)
		{
			temp->Current_Sys_Abnorm_Inf |= 0x00000400;
		}
		temp->Current_Dev_Abnorm_Inf= Dev_Abnorm_Inf_Judgement;
		temp->Current_BMS_Abnorm_Inf= BMS_Abnorm_Inf_Judgement;
		temp->Current_Dev_Abnorm_Inf_Detail= Dev_Abnorm_Inf_Detail_Judgement;
		
		if(BEIDOU_Data_Ready == true)
		{
			BEIDOU_Data_Ready = false;
			temp->Back_Lon = UI_BEIDOU_Instruction.FromUI3_Back_Lon;
		}
		
		if(BEIDOU_Data_Ready == true)
		{
			BEIDOU_Data_Ready = false;
			temp->Back_Lat = UI_BEIDOU_Instruction.FromUI3_Back_Lat;
		}
	
}




void UnpackNetDataTask(void)
{
	
	FOREVER
	{
		if(OK == semTake(semUnpackNetDataTask,WAIT_FOREVER))
		{
			printf("UnpackNetDataTask start::::\r\n");
			if(true == Recv_From_WIFI_Correct_Flag)
			{	
				Unpack_Data_From_UI12_WIFI(From_WIFI_Buf);
				Not_Recv_From_WIFI_No = 0;     /*���ݽ��մ����ʱ������*/
				Not_Recv_From_Jetson_No = 0;   /**< @brief Jetson看门狗喂狗: 收到有效WIFI包即清零 */
				Recv_From_WIFI_Correct_Flag = false;
			}
			if(true == Recv_From_FMCU_Correct_Flag)
			{					
				Unpack_Data_From_FMCU(From_FMCU_Buf);
				Not_Recv_From_FMCU_No = 0;     /*���ݽ��մ����ʱ������*/
				Recv_From_FMCU_Correct_Flag = false;
			}
			
			semGive(semDataStoreTask);
		}
	}
}

void UnpackBMSDataTask(void)
{
    FOREVER
	{
		if(OK == semTake(semUnpackBMSDataTask,WAIT_FOREVER))
		{
			printf("UnpackBMSDataTask start::::\r\n");	
			if(true == Recv_From_BMS_SS_Correct_Flag)
			{						
				Unpack_Data_From_BMS_SS(From_BMS_SS_Buf);
				Recv_From_BMS_SS_Correct_Flag = false;
				Not_Recv_From_BMS_No = 0;
			}
			if(true == Recv_From_BMS_CS_Correct_Flag)
			{						
				Unpack_Data_From_BMS_CS(From_BMS_CS_Buf);				
				Recv_From_BMS_CS_Correct_Flag = false;
				Not_Recv_From_BMS_No = 0;
			}
			
		}
	}	
	
}



void UnpackLORADataTask(void)
{
	            FOREVER
				{
					if(OK == semTake(semUnpackLORADataTask,WAIT_FOREVER))
					{
						printf("UnpackLORADataTask start::::\r\n");	
						if(true == Recv_From_LORA_Correct_Flag)
						{						
							Unpack_Data_From_UI12_LORA(From_LORA_Buf);
							Not_Recv_From_LORA_No = 0;
							Recv_From_LORA_Correct_Flag = false;
						}
					}
				}	
}



void UnpackIMUDataTask(void)
{
	        FOREVER
			{
				if(OK == semTake(semUnpackIMUDataTask,WAIT_FOREVER))
				{
					printf("UnpackIMUDataTask start::::\r\n");	
					if(true == Recv_From_IMU_Correct_Flag)
					{						
						Unpack_Data_From_IMU(From_IMU_Buf);
						Not_Recv_From_IMU_No = 0;
						Recv_From_IMU_Correct_Flag = false;
					}
				}
			}
}




void UnpackPSDDataTask(void)
{
	        FOREVER
			{
				if(OK == semTake(semUnpackPSDDataTask,WAIT_FOREVER))
				{
					printf("UnpackPSDDataTask start::::\r\n");	
					if(true == Recv_From_PSD_Correct_Flag)
					{						
						Unpack_Data_From_PSD(From_PSD_Buf);
						Not_Recv_From_PSD_No = 0;
						Recv_From_PSD_Correct_Flag = false;
					}
				}
			}
}

void UnpackDVLDataTask(void)
{
	        FOREVER
			{
				if(OK == semTake(semUnpackDVLDataTask,WAIT_FOREVER))
				{
					printf("UnpackDVLDataTask start::::\r\n");	
					if(true == BI_Data_Valid_Flag)
					{						
						Unpack_Data_From_DVL_BI(From_DVL_BI_Buf);

						/*������֮��ͻ���*/
						DVL_BI_Speed_Integral();
						BI_Data_Valid_Flag = false;
						Not_Recv_From_DVL_No = 0;
					}
					
					if(true == BD_Data_Valid_Flag)
					{						
						Unpack_Data_From_DVL_BD(From_DVL_BD_Buf);
						BD_Data_Valid_Flag = false;
						Not_Recv_From_DVL_No = 0;
					}
					
					if(true == WI_Data_Valid_Flag)
					{						
						Unpack_Data_From_DVL_WI(From_DVL_WI_Buf);	
						/*������֮��ͻ���*/
						DVL_WI_Speed_Integral();
						WI_Data_Valid_Flag = false;
						Not_Recv_From_DVL_No = 0;
					}
					
					if(true == WD_Data_Valid_Flag)
					{						
						Unpack_Data_From_DVL_WD(From_DVL_WD_Buf);
						WD_Data_Valid_Flag = false;
						Not_Recv_From_DVL_No = 0;
					}
					
					if(true == ACK_Data_Valid_Flag)
					{						
						Unpack_Data_From_DVL_ACK(From_DVL_ACK_Buf);						
						ACK_Data_Valid_Flag = false;
						Not_Recv_From_DVL_No = 0;
					}
					
				}
			}
}






void UnpackGPSDataTask(void)
{
	        FOREVER
			{
				if(OK == semTake(semUnpackGPSDataTask,WAIT_FOREVER))
				{
					printf("UnpackGPSDataTask start::::\r\n");	
					if(true == Recv_From_GPS_GGA_Correct_Flag)
					{						
						Unpack_Data_From_GPS_GGA(From_GPS_GGA_Buf);
						Recv_From_GPS_GGA_Correct_Flag = false;
						if((GPS_Prase_Data.GPS_Position_QC & 0x01) == 0x01)
						{
							Not_Recv_From_GPS_No = 0;
						}
	
					}
					
					if(true == Recv_From_GPS_VTG_Correct_Flag)
					{						
						Unpack_Data_From_GPS_VTG(From_GPS_VTG_Buf);
						Recv_From_GPS_VTG_Correct_Flag = false;
						if((GPS_Prase_Data.GPS_Position_QC & 0x01) == 0x01)
						{
							Not_Recv_From_GPS_No = 0;
						}	
						
						if((GPS_Prase_Data.GPS_Course != 0))
					    {
							  Heading_Deviation=GPS_Prase_Data.GPS_Course-(IMU_Prase_Data.Roll_Pitch_Yaw[2]);
						}
					}
					
				}
			}
}





void UnpackBEIDOUDataTask(void)
{
	FOREVER
		{
			if(OK == semTake(semUnpackBEIDOUDataTask,WAIT_FOREVER))
			{
				printf("UnpackBEIDOUDataTask start::::\r\n");
				
				
				if(true == Recv_From_BEIDOU_Correct_Flag)
				{
					Unpack_Data_From_UI3(From_BEIDOU_Buf_Self);
					Not_Recv_From_BEIDOU_No = 0;
					Recv_From_BEIDOU_Correct_Flag = false;
				}	
			
			}
		}
}




void Unpack_Data_From_FMCU(u8 *temp_buf)
{
	char *ptr = (char *)temp_buf;
	memcpy(Data_From_FMCU.McuFU_Head_Buf, ptr, 6);  
	
	ptr = strstr((char *)temp_buf, ",");	
	Data_From_FMCU.McuFU_Msg_Num = atoi(ptr+1); 	
	
	ptr = strstr(ptr+1, ",");
	strncpy(Data_From_FMCU.McuFU_Back_ID, ptr+1, 2);  
	
	ptr = strstr(ptr+1, ",");   
	Data_From_FMCU.McuFU_Pre_Para1 =  atoi(ptr+1); 	
	
	ptr = strstr(ptr+1, ",");    
	Data_From_FMCU.McuFU_Pre_Para2 =  atoi(ptr+1); 
		
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFU_Pre_Para3 =  atoi(ptr+1); 
		
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFU_Motor1_Back_Speed =  atoi(ptr+1); 
	
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFU_Motor2_Back_Speed =  atoi(ptr+1); 
	
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFU_LH_Back_Rud_Location =  atoi(ptr+1); 
	
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFU_RH_Back_Rud_Location =  atoi(ptr+1); 
		
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFU_UV_Back_Rud_Location =  atoi(ptr+1); 
			
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFU_LV_Back_Rud_Location =  atoi(ptr+1); 
	
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFU_Pres =  atoi(ptr+1); 
	/*Data_From_FMCU.McuFU_Pres =((Data_From_FMCU.McuFU_Pres)/1000);*/
	
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFU_Temp =  atoi(ptr+1); 

	
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFU_Dep =  atoi(ptr+1); 
	/*Data_From_FMCU.McuFU_Dep =((Data_From_FMCU.McuFU_Dep)/1000);*/
	
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFD_Power_State =  atoi(ptr+1); 
	
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFD_Sys_Abnorm_Inf =  atoi(ptr+1); 
	
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFD_Dev_Abnorm_Inf =  atoi(ptr+1); 
	
	ptr = strstr(ptr+1, ",");             
	Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail =  atoi(ptr+1); 
	
	ptr = strstr(ptr+1, ",");
	strncpy(Data_From_FMCU.McuFU_End_Buf, ptr+1, strlen(ptr+1));  /*end*/
	
	memset(temp_buf, 0, strlen((char *)temp_buf));	
	
	/*����֮����������McuFD_Power_State��McuFD_Sys_Abnorm_Inf��McuFD_Dev_Abnorm_Inf��McuFD_Dev_Abnorm_Inf_Detail�ж�״̬*/
	
	/*����Data_From_FMCU.McuFD_Power_State*/
	if((Data_From_FMCU.McuFD_Power_State & 0x0001) == 0x0001)    /*bit0:  �����ϵ�*/
	{
		Device_Power_State_Judgement |= 0x00000001;		
	}
	else
	{
		Device_Power_State_Judgement &= 0xfffffffe;	
	}
		
	
	if((Data_From_FMCU.McuFD_Power_State & 0x0002) == 0x0002)  /*bit1: �����ϵ�*/
	{
		Device_Power_State_Judgement |= 0x00000002;		
	}
	else
	{
		Device_Power_State_Judgement &= 0xfffffffd;
	}
		
	
	if((Data_From_FMCU.McuFD_Power_State & 0x0004) == 0x0004)/*bit2: ˮƽ���ϵ�*/
	{
		Device_Power_State_Judgement |= 0x00000004;	    
	}
	else
	{
		Device_Power_State_Judgement &= 0xfffffffb;		
	}
		
		
	if((Data_From_FMCU.McuFD_Power_State & 0x0008) == 0x0008)/*bit3: ��ֱ���ϵ�*/
	{
		Device_Power_State_Judgement |= 0x00000008;	    
	}
	else
	{
		Device_Power_State_Judgement &= 0xfffffff7;
	}
		
	
	if((Data_From_FMCU.McuFD_Power_State & 0x0010) == 0x0010)  /*Bit4: ����ԴӦ��ѹ���ϵ�*/
	{
		Device_Power_State_Judgement |= 0x00000010;		
	}
	else
	{
		Device_Power_State_Judgement &= 0xffffffef;
	}
	
	if((Data_From_FMCU.McuFD_Power_State & 0x0020) == 0x0020) /*Bit5: ������ԴӦ��ѹ���ϵ�*/
	{
		Device_Power_State_Judgement |= 0x00000020;	   
	}
	else
	{
		Device_Power_State_Judgement &= 0xffffffdf;			
	}
	
	if((Data_From_FMCU.McuFD_Power_State & 0x0040) == 0x0040)  /*Bit6: ����Դͨ��ģ���ϵ�*/
	{
		Device_Power_State_Judgement |= 0x00000040;		
	}
	else
	{
		Device_Power_State_Judgement &= 0xffffffbf;
	}
		
	
	if((Data_From_FMCU.McuFD_Power_State & 0x0080) == 0x0080)  /*Bit7: ������Դͨ��ģ���ϵ�*/
	{	
		Device_Power_State_Judgement |= 0x00000080;	    
	}
	else
	{
		Device_Power_State_Judgement &= 0xffffff7f;
	}
	
	
	if((Data_From_FMCU.McuFD_Power_State & 0x0100) == 0x0100)    /*Bit8: �����ռƳ��ǣ�DVL���ϵ�*/
	{
		Device_Power_State_Judgement |= 0x00000100;		
	}
	else
	{
		Device_Power_State_Judgement &= 0xfffffeff;			
	}
		
	
	if((Data_From_FMCU.McuFD_Power_State & 0x0200) == 0x0200)  /*Bit9������1�ϵ�*/
	{
		Device_Power_State_Judgement |= 0x00000200;		
	}
	else
	{
		Device_Power_State_Judgement &= 0xfffffdff;
	}
	
	
	if((Data_From_FMCU.McuFD_Power_State & 0x0400) == 0x0400)/*Bit10: ����2�ϵ�*/
	{
		Device_Power_State_Judgement |= 0x00000400;	   
	}
	else
	{
		Device_Power_State_Judgement &= 0xfffffbff;
	}
		
	
	
	
	
	/*����Data_From_FMCU.McuFD_Sys_Abnorm_Inf*/
	
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0:  ����©ˮ����*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00000001;		
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xfffffffe;	
	}		
	
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: �����¶ȳ��ޱ���*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00000002;		
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xfffffffd;
	}	
	
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: ����ѹ���쳣����*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00000004;	    
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xfffffffb;
	}
			
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: ϵͳ��Դ�쳣�澯*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00000008;
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xfffffff7;
	}
	
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: �豸��Դ�쳣�澯*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00000010;		
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xffffffef;
	}
	
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: ϵͳͨ���쳣�澯*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00000020;	   
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xffffffdf;
	}
	
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: �豸״̬�쳣�澯*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00000040;		
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xffffffbf;
	}
		
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: MCU��CPUͨ���쳣�澯*/
	{	
		Sys_Abnorm_Inf_Judgement |= 0x00000080;	    
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xffffff7f;
	}
		
/*****************************************************************************/	
	
	
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: CPU��MCUͨ���쳣�澯*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00000100;		
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xfffffeff;	
	}
			
	/*if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0200) == 0x0200)  Bit9�����г��������1�澯
	{
		Sys_Abnorm_Inf_Judgement |= 0x00000200;	
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xfffffdff;
	}*/
	
	/*if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0400) == 0x0400)Bit10: ���г��������2�澯
	{
		Sys_Abnorm_Inf_Judgement |= 0x00000400;	    
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xfffffbff;
	}*/
		
	/**
	 * @brief Preserve software-arbitrated DVL protection bits across live export.
	 * @note  Bit11/12/13 can be asserted by Seafloor_Grounding_Arbitration() before
	 *        MCU feedback carries the same status. Only mirror MCU-set bits here;
	 *        do not clear software-owned bits from the export path.
	 */
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11: ��׳��ޱ�������1�澯*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00000800;	    
	}
	
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12����׳��ޱ�������2�澯*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00001000;		
	}
			
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: ��Ǳ��ʱ�澯*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00002000;	    
	}		
		
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:���г�ʱ�澯*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00004000;		
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xffffbfff;
	}
		
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:��Ǳ��̬���޸澯*/
	{	
		Sys_Abnorm_Inf_Judgement |= 0x00008000;	   
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xffff7fff;
	}
		
		
	/********************************************************************************/		
	
	
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: ������̬���޸澯*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00010000;		
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xfffeffff;	
	}			
	
	if((Data_From_FMCU.McuFD_Sys_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: ƫ���೬�޸澯*/
	{
		Sys_Abnorm_Inf_Judgement |= 0x00020000;		
	}
	else
	{
		Sys_Abnorm_Inf_Judgement &= 0xfffdffff;
	}		
	
	
	
	
	
	/*����Data_From_FMCU.McuFD_Dev_Abnorm_Inf*/		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0: ������Դ�쳣�澯 */
	{
		Dev_Abnorm_Inf_Judgement |= 0x00000001;		
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfffffffe;	
	}
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: ������Դ�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00000002;		
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfffffffd;
	}
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: ˮƽ�����Դ�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00000004;	    
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfffffffb;
	}		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: ˮƽ�Ҷ���Դ�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00000008;	    
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfffffff7;
	}		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: ��ֱ�϶���Դ�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00000010;	
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xffffffef;
	}
			
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: ��ֱ�¶���Դ�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00000020;	   
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xffffffdf;
	}
				
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: Ӧ��ѹ����Դ�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00000040;		
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xffffffbf;
	}
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: DVL��Դ�쳣�澯*/
	{	
		Dev_Abnorm_Inf_Judgement |= 0x00000080;	    
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xffffff7f;
	}
		
/*****************************************************************************/	
	
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: ����1��Դ�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00000100;		
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfffffeff;	
	}
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0200) == 0x0200)  /*Bit9������2��Դ�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00000200;		
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfffffdff;
	}
			
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0400) == 0x0400)/*Bit10: ����ͨ���쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00000400;	    
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfffffbff;
	}
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11:����ͨ���쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00000800;	    
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfffff7ff;
	}
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12��ˮƽ���ͨ���쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00001000;		
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xffffefff;
	}
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: ˮƽ�Ҷ�ͨ���쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00002000;	    
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xffffdfff;
	}
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:��ֱ�϶�ͨ���쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00004000;		
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xffffbfff;
	}
		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:��ֱ�¶�ͨ���쳣�澯*/
	{	
		Dev_Abnorm_Inf_Judgement |= 0x00008000;	   
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xffff7fff;
	}
		
		
	/********************************************************************************/		
	
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: DVLͨ���쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00010000;	
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfffeffff;	
	}
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: �޾�ͨ���쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00020000;		
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfffdffff;
	}
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00040000) == 0x00040000)/*bit18:����1ͨ���쳣�澯 */
	{
		Dev_Abnorm_Inf_Judgement |= 0x00040000;	    
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfffbffff;
	}		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00080000) == 0x00080000)/*bit19: ����2ͨ���쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00080000;	    
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfff7ffff;
	}
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00100000) == 0x00100000)  /*Bit20: ����״̬�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00100000;		
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xffefffff;
	}
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00200000) == 0x00200000) /*Bit21: ����״̬�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00200000;	    
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xffdfffff;
	}
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00400000) == 0x00400000)  /*Bit22: ˮƽ���״̬�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x00400000;		
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xffbfffff;
	}
		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x00800000) == 0x00800000)  /*Bit23:ˮƽ�Ҷ�״̬�쳣�澯*/
	{	
		Dev_Abnorm_Inf_Judgement |= 0x00800000;	 
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xff7fffff;	
	}		
	/********************************************************************************/		

	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x01000000) == 0x01000000)    /*Bit24: ��ֱ�϶�״̬�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x01000000;		
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfeffffff;	
	}
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x02000000) == 0x02000000)  /*Bit25����ֱ�¶�״̬�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x02000000;
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfdffffff;
	}
		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x04000000) == 0x04000000)/*Bit26:Ӧ��ѹ��״̬�쳣�澯����Ч���㣩 */
	{
		Dev_Abnorm_Inf_Judgement |= 0x04000000;
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xfbffffff;
	}
				
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x08000000) == 0x08000000)/*Bit27: DVL״̬�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x08000000;
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xf7ffffff;
	}		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x10000000) == 0x10000000)  /*Bit28���޾�״̬�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x10000000;
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xefffffff;
	}		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x20000000) == 0x20000000) /*Bit29:����1״̬�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x20000000;	  
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xdfffffff;
	}
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x40000000) == 0x40000000)  /*Bit30:����2״̬�쳣�澯*/
	{
		Dev_Abnorm_Inf_Judgement |= 0x40000000;
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0xbfffffff;
	}		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf & 0x80000000) == 0x80000000)  /*Bit31:ͨ��ģ����Դ�쳣�澯*/
	{	
		Dev_Abnorm_Inf_Judgement |= 0x80000000;
	}
	else
	{
		Dev_Abnorm_Inf_Judgement &= 0x7fffffff;		
	}
			

	
	/*����Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail*/
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0001) == 0x0001)    /*bit0: ˮƽ���������*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00000001;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffffe;	
	}
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0002) == 0x0002)  /*bit1: ˮƽ���������*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00000002;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffffd;
	}
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0004) == 0x0004)/*bit2: ˮƽ���������*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00000004;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffffb;
	}
		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0008) == 0x0008)/*bit3: ˮƽ������Ƕȴ���*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00000008;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffff7;
	}
		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0010) == 0x0010)  /*Bit4: ˮƽ�������ѹǷѹ*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00000010;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xffffffef;
	}
		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0020) == 0x0020) /*Bit5: ��ˮƽ�Ҷ�������*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00000020;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xffffffdf;
	}
		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0040) == 0x0040)  /*Bit6: ˮƽ�Ҷ�������*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00000040;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xffffffbf;
	}
		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0080) == 0x0080)  /*Bit7: ˮƽ�Ҷ�������*/
	{	
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00000080;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xffffff7f;
	}
		
/*****************************************************************************/	
	
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0100) == 0x0100)    /*Bit8: ˮƽ�Ҷ����Ƕȴ���*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00000100;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffeff;	
	}
		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0200) == 0x0200)  /*Bit9��ˮƽ�Ҷ�����ѹǷѹ*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00000200;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffdff;
	}
		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0400) == 0x0400)/*Bit10: ��ֱ�϶�������*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00000400;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfffffbff;
	}
		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x0800) == 0x0800)/*Bit11: ��ֱ�϶�������*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00000800;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfffff7ff;
	}
		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x1000) == 0x1000)  /*Bit12����ֱ�϶�������*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00001000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xffffefff;
	}
		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x2000) == 0x2000) /*Bit13: ��ֱ�϶����Ƕȴ���*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00002000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xffffdfff;
	}
		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x4000) == 0x4000)  /*Bit14:��ֱ�϶�����ѹǷѹ*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00004000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xffffbfff;
	}		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x8000) == 0x8000)  /*Bit15: ��ֱ�¶�������*/
	{	
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00008000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xffff7fff;
	}
		
		
	/********************************************************************************/		
	
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00010000) == 0x00010000)    /*bit16: ��ֱ�¶�������*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00010000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfffeffff;
	}
			
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00020000) == 0x00020000)  /*bit17: ��ֱ�¶�������*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00020000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfffdffff;
	}
		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00040000) == 0x00040000)/*bit18: ��ֱ�¶����Ƕȴ���*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00040000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfffbffff;
	}
		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00080000) == 0x00080000)/*bit19: ��ֱ�¶�����ѹǷѹ*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00080000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfff7ffff;
	}
		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00100000) == 0x00100000)  /*Bit20: ���ƶ�תֹͣ*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00100000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xffefffff;
	}
		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00200000) == 0x00200000) /*Bit21:���Ʋ����� */
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00200000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xffdfffff;
	}
		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00400000) == 0x00400000)  /*Bit22: ���ƻ�������*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00400000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xffbfffff;
	}
		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x00800000) == 0x00800000)  /*Bit23: ��Ч����*/
	{	
		Dev_Abnorm_Inf_Detail_Judgement |= 0x00800000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xff7fffff;	
	}
		
	/********************************************************************************/		

	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x01000000) == 0x01000000)    /*Bit24: ��Ч����*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x01000000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfeffffff;	
	}
		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x02000000) == 0x02000000)  /*Bit25����Ч����*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x02000000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfdffffff;
	}
		
	
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x04000000) == 0x04000000)/*Bit26: DVL�Լ��쳣*/
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x04000000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xfbffffff;
	}
		
		
	if((Data_From_FMCU.McuFD_Dev_Abnorm_Inf_Detail & 0x08000000) == 0x08000000)/*Bit27:DVL�Ե���Ч */
	{
		Dev_Abnorm_Inf_Detail_Judgement |= 0x08000000;
	}
	else
	{
		Dev_Abnorm_Inf_Detail_Judgement &= 0xf7ffffff;
	}

	

	
}

void Unpack_Data_From_BMS_SS(u8 *temp_buf)
{
	/*���ģʽ*/
	BMS_Prase_Data.Total_Voltage=(temp_buf[4]<<8) + temp_buf[5];
	BMS_Prase_Data.Total_Current=(temp_buf[6]<<8) + temp_buf[7];
	BMS_Prase_Data.SOC=(u8)((temp_buf[10]<<8) + temp_buf[11]);
	BMS_Prase_Data.SOH =(u8)(((temp_buf[12]<<8) + temp_buf[13])/10);
	BMS_Prase_Data.Single_Max_Voltage =(temp_buf[16]<<8) + temp_buf[17];
	BMS_Prase_Data.Single_Min_Voltage = (temp_buf[20]<<8) + temp_buf[21];
	BMS_Prase_Data.Single_Max_Temp =(temp_buf[24]<<8) + temp_buf[25];
	BMS_Prase_Data.Single_Min_Temp =(temp_buf[28]<<8) + temp_buf[29];

	memset(temp_buf, 0, From_BMS_SS_Length);
}

void Unpack_Data_From_BMS_CS(u8 *temp_buf)
{
	/*���ģʽ*/
	BMS_Prase_Data.BMS_Abnorm_Inf=(temp_buf[6]<<24) + (temp_buf[7]<<16) + (temp_buf[4]<<8) + temp_buf[5];	
	
	/*����BMS_Prase_Data.BMS_Abnorm_Inf֮����������״̬�ж�*/
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0001) == 0x0001)    /*bit0:  �����ѹһ������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00000001;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfffffffe;	
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0002) == 0x0002)  /*bit1: ϵͳ��ѹһ������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00000002;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfffffffd;
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0004) == 0x0004)/*bit2: ������һ������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00000004;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfffffffb;
	}
		
		
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0008) == 0x0008)/*bit3: ����Ƿѹһ������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00000008;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfffffff7;
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0010) == 0x0010)  /*Bit4: ϵͳǷѹһ������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00000010;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xffffffef;
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0020) == 0x0020) /*Bit5: �ŵ����һ������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00000020;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xffffffdf;
	}
		
		
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0040) == 0x0040)  /*Bit6: ����¶ȹ���һ������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00000040;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xffffffbf;
	}
		
		
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0080) == 0x0080)  /*Bit7: ����¶ȹ���һ������*/
	{	
		BMS_Abnorm_Inf_Judgement |= 0x00000080;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xffffff7f;
	}
		
/*****************************************************************************/	
	
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0100) == 0x0100)    /*Bit8: SOC����һ������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00000100;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfffffeff;	
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0200) == 0x0200)  /*Bit9�������������澯*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00000200;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfffffdff;
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0400) == 0x0400)/*Bit10: �����¶ȹ���һ���澯*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00000400;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfffffbff;
	}
		
		
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x0800) == 0x0800)/*Bit11: �����¶ȹ���һ���澯*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00000800;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfffff7ff;
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x1000) == 0x1000)  /*Bit12�������¶ȹ���һ���澯*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00001000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xffffefff;
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x2000) == 0x2000) /*Bit13: �ŵ���������澯����Ч��*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00002000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xffffdfff;
	}
		
		
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x4000) == 0x4000)  /*Bit14:�ŵ��¶ȹ���һ������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00004000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xffffbfff;
	}
		
		
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x8000) == 0x8000)  /*Bit15:�ŵ��¶ȹ���һ������*/
	{	
		BMS_Abnorm_Inf_Judgement |= 0x00008000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xffff7fff;
	}
		
		
	/********************************************************************************/		
	
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00010000) == 0x00010000)    /*bit16: �����ѹ��������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00010000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfffeffff;	
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00020000) == 0x00020000)  /*bit17: ϵͳ��ѹ��������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00020000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfffdffff;
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00040000) == 0x00040000)/*bit18: ��������������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00040000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfffbffff;
	}
		
		
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00080000) == 0x00080000)/*bit19: ����Ƿѹ��������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00080000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfff7ffff;
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00100000) == 0x00100000)  /*Bit20: ϵͳǷѹ��������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00100000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xffefffff;	
	}
		
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00200000) == 0x00200000) /*Bit21: �ŵ������������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00200000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xffdfffff;
	}
		
		
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00400000) == 0x00400000)  /*Bit22: ����¶ȹ��߶�������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x00400000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xffbfffff;
	}
		
		
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x00800000) == 0x00800000)  /*Bit23: ����¶ȹ��Ͷ�������*/
	{	
		BMS_Abnorm_Inf_Judgement |= 0x00800000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xff7fffff;	
	}
		
	/********************************************************************************/		

	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x01000000) == 0x01000000)    /*Bit24: SOC���Ͷ�������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x01000000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfeffffff;	
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x02000000) == 0x02000000)  /*Bit25�������������澯*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x02000000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfdffffff;
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x04000000) == 0x04000000)/*Bit26: �����¶ȹ��߶�������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x04000000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xfbffffff;
	}
		
		
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x08000000) == 0x08000000)/*Bit27: �����¶ȹ��߶����澯*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x08000000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xf7ffffff;
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x10000000) == 0x10000000)  /*Bit28�������¶ȹ��Ͷ����澯*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x10000000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xefffffff;
	}
		
	
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x20000000) == 0x20000000) /*Bit29: �ŵ���������澯*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x20000000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xdfffffff;
	}
		
		
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x40000000) == 0x40000000)  /*Bit30:�ŵ��¶ȹ��߶�������*/
	{
		BMS_Abnorm_Inf_Judgement |= 0x40000000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0xbfffffff;
	}
		
		
	if((BMS_Prase_Data.BMS_Abnorm_Inf & 0x80000000) == 0x80000000)  /*Bit31:�ŵ��¶ȹ��Ͷ�������*/
	{	
		BMS_Abnorm_Inf_Judgement |= 0x80000000;
	}
	else
	{
		BMS_Abnorm_Inf_Judgement &= 0x7fffffff;		
	}
			
	
	memset(temp_buf, 0, From_BMS_CS_Length);
	
}


void Unpack_Data_From_UI12_LORA(u8 *temp_buf)
{	
	 if(temp_buf[6] == Vehicle_No)
	 {
			memcpy(UI_LORA_Instruction.FromUI12_Head_BUF, temp_buf, 4);
			UI_LORA_Instruction.FromUI12_Msg_Length = temp_buf[4];
			UI_LORA_Instruction.FromUI12_Msg_Num = temp_buf[5];
			UI_LORA_Instruction.FromUI12_ID = temp_buf[6];			
			UI_LORA_Instruction.FromUI12_Ctrl_Mode = temp_buf[7];
			
			UI_LORA_Instruction.FromUI12_Depth_Para1 = (temp_buf[8]<<8) + temp_buf[9];
			UI_LORA_Instruction.FromUI12_Depth_Para2 = (temp_buf[10]<<8) + temp_buf[11];
			UI_LORA_Instruction.FromUI12_Height_Para1 = (temp_buf[12]<<8) + temp_buf[13];
			UI_LORA_Instruction.FromUI12_Height_Para2 = (temp_buf[14]<<8) + temp_buf[15];
			
			
			UI_LORA_Instruction.FromUI12_Remain_Time =  (u16)((temp_buf[16]<<8) + temp_buf[17]);
			
			if((temp_buf[18]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Spare_Para1 =  (short int)((temp_buf[18]<<8) + temp_buf[19]);
			}
			
			if((temp_buf[18]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Spare_Para1 =  (short int)((temp_buf[18]<<8) + temp_buf[19]- 65536);
			
			}
			
			if((temp_buf[20]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Spare_Para2 =  (short int)((temp_buf[20]<<8) + temp_buf[21]);
			}
			
			if((temp_buf[20]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Spare_Para2 =  (short int)((temp_buf[20]<<8) + temp_buf[21]-65536);
			}
			
			
			UI_LORA_Instruction.FromUI12_Work_Cmd = temp_buf[22];
			
			
			if((temp_buf[23]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Motor_Speed1 =  (short int)((temp_buf[23]<<8) + temp_buf[24]);
			}
			
			if((temp_buf[23]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Motor_Speed1 =  (short int)((temp_buf[23]<<8) + temp_buf[24]-65536);
			}
						
			
			if((temp_buf[25]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Motor_Speed2 =  (short int)((temp_buf[25]<<8) + temp_buf[26]);
			}
			
			if((temp_buf[25]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Motor_Speed2 =  (short int)((temp_buf[25]<<8) + temp_buf[26]-65536);
			}
						
			
			if((temp_buf[27]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_RCD_LH_Set_Rud_Angle =  (short int)((temp_buf[27]<<8) + temp_buf[28]);
			}
			
			if((temp_buf[27]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_RCD_LH_Set_Rud_Angle =  (short int)((temp_buf[27]<<8) + temp_buf[28]-65536);
			}
						
			
			if((temp_buf[29]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_RCD_RH_Set_Rud_Angle =  (short int)((temp_buf[29]<<8) + temp_buf[30]);
			}
			
			if((temp_buf[29]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_RCD_RH_Set_Rud_Angle =  (short int)((temp_buf[29]<<8) + temp_buf[30]-65536);
			}
									
			
			if((temp_buf[31]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_RCD_UV_Set_Rud_Angle =  (short int)((temp_buf[31]<<8) + temp_buf[32]);
			}
			
			if((temp_buf[31]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_RCD_UV_Set_Rud_Angle =  (short int)((temp_buf[31]<<8) + temp_buf[32]-65536);
			}
									
			
			if((temp_buf[33]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_RCD_LV_Set_Rud_Angle =  (short int)((temp_buf[33]<<8) + temp_buf[34]);
			}
			
			if((temp_buf[33]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_RCD_LV_Set_Rud_Angle =  (short int)((temp_buf[33]<<8) + temp_buf[34]-65536);
			}
			
			UI_LORA_Instruction.FromUI12_Set_Course =  ((u16)((temp_buf[35]<<8) + temp_buf[36]));
			
			
			
			if((temp_buf[37]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Para1 =  ((temp_buf[37]<<24) + (temp_buf[38]<<16)+ (temp_buf[39]<<8)+ temp_buf[40]);	
			}	
			
			if((temp_buf[37]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Para1 =  ((temp_buf[37]<<24) + (temp_buf[38]<<16)+ (temp_buf[39]<<8)+ temp_buf[40]-pow(2,32));		
			}	
					
			
			if((temp_buf[41]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Para2 =  ((temp_buf[41]<<24) + (temp_buf[42]<<16)+ (temp_buf[43]<<8)+ temp_buf[44]);	
			}	
			
			if((temp_buf[41]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Para2 =  ((temp_buf[41]<<24) + (temp_buf[42]<<16)+ (temp_buf[43]<<8)+ temp_buf[44]-pow(2,32));		
			}	
								
			
			if((temp_buf[45]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Para3 =  ((temp_buf[45]<<24) + (temp_buf[46]<<16)+ (temp_buf[47]<<8)+ temp_buf[48]);	
			}	
			
			if((temp_buf[45]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Para3 =  ((temp_buf[45]<<24) + (temp_buf[46]<<16)+ (temp_buf[47]<<8)+ temp_buf[48]-pow(2,32));		
			}	
						
			
			if((temp_buf[49]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Para4 =  ((temp_buf[49]<<24) + (temp_buf[50]<<16)+ (temp_buf[51]<<8)+ temp_buf[52]);	
			}	
			
			if((temp_buf[49]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Para4 =  ((temp_buf[49]<<24) + (temp_buf[50]<<16)+ (temp_buf[51]<<8)+ temp_buf[52]-pow(2,32));		
			}				
			
			
			if((temp_buf[53]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Para5 =  (short int)((temp_buf[53]<<8) + temp_buf[54]);
			}
			
			if((temp_buf[53]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Para5 =  (short int)((temp_buf[53]<<8) + temp_buf[54]-65536);
			}			
			
			
			if((temp_buf[55]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Para6 =  (short int)((temp_buf[55]<<8) + temp_buf[56]);
			}
			
			if((temp_buf[55]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Para6 =  (short int)((temp_buf[55]<<8) + temp_buf[56]-65536);
			}			
						
			
			if((temp_buf[57]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Para7 =  (short int)((temp_buf[57]<<8) + temp_buf[58]);
			}
			
			if((temp_buf[57]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Para7 =  (short int)((temp_buf[57]<<8) + temp_buf[58]-65536);
			}			
						
			
			if((temp_buf[59]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Para8 =  (short int)((temp_buf[59]<<8) + temp_buf[60]);
			}
			
			if((temp_buf[59]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Para8 =  (short int)((temp_buf[59]<<8) + temp_buf[60]-65536);
			}			
									
			
			if((temp_buf[61]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Para9 =  (short int)((temp_buf[61]<<8) + temp_buf[62]);
			}
			
			if((temp_buf[61]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Para9 =  (short int)((temp_buf[61]<<8) + temp_buf[62]-65536);
			}			
							
			
			if((temp_buf[63]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Para10 =  (short int)((temp_buf[63]<<8) + temp_buf[64]);
			}
			
			if((temp_buf[63]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Para10 =  (short int)((temp_buf[63]<<8) + temp_buf[64]-65536);
			}			
							
			
			if((temp_buf[65]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Para11 =  (short int)((temp_buf[65]<<8) + temp_buf[66]);
			}
			
			if((temp_buf[65]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Para11 =  (short int)((temp_buf[65]<<8) + temp_buf[66]-65536);
			}			
								
			
			if((temp_buf[67]&0x80) == 0x00)
			{
				UI_LORA_Instruction.FromUI12_Para12 =  (short int)((temp_buf[67]<<8) + temp_buf[68]);
			}
			
			if((temp_buf[67]&0x80) == 0x80)
			{
				UI_LORA_Instruction.FromUI12_Para12 =  (short int)((temp_buf[67]<<8) + temp_buf[68]-65536);
			}			
						
			UI_LORA_Instruction.FromUI12_Check_Sum = temp_buf[69];
			
			memcpy(UI_LORA_Instruction.FromUI12_End_Buf, temp_buf+70, 2);
		
		memset(temp_buf, 0, FromLORALength);
	 }
}




void Unpack_Data_From_UI12_WIFI(u8 *temp_buf)
{
    if(temp_buf[6] == Vehicle_No) 
    {
		memcpy(UI_WIFI_Instruction.FromUI12_Head_BUF, temp_buf, 4);
		UI_WIFI_Instruction.FromUI12_Msg_Length = temp_buf[4];
		UI_WIFI_Instruction.FromUI12_Msg_Num = temp_buf[5];
		UI_WIFI_Instruction.FromUI12_ID = temp_buf[6];		
		UI_WIFI_Instruction.FromUI12_Ctrl_Mode = temp_buf[7];
		UI_WIFI_Instruction.FromUI12_Depth_Para1 = (temp_buf[8]<<8) + temp_buf[9];
		UI_WIFI_Instruction.FromUI12_Depth_Para2 = (temp_buf[10]<<8) + temp_buf[11];
		UI_WIFI_Instruction.FromUI12_Height_Para1 = (temp_buf[12]<<8) + temp_buf[13];
		UI_WIFI_Instruction.FromUI12_Height_Para2 = (temp_buf[14]<<8) + temp_buf[15];
		
		
		UI_WIFI_Instruction.FromUI12_Remain_Time =  (u16)((temp_buf[16]<<8) + temp_buf[17]);
		
		if((temp_buf[18]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Spare_Para1 =  (short int)((temp_buf[18]<<8) + temp_buf[19]);
		}
		
		if((temp_buf[18]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Spare_Para1 =  (short int)((temp_buf[18]<<8) + temp_buf[19] - 65536);			
		}
		
		if((temp_buf[20]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Spare_Para2 =  (short int)((temp_buf[20]<<8) + temp_buf[21]);
		}		
		
		if((temp_buf[18]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Spare_Para1 =  (short int)((temp_buf[20]<<8) + temp_buf[21] - 65536);	
		}		
		
		UI_WIFI_Instruction.FromUI12_Work_Cmd = temp_buf[22];
		
		if((temp_buf[23]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Motor_Speed1 =  (short int)((temp_buf[23]<<8) + temp_buf[24]);	
		}	
		
		if((temp_buf[23]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Motor_Speed1 =  (short int)((temp_buf[23]<<8) + temp_buf[24]- 65536);	
		}	
		
		if((temp_buf[25]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Motor_Speed2 =  (short int)((temp_buf[25]<<8) + temp_buf[26]);	
		}	
		
		if((temp_buf[25]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Motor_Speed2 =  (short int)((temp_buf[25]<<8) + temp_buf[26]- 65536);	
		}	
		
		if((temp_buf[27]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_RCD_LH_Set_Rud_Angle =  (short int)((temp_buf[27]<<8) + temp_buf[28]);	
			UI_WIFI_Instruction.FromUI12_RCD_LH_Set_Rud_Angle =(UI_WIFI_Instruction.FromUI12_RCD_LH_Set_Rud_Angle)/10;
		}	
		
		if((temp_buf[27]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_RCD_LH_Set_Rud_Angle =  (short int)((temp_buf[27]<<8) + temp_buf[28]- 65536);
			UI_WIFI_Instruction.FromUI12_RCD_LH_Set_Rud_Angle =(UI_WIFI_Instruction.FromUI12_RCD_LH_Set_Rud_Angle)/10;
		}	
		
		if((temp_buf[29]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_RCD_RH_Set_Rud_Angle =  (short int)((temp_buf[29]<<8) + temp_buf[30]);	
			UI_WIFI_Instruction.FromUI12_RCD_RH_Set_Rud_Angle =(UI_WIFI_Instruction.FromUI12_RCD_RH_Set_Rud_Angle)/10;
		}	
		
		if((temp_buf[29]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_RCD_RH_Set_Rud_Angle =  (short int)((temp_buf[29]<<8) + temp_buf[30]- 65536);	
			UI_WIFI_Instruction.FromUI12_RCD_RH_Set_Rud_Angle =(UI_WIFI_Instruction.FromUI12_RCD_RH_Set_Rud_Angle)/10;
		}	
		
		if((temp_buf[31]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_RCD_UV_Set_Rud_Angle =  (short int)((temp_buf[31]<<8) + temp_buf[32]);	
			UI_WIFI_Instruction.FromUI12_RCD_UV_Set_Rud_Angle = (UI_WIFI_Instruction.FromUI12_RCD_UV_Set_Rud_Angle)/10;
		}	
		
		if((temp_buf[31]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_RCD_UV_Set_Rud_Angle =  (short int)((temp_buf[31]<<8) + temp_buf[32]- 65536);	
			UI_WIFI_Instruction.FromUI12_RCD_UV_Set_Rud_Angle = (UI_WIFI_Instruction.FromUI12_RCD_UV_Set_Rud_Angle)/10;
		}	
		
		if((temp_buf[33]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_RCD_LV_Set_Rud_Angle =  (short int)((temp_buf[33]<<8) + temp_buf[34]);	
			UI_WIFI_Instruction.FromUI12_RCD_LV_Set_Rud_Angle = (UI_WIFI_Instruction.FromUI12_RCD_LV_Set_Rud_Angle)/10;
		}	
		
		if((temp_buf[33]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_RCD_LV_Set_Rud_Angle =  (short int)((temp_buf[33]<<8) + temp_buf[34]- 65536);	
			UI_WIFI_Instruction.FromUI12_RCD_LV_Set_Rud_Angle = (UI_WIFI_Instruction.FromUI12_RCD_LV_Set_Rud_Angle)/10;
		}	
		
		UI_WIFI_Instruction.FromUI12_Set_Course =  (u16)((temp_buf[35]<<8) + temp_buf[36]);	
		
		
		if((temp_buf[37]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Para1 =  ((temp_buf[37]<<24) + (temp_buf[38]<<16)+ (temp_buf[39]<<8)+ temp_buf[40]);	
		}	
		
		if((temp_buf[37]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Para1 = ((temp_buf[37]<<24) + (temp_buf[38]<<16)+ (temp_buf[39]<<8)+ temp_buf[40]-pow(2,32));		
		}	
				
		
		if((temp_buf[41]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Para2 =  ((temp_buf[41]<<24) + (temp_buf[42]<<16)+ (temp_buf[43]<<8)+ temp_buf[44]);	
		}	
		
		if((temp_buf[41]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Para2 = ((temp_buf[41]<<24) + (temp_buf[42]<<16)+ (temp_buf[43]<<8)+ temp_buf[44]-pow(2,32));	
		}	
					
		
		if((temp_buf[45]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Para3 = ((temp_buf[45]<<24) + (temp_buf[46]<<16)+ (temp_buf[47]<<8)+ temp_buf[48]);	
		}	
		
		if((temp_buf[45]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Para3 = ((temp_buf[45]<<24) + (temp_buf[46]<<16)+ (temp_buf[47]<<8)+ temp_buf[48]-pow(2,32));		
		}			
		
		if((temp_buf[49]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Para4 =  ((temp_buf[49]<<24) + (temp_buf[50]<<16)+ (temp_buf[51]<<8)+ temp_buf[52]);	
		}	
		
		if((temp_buf[49]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Para4 =  ((temp_buf[49]<<24) + (temp_buf[50]<<16)+ (temp_buf[51]<<8)+ temp_buf[52]-pow(2,32));		
		}	
		
		if((temp_buf[53]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Para5 = (short int)((temp_buf[53]<<8) + temp_buf[54]);	
		}	
		
		if((temp_buf[53]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Para5 = (short int)((temp_buf[53]<<8) + temp_buf[54]- 65536);	
		}	
				
		if((temp_buf[55]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Para6 =  (short int)((temp_buf[55]<<8) + temp_buf[56]);	
		}	
		
		if((temp_buf[55]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Para6 = (short int)((temp_buf[55]<<8) + temp_buf[56]- 65536);	
		}	
		
		if((temp_buf[57]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Para7 = (short int)((temp_buf[57]<<8) + temp_buf[58]);	
		}	
		
		if((temp_buf[57]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Para7 = (short int)((temp_buf[57]<<8) + temp_buf[58]- 65536);	
		}	
		
		if((temp_buf[59]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Para8 = (short int)((temp_buf[59]<<8) + temp_buf[60]);	
		}	
		
		if((temp_buf[59]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Para8 = (short int)((temp_buf[59]<<8) + temp_buf[60]- 65536);	
		}	
		
		if((temp_buf[61]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Para9 = (short int)((temp_buf[61]<<8) + temp_buf[62]);	
		}	
		
		if((temp_buf[61]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Para9 = (short int)((temp_buf[61]<<8) + temp_buf[62]- 65536);	
		}	
			
		if((temp_buf[63]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Para10 = (short int)((temp_buf[63]<<8) + temp_buf[64]);	
		}	
		
		if((temp_buf[63]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Para10 = (short int)((temp_buf[63]<<8) + temp_buf[64]- 65536);	
		}			
		
		if((temp_buf[65]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Para11 = (short int)((temp_buf[65]<<8) + temp_buf[66]);	
		}	
		
		if((temp_buf[65]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Para11 = (short int)((temp_buf[65]<<8) + temp_buf[66]- 65536);	
		}	
					
		
		if((temp_buf[67]&0x80) == 0x00)
		{
			UI_WIFI_Instruction.FromUI12_Para12 = (short int)((temp_buf[67]<<8) + temp_buf[68]);	
		}	
		
		if((temp_buf[67]&0x80) == 0x80)
		{
			UI_WIFI_Instruction.FromUI12_Para12 = (short int)((temp_buf[67]<<8) + temp_buf[68]- 65536);	
		}	
			
		UI_WIFI_Instruction.FromUI12_Check_Sum = temp_buf[69];
		
		memcpy(UI_WIFI_Instruction.FromUI12_End_Buf, temp_buf+70, 2);
		memset(temp_buf, 0, From_UI_WIFI_Length);
    }
}

static u8 g_remote_assignment_output_override = 0;

void Remote_Assignment_Set_Output_Override(u8 enable)
{
	g_remote_assignment_output_override = enable;
}

void Remote_Assignment(_To_MCUFD *temp)
{
	char array[500] = {0};
	char *ptr = array;
	u8 preserve_existing_output = 0;
	
	
	((*temp).McuFD_Msg_Num)++;
	if((temp->McuFD_Msg_Num)>254)/*��255����Ϊ0*/
	{
			temp->McuFD_Msg_Num=0;		
	}	
	
	
	(*temp).McuFD_UTC_Date=(BIOS_RealTime.Year-2000)*10000+BIOS_RealTime.Month*100+BIOS_RealTime.Day;
	(*temp).McuFD_UTC_Time=BIOS_RealTime.Hour*10000+BIOS_RealTime.Minute*100+BIOS_RealTime.Second;

		
	
	(*temp).McuFD_Pre_Para1=0;
	(*temp).McuFD_Pre_Para2=0;
	(*temp).McuFD_Pre_Para3=0;

	if(Initialization_Flag == true)
	{
		strncpy((*temp).McuFD_Action_Cmd, "CS", 2);			
	}
	
	
	if(Initialization_Flag == false)
	{
		strncpy((*temp).McuFD_Action_Cmd, "DZ", 2);			
	}

	if(g_remote_assignment_output_override != 0)
	{
		/**
		 * @brief Preserve already computed actuator outputs for one emergency send.
		 * @note  EmergencyTask computes authoritative motor/rudder values first. The
		 *        normal Remote_Assignment path rebuilds these fields from UI shadow
		 *        commands, which overwrites self-rescue outputs. Consume the override
		 *        flag once so regular remote packets keep their original behavior.
		 */
		preserve_existing_output = 1;
		g_remote_assignment_output_override = 0;
	}

	if(preserve_existing_output == 0)
	{
		if(UI_Channel_Selection_Down == 0x01)
		{
			(*temp).McuFD_Motor1_Set_Speed = UI_LORA_Instruction.FromUI12_Motor_Speed1;
		}
		if(UI_Channel_Selection_Down == 0x02)
		{
			(*temp).McuFD_Motor1_Set_Speed = UI_WIFI_Instruction.FromUI12_Motor_Speed1;
		}	
		
		if(UI_Channel_Selection_Down == 0x01)
		{
			(*temp).McuFD_Motor2_Set_Speed = UI_LORA_Instruction.FromUI12_Motor_Speed2;
		}
		if(UI_Channel_Selection_Down == 0x02)
		{
			(*temp).McuFD_Motor2_Set_Speed = UI_WIFI_Instruction.FromUI12_Motor_Speed2;
		}	
			
		if(UI_Channel_Selection_Down == 0x01)
		{
		    (*temp).McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location - (UI_LORA_Instruction.FromUI12_RCD_LH_Set_Rud_Angle) * 4096/360);		
		}
		if(UI_Channel_Selection_Down == 0x02)
		{
			(*temp).McuFD_LH_Set_Rud_Location = (u16)(LH_Ref_Location - (UI_WIFI_Instruction.FromUI12_RCD_LH_Set_Rud_Angle) * 4096/360);
		}	
				
		if(UI_Channel_Selection_Down == 0x01)
		{
		    (*temp).McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location + (UI_LORA_Instruction.FromUI12_RCD_RH_Set_Rud_Angle) * 4096/360);
		}
		if(UI_Channel_Selection_Down == 0x02)
		{
			(*temp).McuFD_RH_Set_Rud_Location = (u16)(RH_Ref_Location + (UI_WIFI_Instruction.FromUI12_RCD_RH_Set_Rud_Angle) * 4096/360);
		}	
					
		if(Course_Keep_Flag == false)
		{
			if(UI_Channel_Selection_Down == 0x01)
			{
				(*temp).McuFD_UV_Set_Rud_Location = (u16)(UV_Ref_Location - (UI_LORA_Instruction.FromUI12_RCD_UV_Set_Rud_Angle) * 4096/360);
				(*temp).McuFD_LV_Set_Rud_Location = (u16)(LV_Ref_Location + (UI_LORA_Instruction.FromUI12_RCD_LV_Set_Rud_Angle) * 4096/360);
			}	
			
			if(UI_Channel_Selection_Down == 0x02)
			{
				(*temp).McuFD_UV_Set_Rud_Location = (u16)(UV_Ref_Location - (UI_WIFI_Instruction.FromUI12_RCD_UV_Set_Rud_Angle) * 4096/360);
				(*temp).McuFD_LV_Set_Rud_Location = (u16)(LV_Ref_Location + (UI_WIFI_Instruction.FromUI12_RCD_LV_Set_Rud_Angle) * 4096/360);
			}			
			
		}
		
		if(Course_Keep_Flag == true)
		{
			/*�Ա�*/
			if(UI_Channel_Selection_Down == 0x01)
			{
				Course_set_angle = UI_LORA_Instruction.FromUI12_Set_Course;
			}
			
			if(UI_Channel_Selection_Down == 0x02)
			{
				Course_set_angle = UI_WIFI_Instruction.FromUI12_Set_Course;
			}	
			Course_Keep_UV_Set_Rud_Angle=Course_Keep_Algorithm(Course_set_angle, Current_State.Current_IMU_Heading, IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[2]);/*Ԥ����д,Ҫ�޸�*/
			Course_Keep_LV_Set_Rud_Angle=Course_Keep_Algorithm(Course_set_angle, Current_State.Current_IMU_Heading, IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[2]);/*Ԥ����д,Ҫ�޸�*/		
			(*temp).McuFD_UV_Set_Rud_Location = (u16)(UV_Ref_Location - (Course_Keep_UV_Set_Rud_Angle) * 4096/360);
			(*temp).McuFD_LV_Set_Rud_Location = (u16)(LV_Ref_Location + (Course_Keep_LV_Set_Rud_Angle) * 4096/360);
		}
	}	
	
				
	(*temp).McuFD_Power_Control= Instruction_To_FMCU.McuFD_Power_Control;
	
	/*************************test para*********************************/
#if 0
	 temp->McuFD_UTC_Date = 112233;
	 temp->McuFD_UTC_Time = 112233;
	 /*temp->McuFD_Action_Cmd[0] = 'C';*/
	 /*temp->McuFD_Action_Cmd[1] = 'S';*/
	 temp->McuFD_Action_Cmd[0] = 'D';
	 temp->McuFD_Action_Cmd[1] = 'Z';
	 temp->McuFD_Motor1_Set_Speed=100;
	 temp->McuFD_Motor2_Set_Speed=0;
	 temp->McuFD_LH_Set_Rud_Location=2162;
	 temp->McuFD_RH_Set_Rud_Location=1934;
	 temp->McuFD_UV_Set_Rud_Location=2162;
	 temp->McuFD_LV_Set_Rud_Location=1934;
	 temp->McuFD_Power_Control=0;
#endif	
	
	strncpy((*temp).McuFD_Head_Buf, "$MCUFD", 6);
	strncpy((*temp).McuFD_End_Buf,"*RN", strlen("*RN"));


	
	strncpy(ptr, (*temp).McuFD_Head_Buf, 6);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
		
	sprintf(ptr, "%03d", (*temp).McuFD_Msg_Num);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%06d", (*temp).McuFD_UTC_Date);
	ptr = ptr + strlen(ptr);		
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%06d", (*temp).McuFD_UTC_Time);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;

	sprintf(ptr, "%02d", (*temp).McuFD_Pre_Para1);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;	
	
	sprintf(ptr, "%02d", (*temp).McuFD_Pre_Para2);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;	
	
	sprintf(ptr, "%02d", (*temp).McuFD_Pre_Para3);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;			

	strncpy(ptr , (*temp).McuFD_Action_Cmd, 2);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%05d", (*temp).McuFD_Motor1_Set_Speed);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%05d", (*temp).McuFD_Motor2_Set_Speed);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%04d", (*temp).McuFD_LH_Set_Rud_Location);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%04d", (*temp).McuFD_RH_Set_Rud_Location);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%04d", (*temp).McuFD_UV_Set_Rud_Location);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%04d", (*temp).McuFD_LV_Set_Rud_Location);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%02d", (*temp).McuFD_Power_Control);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	strncpy(ptr, (*temp).McuFD_End_Buf, strlen("*RN"));
	ptr = ptr + strlen(ptr);
	
	ptr = array;
		
	strncpy((char *)to_MCU_buf, ptr, strlen(ptr));	
	

}


void Auto_FixedDirection_Remote_Assignment(_To_MCUFD *temp)
{
	char array[500] = {0};
	char *ptr = array;
	
	
	((*temp).McuFD_Msg_Num)++;
	if((temp->McuFD_Msg_Num)>254)/*��255����Ϊ0*/
	{
			temp->McuFD_Msg_Num=0;		
	}	
	
	
	(*temp).McuFD_UTC_Date=(BIOS_RealTime.Year-2000)*10000+BIOS_RealTime.Month*100+BIOS_RealTime.Day;
	(*temp).McuFD_UTC_Time=BIOS_RealTime.Hour*10000+BIOS_RealTime.Minute*100+BIOS_RealTime.Second;

		
	
	(*temp).McuFD_Pre_Para1=0;
	(*temp).McuFD_Pre_Para2=0;
	(*temp).McuFD_Pre_Para3=0;
	
	if(Initialization_Flag == true)
	{
		strncpy((*temp).McuFD_Action_Cmd, "CS", 2);			
	}
	
	if(Initialization_Flag == false)
	{
		strncpy((*temp).McuFD_Action_Cmd, "DZ", 2);			
	}	

	if(Current_State.Current_Mode == 0x03)
	{
		(*temp).McuFD_Motor1_Set_Speed = Instruction_To_FMCU.McuFD_Motor1_Set_Speed;
		(*temp).McuFD_LH_Set_Rud_Location = Instruction_To_FMCU.McuFD_LH_Set_Rud_Location;	
		(*temp).McuFD_LH_Set_Rud_Location = Instruction_To_FMCU.McuFD_RH_Set_Rud_Location;
	    (*temp).McuFD_RH_Set_Rud_Location = Instruction_To_FMCU.McuFD_UV_Set_Rud_Location;		
		(*temp).McuFD_RH_Set_Rud_Location = Instruction_To_FMCU.McuFD_LV_Set_Rud_Location;		
	}
		
			
	(*temp).McuFD_Power_Control= Instruction_To_FMCU.McuFD_Power_Control;
	
	/*************************test para*********************************/
#if 0
	 temp->McuFD_UTC_Date = 112233;
	 temp->McuFD_UTC_Time = 112233;
	 /*temp->McuFD_Action_Cmd[0] = 'C';*/
	 /*temp->McuFD_Action_Cmd[1] = 'S';*/
	 temp->McuFD_Action_Cmd[0] = 'D';
	 temp->McuFD_Action_Cmd[1] = 'Z';
	 temp->McuFD_Motor1_Set_Speed=100;
	 temp->McuFD_Motor2_Set_Speed=0;
	 temp->McuFD_LH_Set_Rud_Location=2162;
	 temp->McuFD_RH_Set_Rud_Location=1934;
	 temp->McuFD_UV_Set_Rud_Location=2162;
	 temp->McuFD_LV_Set_Rud_Location=1934;
	 temp->McuFD_Power_Control=0;
#endif	
	
	strncpy((*temp).McuFD_Head_Buf, "$MCUFD", 6);
	strncpy((*temp).McuFD_End_Buf,"*RN", strlen("*RN"));


	
	strncpy(ptr, (*temp).McuFD_Head_Buf, 6);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
		
	sprintf(ptr, "%03d", (*temp).McuFD_Msg_Num);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%06d", (*temp).McuFD_UTC_Date);
	ptr = ptr + strlen(ptr);		
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%06d", (*temp).McuFD_UTC_Time);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;

	sprintf(ptr, "%02d", (*temp).McuFD_Pre_Para1);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;	
	
	sprintf(ptr, "%02d", (*temp).McuFD_Pre_Para2);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;	
	
	sprintf(ptr, "%02d", (*temp).McuFD_Pre_Para3);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;			

	strncpy(ptr , (*temp).McuFD_Action_Cmd, 2);
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%05d", (*temp).McuFD_Motor1_Set_Speed);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%05d", (*temp).McuFD_Motor2_Set_Speed);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%04d", (*temp).McuFD_LH_Set_Rud_Location);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%04d", (*temp).McuFD_RH_Set_Rud_Location);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%04d", (*temp).McuFD_UV_Set_Rud_Location);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%04d", (*temp).McuFD_LV_Set_Rud_Location);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	sprintf(ptr, "%02d", (*temp).McuFD_Power_Control);   
	ptr = ptr + strlen(ptr);
	strncpy(ptr, ",", 1);
	ptr++;
	
	strncpy(ptr, (*temp).McuFD_End_Buf, strlen("*RN"));
	ptr = ptr + strlen(ptr);
	
	ptr = array;
		
	strncpy((char *)to_MCU_buf, ptr, strlen(ptr));	
	

}







void Pack_Data_To_UI12(_To_UI12 *temp)
{
	u8 ToUI12_Head_Buf[4] = {"$AUV"};
	u8 ToUI12_End_Buf[2] = {0xFF,0xFF};  
	

	u16 cycle_number = 0;
	
	u16 convert_u16_data1;
	u32 convert_u32_data2;	
	

	memcpy(temp->ToUI12_Head_Buf, ToUI12_Head_Buf, 4);
	temp->ToUI12_Msg_Length = ToUI12_Msg_Length;	
	temp->ToUI12_Msg_Num = Current_State.Msg_Num; 
	temp->ToUI12_ID = Current_State.ID;	
	temp->ToUI12_Ctrl_Mode = Current_State.Current_Mode;
	temp->ToUI12_Depth_Para1=Current_State.Current_Depth_Para1;
	temp->ToUI12_Depth_Para2=Current_State.Current_Depth_Para2;	
	temp->ToUI12_Height_Para1=Current_State.Current_Height_Para1;
	temp->ToUI12_Height_Para2=Current_State.Current_Height_Para2;
	temp->ToUI12_Remain_Time=Current_State.Current_Remain_Time;	
	temp->ToUI12_Spare_Para1=Current_State.Current_Spare_Para1;
	temp->ToUI12_Spare_Para2=Current_State.Current_Spare_Para2;
	temp->ToUI12_Work_Cmd=Current_State.Current_Work_Cmd;
	temp->ToUI12_Motor_Speed1=Current_State.Current_Motor_Speed1;
	temp->ToUI12_Motor_Speed2=Current_State.Current_Motor_Speed2;
	
	temp->ToUI12_HL_Rud_Angle=(LH_Ref_Location - (Current_State.Current_LH_Rud_Location))*360/4096;
	temp->ToUI12_HR_Rud_Angle=((Current_State.Current_RH_Rud_Location) - RH_Ref_Location)*360/4096;
	temp->ToUI12_VU_Rud_Angle=(UV_Ref_Location - (Current_State.Current_UV_Rud_Location))*360/4096;
	temp->ToUI12_VL_Rud_Angle=((Current_State.Current_LV_Rud_Location) - LV_Ref_Location)*360/4096;

	temp->ToUI12_Pres=(Current_State.Current_Pres)*1000;			
	temp->ToUI12_Temp=Current_State.Current_Temp;	
	temp->ToUI12_Depth=Current_State.Current_Dep;
	
	temp->ToUI12_Para1=(Current_State.Current_Para1);
	temp->ToUI12_Para2=(Current_State.Current_Para2);
	temp->ToUI12_Para3=(Current_State.Current_Para3);
	temp->ToUI12_Para4=(Current_State.Current_Para4);
	temp->ToUI12_Para5=(Current_State.Current_Para5);
	temp->ToUI12_Para6=(Current_State.Current_Para6);
	temp->ToUI12_Para7=(Current_State.Current_Para7);
	temp->ToUI12_Para8=(Current_State.Current_Para8);
	temp->ToUI12_Para9=(Current_State.Current_Para9);
	temp->ToUI12_Para10=(Current_State.Current_Para10);
	temp->ToUI12_Para11=(Current_State.Current_Para11);
	temp->ToUI12_Para12=(Current_State.Current_Para12);
	
	/**
	 * @brief DVL three-axis velocity uplink extension in body frame.
	 * @details Para5/6/7 carry BI_X/BI_Y/BI_Z in mm/s for the Jetson ES-EKF.
	 *          Bench polarity:
	 *          BI_X: surge, +X = forward.
	 *          BI_Y: sway, +Y = starboard.
	 *          BI_Z: heave, +Z = down.
	 * @author Tsinghua AUV Group
	 */
	temp->ToUI12_Para5 = (short int)DVL_Prase_Data.BI_X;  /* DVL Body X (mm/s) */
	temp->ToUI12_Para6 = (short int)DVL_Prase_Data.BI_Y;  /* DVL Body Y (mm/s) */
	temp->ToUI12_Para7 = (short int)DVL_Prase_Data.BI_Z;  /* DVL Body Z (mm/s) */

	/**
	 * @brief IMU three-axis angular-rate uplink extension in body frame.
	 * @details Para8/9/10 carry roll/pitch/yaw rates encoded as rad/s x 1000.
	 * @author Tsinghua AUV Group
	 */
	temp->ToUI12_Para8  = (short int)(IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[0] * 1000.0f);
	temp->ToUI12_Para9  = (short int)(IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[1] * 1000.0f);
	temp->ToUI12_Para10 = (short int)(IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[2] * 1000.0f);

	/**
	 * @brief PC104 relative-time uplink extension.
	 * @details Para3 carries packet pack uptime in milliseconds. Para4 carries
	 *          the latest DVL BI parse uptime in milliseconds. Para12 carries a
	 *          fixed marker so Jetson can distinguish new firmware from legacy
	 *          frames that only echoed command parameters.
	 * @author Tsinghua AUV Group
	 */
	temp->ToUI12_Para3 = Get_PC104_Uptime_Ms();
	temp->ToUI12_Para4 = DVL_BI_Uptime_Ms;
	temp->ToUI12_Para12 = PC104_UPTIME_VALID_MARKER;

	/**
	 * @brief Downlink receive echo extension for PC104 timing probes.
	 * @details Spare1 carries marker 0x4543, Spare2 carries the latest received
	 *          $CKTH frame number, and Para1 carries the PC104 receive uptime.
	 *          Together with Para3 pack uptime, Jetson can compute RTT and the
	 *          PC104 receive-to-pack interval without synchronized clocks.
	 * @author Tsinghua AUV Group
	 */
	if(g_pc104_timing_downlink_echo_valid == true)
	{
		temp->ToUI12_Spare_Para1 = PC104_DOWNLINK_ECHO_MARKER;
		temp->ToUI12_Spare_Para2 = (short int)g_pc104_timing_last_downlink_frame;
		temp->ToUI12_Para1 = g_pc104_timing_last_downlink_rx_uptime_ms;
	}
		
	temp->ToUI12_IMU_Heading=(Current_State.Current_IMU_Heading)*10;
	temp->ToUI12_IMU_Pitch=(Current_State.Current_IMU_Pitch)*10;
	temp->ToUI12_IMU_Roll=(Current_State.Current_IMU_Roll)*10;	
	temp->ToUI12_GPS_Heading=(Current_State.Current_GPS_Heading)*10;
	temp->ToUI12_GPS_Velocity=(Current_State.Current_GPS_Velocity_Kn)*10;
	temp->ToUI12_DVL_Velocity=(short int)(DVL_Prase_Data.BI_V / 100.0f);  /**< @brief DVL speed encoded as m/s x 10. */
	temp->ToUI12_Height=(Current_State.Current_Height)*10;
	
	temp->ToUI12_Cal_Longitude=(Current_State.Current_Cal_Longitude)*1000000;
	temp->ToUI12_Cal_Latitude=(Current_State.Current_Cal_Latitude)*1000000;
	temp->ToUI12_GPS_Longitude=(Current_State.Current_GPS_Longitude)*1000000;
	temp->ToUI12_GPS_Latitude=(Current_State.Current_GPS_Latitude)*1000000;
	
	temp->ToUI12_Total_Voltage=(Current_State.Current_Total_Voltage)*10;
	temp->ToUI12_Total_Current=(Current_State.Current_Total_Current)*10;
	
	temp->ToUI12_SOC=(Current_State.Current_SOC);
	temp->ToUI12_SOH=(Current_State.Current_SOH);
	
	temp->ToUI12_SingleMax_Voltage=(Current_State.Current_Single_Max_Voltage)*1000;
	temp->ToUI12_SingleMin_Voltage=(Current_State.Current_Single_Min_Voltage)*1000;	
	
	temp->ToUI12_SingleMax_Temp=(Current_State.Current_Single_Max_Temp);
	temp->ToUI12_SingleMin_Temp=(Current_State.Current_Single_Min_Temp);	
	
	temp->ToUI12_DevicePower_State=(Current_State.Current_Device_Power_State);
	temp->ToUI12_Cmd_State=(Current_State.Current_Cmd_State);	
	temp->ToUI12_Sail_State=(Current_State.Current_Sail_State);
	temp->ToUI12_Sys_Abnorm_Inf=(Current_State.Current_Sys_Abnorm_Inf);
	temp->ToUI12_Dev_Abnorm_Inf=(Current_State.Current_Dev_Abnorm_Inf);
	temp->ToUI12_BMS_Abnorm_Inf=(Current_State.Current_BMS_Abnorm_Inf);
	temp->ToUI12_Dev_Abnorm_Inf_Detail=(Current_State.Current_Dev_Abnorm_Inf_Detail);
	
	
	memcpy(temp->ToUI12_End_Buf, ToUI12_End_Buf, 2);
	
	/*****************test para***********/
#if 0
	 temp->ToUI12_Msg_Length=145;/*������144�����Ͻ��������145*/
	 temp->ToUI12_Msg_Num=1;
	 temp->ToUI12_ID = 2;
	 temp->ToUI12_Ctrl_Mode = 0x03;
	 temp->ToUI12_Depth_Para1=9;
	 temp->ToUI12_Depth_Para2=9;
	 temp->ToUI12_Height_Para1=8;
	 temp->ToUI12_Height_Para2=8;
	 temp->ToUI12_Remain_Time=100;
	 temp->ToUI12_Work_Cmd=0x80;
	 temp->ToUI12_Motor_Speed1=500;
	 temp->ToUI12_Motor_Speed2=600;
	 temp->ToUI12_HL_Rud_Angle=15; 
	 temp->ToUI12_HR_Rud_Angle=5; 
	 temp->ToUI12_VU_Rud_Angle=15; 
	 temp->ToUI12_VL_Rud_Angle=15; 
	 temp->ToUI12_Pres=30; 
	 temp->ToUI12_Temp=60;
	 temp->ToUI12_Depth=50;
	 temp->ToUI12_IMU_Heading=45;
	 temp->ToUI12_IMU_Pitch=20;
	 temp->ToUI12_IMU_Roll=1;	 
	 temp->ToUI12_GPS_Heading=1;
	 temp->ToUI12_GPS_Velocity=1;
	 temp->ToUI12_DVL_Velocity=1;
	 temp->ToUI12_Height=1;
	 temp->ToUI12_Cal_Longitude=1;
	 temp->ToUI12_Cal_Latitude=1;
	 temp->ToUI12_GPS_Longitude=1;	 
	 temp->ToUI12_GPS_Latitude=1;
	 temp->ToUI12_Total_Voltage=1;
	 temp->ToUI12_Total_Current=1;
	 temp->ToUI12_SOC=1;
	 temp->ToUI12_SOH=1;	 
	 temp->ToUI12_SingleMax_Voltage=1;
	 temp->ToUI12_SingleMin_Voltage=1;	 
	 temp->ToUI12_SingleMax_Temp=1;
	 temp->ToUI12_SingleMin_Temp=1;	 
	 temp->ToUI12_DevicePower_State=1;
	 temp->ToUI12_Cmd_State=1;
	 temp->ToUI12_Sail_State=1;
	 temp->ToUI12_Sys_Abnorm_Inf=1;
	 temp->ToUI12_Dev_Abnorm_Inf=1;
	 temp->ToUI12_BMS_Abnorm_Inf=1;
	 temp->ToUI12_Dev_Abnorm_Inf_Detail=1;
#endif
	 /***********************************/
	 
	/*���ṹ������洢��������*/
	memcpy(To_UI12_Buf, temp->ToUI12_Head_Buf, 4);
	To_UI12_Buf[4] = temp->ToUI12_Msg_Length;
	To_UI12_Buf[5] = temp->ToUI12_Msg_Num;
	To_UI12_Buf[6] = temp->ToUI12_ID;
	To_UI12_Buf[7] = temp->ToUI12_Ctrl_Mode;                
	
	convert_u16_data1 = (u16)(temp->ToUI12_Depth_Para1);        
	To_UI12_Buf[8] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[9] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = (u16)(temp->ToUI12_Depth_Para2);        
	To_UI12_Buf[10] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[11] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = (u16)(temp->ToUI12_Height_Para1);        
	To_UI12_Buf[12] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[13] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = (u16)(temp->ToUI12_Height_Para2);        
	To_UI12_Buf[14] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[15] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = (u16)(temp->ToUI12_Remain_Time);        
	To_UI12_Buf[16] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[17] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/

	convert_u16_data1 = (u16)(temp->ToUI12_Spare_Para1);
	To_UI12_Buf[18] = convert_u16_data1>>8;
	To_UI12_Buf[19] = convert_u16_data1;

	convert_u16_data1 = (u16)(temp->ToUI12_Spare_Para2);
	To_UI12_Buf[20] = convert_u16_data1>>8;
	To_UI12_Buf[21] = convert_u16_data1;
	
	To_UI12_Buf[22] = temp->ToUI12_Work_Cmd;     
	
	convert_u16_data1 = temp->ToUI12_Motor_Speed1;        
	To_UI12_Buf[23] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[24] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = temp->ToUI12_Motor_Speed2;        
	To_UI12_Buf[25] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[26] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = temp->ToUI12_HL_Rud_Angle;        
	To_UI12_Buf[27] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[28] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = temp->ToUI12_HR_Rud_Angle;        
	To_UI12_Buf[29] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[30] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = temp->ToUI12_VU_Rud_Angle;        
	To_UI12_Buf[31] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[32] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = temp->ToUI12_VL_Rud_Angle;        
	To_UI12_Buf[33] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[34] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = temp->ToUI12_Pres;        
	To_UI12_Buf[35] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[36] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	To_UI12_Buf[37] = temp->ToUI12_Temp;    
	
	convert_u16_data1 = (u16)(temp->ToUI12_Depth);        
	To_UI12_Buf[38] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[39] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	
	convert_u32_data2 = htonl((u32)(temp->ToUI12_Para1));        /*ת��Ϊ�����ֽ���*/
		for(cycle_number=0; cycle_number<4; cycle_number++)
			To_UI12_Buf[40+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
		
		
	convert_u32_data2 = htonl((u32)(temp->ToUI12_Para2));        /*ת��Ϊ�����ֽ���*/
		for(cycle_number=0; cycle_number<4; cycle_number++)
			To_UI12_Buf[44+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
			
		
	convert_u32_data2 = htonl((u32)(temp->ToUI12_Para3));        /*ת��Ϊ�����ֽ���*/
		for(cycle_number=0; cycle_number<4; cycle_number++)
			To_UI12_Buf[48+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
			
		
	convert_u32_data2 = htonl((u32)(temp->ToUI12_Para4));        /*ת��Ϊ�����ֽ���*/
		for(cycle_number=0; cycle_number<4; cycle_number++)
			To_UI12_Buf[52+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
			
		
	convert_u16_data1 = (u16)(temp->ToUI12_Para5);        
	To_UI12_Buf[56] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[57] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
	
	convert_u16_data1 = (u16)(temp->ToUI12_Para6);        
	To_UI12_Buf[58] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[59] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
					
	
	convert_u16_data1 = (u16)(temp->ToUI12_Para7);        
	To_UI12_Buf[60] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[61] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	
	convert_u16_data1 = (u16)(temp->ToUI12_Para8);        
	To_UI12_Buf[62] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[63] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
	
	convert_u16_data1 = (u16)(temp->ToUI12_Para9);        
	To_UI12_Buf[64] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[65] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
	
	convert_u16_data1 = (u16)(temp->ToUI12_Para10);        
	To_UI12_Buf[66] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[67] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
	
	convert_u16_data1 = (u16)(temp->ToUI12_Para11);        
	To_UI12_Buf[68] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[69] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
					
	
	convert_u16_data1 = (u16)(temp->ToUI12_Para12);        
	To_UI12_Buf[70] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[71] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
				

	convert_u16_data1 = (u16)(temp->ToUI12_IMU_Heading);        
	To_UI12_Buf[72] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[73] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = temp->ToUI12_IMU_Pitch;        
	To_UI12_Buf[74] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[75] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = temp->ToUI12_IMU_Roll;        
	To_UI12_Buf[76] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[77] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = (u16)(temp->ToUI12_GPS_Heading);        
	To_UI12_Buf[78] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[79] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = (u16)(temp->ToUI12_GPS_Velocity);        
	To_UI12_Buf[80] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[81] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = temp->ToUI12_DVL_Velocity;        
	To_UI12_Buf[82] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[83] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = (u16)(temp->ToUI12_Height);        
	To_UI12_Buf[84] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[85] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u32_data2 = htonl((temp->ToUI12_Cal_Longitude));        /*ת��Ϊ�����ֽ���*/
	for(cycle_number=0; cycle_number<4; cycle_number++)
		To_UI12_Buf[86+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
	
	convert_u32_data2 = htonl((temp->ToUI12_Cal_Latitude));        /*ת��Ϊ�����ֽ���*/
	for(cycle_number=0; cycle_number<4; cycle_number++)
		To_UI12_Buf[90+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
	
	convert_u32_data2 = htonl((temp->ToUI12_GPS_Longitude));        /*ת��Ϊ�����ֽ���*/
	for(cycle_number=0; cycle_number<4; cycle_number++)
		To_UI12_Buf[94+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
	
	convert_u32_data2 = htonl((temp->ToUI12_GPS_Latitude));        /*ת��Ϊ�����ֽ���*/
	for(cycle_number=0; cycle_number<4; cycle_number++)
		To_UI12_Buf[98+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
	
	convert_u16_data1 = (u16)(temp->ToUI12_Total_Voltage);        
	To_UI12_Buf[102] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[103] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = (u16)(temp->ToUI12_Total_Current);        
	To_UI12_Buf[104] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[105] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	To_UI12_Buf[106] = temp->ToUI12_SOC;   
	To_UI12_Buf[107] = temp->ToUI12_SOH;   
	
	convert_u16_data1 = (u16)(temp->ToUI12_SingleMax_Voltage);        
	To_UI12_Buf[108] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[109] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	convert_u16_data1 = (u16)(temp->ToUI12_SingleMin_Voltage);        
	To_UI12_Buf[110] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
	To_UI12_Buf[111] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
	
	To_UI12_Buf[112] = temp->ToUI12_SingleMax_Temp;   
	To_UI12_Buf[113] = temp->ToUI12_SingleMin_Temp;   
	
	convert_u32_data2 = htonl((u32)(temp->ToUI12_DevicePower_State));        /*ת��Ϊ�����ֽ���*/
	for(cycle_number=0; cycle_number<4; cycle_number++)
		To_UI12_Buf[114+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
	
	convert_u32_data2 = htonl((u32)(temp->ToUI12_Cmd_State));        /*ת��Ϊ�����ֽ���*/
	for(cycle_number=0; cycle_number<4; cycle_number++)
		To_UI12_Buf[118+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
	
	convert_u32_data2 = htonl((u32)(temp->ToUI12_Sail_State));        /*ת��Ϊ�����ֽ���*/
	for(cycle_number=0; cycle_number<4; cycle_number++)
		To_UI12_Buf[122+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
	
	convert_u32_data2 = htonl((u32)(temp->ToUI12_Sys_Abnorm_Inf));        /*ת��Ϊ�����ֽ���*/
	for(cycle_number=0; cycle_number<4; cycle_number++)
		To_UI12_Buf[126+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
	
	convert_u32_data2 = htonl((u32)(temp->ToUI12_Dev_Abnorm_Inf));        /*ת��Ϊ�����ֽ���*/
	for(cycle_number=0; cycle_number<4; cycle_number++)
		To_UI12_Buf[130+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
	
	convert_u32_data2 = htonl((u32)(temp->ToUI12_BMS_Abnorm_Inf));        /*ת��Ϊ�����ֽ���*/
	for(cycle_number=0; cycle_number<4; cycle_number++)
		To_UI12_Buf[134+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
	
	convert_u32_data2 = htonl((u32)(temp->ToUI12_Dev_Abnorm_Inf_Detail));        /*ת��Ϊ�����ֽ���*/
	for(cycle_number=0; cycle_number<4; cycle_number++)
		To_UI12_Buf[138+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
	
	To_UI12_Buf[142] = temp->ToUI12_Check_Sum=Check_Sum(To_UI12_Buf, ToUI12_Msg_Length - 3);;   
	memcpy(&To_UI12_Buf[143], temp->ToUI12_End_Buf, 2);   
	

}

void Unpack_Data_From_DVL_BI(u8 *temp_buf)
{
	
	    char *ptr = (char *)temp_buf;
	   /* char i[1];	����������Ч��־λA
	    char j[1]={"A"};*/	 
	    
		memcpy(DVL_Prase_Data.head_buf, temp_buf, 3);          /*֡ͷ*/
		ptr = strstr(ptr+1, ",");
		DVL_Prase_Data.BI_X = atoi(ptr+1);   /*X���ٶ�*/
		ptr = strstr(ptr+1, ","); 
		DVL_Prase_Data.BI_Y = atoi(ptr+1);   /*Y���ٶ�*/
		ptr = strstr(ptr+1, ","); 
		DVL_Prase_Data.BI_Z = atoi(ptr+1);   /*Z���ٶ�*/
		
		DVL_Prase_Data.BI_V = sqrt(((DVL_Prase_Data.BI_X)*(DVL_Prase_Data.BI_X))+((DVL_Prase_Data.BI_Y)*(DVL_Prase_Data.BI_Y))+((DVL_Prase_Data.BI_Z)*(DVL_Prase_Data.BI_Z)));   /*BI_V*/
		DVL_BI_Uptime_Ms = Get_PC104_Uptime_Ms();
		
		/*ptr = strstr(ptr+1, ","); 		
		ptr = strstr(ptr+1, ","); 
		strncpy(i, ptr+1, strlen(ptr+1));  ��Ч��־λ
		
		if(i[0] == j[0])
		{
			DVL_Prase_Data.BI_Valid_Flag=true;
		}
		else
		{
			DVL_Prase_Data.BI_Valid_Flag=false;
		}*/		
		/*DVL_Prase_Data.BI_Valid_Flag=true;*/
		memset(temp_buf, 0, From_DVL_BI_Length);/*���temp_buf*/	
		
}
void Unpack_Data_From_DVL_BD(u8 *temp_buf)
{
    char *ptr = (char *)temp_buf;
	memcpy(DVL_Prase_Data.head_buf, temp_buf, 3);          /*֡ͷ*/
	ptr = strstr(ptr+1, ",");
	DVL_Prase_Data.BD_Check = atof(ptr+1);   
	
	ptr = strstr(ptr+1, ","); 	
	ptr = strstr(ptr+1, ","); 	
	ptr = strstr(ptr+1, ","); 
	
	DVL_Prase_Data.BD_Height = atof(ptr+1);   
	
	memset(temp_buf, 0, From_DVL_BD_Length);	
	
}
void Unpack_Data_From_DVL_WI(u8 *temp_buf)
{

    char *ptr = (char *)temp_buf;
	memcpy(DVL_Prase_Data.head_buf, temp_buf, 3);          /*֡ͷ*/
	ptr = strstr(ptr+1, ",");
	DVL_Prase_Data.WI_X = atoi(ptr+1);   /*X���ٶ�*/
	ptr = strstr(ptr+1, ","); 
	DVL_Prase_Data.WI_Y = atoi(ptr+1);   /*Y���ٶ�*/
	ptr = strstr(ptr+1, ","); 
	DVL_Prase_Data.WI_Z = atoi(ptr+1);   /*Z���ٶ�*/
	
	DVL_Prase_Data.WI_V = sqrt(((DVL_Prase_Data.WI_X)*(DVL_Prase_Data.WI_X))+((DVL_Prase_Data.WI_Y)*(DVL_Prase_Data.WI_Y))+((DVL_Prase_Data.WI_Z)*(DVL_Prase_Data.WI_Z)));   /*WI_V*/
	
	/*DVL_Prase_Data.WI_Valid_Flag = true;*/
	memset(temp_buf, 0, From_DVL_WI_Length);	
}
void Unpack_Data_From_DVL_WD(u8 *temp_buf)
{
    char *ptr = (char *)temp_buf;
	memcpy(DVL_Prase_Data.head_buf, temp_buf, 3);          /*֡ͷ*/
	ptr = strstr(ptr+1, ",");
	DVL_Prase_Data.WD_Check = atof(ptr+1);   
	
	ptr = strstr(ptr+1, ","); 	
	ptr = strstr(ptr+1, ","); 	
	ptr = strstr(ptr+1, ","); 
	
	DVL_Prase_Data.WD_Depth = atof(ptr+1);   
	
	memset(temp_buf, 0, From_DVL_WD_Length);	
	
}
void Unpack_Data_From_DVL_ACK(u8 *temp_buf)
{
	char *ptr = (char *)temp_buf;
	memcpy(GetACKfromDVL.head_buf, temp_buf, 4);          /*֡ͷ*/
	ptr = strstr(ptr+1, ",");
	GetACKfromDVL.F_selftest= atof(ptr+1); /*F�����Լ�ģʽ��Ӧ*/		
	ptr = strstr(ptr+1, ",");
	GetACKfromDVL.A_channel= atof(ptr+1);  /*A,B,C,D�����ĸ�ͨ��*/	
	ptr = strstr(ptr+1, ",");
	GetACKfromDVL.B_channel= atof(ptr+1);  /*A,B,C,D�����ĸ�ͨ��*/	
	ptr = strstr(ptr+1, ",");
	GetACKfromDVL.C_channel= atof(ptr+1);  /*A,B,C,D�����ĸ�ͨ��*/		
	ptr = strstr(ptr+1, ",");
	GetACKfromDVL.D_channel= atof(ptr+1);  /*A,B,C,D�����ĸ�ͨ��*/		
	memset(temp_buf, 0, strlen((char *)temp_buf));	
	
}




void Unpack_Data_From_GPS_GGA(u8 *temp_buf)
{
	char N_Or_S;
	char E_Or_W;
	char *ptr = (char *)temp_buf;
	double Latitude_GPS = 0,Longitude_GPS = 0;
	u8 Latitude_Degree = 0 ,Longitude_Degree = 0;
	double Latitude_Minute = 0,Longitude_Minute = 0;
	int UTC_Hour=0;
	
	
	ptr = strstr((char *)temp_buf, ",");
	GPS_Prase_Data.UTC_Time = atof(ptr+1);                 /*1 hhmmss.ss,ȡ��ʱ�������*/
	      
	ptr = strstr(ptr+1, ","); 
	Latitude_GPS = atof(ptr+1);
	Latitude_Degree = (u8)(Latitude_GPS/100.);
    Latitude_Minute = (Latitude_GPS/100. - Latitude_Degree)*100.;
    GPS_Prase_Data.GPS_Latitude = Latitude_Degree + Latitude_Minute/60.;   /*2*/
	
	ptr = strstr(ptr+1, ",");                          
	N_Or_S = *(ptr + 1);                           /*3*/
	
	if('N' == N_Or_S)
		GPS_Prase_Data.GPS_Latitude = GPS_Prase_Data.GPS_Latitude;
	if('S' == N_Or_S)
		GPS_Prase_Data.GPS_Latitude = -GPS_Prase_Data.GPS_Latitude;
	
	ptr = strstr(ptr+1, ",");        
	Longitude_GPS = atof(ptr+1);             
	Longitude_Degree = (u8)(Longitude_GPS/100.);
	Longitude_Minute = (Longitude_GPS/100. - Longitude_Degree)*100.;
	GPS_Prase_Data.GPS_Longtitude = Longitude_Degree + Longitude_Minute/60.;  /*4*/
	
	
	
	ptr = strstr(ptr+1, ",");                          
	E_Or_W = *(ptr + 1);                           /*5*/
	
	if('E' == E_Or_W)
		GPS_Prase_Data.GPS_Longtitude = GPS_Prase_Data.GPS_Longtitude;
	if('W' == E_Or_W)
		GPS_Prase_Data.GPS_Longtitude = -GPS_Prase_Data.GPS_Longtitude;
	
	ptr = strstr(ptr+1, ",");                  /*6*/
	GPS_Prase_Data.GPS_Position_QC = atoi(ptr + 1);  /*GPS״̬��0���ϣ�1��Ч*/
	
	/*printf("gps_sta.utcdmy is:%d\n",gps_sta.utcdmy);
					printf("gps_sta.utchms is:%f\n",gps_sta.utchms);*/
	
	/*������ʱ�����*/

	if((GPS_Prase_Data.GPS_Position_QC & 0x01) == 0x01)   /*���GPS״̬��Ч*/      
	{
		Recv_From_GPS_QC_Flag = true;/*���GPS״̬��Ч,��������ں�λ����*/
		
		if(GPS_Prase_Data.UTC_Time > 0)/*���UTCʱ����Ч*/  
		{
			UTC_Hour = (int)(((int)GPS_Prase_Data.UTC_Time) / 10000);
			BiosTimeSetting.minute = (int)((((int)GPS_Prase_Data.UTC_Time) - UTC_Hour*10000)/100) ;
			BiosTimeSetting.second = (int)GPS_Prase_Data.UTC_Time - UTC_Hour*10000 - BiosTimeSetting.minute*100;
			
			BiosTimeSetting.hour = UTC_Hour + 8;
			
		}
		/*printf("year:%d    month:%d   day:%d   hour:%d   min:%d   sec:%d\n",year, month, day, hour, min, sec);*/
	}
	
	if((GPS_Prase_Data.GPS_Position_QC & 0x01) != 0x01)   /*���GPS״̬��Ч*/    
	{
		Not_Recv_From_GPS_No++;/*���GPS״̬��Ч,�������Security.c�ͻὫRecv_From_GPS_QC_Flag��true*/
	}
	
	memset(temp_buf, 0, strlen((char *)temp_buf));
}

void Unpack_Data_From_GPS_VTG(u8 *temp_buf)
{
	char *ptr = (char *)temp_buf;	
	ptr = strstr(ptr+1, ",");
	ptr = strstr(ptr+1, ","); 
	ptr = strstr(ptr+1, ","); 
	GPS_Prase_Data.GPS_Course = atof(ptr+1);   /*ȡ���Եشű����򣬵�λΪ��*/
	ptr = strstr(ptr+1, ","); 
	ptr = strstr(ptr+1, ","); 
	GPS_Prase_Data.GPS_Velocity_Kn = atof(ptr+1);   /*ȡ���Ե��ٶȣ���λ�ǽ�*/
	ptr = strstr(ptr+1, ","); 
	ptr = strstr(ptr+1, ","); 	
	GPS_Prase_Data.GPS_Velocity_Kmph = atof(ptr+1);  /*ȡ���Ե��ٶȣ���λ��ǧ��ÿСʱ*/	
	memset(temp_buf, 0, strlen((char *)temp_buf));
}







void Unpack_Data_From_UI3(u8 *temp_buf)
{
  if(temp_buf[6] == Vehicle_No) 
  {
	
	memcpy(UI_BEIDOU_Instruction.FromUI3_Head_BUF, temp_buf, 4);
	UI_BEIDOU_Instruction.FromUI3_Msg_Length = temp_buf[4];
	UI_BEIDOU_Instruction.FromUI3_Msg_Num = temp_buf[5];
	UI_BEIDOU_Instruction.FromUI3_ID = temp_buf[6];
	UI_BEIDOU_Instruction.FromUI3_Ctrl_Mode = temp_buf[7];
	UI_BEIDOU_Instruction.FromUI3_Depth_Para1 = (temp_buf[8] << 8) + temp_buf[9];
	UI_BEIDOU_Instruction.FromUI3_Depth_Para2 = (temp_buf[10] << 8) + temp_buf[11];
	UI_BEIDOU_Instruction.FromUI3_Height_Para1 = (temp_buf[12] << 8) + temp_buf[13];
	UI_BEIDOU_Instruction.FromUI3_Height_Para2 = (temp_buf[14] << 8) + temp_buf[15];
	UI_BEIDOU_Instruction.FromUI3_Remain_Time= (temp_buf[16] << 8) + temp_buf[17];
	
	if((temp_buf[18]&0x80) == 0x00)
	{
		UI_BEIDOU_Instruction.FromUI3_Spare_Para1= (temp_buf[18] << 8) + temp_buf[19];
	}
	if((temp_buf[18]&0x80) == 0x80)
	{
		UI_BEIDOU_Instruction.FromUI3_Spare_Para1= (u16)((temp_buf[18]<<8) + temp_buf[19]-65536);
		 
	}
	
	if((temp_buf[20]&0x80) == 0x00)
	{
		UI_BEIDOU_Instruction.FromUI3_Spare_Para2= (temp_buf[20] << 8) + temp_buf[21];
	}
	if((temp_buf[20]&0x80) == 0x80)
	{
		UI_BEIDOU_Instruction.FromUI3_Spare_Para2= (u16)((temp_buf[20]<<8) + temp_buf[21]-65536);
		 
	}
		
	UI_BEIDOU_Instruction.FromUI3_Work_Cmd=temp_buf[22];

	
	if((temp_buf[23]&0x80) == 0x00)
	{
	   UI_BEIDOU_Instruction.FromUI3_Back_Lat =  ((temp_buf[23]<<24) + (temp_buf[24]<<16)+ (temp_buf[25]<<8)+ temp_buf[26]);	
	}
	if((temp_buf[23]&0x80) == 0x80)
	{
	   UI_BEIDOU_Instruction.FromUI3_Back_Lat =  ((temp_buf[23]<<24) + (temp_buf[24]<<16)+ (temp_buf[25]<<8)+ temp_buf[26]-pow(2,32));
	}
			
	
	if((temp_buf[27]&0x80) == 0x00)
	{
	   UI_BEIDOU_Instruction.FromUI3_Back_Lon =  ((temp_buf[27]<<24) + (temp_buf[28]<<16)+ (temp_buf[29]<<8)+ temp_buf[30]);	
	}
	if((temp_buf[27]&0x80) == 0x80)
	{
	   UI_BEIDOU_Instruction.FromUI3_Back_Lon =  ((temp_buf[27]<<24) + (temp_buf[28]<<16)+ (temp_buf[29]<<8)+ temp_buf[30]-pow(2,32));
	}

	UI_BEIDOU_Instruction.FromUI3_Check_Sum = temp_buf[31];
	memcpy(UI_BEIDOU_Instruction.FromUI3_End_Buf, temp_buf+32, 2);
	memset(temp_buf, 0, From_UI_BEIDOU_Length);
  }
}


void Pack_Data_To_UI3(_ToUI3 *temp)
{
	/*
	u8 BEIDOU_Head_Buf[6] = {"$CCTXA"};	
	u8 BEIDOUID[7] = {"0989564"};*/	
	u8 ToUI3_Head_Buf[4] = {"$AUV"};	
	u8 ToUI3_End_Buf[2] = {0xFF,0xFF}; 

	/*
	memcpy(temp->BEIDOU_Head_Buf, BEIDOU_Head_Buf, 6);
	memcpy(temp->BEIDOUID, BEIDOUID, 7);*/	
	memcpy(temp->ToUI3_Head_Buf, ToUI3_Head_Buf, 4);

	u16 cycle_number = 0;
	u16 convert_u16_data1;
	u32 convert_u32_data2;
	
	/*
	int i = 0;
	int j = 0;*/

	
	u8 Check_Sum_buf[256] = {0};
	/*u8 BEIDOU_CRC_buf[256] = {0};
	u8 BEIDOU_CRC_L; */
	
	temp->ToUI3_Msg_Length = ToUI3_Msg_Length;	
	temp->ToUI3_Msg_Num = Current_State.Msg_Num; 
	temp->ToUI3_ID = Current_State.ID;	
	temp->ToUI3_Ctrl_Mode = Current_State.Current_Mode;
	temp->ToUI3_Depth_Para1=Current_State.Current_Depth_Para1;
	temp->ToUI3_Depth_Para2=Current_State.Current_Depth_Para2;
	temp->ToUI3_Height_Para1=Current_State.Current_Height_Para1;
	temp->ToUI3_Height_Para2=Current_State.Current_Height_Para2;
	temp->ToUI3_Remain_Time=Current_State.Current_Remain_Time;
	temp->ToUI3_Spare_Para1=Current_State.Current_Spare_Para1;
	temp->ToUI3_Spare_Para2=Current_State.Current_Spare_Para2;		
	temp->ToUI3_Back_Longitude=Current_State.Back_Lon;/*Э������д��Back_Lon����Ҫȷ��һ���ǲ���Current_Cal_Longitude��������Ҫ�ڽṹ���������¶���һ��Back_Lon*/
	temp->ToUI3_Back_Latitude=Current_State.Back_Lat;/*Э������д��Back_Lat����Ҫȷ��һ���ǲ���Current_Cal_Latitude��������Ҫ�ڽṹ���������¶���һ��Back_Lat*/
	temp->ToUI3_Pres=(Current_State.Current_Pres)*1000;	
	temp->ToUI3_Temp=Current_State.Current_Temp;	
	temp->ToUI3_Depth=(Current_State.Current_Dep)*10;	
	temp->ToUI3_IMU_Heading=(Current_State.Current_IMU_Heading)*10;	
	temp->ToUI3_IMU_Pitch=(Current_State.Current_IMU_Pitch)*10;	
	temp->ToUI3_IMU_Roll=(Current_State.Current_IMU_Roll)*10;		
	temp->ToUI3_GPS_Heading=(Current_State.Current_GPS_Heading)*10;	
	temp->ToUI3_GPS_Velocity=(Current_State.Current_GPS_Velocity_Kn)*10;	
	temp->ToUI3_DVL_Velocity=(Current_State.Current_DVL_Velocity_Kn)*10;	
	temp->ToUI3_Height=(Current_State.Current_Height)*10;	
	temp->ToUI3_GPS_Longitude=(Current_State.Current_GPS_Longitude)*1000000;	
	temp->ToUI3_GPS_Latitude=(Current_State.Current_GPS_Latitude)*1000000;
	temp->ToUI3_Total_Voltage=(Current_State.Current_Total_Voltage)*10;	
	temp->ToUI3_SOC=Current_State.Current_SOC;	
	temp->ToUI3_SOH=Current_State.Current_SOH;	
	temp->ToUI3_Sail_State=Current_State.Current_Sail_State;	
	temp->ToUI3_Sys_Abnorm_Inf=Current_State.Current_Sys_Abnorm_Inf;
	
	memcpy(temp->ToUI3_End_Buf, ToUI3_End_Buf, 2);

	/*****************test para***********/
#if 0
	 temp->ToUI3_Msg_Length=145;
	 temp->ToUI3_Msg_Num=1;
	 temp->ToUI3_ID = 2;
	 temp->ToUI3_Ctrl_Mode = 0x03;
	 temp->ToUI3_Depth_Para1=9;
	 temp->ToUI3_Depth_Para2=9;
	 temp->ToUI3_Height_Para1=8;
	 temp->ToUI3_Height_Para2=8;
	 temp->ToUI3_Remain_Time=100;
	 temp->ToUI3_Spare_Para1=80;
	 temp->ToUI3_Spare_Para2=10;
	 temp->ToUI3_Back_Longitude=60;
	 temp->ToUI3_Back_Latitude=15; 
	 temp->ToUI3_Pres=5; 
	 temp->ToUI3_Temp=15; 
	 temp->ToUI3_Depth=15; 
	 temp->ToUI3_IMU_Heading=30; 
	 temp->ToUI3_IMU_Pitch=60;
	 temp->ToUI3_IMU_Roll=50;
	 temp->ToUI3_GPS_Heading=45;
	 temp->ToUI3_GPS_Velocity=20;
	 temp->ToUI3_DVL_Velocity=1;	 
	 temp->ToUI3_Height=1;
	 temp->ToUI3_GPS_Longitude=1;
	 temp->ToUI3_GPS_Latitude=1;
	 temp->ToUI3_Total_Voltage=1;
	 temp->ToUI3_SOC=1;
	 temp->ToUI3_SOH=1;
	 temp->ToUI3_Sail_State=1;
	 temp->ToUI3_Sys_Abnorm_Inf=1;
#endif
	 /***********************************/
	 
		 
		/*���ṹ������洢�������У������ֽ�Ҳ���Ǵ�˷��͵���˼	
	    memcpy(To_UI3_Buf, temp->BEIDOU_Head_Buf, 6);
	    memcpy(&To_UI3_Buf[6], ",", 1);  
	    memcpy(&To_UI3_Buf[7], temp->BEIDOUID, 6);
	    memcpy(&To_UI3_Buf[13], ",", 1);  
	    memcpy(&To_UI3_Buf[14], "1", 1);
	    memcpy(&To_UI3_Buf[15], ",", 1);  
	    memcpy(&To_UI3_Buf[16], "1", 1);
	    memcpy(&To_UI3_Buf[17], ",", 1);*/  

	    
	    memcpy(To_UI3_Buf, temp->ToUI3_Head_Buf, 4);

	    To_UI3_Buf[4] = temp->ToUI3_Msg_Length;
	    To_UI3_Buf[5] = temp->ToUI3_Msg_Num;
	    To_UI3_Buf[6] = temp->ToUI3_ID;
	    To_UI3_Buf[7] = temp->ToUI3_Ctrl_Mode;                
		
		convert_u16_data1 = (u16)(temp->ToUI3_Depth_Para1);        
		To_UI3_Buf[8] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[9] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		convert_u16_data1 = (u16)(temp->ToUI3_Depth_Para2);        
		To_UI3_Buf[10] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[11] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		convert_u16_data1 = (u16)(temp->ToUI3_Height_Para1);        
		To_UI3_Buf[12] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[13] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		convert_u16_data1 = (u16)(temp->ToUI3_Height_Para2);        
		To_UI3_Buf[14] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[15] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		convert_u16_data1 = (u16)(temp->ToUI3_Remain_Time);        
		To_UI3_Buf[16] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[17] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		convert_u16_data1 = (u16)(temp->ToUI3_Spare_Para1);        
		To_UI3_Buf[18] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[19] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/		
		
		convert_u16_data1 = (u16)(temp->ToUI3_Spare_Para2);        
		To_UI3_Buf[20] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[21] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/	
		
		convert_u32_data2 = htonl((temp->ToUI3_Back_Longitude));        /*ת��Ϊ�����ֽ���*/
		for(cycle_number=0; cycle_number<4; cycle_number++)
			To_UI3_Buf[22+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
		
		convert_u32_data2 = htonl((temp->ToUI3_Back_Latitude));        /*ת��Ϊ�����ֽ���*/
		for(cycle_number=0; cycle_number<4; cycle_number++)
			To_UI3_Buf[26+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
		
		convert_u16_data1 = temp->ToUI3_Pres;        
		To_UI3_Buf[30] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[31] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		To_UI3_Buf[32] = temp->ToUI3_Temp;    
		
		convert_u16_data1 = (u16)(temp->ToUI3_Depth);        
		To_UI3_Buf[33] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[34] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		convert_u16_data1 = (u16)(temp->ToUI3_IMU_Heading);        
		To_UI3_Buf[35] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[36] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		convert_u16_data1 = temp->ToUI3_IMU_Pitch;        
		To_UI3_Buf[37] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[38] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		convert_u16_data1 = temp->ToUI3_IMU_Roll;        
		To_UI3_Buf[39] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[40] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		convert_u16_data1 = (u16)(temp->ToUI3_GPS_Heading);        
		To_UI3_Buf[41] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[42] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		convert_u16_data1 = (u16)(temp->ToUI3_GPS_Velocity);        
		To_UI3_Buf[43] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[44] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		convert_u16_data1 = temp->ToUI3_DVL_Velocity;        
		To_UI3_Buf[45] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[46] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		convert_u16_data1 = (u16)(temp->ToUI3_Height);        
		To_UI3_Buf[47] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[48] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		convert_u32_data2 = htonl((temp->ToUI3_GPS_Longitude));        /*ת��Ϊ�����ֽ���*/
		for(cycle_number=0; cycle_number<4; cycle_number++)
			To_UI3_Buf[49+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 

		convert_u32_data2 = htonl((temp->ToUI3_GPS_Latitude));        /*ת��Ϊ�����ֽ���*/
		for(cycle_number=0; cycle_number<4; cycle_number++)
			To_UI3_Buf[53+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
		
		convert_u16_data1 = (u16)(temp->ToUI3_Total_Voltage);        
		To_UI3_Buf[57] = convert_u16_data1>>8;/*�൱��ȡ�߰�λ*/
		To_UI3_Buf[58] = convert_u16_data1;	 /*ȡ�Ͱ�λ   ת��Ϊ�����ֽ���*/
		
		To_UI3_Buf[59] = temp->ToUI3_SOC;   
		To_UI3_Buf[60] = temp->ToUI3_SOH;   
		
		convert_u32_data2 = htonl((temp->ToUI3_Sail_State));        /*ת��Ϊ�����ֽ���*/
		for(cycle_number=0; cycle_number<4; cycle_number++)
			To_UI3_Buf[61+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
		
		convert_u32_data2 = htonl((temp->ToUI3_Sys_Abnorm_Inf));        /*ת��Ϊ�����ֽ���*/
		for(cycle_number=0; cycle_number<4; cycle_number++)
			To_UI3_Buf[65+cycle_number] = *((u8 *)&convert_u32_data2 + cycle_number); 
		
		To_UI3_Buf[69] = temp->ToUI3_Check_Sum=Check_Sum(Check_Sum_buf, 69); 
		
		memcpy(&To_UI3_Buf[70], temp->ToUI3_End_Buf, 2);
		/*�����Լ����ݵ�У���
		for(i=18;i<87;i++)
		{
			Check_Sum_buf[i-18]=To_UI3_Buf[i];
		}
		
		To_UI3_Buf[87] = temp->ToUI3_Check_Sum=Check_Sum(Check_Sum_buf, 69); 
		
		memcpy(&To_UI3_Buf[88], temp->ToUI3_End_Buf, 2); */
		
		/*���Լ���hex������ת��Ϊascii��
		for(i=18;i<89;i++)
		{
			To_UI3_Buf[i]=	HEX_to_ASCII(To_UI3_Buf[i]);
		}		*/
		
		/*���㱱���̱��ĵ�У��
		for(j=1;j<90;j++)
		{
			BEIDOU_CRC_buf[j-1]=To_UI3_Buf[j];
		}	
		
		BEIDOU_CRC_L =  Data_XOR(BEIDOU_CRC_buf, 90);
		
		memcpy(&To_UI3_Buf[90], "*", 1); 
		
		To_UI3_Buf[91] = temp->BEIDOU_CRC_L;*/
		
		memset(Check_Sum_buf, 0, 72);
		
		
}






	
void Unpack_Data_From_IMU(u8 *temp_buf)
{
	 if(1)/**/
	  {	
	
		int i;
		
		IMU_Prase_Data.head_buf=temp_buf[0];
		for (i=0; i<3; i++) 
		{
			IMU_Prase_Data.Roll_Pitch_Yaw[i] = FloatFromBytes(&temp_buf[1 + i*4]);
			
			IMU_Prase_Data.Roll_Pitch_Yaw[i]=(IMU_Prase_Data.Roll_Pitch_Yaw[i]*(180/3.1415926));/*radת��Ϊ��*/
			
			IMU_Prase_Data.Roll_Pitch_Yaw[2] = IMU_Prase_Data.Roll_Pitch_Yaw[2]+139.0;	/*����У׼�õ�*/
			
			IMU_Prase_Data.AngRateX_AngRateY_AngRateZ[i] = FloatFromBytes(&temp_buf[13 + i*4]);	
			
			
			
		}
		memset(temp_buf, 0, 32);
		
	  }
}




void Unpack_Data_From_PSD(u8 *temp_buf)
{
 
	PSD_Prase_Data._From_PSD = temp_buf[4];          
	memset(temp_buf, 0, 4);
    
}


void Pack_Data_To_PSD(_ToPSD *temp)
{
	u16 ii = 0;	
	
	if(1)/*�������,���ݻ�����ִ�к��������Ȼ����Ƶ���ƶ�Ӧ�ĵ�������*/
	{
		temp->head_buf = 0xAA;
		temp->command_code= 0x11; 
		temp->msg_length=0x01; 
		
		temp->white_led_power=0x01; 
		temp->blue_led_power=0x01; 
		temp->red_led_power=0x01; 
		temp->yellow_led_power=0x01; 
		
		   /*���ṹ������洢��������*/
		   to_PSD_buf[0]= temp->head_buf;
		   to_PSD_buf[1]= temp->command_code;
		   to_PSD_buf[2]= temp->msg_length;
		   to_PSD_buf[3] |= temp->white_led_power&0x01;	/*ȡwhite_led_power�����λֵ������,white_led_power�Ѿ���powerprocess.c�б�������ֵΪ0x01������������*/
		   to_PSD_buf[3] |= temp->blue_led_power<<1;
		   to_PSD_buf[3] |= temp->red_led_power<<2;
		   to_PSD_buf[3] |= temp->yellow_led_power<<3;

		   
		   for(ii = 0 , temp->check_sum = 0; ii<4; ii++)
		   {
			   temp->check_sum += to_PSD_buf[ii]; 
		   }
		   to_PSD_buf[4] = temp->check_sum;
	}

}




/*CRCУ���㷨*/
/*
 * @function:CRC16У���㷨
 * @para:
 * puchMsg:��������޷��ŵ��ֽ�������
 * usDataLen������������鳤�ȣ�
 * @return:CRCУ����
 * */
u16 CRC16_MODBUS(u8* puchMsg, int usDataLen)
{
	u16 wCRCin = 0xFFFF;
	u16 wCPoly = 0x8005;
	byte wChar = 0;
	int ii = 0, jj= 0;


	for (ii = 0; ii < usDataLen; ii++)
	{
		wChar = puchMsg[ii];
		wCRCin ^= (u16)(InvertUint8(wChar) << 8);
		for (jj = 0; jj < 8; jj++)
		{
			if ((wCRCin & 0x8000) > 0)
				wCRCin = (u16)((wCRCin << 1) ^ wCPoly);
			else
				wCRCin = (u16)(wCRCin << 1);
		}
	}
	return InvertUint16(wCRCin);
}


/*��������ʱ��HEXת����ASCII*/
u8 ASCII_to_HEX(u8 aChar)
{
	if((aChar>=0x30)&&(aChar<=0x39))
	{
		aChar -= 0x30;
	}
	else if((aChar>=0x41)&&(aChar<=0x46))/*��д��ĸ*/
	{
		aChar -= 0x37;
	}
	return aChar;   
}

/*��������ʱ��ASCIIת����HEX*/
u8 HEX_to_ASCII(u8  aHex)
{
	if(aHex <= 0x09)
	{
		aHex += 0x30;
	}
	else if((aHex>=10)&&(aHex<=15))/*A-F*/
	{
		aHex += 0x37;
	}
    return aHex;
	 
}



/*��������ʱ�������֤*/
uint8_t Data_XOR(uint8_t* data, uint8_t num)
{
  uint8_t xor,i;
  xor=data[0];
  if(data==NULL)
  {
     return 0;
  }
  else
  {
    for(i=1;i<num;i++)
    { 
    xor=xor^data[i];
    }
  }
  return xor;
}






/*У��ͣ��ۼӺͣ��Լ��ӵ�*/
u16 Check_Sum (u8* puchMsg1, int usDataLen)
{
        u16 tmp = 0;
        int i = 0;
        
        for (i = 0; i < usDataLen; i++)
        {
            tmp += puchMsg1[i];
        }
        tmp=tmp&0xff;
        return tmp;
}


byte InvertUint8(byte srcBuf)
{
	byte tmp = 0;
	int ii = 0;

	for (ii = 0; ii < 8; ii++)
	{
		if ((srcBuf & (1 << ii)) == (1 << ii))
			tmp |= (byte)(1 << (7 - ii));
	}
	return tmp;
}

u16 InvertUint16(u16 srcBuf)
{
	u16 tmp = 0;
	int ii = 0;

	for (ii = 0; ii < 16; ii++)
	{
		if ((srcBuf & (1 << ii)) == (1 << ii))
			tmp |= (u16)(1 << (15 - ii));
	}
	return tmp;
}

/*�޾��Ľ����ֽں���*/
float FloatFromBytes(const unsigned char* pBytes)
{
	float f = 0;	
	((BYTE*)(&f))[0] = pBytes[3];
	((BYTE*)(&f))[1] = pBytes[2];
	((BYTE*)(&f))[2] = pBytes[1];
	((BYTE*)(&f))[3] = pBytes[0];	
	return f; 
}

void DVL_BI_Speed_Integral(void)
{ 
	ReadBIOSRealTime();
	Integ_t1=BIOS_RealTime.Hour*3600+BIOS_RealTime.Minute*60+BIOS_RealTime.Second;/*��¼һ��ʱ�������λ��*/	
	
	BI_V_Pass[1] = DVL_Prase_Data.BI_Y;
	
	if(Integ_t1 > Integ_t2)
	{
	  /*����*/
	  BI_displayment[1] = BI_displayment[0] + ((BI_V_Pass[1] +BI_V_Pass[0])/2)*(Integ_t1-Integ_t2);
    }

	
	/*����ǰ�ٶ�,ʱ�串����һ��*/ 	
	Integ_t2=Integ_t1;/*����һ��ʱ���������Integ_t2*/
	BI_V_Pass[0] = BI_V_Pass[1];
	BI_displayment[0]=BI_displayment[1];
}

void DVL_WI_Speed_Integral(void)
{
	ReadBIOSRealTime();
	
	Integ_t1=BIOS_RealTime.Hour*3600+BIOS_RealTime.Minute*60+BIOS_RealTime.Second;/*��¼һ��ʱ�������λ��*/
	
	WI_V_Pass[1] = DVL_Prase_Data.WI_Y;	
	
	if(Integ_t1 > Integ_t2)
	{
	  /*����*/
	  WI_displayment[1] = WI_displayment[0] + ((WI_V_Pass[1] +WI_V_Pass[0])/2)*(Integ_t1-Integ_t2);
	}

	/*����ǰ�ٶ�,ʱ�串����һ��*/ 	
	Integ_t2=Integ_t1;/*����һ��ʱ���������Integ_t2*/
	WI_V_Pass[0] = WI_V_Pass[1];
	WI_displayment[0]=WI_displayment[1];
}

