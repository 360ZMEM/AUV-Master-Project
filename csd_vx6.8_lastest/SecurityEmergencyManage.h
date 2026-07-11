#include "AgreedTerms.h"



extern void EmergencyTask(void);
extern SEM_ID semEmergencyTask;




extern u16 Not_Recv_From_WIFI_No;
extern u16 Not_Recv_From_FMCU_No;
extern u16 Not_Recv_From_BMS_No;
extern u16 Not_Recv_From_LORA_No;
extern u16 Not_Recv_From_GPS_No;
extern u16 Not_Recv_From_DVL_No;
extern u16 Not_Recv_From_BEIDOU_No;
extern u16 Not_Recv_From_PSD_No;
extern u16 Not_Recv_From_IMU_No;

extern u16 Not_Recv_From_BI_DVL_No;
extern u16 Not_Recv_From_WI_DVL_No;

extern u16 Not_Recv_From_Jetson_No;  /**< @brief Jetsonʧ�������� (0.1s/tick, ��ֵ10=1.0s) */

/* BUG-5/6: ��׸߶�Ӳդ����ȫ�ٲ� */
void Seafloor_Grounding_Arbitration(void);

/* BUG-7: ˮ�ز��԰�ȫģʽ */
#if POOL_TEST_MODE
void Pool_Safety_Check(void);
#endif

extern u16 Depth_Exceed_FromUI12_Depth_Para1;
extern u16 Depth_Exceed_FromUI12_Depth_Para2;

extern u32 Device_Power_State_Judgement;
extern u32 Cmd_State_Judgement;
extern u32 Sail_State_Judgement;
extern u32 Sys_Abnorm_Inf_Judgement;
extern u32 Dev_Abnorm_Inf_Judgement;
extern u32 BMS_Abnorm_Inf_Judgement;
extern u32 Dev_Abnorm_Inf_Detail_Judgement;






