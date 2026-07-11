#include <stdio.h>

#include "AgreedTerms.h"
#include "PowerManage.h"
#include "DataProcess.h"



void MT_Power_Control(u8 para);
void LT_Power_Control(u8 para);
void HR_Power_Control(u8 para);
void VR_Power_Control(u8 para);
void EL_Power_Control(u8 para);
void DVL_Power_Control(u8 para);
void CM_Power_Control(u8 para);
void S1_Power_Control(u8 para);
void S2_Power_Control(u8 para);

u8 Power_ON = 1;
u8 Power_OFF = 0;
bool PSD_Power_State_Flag=false;


void MT_Power_Control(u8 para)
{
	para = para&0x01;
	if(Power_ON == para)
	{
		Instruction_To_FMCU.McuFD_Power_Control |= 0x01;
	}
	else
	{
		Instruction_To_FMCU.McuFD_Power_Control &= 0xFE;
	}
}

void LT_Power_Control(u8 para)
{
	para = para&0x01;
	if(Power_ON == para)
	{
		Instruction_To_FMCU.McuFD_Power_Control |= 0x02;
	}
	else
	{
		Instruction_To_FMCU.McuFD_Power_Control &= 0xFD;
	}
}

void HR_Power_Control(u8 para)
{
	para = para&0x01;
	if(Power_ON == para)
	{
		Instruction_To_FMCU.McuFD_Power_Control |= 0x04;
	}
	else
	{
		Instruction_To_FMCU.McuFD_Power_Control &= 0xFB;
	}
}

void VR_Power_Control(u8 para)
{
	para = para&0x01;
	if(Power_ON == para)
	{
		Instruction_To_FMCU.McuFD_Power_Control |= 0x08;
	}
	else
	{
		Instruction_To_FMCU.McuFD_Power_Control &= 0xF7;
	}
}

void EL_Power_Control(u8 para)
{
	para = para&0x01;
	if(Power_ON == para)
	{
		Instruction_To_FMCU.McuFD_Power_Control |= 0x10;
	}
	else
	{
		Instruction_To_FMCU.McuFD_Power_Control &= 0xEF;
	}
}

void DVL_Power_Control(u8 para)
{
	para = para&0x01;
	if(Power_ON == para)
	{
		Instruction_To_FMCU.McuFD_Power_Control |= 0x20;
	}
	else
	{
		Instruction_To_FMCU.McuFD_Power_Control &= 0xDF;
	}
}

void CM_Power_Control(u8 para)
{
	para = para&0x01;
	if(Power_ON == para)
	{
		Instruction_To_FMCU.McuFD_Power_Control |= 0x40;		
	}
	else
	{
		Instruction_To_FMCU.McuFD_Power_Control &= 0xBF;
	}
}

void S1_Power_Control(u8 para)
{
	para = para&0x01;
	if(Power_ON == para)
	{
		Instruction_To_FMCU.McuFD_Power_Control |= 0x80;
	}
	else
	{
		Instruction_To_FMCU.McuFD_Power_Control &= 0x7F;
	}
}

void S2_Power_Control(u8 para)
{
	para = para&0x01;
	if(Power_ON == para)
	{
		Instruction_To_FMCU.McuFD_Power_Control |= 0x100;
	}
	else
	{
		Instruction_To_FMCU.McuFD_Power_Control &= 0xFF;
	}
}




