#include "AgreedTerms.h"


extern void UartSendToBEIDOUTask(void);
extern void UartRecvFormBEIDOUTask(void);

extern void NetSendTask(void);
extern void NetRecvTask(void);

extern void UartSendToPSDTask(void);
extern void UartRecvFormPSDTask(void);


extern void UartRecvFormGPSTask(void);


extern void UartRecvFormDVLTask(void);


extern void UartRecvFormIMUTask(void);

extern void UartSendToLORATask(void);
extern void UartRecvFormLORATask(void);


extern void UartRecvFormBMSTask(void);


extern int com_read_ex(int fd, char *buffer, size_t maxbytes, struct timeval *pTimeOut);
extern u16 CRC16_MODBUS(u8* puchMsg, int usDataLen);
extern u16 Check_Sum(u8* puchMsg1, int usDataLen);


extern SEM_ID semUartSendToBEIDOUTask;
extern SEM_ID semUartRecvFormBEIDOUTask;
extern SEM_ID semPackBEIDOUDataTask;
extern SEM_ID semUnpackBEIDOUDataTask;

extern SEM_ID semUartSendToPSDTask;
extern SEM_ID semUartRecvFormPSDTask;
extern SEM_ID semPackPSDDataTask;
extern SEM_ID semUnpackPSDDataTask;                                                                       


extern SEM_ID semUartRecvFormGPSTask;
extern SEM_ID semUnpackGPSDataTask; 


extern SEM_ID semUartRecvFormDVLTask;
extern SEM_ID semUnpackDVLDataTask; 

extern SEM_ID semUartSendToLORATask;
extern SEM_ID semUartRecvFormLORATask;

extern SEM_ID semUnpackLORADataTask;   


extern SEM_ID semUartRecvFormBMSTask;
extern SEM_ID semUnpackBMSDataTask; 

extern SEM_ID semNetSendTask;
extern SEM_ID semNetRecvTask;
extern SEM_ID semPackNetDataTask;
extern SEM_ID semUnpackNetDataTask;


extern SEM_ID semUartRecvFormIMUTask;
extern SEM_ID semUnpackIMUDataTask; 


extern unsigned short int DEBUG;

extern char *g_ExtComName[];  /*资源在test文件中定义*/



extern bool send_TXSQ_to_Beid_to_beid_flag;		
extern bool send_MSG_to_PSD_flag;
/*extern bool send_MSG_to_GPS_flag;*/
/*extern bool send_MSG_to_DVL_flag;*/
extern bool send_MSG_to_Compass_flag;
extern bool send_MSG_to_LORA_flag;
extern bool send_MSG_to_BMS_flag;


extern bool Recv_From_WIFI_Correct_Flag;
extern bool Recv_From_FMCU_Correct_Flag;
extern bool Recv_From_WIFI_OK_No_Flag;

extern bool WIFI_Socket_Initial_Flag;
extern bool FMCU_Socket_Initial_Flag;

			


extern u16 ToUI12_Msg_Length;
extern u16 From_UI_WIFI_Length;

extern u16 ToLORALength;
extern u16 FromLORALength;

extern u16 ToUI3_Msg_Length;
extern u16 From_UI_BEIDOU_Length;

extern u16 From_DVL_BI_Length;
extern u16 From_DVL_BD_Length;
extern u16 From_DVL_WI_Length;
extern u16 From_DVL_WD_Length;





extern u16 From_BMS_SS_Length;
extern u16 From_BMS_CS_Length;

extern u16 FromMCULength;	

extern u16 From_IMU_Length;


extern u8 To_UI12_Buf[];
extern u8 From_WIFI_Buf[];
extern u8 to_LORA_buf[];
extern u8 From_LORA_Buf[];

extern u8 to_BMS_summary_state_buf[];
extern u8 to_BMS_critical_state_buf[];
extern u8 From_BMS_SS_Buf[];
extern u8 From_BMS_CS_Buf[];


extern u8 from_GPS_buf[];
extern u8 from_DVL_buf[];

extern u8 To_UI3_Buf[];


extern u8 to_MCU_buf[];
extern u8 From_FMCU_Buf[];

extern u8 to_Compass_buf[];
extern u8 From_IMU_Buf[];





extern u8 to_Beid_XTZJ_buf[];
extern u8 to_PSD_buf[];
extern u8 From_PSD_Buf[];
extern u8 From_BEIDOU_Buf[];
extern u8 From_BEIDOU_Buf_Self[];
extern u8 from_Beid_FKXX_buf[];
extern u8 from_Beid_ZJXX_buf[];

extern u8 From_GPS_GGA_Buf[];
extern u8 From_GPS_VTG_Buf[];

extern u8 From_DVL_BI_Buf[];
extern u8 From_DVL_BD_Buf[];
extern u8 From_DVL_WI_Buf[];
extern u8 From_DVL_WD_Buf[];
extern u8 From_DVL_ACK_Buf[];

extern u8 selftest_buf[];


extern bool Recv_From_WIFI_Correct_Flag;
extern bool WIFI_Socket_Initial_Flag;

extern bool Recv_From_FMCU_Correct_Flag;
extern bool FMCU_Socket_Initial_Flag;

extern bool Recv_From_LORA_Correct_Flag;



extern bool Recv_From_IMU_Correct_Flag;

extern bool Recv_From_BMS_SS_Correct_Flag;
extern bool Recv_From_BMS_CS_Correct_Flag;




extern bool Recv_From_BEIDOU_Correct_Flag;

extern bool Recv_From_PSD_Correct_Flag;

extern bool Recv_From_GPS_GGA_Correct_Flag;
extern bool Recv_From_GPS_VTG_Correct_Flag;
extern bool Recv_From_GPS_QC_Flag;

extern bool BI_Data_Valid_Flag;
extern bool BD_Data_Valid_Flag;
extern bool WI_Data_Valid_Flag;
extern bool WD_Data_Valid_Flag;
extern bool ACK_Data_Valid_Flag;
extern bool BI_Cal_Data_Flag;
extern bool WI_Cal_Data_Flag;



extern u8 GPS_Recv_num;
