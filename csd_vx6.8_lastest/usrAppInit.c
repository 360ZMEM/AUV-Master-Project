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
#include "UdpLogger.h"

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

	 /* UDP 日志模块初始化 (必须在网络初始化之后) */
	 UdpLogger_Init();
	 
	    /* CSD�����豸���� */
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
	    
	    /* ��ʼ��CSD�����豸 */
	    CsdSerialHwInit(0x200, 0, com);
#endif
	    CreatTask();
	    CreatCanDrv();
	     ProgromStartPoint();/**/
    }



void CreatTask(void)
{
    
	ComResource_t cr;
	cr.type = 0;            /* i8250���� */
	cr.base[0] = 0x110;     /* ����1����ַ */
	cr.irq[0] = 6;          /* ����1�ж� */
	cr.base[1] = 0x118;     /* ����2����ַ */
	cr.irq[1] = 6;          /* ����2�ж� */
	cr.base[2] = 0x120;     /* ����3����ַ */
	cr.irq[2] = 6;         /* ����3�ж� */
	cr.base[3] = 0x128;     /* ����4����ַ */
	cr.irq[3] = 6;         /* ����4�ж� */
	cr.isr_base = 0x200;    /* �ж�״̬�Ĵ�����ַ */   
	cr.nchannel = 4;        /* ���ڸ��� */
	cr.fifo = 64;           /* ����fifo�ֽ��� */
	sprintf(cr.description, "A3CSD");
	ComDrv();
	if(ComCreate(&cr) == -2)
	{
		
		printf("Not find CSD board!\n");
		return -1;
	}
}




