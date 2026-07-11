
#include "AgreedTerms.h"
#define ProgramVsion v20180401
#define PI 3.141592
extern void Work_Cmd_Execute(u8 *work_command_ptr);

extern u8 UI_Channel_Selection_Down;
extern u8 UI_Channel_Selection_Up;
/*extern u8 CtrlMode;*/
extern u8 Remote;
extern u8 Auto_FixedPoint;
extern u8 Auto_FixedDirection;
extern u8 Auto_Back;
extern u8 Jetson_Shadow;        /**< @brief 0xEE Ӱ���յ�ģʽ */
extern u8 Jetson_Hybrid;        /**< @brief 0xEF ȫ͸�����ģʽ */

/**
 * @brief ˮ�ز���ģʽ���� (����ʱ����)
 * 0 = ����ģʽ (soft_limit=3.0m, hard_limit=1.8m)
 * 1 = ˮ��ģʽ (���Χ��0.9m + Pitch��10�� + Roll��20�� + ת��200RPM)
 */
#define POOL_TEST_MODE  0


extern bool Parameter_Adjustment_Flag;
extern bool Initialization_Flag;
extern bool Course_Keep_Flag;
extern bool BEIDOU_Data_Ready;
extern bool Auto_FixedPoint_Process_Initial_Flag;
extern bool Auto_FixedDirection_Process_Initial_Flag;
extern bool Auto_FixedPoint_Process_Initial_Complete_Flag;
extern bool Auto_FixedDirection_Process_Initial_Complete_Flag;
extern bool Auto_Task_Carry_Flag;

