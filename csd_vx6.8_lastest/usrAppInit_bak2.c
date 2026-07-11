/* usrAppInit.c - stub application initialization routine */

/* Copyright (c) 1998,2006 Wind River Systems, Inc. 
 *
 * The right to copy, distribute, modify or otherwise make use
 * of this software may be licensed only pursuant to the terms
 * of an applicable Wind River license agreement.
 */

/*
modification history
--------------------
01b,16mar06,jmt  Add header file to find USER_APPL_INIT define
01a,02jun98,ms   written
*/

/*
DESCRIPTION
Initialize user application code.
*/ 

#include <vxWorks.h>
#if defined(PRJ_BUILD)
#include "prjParams.h"
#endif /* defined PRJ_BUILD */
#include "comDrv.h"
#include "CanDrv.h"

/******************************************************************************
*
* usrAppInit - initialize the users application
*/ 

void usrAppInit (void)
    {
#ifdef	USER_APPL_INIT
	USER_APPL_INIT;		/* for backwards compatibility */
#endif

    /* add application specific code here */
	
    sysClkRateSet(1000);
#ifdef	USER_APPL_INIT
	USER_APPL_INIT;		/* for backwards compatibility */
#endif

    /* add application specific code here */

	ipAttach (1,"fei");
	 ifconfig("fei1 192.168.0.101 up");
	 
	    /* CSD串口设备定义 */
#if 0	
	com_info_t com[4];
	    com[0].ushBase = 0x110;
	    com[0].irq = 6;
	    com[1].ushBase = 0x118;
	    com[1].irq = 6;
	    com[2].ushBase = 0x120;
	    com[2].irq = 6;
	    com[3].ushBase = 0x128;
	    com[3].irq = 6;
	    
	    /* 初始化CSD串口设备 */
	    CsdSerialHwInit(0x200, 0, com);
#endif
	    CreatTask();
	    CreatCanDrv();
	     ProgromStartPoint();/**/
    }



void CreatTask(void)
{
    
	ComResource_t cr;
	cr.type = 0;            /* i8250兼容 */
	cr.base[0] = 0x110;     /* 串口1基地址 */
	cr.irq[0] = 6;          /* 串口1中断 */
	cr.base[1] = 0x118;     /* 串口2基地址 */
	cr.irq[1] = 6;          /* 串口2中断 */
	cr.base[2] = 0x120;     /* 串口3基地址 */
	cr.irq[2] = 6;         /* 串口3中断 */
	cr.base[3] = 0x128;     /* 串口4基地址 */
	cr.irq[3] = 6;         /* 串口4中断 */
	cr.isr_base = 0x200;    /* 中断状态寄存器地址 */   
	cr.nchannel = 4;        /* 串口个数 */
	cr.fifo = 64;           /* 串口fifo字节数 */
	sprintf(cr.description, "A3CSD");
	ComDrv();
	if(ComCreate(&cr) == -2)
	{
		
		printf("Not find CSD board!\n");
		return -1;
	}
}




