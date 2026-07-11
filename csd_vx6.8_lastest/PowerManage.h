#ifndef _POWERMANAGE_H_
#define _POWERMANAGE_H_

#include "AgreedTerms.h"


extern void MT_Power_Control(u8 para);
extern void LT_Power_Control(u8 para);
extern void HR_Power_Control(u8 para);
extern void VR_Power_Control(u8 para);
extern void EL_Power_Control(u8 para);
extern void DVL_Power_Control(u8 para);
extern void CM_Power_Control(u8 para);
extern void S1_Power_Control(u8 para);
extern void S2_Power_Control(u8 para);



extern u8 Power_ON;
extern u8 Power_OFF;

#endif

